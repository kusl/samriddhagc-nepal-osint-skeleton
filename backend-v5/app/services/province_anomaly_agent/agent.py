"""Province Anomaly Agent — main orchestrator.

Lightweight agent that:
1. Collects stories + tweets from the last 8 hours
2. Classifies them by province via keyword matching (pure Python)
3. Sends a single structured OpenAI call for all 7 provinces
4. Stores results in province_anomaly_runs / province_anomalies tables
"""
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.province_anomaly import ProvinceAnomalyRun, ProvinceAnomaly
from app.services.province_anomaly_agent.data_collector import (
    collect_province_data,
    PROVINCE_NAMES,
)
from app.services.province_anomaly_agent.prompts import build_prompt
from app.services.openai_runtime import get_openai_runtime

logger = logging.getLogger(__name__)


PROVINCE_RESULT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "provinces": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "province_id": {"type": "integer"},
                    "province_name": {"type": "string"},
                    "threat_level": {"type": "string"},
                    "threat_trajectory": {"type": "string"},
                    "summary": {"type": "string"},
                    "political": {"type": ["string", "null"]},
                    "economic": {"type": ["string", "null"]},
                    "security": {"type": ["string", "null"]},
                    "anomalies": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "type": {"type": "string"},
                                "description": {"type": "string"},
                                "severity": {"type": "string"},
                                "district": {"type": ["string", "null"]},
                            },
                            "required": ["type", "description", "severity", "district"],
                        },
                    },
                },
                "required": [
                    "province_id",
                    "province_name",
                    "threat_level",
                    "threat_trajectory",
                    "summary",
                    "political",
                    "economic",
                    "security",
                    "anomalies",
                ],
            },
        },
    },
    "required": ["provinces"],
}


class ProvinceAnomalyAgent:
    """Orchestrates province anomaly detection."""

    def __init__(self, db: AsyncSession, hours: int = 8):
        self.db = db
        self.hours = hours
        self.openai = get_openai_runtime()

    async def _run_model(self, prompt: str) -> dict[str, Any]:
        system_prompt = (
            "You write sober provincial monitoring assessments for NepalOSINT. "
            "Use only the provided source material. Return strict JSON matching the schema. "
            "Do not invent incidents or overstate threat."
        )
        return await self.openai.json_completion(
            system_prompt=system_prompt,
            user_prompt=prompt,
            schema_name="province_anomaly_run",
            schema=PROVINCE_RESULT_SCHEMA,
            model=self.openai.settings.openai_briefing_model,
            max_completion_tokens=2200,
            prompt_char_limit=90000,
            cache_scope=f"province_anomaly:{self.hours}",
            usage_bucket="structured",
        )

    async def run(self) -> ProvinceAnomalyRun:
        """Execute a full anomaly detection run."""
        run = ProvinceAnomalyRun(
            status="running",
            started_at=datetime.now(timezone.utc),
        )
        self.db.add(run)
        await self.db.flush()

        try:
            # 1. Collect & classify data
            logger.info("Province Anomaly Agent: collecting data (last %dh)...", self.hours)
            province_data = await collect_province_data(self.db, hours=self.hours)

            total_stories = sum(pd.story_count for pd in province_data.values())
            total_tweets = sum(pd.tweet_count for pd in province_data.values())

            run.stories_analyzed = total_stories
            run.tweets_analyzed = total_tweets

            # 2. Build prompt contexts
            province_contexts = {}
            for pid, pd in province_data.items():
                province_contexts[pid] = {
                    "name": pd.province_name,
                    "stories": [
                        {"source": s.source, "title": s.title, "snippet": s.snippet}
                        for s in pd.stories
                    ],
                    "tweets": [
                        {"title": t.title, "snippet": t.snippet}
                        for t in pd.tweets
                    ],
                }

            prompt = build_prompt(province_contexts)

            # 3. Single structured OpenAI call
            logger.info(
                "Province Anomaly Agent: calling OpenAI (%d stories, %d tweets)...",
                total_stories, total_tweets,
            )
            result = await self._run_model(prompt)

            # 4. Parse and store results
            provinces_result = result.get("provinces", [])

            # Ensure we have all 7 provinces
            result_by_pid = {p["province_id"]: p for p in provinces_result}

            for pid in range(1, 8):
                pdata = result_by_pid.get(pid, {})
                pd = province_data.get(pid)

                anomaly = ProvinceAnomaly(
                    run_id=run.id,
                    province_id=pid,
                    province_name=PROVINCE_NAMES.get(pid, f"Province {pid}"),
                    threat_level=pdata.get("threat_level", "LOW"),
                    threat_trajectory=pdata.get("threat_trajectory", "STABLE"),
                    summary=pdata.get("summary", "No significant developments reported in this period."),
                    political=pdata.get("political"),
                    economic=pdata.get("economic"),
                    security=pdata.get("security"),
                    anomalies_data=pdata.get("anomalies", []),
                    story_count=pd.story_count if pd else 0,
                    tweet_count=pd.tweet_count if pd else 0,
                    key_sources=[],
                )
                self.db.add(anomaly)

            # 5. Mark run complete
            run.status = "completed"
            run.completed_at = datetime.now(timezone.utc)
            await self.db.commit()

            logger.info(
                "Province Anomaly Agent: complete (%d stories, %d tweets, 7 provinces assessed)",
                total_stories, total_tweets,
            )
            return run

        except Exception as exc:
            logger.exception("Province Anomaly Agent failed: %s", exc)
            run.status = "failed"
            run.error_message = str(exc)[:1000]
            run.completed_at = datetime.now(timezone.utc)
            await self.db.commit()
            return run
