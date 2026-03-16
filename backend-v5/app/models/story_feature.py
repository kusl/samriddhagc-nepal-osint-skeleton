"""StoryFeature model - cached clustering features for stories."""
from datetime import datetime
from typing import Optional, TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, func, String, Float
from sqlalchemy.dialects.postgresql import UUID as PGUUID, ARRAY
from sqlalchemy import Text, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.story import Story


class StoryFeature(Base):
    """Cached clustering features for a story."""

    __tablename__ = "story_features"

    # Primary key (same as story_id)
    story_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("stories.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # MinHash signature for content similarity (128 hash values)
    content_minhash: Mapped[Optional[list[int]]] = mapped_column(
        ARRAY(Integer),
        nullable=True,
        comment="128-value MinHash signature for content",
    )

    # Tokenized title for matching
    title_tokens: Mapped[Optional[list[str]]] = mapped_column(
        ARRAY(Text),
        nullable=True,
        comment="Tokenized and normalized title words",
    )

    # Geographic entities
    districts: Mapped[Optional[list[str]]] = mapped_column(
        ARRAY(Text),
        nullable=True,
        comment="Nepal districts mentioned in story",
    )
    provinces: Mapped[Optional[list[str]]] = mapped_column(
        ARRAY(Text),
        nullable=True,
        comment="Nepal provinces inferred from place mentions",
    )
    municipalities: Mapped[Optional[list[str]]] = mapped_column(
        ARRAY(Text),
        nullable=True,
        comment="Cities or municipalities mentioned in story",
    )
    place_mentions: Mapped[Optional[list[str]]] = mapped_column(
        ARRAY(Text),
        nullable=True,
        comment="Normalized place mentions used for event matching",
    )
    constituencies: Mapped[Optional[list[str]]] = mapped_column(
        ARRAY(Text),
        nullable=True,
        comment="Nepal constituencies mentioned in story",
    )
    geo_confidence: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="Confidence that primary geography is correctly assigned (0-1)",
    )
    primary_province: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Primary province for the story",
    )
    primary_municipality: Mapped[Optional[str]] = mapped_column(
        String(120),
        nullable=True,
        comment="Primary municipality/city for the story",
    )

    # Key terms for entity matching
    key_terms: Mapped[Optional[list[str]]] = mapped_column(
        ARRAY(Text),
        nullable=True,
        comment="Extracted key terms (names, orgs, etc.)",
    )
    named_people: Mapped[Optional[list[str]]] = mapped_column(
        ARRAY(Text),
        nullable=True,
        comment="Canonical people detected in story",
    )
    named_orgs: Mapped[Optional[list[str]]] = mapped_column(
        ARRAY(Text),
        nullable=True,
        comment="Organizations or agencies detected in story",
    )
    named_parties: Mapped[Optional[list[str]]] = mapped_column(
        ARRAY(Text),
        nullable=True,
        comment="Political parties detected in story",
    )
    named_infrastructure: Mapped[Optional[list[str]]] = mapped_column(
        ARRAY(Text),
        nullable=True,
        comment="Infrastructure or logistics nodes detected in story",
    )

    # International locations for blocking
    international_countries: Mapped[Optional[list[str]]] = mapped_column(
        ARRAY(Text),
        nullable=True,
        comment="International countries/cities mentioned",
    )

    # Topic classification for hard blocking
    topic: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="Topic classification (election, weather, sports, stock_market, etc.)",
    )
    event_type: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="Canonical event type (protest, arrest, fuel_shortage, etc.)",
    )
    operational_domain: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="Operational domain (governance, public_order, energy, disaster, etc.)",
    )
    event_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Resolved event time when explicit in content",
    )
    freshness_score: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="Freshness score used in event ranking (0-1)",
    )

    # Title-specific geographic blocking
    title_district: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Primary Nepal district in title for hard blocking",
    )

    title_country: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Primary international country in title for hard blocking",
    )

    # Named entities for PALANTIR-GRADE entity blocking (CRITICAL)
    # Stories about Oli should NEVER cluster with stories about Karki
    title_entities: Mapped[Optional[list[str]]] = mapped_column(
        ARRAY(Text),
        nullable=True,
        comment="Canonical named entities in title (e.g., ['oli'], ['karki'])",
    )

    # Action/event type for event-based blocking
    # "Oli's clarification" should NOT cluster with "Oli meets ambassador"
    title_action: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="Canonical action type (meeting, clarification, arrest, etc.)",
    )

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
    )

    # Relationship
    story: Mapped["Story"] = relationship(
        "Story",
        back_populates="features",
    )

    def __repr__(self) -> str:
        return f"<StoryFeature story_id={self.story_id}>"
