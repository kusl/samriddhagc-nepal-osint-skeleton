"""
Bootstrap training labels with Claude Haiku (optional).

This generates ExperienceRecords for:
  - CLASSIFICATION (category)
  - PRIORITY (severity)

Use this to quickly create an initial benchmark/training dataset before you have
enough analyst labels.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import aiohttp

import sys
from collections import deque
from sqlalchemy import select, text

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# Ensure Settings env_file (".env") resolves correctly even when invoked from repo root.
if not Path(".env").exists() and (BACKEND_ROOT / ".env").exists():
    os.chdir(str(BACKEND_ROOT))

from app.config import get_settings  # noqa: E402
from app.core.database import AsyncSessionLocal  # noqa: E402
from app.ml.feature_extraction import build_priority_features, build_story_text, extract_severity_tokens  # noqa: E402
from app.ml.inference import get_predictor  # noqa: E402
from app.models.experience_record import ExperienceRecord, ExperienceType  # noqa: E402
from app.models.story import Story  # noqa: E402


ANTHROPIC_API_BASE = "https://api.anthropic.com/v1/messages"
HAIKU_MODEL = os.environ.get(
    "ANTHROPIC_LABEL_MODEL",
    os.environ.get("ANTHROPIC_MODEL", "claude-3-haiku-20240307"),
)

CATEGORIES = ["political", "economic", "security", "disaster", "social"]
PRIORITIES = ["low", "medium", "high", "critical"]

SYSTEM_PROMPT = """You label Nepal-related news stories.

Task: classify the story into:
- category: political|economic|security|disaster|social
- severity: critical|high|medium|low

Guidance:
- political: elections, government, parliament, parties, diplomacy
- security: crime, police, arrests, border, violence, military
- disaster: earthquake, flood, landslide, fire, accident, epidemic
- economic: markets, trade, banks, taxes, business, inflation
- social: protests, education, health, culture, environment

