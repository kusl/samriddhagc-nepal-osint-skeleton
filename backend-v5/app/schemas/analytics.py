"""Analytics Pydantic schemas for dashboard widgets."""
from datetime import datetime, timezone
import re
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.publishing import PeerReviewSummary

NEPALI_LOCATION_SUFFIXES = [
    "बाटै", "हरुमा", "हरूमा", "हरुका", "हरूका", "हरुको", "हरूको",
    "सम्म", "सँग", "बाट", "देखि", "भित्र", "माथि", "तर्फ", "नजिक", "अघि", "पछि",
    "मा", "मै", "को", "का", "की", "ले",
]

DISTRICT_ALIAS_HINTS: dict[str, list[str]] = {
    "kathmandu": ["kathmandu", "काठमाडौं", "काठमाण्डौ", "काठमाण्डू", "काठमाडौँ"],
    "gorkha": ["gorkha", "गोरखा"],
    "kaski": ["kaski", "कास्की"],
    "banke": ["banke", "बाँके", "बांके"],
    "nepalgunj": ["nepalgunj", "नेपालगञ्ज", "नेपालगंज", "नेपालगन्ज"],
}

PROVINCE_ALIAS_HINTS: dict[str, list[str]] = {
    "gandaki": ["gandaki", "गण्डकी", "गंडकी"],
    "bagmati": ["bagmati", "बागमती"],
    "koshi": ["koshi", "कोशी"],
    "madhesh": ["madhesh", "madhes", "मधेस"],
    "lumbini": ["lumbini", "लुम्बिनी"],
    "karnali": ["karnali", "कर्णाली"],
    "sudurpashchim": ["sudurpashchim", "sudurpaschim", "सुदूरपश्चिम"],
}


def _contains_nepali_place_alias(text: str, alias: str) -> bool:
    suffix_pattern = "|".join(sorted((re.escape(s) for s in NEPALI_LOCATION_SUFFIXES), key=len, reverse=True))
    pattern = rf"(?<![\u0900-\u097F]){re.escape(alias)}(?:{suffix_pattern})?(?![\u0900-\u097F])"
    return re.search(pattern, text) is not None


def _text_mentions_geo(full_text_lower: str, canonical: str, aliases: list[str]) -> bool:
    for alias in aliases:
        alias_lower = alias.lower()
        if any("\u0900" <= char <= "\u097F" for char in alias_lower):
            if _contains_nepali_place_alias(full_text_lower, alias_lower):
                return True
        else:
            if re.search(rf"\b{re.escape(alias_lower)}\b", full_text_lower):
                return True
    if canonical not in aliases:
        if re.search(rf"\b{re.escape(canonical.lower())}\b", full_text_lower):
            return True
    return False


