"""Government decision extraction records."""
from datetime import datetime
from typing import Optional, TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Float, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.govt_decision_review import GovtDecisionReview


class GovtDecisionItem(Base):
    """Machine-extracted government decision candidate."""

    __tablename__ = "govt_decision_items"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    external_key: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    event_key: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    candidate_signature: Mapped[str] = mapped_column(String(120), nullable=False, index=True)

    source_story_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    source_announcement_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")

    representative_title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    representative_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    office: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    implementing_ministry: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    decision_type: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    decision_title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    decision_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    evidence_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_actual_decision: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    raw_model_payload: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now(), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
        onupdate=func.now(),
    )

    review: Mapped[Optional["GovtDecisionReview"]] = relationship(
        "GovtDecisionReview",
        back_populates="decision_item",
        cascade="all, delete-orphan",
        uselist=False,
    )

    __table_args__ = (
        Index("idx_govt_decision_event_published", "event_key", "published_at"),
    )
