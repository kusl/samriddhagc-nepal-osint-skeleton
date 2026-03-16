"""Data collection layer — queries DB and formats context per province.

All data collection is Python/DB only (no Claude calls).
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, func, and_, desc, cast
from sqlalchemy.dialects.postgresql import JSONB as PG_JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.story import Story
from app.models.story_cluster import StoryCluster
from app.models.disaster import DisasterIncident
from app.models.election import Election, Constituency, Candidate
from app.models.situation_brief import SituationBrief, ProvinceSitrep
from app.data.nepal_districts import NEPAL_PROVINCES

logger = logging.getLogger(__name__)

# Province ID → Name lookup
PROVINCE_MAP = {p["id"]: p["name_en"] for p in NEPAL_PROVINCES}


@dataclass
class StoryContext:
    """Minimal story representation for province context."""
    story_id: str
    title: str
    source_name: str
    published_at: Optional[str]
    category: Optional[str]
    severity: Optional[str]
    summary: Optional[str]  # from ai_summary
    cluster_id: Optional[str]
    cluster_headline: Optional[str]
    confidence_level: Optional[str]
    unique_sources: Optional[list]
    diversity_score: Optional[float]


@dataclass
class DisasterContext:
    """Minimal disaster representation."""
    hazard_type: str
    title: str
    district: Optional[str]
    severity: Optional[str]
    deaths: int
    injured: int
    incident_on: Optional[str]


@dataclass
class ProvinceContext:
    """All data for a single province, ready for Claude analysis."""
    province_id: int
    province_name: str
    stories: list[StoryContext] = field(default_factory=list)
    disasters: list[DisasterContext] = field(default_factory=list)
    cluster_count: int = 0
    election_summary: str = "No recent election updates."
    previous_bluf: str = "No previous brief available."

    @property
    def is_empty(self) -> bool:
        return len(self.stories) == 0 and len(self.disasters) == 0

    @property
    def story_count(self) -> int:
        return len(self.stories)

    def format_stories_section(self) -> str:
        if not self.stories:
            return "No recent stories for this province."
        lines = []
        for s in self.stories:
            summary = s.summary or "(no summary available)"
            corr = ""
            if s.confidence_level and s.confidence_level != "single_source":
                corr = f" | Corroboration: {s.confidence_level}"
                if s.unique_sources:
                    corr += f", {len(s.unique_sources)} sources"
            lines.append(
                f"- [{s.category or 'uncategorized'}][{s.severity or '?'}] "
                f"{s.title}\n  Source: {s.source_name} | {s.published_at}{corr}\n"
                f"  Summary: {summary}\n"
                f"  story_id: {s.story_id}"
            )
        return "\n".join(lines)

    def format_disasters_section(self) -> str:
        if not self.disasters:
            return "No active disasters in this province."
        lines = []
        for d in self.disasters:
            impact = []
            if d.deaths > 0:
                impact.append(f"{d.deaths} dead")
            if d.injured > 0:
                impact.append(f"{d.injured} injured")
            impact_str = ", ".join(impact) if impact else "no casualties reported"
            lines.append(
                f"- [{d.hazard_type}][{d.severity or '?'}] {d.title}\n"
                f"  District: {d.district or 'unknown'} | {d.incident_on}\n"
                f"  Impact: {impact_str}"
            )
        return "\n".join(lines)


class DataCollector:
    """Collects and formats data from DB for the analyst agent."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def collect_recent_stories(
        self, since: datetime, province_name: Optional[str] = None,
    ) -> list[StoryContext]:
        """Fetch stories since the given time, optionally filtered by province."""
        query = (
            select(Story)
            .options(selectinload(Story.cluster))
            .where(Story.created_at >= since)
            .order_by(desc(Story.published_at))
        )
        if province_name:
            # Stories with this province in their provinces JSONB array
            query = query.where(
                Story.provinces.op("@>")(cast(f'["{province_name}"]', PG_JSONB))
            )

        result = await self.db.execute(query)
        stories = result.scalars().all()

        contexts = []
        for s in stories:
            # Extract haiku summary text from ai_summary JSONB
            summary_text = None
            if s.ai_summary:
                summary_text = (
                    s.ai_summary.get("haiku_summary")
                    or s.ai_summary.get("summary")
                    or s.ai_summary.get("bluf")
                )

            # Get cluster info if available
            cluster_headline = None
            confidence_level = None
            unique_sources = None
            diversity_score = None
            if s.cluster:
                cluster_headline = s.cluster.headline
                confidence_level = s.cluster.confidence_level
                unique_sources = s.cluster.unique_sources
                diversity_score = s.cluster.diversity_score

            contexts.append(StoryContext(
                story_id=str(s.id),
                title=s.title,
                source_name=s.source_name or s.source_id,
                published_at=s.published_at.isoformat() if s.published_at else None,
                category=s.category,
                severity=s.severity,
                summary=summary_text,
                cluster_id=str(s.cluster_id) if s.cluster_id else None,
                cluster_headline=cluster_headline,
                confidence_level=confidence_level,
                unique_sources=unique_sources,
                diversity_score=diversity_score,
            ))

        return contexts

    async def collect_active_disasters(
        self, since: datetime, province_id: Optional[int] = None,
    ) -> list[DisasterContext]:
        """Fetch disaster incidents from the last 24h or since given time."""
        query = (
            select(DisasterIncident)
            .where(DisasterIncident.created_at >= since)
            .order_by(desc(DisasterIncident.incident_on))
        )
        if province_id:
            query = query.where(DisasterIncident.province == province_id)

        result = await self.db.execute(query)
        incidents = result.scalars().all()

        return [
            DisasterContext(
                hazard_type=d.hazard_type,
                title=d.title,
                district=d.district,
                severity=d.severity,
                deaths=d.deaths,
                injured=d.injured,
                incident_on=d.incident_on.isoformat() if d.incident_on else None,
            )
            for d in incidents
        ]

    async def collect_election_updates(self) -> str:
        """Build a summary of recent election data."""
        # Count active elections
        result = await self.db.execute(
            select(func.count(Election.id)).where(Election.status == "active")
        )
        active_count = result.scalar() or 0

        if active_count == 0:
            return "No active elections at this time."

        # Get constituency-level summary
        result = await self.db.execute(
            select(func.count(Constituency.id))
            .join(Election, Constituency.election_id == Election.id)
            .where(Election.status == "active")
        )
        constituency_count = result.scalar() or 0

        result = await self.db.execute(
            select(func.count(Candidate.id))
            .join(Constituency, Candidate.constituency_id == Constituency.id)
            .join(Election, Constituency.election_id == Election.id)
            .where(Election.status == "active")
        )
        candidate_count = result.scalar() or 0

        return (
            f"{active_count} active election(s), "
            f"{constituency_count} constituencies, "
            f"{candidate_count} candidates registered."
        )

    async def collect_previous_brief(self) -> Optional[SituationBrief]:
        """Load the most recent completed SituationBrief."""
        result = await self.db.execute(
            select(SituationBrief)
            .options(selectinload(SituationBrief.province_sitreps))
            .where(SituationBrief.status == "completed")
            .order_by(desc(SituationBrief.created_at))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_next_run_number(self) -> int:
        """Get the next run number (max + 1)."""
        result = await self.db.execute(
            select(func.coalesce(func.max(SituationBrief.run_number), 0))
        )
        return (result.scalar() or 0) + 1

    async def count_clusters_since(self, since: datetime) -> int:
        """Count clusters updated since the given time."""
        result = await self.db.execute(
            select(func.count(StoryCluster.id))
            .where(StoryCluster.created_at >= since)
        )
        return result.scalar() or 0

    async def build_province_contexts(
        self,
        since: datetime,
        province_filter: Optional[str] = None,
    ) -> dict[int, ProvinceContext]:
        """Build context dicts for all provinces with data.

        Args:
            since: Start of analysis window.
            province_filter: If set, only build context for this province name.

        Returns:
            Dict mapping province_id → ProvinceContext.
        """
        election_summary = await self.collect_election_updates()
        previous = await self.collect_previous_brief()

        # Build previous BLUF lookup
        prev_bluf_by_province: dict[int, str] = {}
        if previous:
            for sitrep in previous.province_sitreps:
                if sitrep.bluf:
                    prev_bluf_by_province[sitrep.province_id] = sitrep.bluf

        contexts: dict[int, ProvinceContext] = {}

        for prov in NEPAL_PROVINCES:
            prov_id = prov["id"]
            prov_name = prov["name_en"]

            if province_filter and prov_name.lower() != province_filter.lower():
                continue

            # Collect stories for this province
            stories = await self.collect_recent_stories(since, prov_name)

            # Collect disasters for this province
            disasters = await self.collect_active_disasters(since, prov_id)

            # Count distinct clusters
            cluster_ids = {s.cluster_id for s in stories if s.cluster_id}

            ctx = ProvinceContext(
                province_id=prov_id,
                province_name=prov_name,
                stories=stories,
                disasters=disasters,
                cluster_count=len(cluster_ids),
                election_summary=election_summary,
                previous_bluf=prev_bluf_by_province.get(
                    prov_id, "No previous brief available."
                ),
            )
            contexts[prov_id] = ctx

        # Also collect "national" stories (no province assigned or multiple)
        all_stories = await self.collect_recent_stories(since)
        national_stories = [
            s for s in all_stories
            if not any(
                s.story_id == ps.story_id
                for ctx in contexts.values()
                for ps in ctx.stories
            )
        ]
        if national_stories:
            national_disasters = await self.collect_active_disasters(since)
            national_cluster_ids = {s.cluster_id for s in national_stories if s.cluster_id}
            contexts[0] = ProvinceContext(
                province_id=0,
                province_name="National",
                stories=national_stories,
                disasters=national_disasters,
                cluster_count=len(national_cluster_ids),
                election_summary=election_summary,
                previous_bluf=prev_bluf_by_province.get(
                    0, "No previous national brief."
                ),
            )

        active = {pid: ctx for pid, ctx in contexts.items() if not ctx.is_empty}
        logger.info(
            "Built %d province contexts (%d with data), %d total stories",
            len(contexts), len(active),
            sum(ctx.story_count for ctx in active.values()),
        )
        return active
