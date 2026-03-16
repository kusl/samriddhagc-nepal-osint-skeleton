"""Narada Analyst Agent — multi-step intelligence analysis orchestrator.

Workflow:
    1. COLLECT  — Python DB queries, no Claude
    2. ANALYZE  — Claude CLI per province with data
    3. VERIFY   — Web search + Claude for flagged stories
    4. SYNTHESIZE — One Claude call for national brief
    5. STORE    — Persist to DB, publish via Redis
"""
import json
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.situation_brief import SituationBrief, ProvinceSitrep, FakeNewsFlag
from app.services.analyst_agent.claude_runner import call_claude_json
from app.services.analyst_agent.data_collector import DataCollector, ProvinceContext
from app.services.analyst_agent.verifier import Verifier
from app.services.analyst_agent.prompts import (
    ANALYST_PERSONA,
    PROVINCE_ANALYSIS_PROMPT,
    PROVINCE_SITREP_SCHEMA,
    NATIONAL_SYNTHESIS_PROMPT,
    NATIONAL_SYNTHESIS_SCHEMA,
)

logger = logging.getLogger(__name__)


class NaradaAnalystAgent:
    """Multi-step intelligence analyst agent."""

    def __init__(
        self,
        db: AsyncSession,
        since: Optional[datetime] = None,
        hours: int = 3,
        province_filter: Optional[str] = None,
        dry_run: bool = False,
    ):
        self.db = db
        self.since = since or (datetime.now(timezone.utc) - timedelta(hours=hours))
        self.period_end = datetime.now(timezone.utc)
        self.province_filter = province_filter
        self.dry_run = dry_run
        self.collector = DataCollector(db)
        self.verifier = Verifier(db)
        self.claude_calls = 0

    async def run(self) -> SituationBrief:
        """Execute full analysis cycle."""
        start_time = time.time()
        run_number = await self.collector.get_next_run_number()

        brief = SituationBrief(
            run_number=run_number,
            status="running",
            period_start=self.since,
            period_end=self.period_end,
        )
        self.db.add(brief)
        await self.db.flush()

        logger.info(
            "=== NARADA Analyst Agent Run #%d ===\n"
            "  Period: %s → %s\n"
            "  Province filter: %s\n"
            "  Dry run: %s",
            run_number,
            self.since.isoformat(),
            self.period_end.isoformat(),
            self.province_filter or "all",
            self.dry_run,
        )

        try:
            # ── Step 1: COLLECT ──
            logger.info("Step 1: Collecting data...")
            contexts = await self.collector.build_province_contexts(
                since=self.since,
                province_filter=self.province_filter,
            )
            previous = await self.collector.collect_previous_brief()

            total_stories = sum(ctx.story_count for ctx in contexts.values())
            total_clusters = sum(ctx.cluster_count for ctx in contexts.values())
            brief.stories_analyzed = total_stories
            brief.clusters_analyzed = total_clusters

            if not contexts or total_stories < 5:
                logger.info(
                    "Insufficient data (%d stories) in analysis window. Skipping Claude calls.",
                    total_stories,
                )
                brief.status = "completed"
                brief.national_summary = "No significant activity in analysis window."
                brief.trend_vs_previous = "stable"
                brief.duration_seconds = time.time() - start_time
                await self.db.commit()
                return brief

            # Drop provinces with <3 stories — not enough signal for a full analysis call
            thin_provinces = {k: v for k, v in contexts.items() if v.story_count < 3}
            contexts = {k: v for k, v in contexts.items() if v.story_count >= 3}
            if thin_provinces:
                logger.info(
                    "Skipped %d provinces with <3 stories: %s",
                    len(thin_provinces),
                    ", ".join(v.province_name for v in thin_provinces.values()),
                )

            logger.info(
                "Collected %d stories across %d provinces (%d clusters, %d thin provinces skipped)",
                total_stories, len(contexts), total_clusters, len(thin_provinces),
            )

            if self.dry_run:
                self._print_dry_run(contexts)
                brief.status = "completed"
                brief.national_summary = "[DRY RUN] Data collection only."
                brief.duration_seconds = time.time() - start_time
                await self.db.commit()
                return brief

            # ── Step 2: ANALYZE ──
            logger.info("Step 2: Analyzing %d provinces...", len(contexts))
            sitreps: list[ProvinceSitrep] = []
            all_suspicious: list[dict] = []

            for prov_id, ctx in sorted(contexts.items()):
                sitrep = await self._analyze_province(brief.id, ctx)
                sitreps.append(sitrep)
                if sitrep.flagged_stories:
                    all_suspicious.extend(sitrep.flagged_stories)

            logger.info(
                "Step 2 complete: %d sitreps, %d suspicious stories flagged",
                len(sitreps), len(all_suspicious),
            )

            # ── Step 3: VERIFY (Nepal-domestic only) ──
            # Filter out international news — only verify Nepal-domestic stories
            nepal_suspicious = [
                s for s in all_suspicious
                if not self._is_international_story(s)
            ]
            if len(nepal_suspicious) < len(all_suspicious):
                logger.info(
                    "Filtered %d international stories from verification queue",
                    len(all_suspicious) - len(nepal_suspicious),
                )

            flags: list[FakeNewsFlag] = []
            if nepal_suspicious:
                logger.info("Step 3: Verifying %d Nepal-domestic suspicious stories...", len(nepal_suspicious))
                for suspicious in nepal_suspicious[:3]:  # Cap at 3 verifications per run
                    flag = await self._verify_story(brief.id, suspicious)
                    if flag:
                        flags.append(flag)
            else:
                logger.info("Step 3: No suspicious stories to verify.")

            # ── Step 4: SYNTHESIZE ──
            logger.info("Step 4: Synthesizing national brief...")
            national = await self._synthesize(sitreps, flags, previous)

            # Update brief with national synthesis
            brief.national_summary = national.get("national_summary", "")
            brief.national_analysis = national
            brief.hotspots = national.get("hotspots", [])
            brief.trend_vs_previous = national.get("trend_vs_previous", "stable")
            brief.key_judgment = national.get("key_judgment", "")

            # ── Step 5: STORE ──
            logger.info("Step 5: Persisting results...")
            for sitrep in sitreps:
                self.db.add(sitrep)
            for flag in flags:
                self.db.add(flag)

            brief.claude_calls = self.claude_calls
            brief.duration_seconds = time.time() - start_time
            brief.status = "completed"
            await self.db.commit()

            # Notify via Redis
            await self._notify(brief)

            logger.info(
                "=== Run #%d COMPLETE ===\n"
                "  Duration: %.1fs\n"
                "  Claude calls: %d\n"
                "  Province sitreps: %d\n"
                "  Fake news flags: %d\n"
                "  Trend: %s",
                run_number,
                brief.duration_seconds,
                self.claude_calls,
                len(sitreps),
                len(flags),
                brief.trend_vs_previous,
            )
            return brief

        except Exception as e:
            logger.error("Agent run failed: %s", e, exc_info=True)
            brief.status = "failed"
            brief.error = str(e)
            brief.duration_seconds = time.time() - start_time
            brief.claude_calls = self.claude_calls
            await self.db.commit()
            raise

    MAX_STORIES_PER_PROMPT = 100  # Keep prompt under ~50K tokens

    async def _analyze_province(
        self, brief_id: UUID, ctx: ProvinceContext,
    ) -> ProvinceSitrep:
        """Run Step 2 analysis for a single province."""
        # Cap stories to avoid prompt bloat — prioritize critical/high severity
        stories_for_prompt = ctx.stories
        if len(stories_for_prompt) > self.MAX_STORIES_PER_PROMPT:
            severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
            stories_for_prompt = sorted(
                stories_for_prompt,
                key=lambda s: severity_order.get(s.severity or "low", 3),
            )[:self.MAX_STORIES_PER_PROMPT]
            logger.info(
                "  Capped %d stories to %d for %s",
                len(ctx.stories), len(stories_for_prompt), ctx.province_name,
            )

        # Build stories section from capped list
        capped_ctx = ProvinceContext(
            province_id=ctx.province_id,
            province_name=ctx.province_name,
            stories=stories_for_prompt,
            disasters=ctx.disasters,
            cluster_count=ctx.cluster_count,
            election_summary=ctx.election_summary,
            previous_bluf=ctx.previous_bluf,
        )

        prompt = PROVINCE_ANALYSIS_PROMPT.format(
            persona=ANALYST_PERSONA,
            province_name=ctx.province_name,
            period_start=self.since.strftime("%Y-%m-%d %H:%M UTC"),
            period_end=self.period_end.strftime("%Y-%m-%d %H:%M UTC"),
            story_count=ctx.story_count,
            cluster_count=ctx.cluster_count,
            stories_section=capped_ctx.format_stories_section(),
            disasters_section=capped_ctx.format_disasters_section(),
            election_section=ctx.election_summary,
            previous_section=ctx.previous_bluf,
            schema=PROVINCE_SITREP_SCHEMA,
        )

        logger.info("  Analyzing %s (%d stories, %d in prompt)...", ctx.province_name, ctx.story_count, len(stories_for_prompt))
        result = await call_claude_json(prompt, timeout=300, model="haiku")
        self.claude_calls += 1

        sitrep = ProvinceSitrep(
            brief_id=brief_id,
            province_id=ctx.province_id,
            province_name=ctx.province_name,
            bluf=result.get("bluf"),
            security=result.get("security"),
            political=result.get("political"),
            economic=result.get("economic"),
            disaster=result.get("disaster"),
            election=result.get("election"),
            threat_level=result.get("threat_level", "low"),
            threat_trajectory=result.get("threat_trajectory", "stable"),
            hotspots=result.get("hotspots", []),
            flagged_stories=result.get("flagged_stories", []),
            story_count=ctx.story_count,
        )

        logger.info(
            "  → %s: threat=%s, trajectory=%s, flagged=%d",
            ctx.province_name,
            sitrep.threat_level,
            sitrep.threat_trajectory,
            len(sitrep.flagged_stories or []),
        )
        return sitrep

    async def _verify_story(
        self, brief_id: UUID, suspicious: dict,
    ) -> Optional[FakeNewsFlag]:
        """Run Step 3 verification for a single suspicious story."""
        story_id_str = suspicious.get("story_id")
        headline = suspicious.get("headline", "Unknown headline")
        source_name = suspicious.get("source_name", "Unknown source")
        reason = suspicious.get("reason", "Flagged by analyst")

        logger.info("  Verifying: %s", headline[:80])

        try:
            # Build verification context (web search + DB cross-ref)
            verdict_data = await self.verifier.verify_story(
                headline=headline,
                source_name=source_name,
                flag_reason=reason,
                story_id=story_id_str,
            )
            self.claude_calls += 1  # verifier makes one Claude call

            # Parse story_id UUID if available
            story_uuid = None
            if story_id_str:
                try:
                    story_uuid = UUID(story_id_str)
                except (ValueError, TypeError):
                    pass

            flag = FakeNewsFlag(
                brief_id=brief_id,
                story_id=story_uuid,
                headline=headline,
                source_name=source_name,
                flag_reason=reason,
                evidence=verdict_data.get("evidence"),
                verdict=verdict_data.get("verdict", "inconclusive"),
                verdict_reasoning=verdict_data.get("reasoning", ""),
                confidence=verdict_data.get("confidence", 0.5),
            )

            logger.info(
                "  → Verdict: %s (confidence: %.2f)",
                flag.verdict, flag.confidence or 0,
            )
            return flag

        except Exception as e:
            logger.warning("  → Verification failed for '%s': %s", headline[:50], e)
            return FakeNewsFlag(
                brief_id=brief_id,
                headline=headline,
                source_name=source_name,
                flag_reason=reason,
                verdict="inconclusive",
                verdict_reasoning=f"Verification failed: {e}",
                confidence=0.0,
            )

    async def _synthesize(
        self,
        sitreps: list[ProvinceSitrep],
        flags: list[FakeNewsFlag],
        previous: Optional[SituationBrief],
    ) -> dict:
        """Run Step 4 national synthesis."""
        # Format sitreps section
        sitreps_lines = []
        for s in sitreps:
            sitreps_lines.append(
                f"### {s.province_name} (threat: {s.threat_level}, "
                f"trajectory: {s.threat_trajectory})\n"
                f"BLUF: {s.bluf}\n"
                f"Security: {s.security}\n"
                f"Political: {s.political}\n"
                f"Hotspots: {json.dumps(s.hotspots or [])}\n"
            )

        # Format verification section
        if flags:
            verif_lines = []
            for f in flags:
                verif_lines.append(
                    f"- {f.headline}: verdict={f.verdict}, "
                    f"confidence={f.confidence:.2f}\n"
                    f"  Reasoning: {f.verdict_reasoning}"
                )
            verification_section = "\n".join(verif_lines)
        else:
            verification_section = "No stories were flagged for verification."

        # Previous brief
        prev_section = "No previous brief available."
        if previous:
            prev_section = (
                f"Previous run #{previous.run_number} ({previous.created_at.isoformat()}):\n"
                f"Summary: {previous.national_summary}\n"
                f"Trend: {previous.trend_vs_previous}\n"
                f"Key judgment: {previous.key_judgment}"
            )

        prompt = NATIONAL_SYNTHESIS_PROMPT.format(
            persona=ANALYST_PERSONA,
            period_start=self.since.strftime("%Y-%m-%d %H:%M UTC"),
            period_end=self.period_end.strftime("%Y-%m-%d %H:%M UTC"),
            sitreps_section="\n".join(sitreps_lines),
            verification_section=verification_section,
            previous_section=prev_section,
            schema=NATIONAL_SYNTHESIS_SCHEMA,
        )

        result = await call_claude_json(prompt, timeout=300)
        self.claude_calls += 1
        return result

    async def _notify(self, brief: SituationBrief) -> None:
        """Publish brief notification via Redis for WebSocket clients."""
        try:
            from app.core.redis import get_redis
            redis = await get_redis()
            await redis.publish("news:updates", json.dumps({
                "type": "situation_brief",
                "brief_id": str(brief.id),
                "run_number": brief.run_number,
                "national_summary": brief.national_summary,
                "trend": brief.trend_vs_previous,
                "status": brief.status,
            }))
            logger.info("Published brief notification to Redis")
        except Exception as e:
            logger.warning("Failed to publish Redis notification: %s", e)

    # International keywords that indicate non-Nepal stories
    _INTL_KEYWORDS = {
        "iran", "khamenei", "trump", "biden", "ukraine", "russia", "putin",
        "gaza", "israel", "hamas", "china", "xi jinping", "modi",
        "pakistan", "afghanistan", "taliban", "myanmar", "bangladesh",
        "north korea", "kim jong", "europe", "eu ", "nato",
        "pentagon", "white house", "kremlin", "beijing",
    }

    def _is_international_story(self, suspicious: dict) -> bool:
        """Check if a flagged story is international (non-Nepal) news."""
        headline = (suspicious.get("headline") or "").lower()
        # If headline mentions Nepal, it's domestic regardless of other keywords
        if "nepal" in headline or "नेपाल" in headline:
            return False
        return any(kw in headline for kw in self._INTL_KEYWORDS)

    def _print_dry_run(self, contexts: dict[int, ProvinceContext]) -> None:
        """Print province contexts for dry-run inspection."""
        for prov_id, ctx in sorted(contexts.items()):
            print(f"\n{'='*60}")
            print(f"Province: {ctx.province_name} (id={prov_id})")
            print(f"Stories: {ctx.story_count}, Clusters: {ctx.cluster_count}")
            print(f"Disasters: {len(ctx.disasters)}")
            print(f"{'='*60}")
            print("\nStories:")
            print(ctx.format_stories_section()[:2000])
            print("\nDisasters:")
            print(ctx.format_disasters_section()[:1000])
            print(f"\nElection: {ctx.election_summary}")
            print(f"Previous BLUF: {ctx.previous_bluf[:200]}")