class ConsolidatedStoryResponse(BaseModel):
    """Story response for consolidated-stories endpoint (StoriesWidget)."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_id: str
    source_name: Optional[str] = None

    # Display fields - mapping to frontend expectations
    canonical_headline: str  # Alias for title
    canonical_headline_ne: Optional[str] = None
    summary: Optional[str] = None
    summary_ne: Optional[str] = None
    url: str  # Original article URL

    # Classification
    story_type: Optional[str] = None  # category field
    severity: Optional[str] = None  # severity field
    nepal_relevance: Optional[str] = None

    # Metadata
    source_count: int = 1
    first_reported_at: Optional[datetime] = None
    last_updated_at: Optional[datetime] = None
    districts_affected: list[str] = []
    provinces_affected: list[str] = []
    location_verified: bool = False
    display_location: Optional[str] = None
    is_verified: bool = False
    confidence_score: Optional[float] = None
    cluster_id: Optional[UUID] = None

    @classmethod
    def from_story(cls, story) -> "ConsolidatedStoryResponse":
        """Create from Story model."""
        full_text_lower = " ".join(
            filter(None, [getattr(story, "title", None), getattr(story, "summary", None), getattr(story, "content", None)])
        ).lower()

        # Use persisted category if available, otherwise derive from categories
        story_type = story.category
        if not story_type and story.categories:
            cat_lower = [c.lower() for c in story.categories if c]
            if any(k in cat_lower for k in ["politics", "election", "government"]):
                story_type = "political"
            elif any(k in cat_lower for k in ["crime", "police", "arrest"]):
                story_type = "security"
            elif any(k in cat_lower for k in ["flood", "earthquake", "disaster", "landslide"]):
                story_type = "disaster"
            elif any(k in cat_lower for k in ["economy", "business", "market"]):
                story_type = "economic"
            elif any(k in cat_lower for k in ["protest", "strike", "health", "education"]):
                story_type = "social"

        # Use persisted severity if available, otherwise derive
        severity = story.severity
        if not severity:
            severity = "low"
            if story.nepal_relevance == "NEPAL_DOMESTIC":
                severity = "medium"
                if story.relevance_score and story.relevance_score > 0.8:
                    severity = "high"

        # Avoid triggering lazy relationship loads inside async response
        # serialization for ORM objects. If features were eagerly loaded they
        # will already be in __dict__; otherwise we treat them as absent and
        # fall back to persisted district/province fields. For plain Python
        # stubs in tests, read the attribute normally.
        features = getattr(story, "__dict__", {}).get("features")
        if features is None and not hasattr(story, "_sa_instance_state"):
            try:
                features = getattr(story, "features", None)
            except Exception:
                features = None
        geo_confidence = getattr(features, "geo_confidence", None)
        title_district = getattr(features, "title_district", None)
        primary_municipality = getattr(features, "primary_municipality", None)
        raw_districts = list(story.districts or [])
        raw_provinces = list(story.provinces or [])
        districts_affected = [
            district
            for district in raw_districts
            if _text_mentions_geo(
                full_text_lower,
                district.lower(),
                DISTRICT_ALIAS_HINTS.get(district.lower(), [district]),
            )
        ]
        provinces_affected = [
            province
            for province in raw_provinces
            if _text_mentions_geo(
                full_text_lower,
                province.lower(),
                PROVINCE_ALIAS_HINTS.get(province.lower(), [province]),
            )
        ]
        verified_title_district = bool(
            title_district
            and _text_mentions_geo(
                full_text_lower,
                str(title_district).lower(),
                DISTRICT_ALIAS_HINTS.get(str(title_district).lower(), [str(title_district)]),
            )
        )
        verified_primary_municipality = bool(
            primary_municipality
            and _text_mentions_geo(
                full_text_lower,
                str(primary_municipality).lower(),
                DISTRICT_ALIAS_HINTS.get(str(primary_municipality).lower(), [str(primary_municipality)]),
            )
        )
        if not districts_affected and (verified_title_district or verified_primary_municipality):
            districts_affected = raw_districts
        if not provinces_affected and (verified_title_district or verified_primary_municipality):
            provinces_affected = raw_provinces
        location_verified = bool(
            districts_affected
            or provinces_affected
            or verified_title_district
            or verified_primary_municipality
            or (
                geo_confidence is not None
                and geo_confidence >= 0.5
                and (districts_affected or provinces_affected)
            )
        )
        display_location = None
        if districts_affected:
            display_location = districts_affected[0]
        elif provinces_affected:
            display_location = provinces_affected[0]
        elif story.nepal_relevance == "NEPAL_DOMESTIC":
            # Ambiguous domestic stories should not inherit outlet branding or
            # stale low-confidence regional tags; default them to Kathmandu.
            display_location = "Kathmandu"

        return cls(
            id=story.id,
            source_id=story.source_id,
            source_name=story.source_name,
            canonical_headline=story.title,
            summary=story.summary,
            url=story.url,
            story_type=story_type,
            severity=severity,
            nepal_relevance=story.nepal_relevance,
            source_count=1,
            first_reported_at=story.published_at,
            last_updated_at=story.created_at,
            districts_affected=districts_affected,
            provinces_affected=provinces_affected,
            location_verified=location_verified,
            display_location=display_location,
            is_verified=False,
            confidence_score=float(story.relevance_score) if story.relevance_score else None,
            cluster_id=story.cluster_id,
        )


class HourlyTrend(BaseModel):
    """Hourly story count."""
    hour: str
    count: int


class AnalyticsSummaryResponse(BaseModel):
    """Analytics summary for KPI widget."""
    stories: int  # Renamed from story_count for frontend compatibility
    events: int  # Renamed from event_count
    entities: int = 0  # Placeholder
    active_alerts: int = 0  # Placeholder
    sources_breakdown: dict[str, int]
    hourly_trend: list[HourlyTrend]
    time_range_hours: int


class ThreatCategoryItem(BaseModel):
    """Single threat category in the matrix."""
    category: str
    level: str  # critical | elevated | guarded | low
    trend: str = "stable"  # escalating | stable | deescalating
    event_count: int
    top_event: Optional[str] = None
    severity_breakdown: dict[str, int]


class ThreatMatrixResponse(BaseModel):
    """Threat matrix for ThreatsWidget."""
    matrix: list[ThreatCategoryItem]
    overall_threat_level: str = "GUARDED"
    last_updated: datetime


class ClusterStoryItem(BaseModel):
    """Individual story within a cluster."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_id: str
    source_name: Optional[str] = None
    title: str
    summary: Optional[str] = None
    url: str
    published_at: Optional[datetime] = None