Output ONLY valid JSON (no markdown), matching:
{"category":"...", "severity":"...", "confidence":0.0-1.0, "reason":"..."}"""


def _priority_reward(system_priority: str, human_priority: str) -> float:
    priority_order = ["low", "medium", "high", "critical"]
    sys_idx = priority_order.index(system_priority) if system_priority in priority_order else 1
    human_idx = priority_order.index(human_priority) if human_priority in priority_order else 1
    diff = abs(sys_idx - human_idx)
    return float(1.0 - (diff / 1.5))


def _headers(api_key: str) -> dict:
    return {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }


class _RateLimiter:
    """Simple max-requests-per-minute limiter (process local)."""

    def __init__(self, max_per_minute: int):
        self.max_per_minute = max(1, int(max_per_minute))
        self._hits: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = asyncio.get_event_loop().time()

            # Drop timestamps older than 60s
            while self._hits and (now - self._hits[0]) > 60.0:
                self._hits.popleft()

            if len(self._hits) < self.max_per_minute:
                self._hits.append(now)
                return

            # Need to wait until the oldest hit falls out of the window
            sleep_s = max(0.0, 60.0 - (now - self._hits[0]) + 0.05)

        await asyncio.sleep(sleep_s)
        await self.acquire()


async def _label_story(session: aiohttp.ClientSession, api_key: str, *, title: str, summary: Optional[str]) -> Optional[dict]:
    text_in = build_story_text(title, summary)
    if not text_in.strip():
        return None

    user_prompt = f"Story:\nTITLE: {title}\nSUMMARY: {summary or ''}\n"

    async with session.post(
        ANTHROPIC_API_BASE,
        headers=_headers(api_key),
        json={
            "model": HAIKU_MODEL,
            "max_tokens": 250,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": user_prompt}],
        },
    ) as resp:
        if resp.status != 200:
            try:
                err = await resp.text()
            except Exception:
                err = ""
            return {"error_status": resp.status, "error": err[:300]}

        data = await resp.json()
        content = data.get("content", [{}])[0].get("text", "") or ""
        try:
            s = content.strip()
            if "```json" in s:
                s = s.split("```json", 1)[1].split("```", 1)[0].strip()
            elif "```" in s:
                s = s.split("```", 1)[1].split("```", 1)[0].strip()
            return json.loads(s)
        except Exception:
            return None


async def run(hours: int, limit: int, concurrency: int) -> int:
    settings = get_settings()
    api_key = settings.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ANTHROPIC_API_KEY not set; cannot run Haiku bootstrap.")
        return 2

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    predictor = get_predictor()
    if not predictor._initialized:
        predictor.initialize()

    async with AsyncSessionLocal() as db:
        # Candidate stories (Nepal-relevant, recent, with embeddings)
        stories = (
            await db.execute(
                select(Story)
                .where(
                    Story.created_at >= cutoff,
                    Story.nepal_relevance.in_(["NEPAL_DOMESTIC", "NEPAL_NEIGHBOR"]),
                )
                .order_by(Story.published_at.desc().nullslast())
                .limit(limit)
            )
        ).scalars().all()

        story_ids = [s.id for s in stories]
        if not story_ids:
            print("No stories found.")
            return 0

        # Skip stories already labeled by haiku
        already = (
            await db.execute(
                text(
                    """
                    SELECT story_id
                    FROM experience_records
                    WHERE story_id = ANY(:ids)
                      AND experience_type IN ('CLASSIFICATION','PRIORITY')
                      AND (context_features->>'label_source') = 'haiku_label'
                    """
                ),
                {"ids": story_ids},
            )
        ).all()
        already_ids = {row[0] for row in already}

        to_label = [s for s in stories if s.id not in already_ids]
        print(f"Stories in window: {len(stories)} | to label: {len(to_label)}")

    sem = asyncio.Semaphore(max(1, concurrency))
    rate = _RateLimiter(max_per_minute=int(os.environ.get("ANTHROPIC_RPM", "45")))

    async def worker(session: aiohttp.ClientSession, story: Story) -> tuple[Story, Optional[dict]]:
        async with sem:
            await rate.acquire()
            res = await _label_story(session, api_key, title=story.title, summary=story.summary)
            return story, res

    labeled: list[tuple[Story, dict]] = []
    errors = 0
    first_error: Optional[dict] = None
    async with aiohttp.ClientSession() as session:
        tasks = [asyncio.create_task(worker(session, s)) for s in to_label]
        for fut in asyncio.as_completed(tasks):
            story, res = await fut
            if not res:
                continue
            if "error_status" in res:
                errors += 1
                if first_error is None:
                    first_error = res
                continue
            if res:
                labeled.append((story, res))

    created = 0
    now = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as db:
        records: list[ExperienceRecord] = []

        for story, res in labeled:
            category = str(res.get("category", "")).lower()
            severity = str(res.get("severity", "")).lower()
            conf = float(res.get("confidence", 0.0) or 0.0)
            reason = str(res.get("reason", ""))[:500]

            if category not in CATEGORIES or severity not in PRIORITIES:
                continue

            system_category = (story.category or "unknown").lower()
            system_priority = (story.severity or "medium").lower()

            # Classification record
            records.append(
                ExperienceRecord(
                    experience_type=ExperienceType.CLASSIFICATION,
                    story_id=story.id,
                    source_id=story.source_id,
                    context_features={
                        "text": build_story_text(story.title, story.summary),
                        "label_source": "haiku_label",
                        "llm_model": HAIKU_MODEL,
                        "llm_confidence": conf,
                        "llm_reason": reason,
                        "labeled_at": now.isoformat(),
                    },
                    system_action=system_category,
                    human_action=category,
                    reward=Decimal("1.0") if system_category == category else Decimal("-1.0"),
                    used_in_training=False,
                )
            )
            created += 1

            # Priority record
            severity_tokens = extract_severity_tokens(story.title, story.summary)
            features = build_priority_features(
                predictor,
                category=category,
                source_id=story.source_id,
                published_at=story.published_at,
                severity_tokens=severity_tokens,
                entity_count=0,
            )
            records.append(
                ExperienceRecord(
                    experience_type=ExperienceType.PRIORITY,
                    story_id=story.id,
                    source_id=story.source_id,
                    context_features={
                        "features": features,
                        "label_source": "haiku_label",
                        "llm_model": HAIKU_MODEL,
                        "llm_confidence": conf,
                        "llm_reason": reason,
                        "labeled_at": now.isoformat(),
                    },
                    system_action=system_priority,
                    human_action=severity,
                    reward=Decimal(str(_priority_reward(system_priority, severity))),
                    used_in_training=False,
                )
            )
            created += 1

        if records:
            db.add_all(records)
            await db.commit()

    print(f"Created experience records: {created}")
    if errors:
        print(f"LLM requests failed: {errors}")
        if first_error:
            print(f"First error: status={first_error.get('error_status')} msg={str(first_error.get('error', ''))[:200]}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap RL labels with Claude Haiku.")
    parser.add_argument("--hours", type=int, default=72, help="Time window in hours (default: 72)")
    parser.add_argument("--limit", type=int, default=120, help="Max stories to label (default: 120)")
    parser.add_argument("--concurrency", type=int, default=4, help="Concurrent requests (default: 4)")
    args = parser.parse_args()

    return asyncio.run(run(hours=args.hours, limit=args.limit, concurrency=args.concurrency))


if __name__ == "__main__":
    raise SystemExit(main())
