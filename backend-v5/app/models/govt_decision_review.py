"""Human moderation layer for government decision candidates."""
from datetime import datetime
from typing import Optional, TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.govt_decision import GovtDecisionItem
    from app.models.user import User


class GovtDecisionReview(Base):
    """Developer review state for a raw government decision extraction."""

    __tablename__ = "govt_decision_reviews"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    govt_decision_item_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("govt_decision_items.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    workflow_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="draft",
        server_default="draft",
        index=True,
    )
    final_office: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    final_implementing_ministry: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    final_decision_type: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    final_decision_title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    final_decision_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    final_status: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    final_source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    final_evidence_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    final_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    reviewer_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    approved_by_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_by_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    rejected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    needs_rerun: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    rerun_requested_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    rerun_requested_by_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now(), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
        onupdate=func.now(),
    )

    decision_item: Mapped["GovtDecisionItem"] = relationship("GovtDecisionItem", back_populates="review")
    approved_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[approved_by_id])
    rejected_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[rejected_by_id])
    rerun_requested_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[rerun_requested_by_id])