class ClusterStoryGroupItem(BaseModel):
    """Near-identical stories collapsed into a single canonical item."""

    canonical: ClusterStoryItem
    duplicates: list[ClusterStoryItem] = Field(default_factory=list)
    duplicate_count: int = 0


class AggregatedCluster(BaseModel):
    """Aggregated news cluster."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    headline: str
    summary: Optional[str] = None
    category: Optional[str] = None
    severity: Optional[str] = None
    story_count: int
    source_count: int
    sources: list[str]  # List of source names
    first_published: Optional[datetime] = None
    last_updated: Optional[datetime] = None
    stories: list[ClusterStoryItem]
    story_groups: Optional[list[ClusterStoryGroupItem]] = None
    published_at: Optional[datetime] = None
    latest_version: Optional[int] = None
    latest_publication_at: Optional[datetime] = None
    citations_count: Optional[int] = None
    official_confirmation: Optional[bool] = None
    peer_review: Optional[PeerReviewSummary] = None

    @classmethod
    def from_cluster(
        cls,
        cluster,
        prefer_analyst: bool = False,
        story_groups: Optional[list[ClusterStoryGroupItem]] = None,
        *,
        published_at: Optional[datetime] = None,
        latest_version: Optional[int] = None,
        latest_publication_at: Optional[datetime] = None,
        citations_count: Optional[int] = None,
        official_confirmation: Optional[bool] = None,
        peer_review: Optional[PeerReviewSummary] = None,
    ) -> "AggregatedCluster":
        """Create from StoryCluster model with stories loaded."""
        sources = list(set(
            s.source_name or s.source_id
            for s in cluster.stories
        ))

        if prefer_analyst:
            headline = cluster.analyst_headline or cluster.headline
            # Prefer customer_brief when published
            summary = (
                cluster.customer_brief
                or cluster.analyst_summary
                or cluster.summary
            )
            category = cluster.analyst_category or cluster.category
            severity = cluster.analyst_severity or cluster.severity
        else:
            headline = cluster.headline
            summary = cluster.summary
            category = cluster.category
            severity = cluster.severity

        stories = [
            ClusterStoryItem(
                id=s.id,
                source_id=s.source_id,
                source_name=s.source_name,
                title=s.title,
                summary=s.summary,
                url=s.url,
                published_at=s.published_at,
            )
            for s in sorted(
                cluster.stories,
                key=lambda x: x.published_at or datetime.min.replace(tzinfo=timezone.utc),
                reverse=True,
            )
        ]

        return cls(
            id=cluster.id,
            headline=headline,
            summary=summary,
            category=category,
            severity=severity,
            story_count=cluster.story_count,
            source_count=cluster.source_count,
            sources=sources,
            first_published=cluster.first_published,
            last_updated=cluster.last_updated,
            stories=stories,
            story_groups=story_groups,
            published_at=published_at,
            latest_version=latest_version,
            latest_publication_at=latest_publication_at,
            citations_count=citations_count,
            official_confirmation=official_confirmation,
            peer_review=peer_review,
        )


class AggregatedNewsResponse(BaseModel):
    """Response for aggregated-news endpoint."""
    clusters: list[AggregatedCluster]
    unclustered_count: int
    total_stories: int


# ============================================================
# Key Actors (Political Entities) Schemas
# ============================================================

class StoryBrief(BaseModel):
    """Brief story info for entity detail view."""
    id: UUID
    title: str
    source_name: Optional[str] = None
    published_at: Optional[datetime] = None
    url: str


class KeyActorResponse(BaseModel):
    """Key actor (political entity) response for dashboard."""
    model_config = ConfigDict(from_attributes=True)

    entity_id: UUID
    canonical_id: str
    name: str
    name_ne: Optional[str] = None
    entity_type: str  # person, party, organization, institution
    party: Optional[str] = None
    role: Optional[str] = None
    image_url: Optional[str] = None

    # Mention stats
    mention_count: int  # Total mentions
    mention_count_24h: int  # Last 24 hours
    mention_count_7d: int  # Last 7 days
    trend: str  # rising, stable, falling
    last_mentioned_at: Optional[datetime] = None

    # Top stories mentioning this entity
    top_stories: list[StoryBrief] = []

    @classmethod
    def from_entity(
        cls,
        entity,
        top_stories: list = None,
    ) -> "KeyActorResponse":
        """Create from PoliticalEntity model."""
        stories = []
        if top_stories:
            stories = [
                StoryBrief(
                    id=s.id,
                    title=s.title,
                    source_name=s.source_name,
                    published_at=s.published_at,
                    url=s.url,
                )
                for s in top_stories[:5]
            ]

        return cls(
            entity_id=entity.id,
            canonical_id=entity.canonical_id,
            name=entity.name_en,
            name_ne=entity.name_ne,
            entity_type=entity.entity_type.value,
            party=entity.party,
            role=entity.role,
            image_url=entity.image_url,
            mention_count=entity.total_mentions,
            mention_count_24h=entity.mentions_24h,
            mention_count_7d=entity.mentions_7d,
            trend=entity.trend.value,
            last_mentioned_at=entity.last_mentioned_at,
            top_stories=stories,
        )


# ============================================================
# Executive Summary (AI-Generated)
# ============================================================

class PriorityDevelopment(BaseModel):
    """Priority development item in executive summary."""
    headline: str
    significance: str
    districts: list[str] = []


class ExecutiveSummaryResponse(BaseModel):
    """AI-generated executive summary response."""
    key_judgment: str
    situation_overview: str
    priority_developments: list[PriorityDevelopment]
    geographic_focus: list[str]
    threat_level: str  # CRITICAL | ELEVATED | GUARDED | LOW
    threat_trajectory: str  # ESCALATING | STABLE | DE-ESCALATING
    watch_items: list[str]
    story_count: int
    time_range_hours: int
    generated_at: datetime


# ============================================================
# AI-Enhanced Threat Matrix
# ============================================================

class CategoryInsight(BaseModel):
    """AI-generated insight for a threat category."""
    narrative: str
    key_development: str
    watch_for: str


class ThreatMatrixAIResponse(BaseModel):
    """AI-enhanced threat matrix response."""
    matrix: list[ThreatCategoryItem]
    overall_threat_level: str
    last_updated: datetime
    overall_assessment: str
    category_insights: dict[str, CategoryInsight]
    priority_watch_items: list[str]
    escalation_risk: str  # LOW | MODERATE | HIGH
    ai_generated: bool = True


# ============================================================
# Cluster Timeline (Situation Monitor)
# ============================================================

class ClusterTimelineStory(BaseModel):
    """Single story within a cluster timeline."""
    source_name: Optional[str] = None
    title: str
    published_at: Optional[datetime] = None
    url: Optional[str] = None


class ClusterTimelineEntry(BaseModel):
    """A story cluster with chronological source timeline."""
    cluster_id: UUID
    headline: str
    category: Optional[str] = None
    severity: Optional[str] = None
    story_count: int
    source_count: int
    first_published: Optional[datetime] = None
    last_updated: Optional[datetime] = None
    diversity_score: Optional[float] = None
    confidence_level: Optional[str] = None
    bluf: Optional[str] = None
    development_stage: Optional[str] = None  # emerging | developing | mature | resolved
    timeline: list[ClusterTimelineStory]


class DevelopingStoryEntry(BaseModel):
    """Event-level developing story feed item."""
    cluster_id: UUID
    headline: str
    category: Optional[str] = None
    severity: Optional[str] = None
    story_count: int
    source_count: int
    first_published: Optional[datetime] = None
    last_updated: Optional[datetime] = None
    diversity_score: Optional[float] = None
    confidence_level: Optional[str] = None
    bluf: Optional[str] = None
    development_stage: Optional[str] = None
    timeline: list[ClusterTimelineStory]
    new_sources_6h: int = 0
    update_velocity: int = 0
    urgency_score: float = 0.0
    cross_lingual: bool = False


class StoryTrackerClusterRef(BaseModel):
    """Cluster within a higher-level narrative."""
    cluster_id: UUID
    headline: str
    category: Optional[str] = None
    severity: Optional[str] = None
    story_count: int
    source_count: int
    last_updated: Optional[datetime] = None
    bluf: Optional[str] = None
    similarity_score: Optional[float] = None


class StoryTrackerEntry(BaseModel):
    """Narrative-level tracker item spanning multiple clusters."""
    narrative_id: UUID
    label: str
    thesis: Optional[str] = None
    category: Optional[str] = None
    direction: Optional[str] = None
    momentum_score: float
    confidence: Optional[float] = None
    cluster_count: int
    lead_regions: list[str] = []
    lead_entities: list[str] = []
    first_seen_at: Optional[datetime] = None
    last_updated: Optional[datetime] = None
    clusters: list[StoryTrackerClusterRef]
