"""Cabinet 100-day action tracker models."""
from datetime import date, datetime
from typing import TYPE_CHECKING, Optional
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.promise import ManifestoPromise
    from app.models.user import User


class CabinetActionProgram(Base):
    """Canonical source program for a cabinet action package."""

    __tablename__ = "cabinet_action_programs"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    program_key: Mapped[str] = mapped_column(String(80), nullable=False, unique=True, index=True)
    title_ne: Mapped[str] = mapped_column(Text, nullable=False)
    title_en: Mapped[str] = mapped_column(Text, nullable=False)
    source_pdf_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    source_pdf_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_pdf_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    approval_date_bs: Mapped[str] = mapped_column(String(20), nullable=False)
    approval_date_ad: Mapped[date] = mapped_column(Date, nullable=False)
    source_language: Mapped[str] = mapped_column(String(12), nullable=False, default="ne", server_default="ne")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now(), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
        onupdate=func.now(),
    )

    items: Mapped[list["CabinetActionItem"]] = relationship(
        "CabinetActionItem",
        back_populates="program",
        cascade="all, delete-orphan",
    )


class CabinetActionItem(Base):
    """Parent record for one numbered cabinet action item."""

    __tablename__ = "cabinet_action_items"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    program_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("cabinet_action_programs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    item_number: Mapped[int] = mapped_column(Integer, nullable=False)
    section_key: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    section_title_ne: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    section_title_en: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_text_ne: Mapped[str] = mapped_column(Text, nullable=False)
    title_en: Mapped[str] = mapped_column(Text, nullable=False)
    summary_en: Mapped[str] = mapped_column(Text, nullable=False)
    lead_institution: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    supporting_institutions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    action_type: Mapped[Optional[str]] = mapped_column(String(80), nullable=True, index=True)
    trackability_class: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    deadline_text_ne: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    deadline_kind: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    deadline_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    due_date_bs: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    due_date_ad: Mapped[Optional[date]] = mapped_column(Date, nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="announced", server_default="announced", index=True)
    evidence_strength: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true", index=True)
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    source_pdf_page: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    notes_internal: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_seed_payload: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now(), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
        onupdate=func.now(),
    )

    program: Mapped["CabinetActionProgram"] = relationship("CabinetActionProgram", back_populates="items")
    milestones: Mapped[list["CabinetActionMilestone"]] = relationship(
        "CabinetActionMilestone",
        back_populates="item",
        cascade="all, delete-orphan",
        order_by="CabinetActionMilestone.milestone_order",
    )
    review: Mapped[Optional["CabinetActionReview"]] = relationship(
        "CabinetActionReview",
        back_populates="item",
        cascade="all, delete-orphan",
        uselist=False,
    )
    evidence_entries: Mapped[list["CabinetActionEvidence"]] = relationship(
        "CabinetActionEvidence",
        back_populates="item",
        cascade="all, delete-orphan",
        order_by="CabinetActionEvidence.published_at.desc()",
    )
    promise_links: Mapped[list["CabinetActionPromiseLink"]] = relationship(
        "CabinetActionPromiseLink",
        back_populates="item",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("program_id", "item_number", name="uq_cabinet_action_program_item"),
        Index("idx_cabinet_action_section_status", "section_key", "status"),
    )


class CabinetActionMilestone(Base):
    """Sub-action or milestone nested under a cabinet action item."""

    __tablename__ = "cabinet_action_milestones"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    item_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("cabinet_action_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    milestone_order: Mapped[int] = mapped_column(Integer, nullable=False)
    source_text_ne: Mapped[str] = mapped_column(Text, nullable=False)
    title_en: Mapped[str] = mapped_column(Text, nullable=False)
    summary_en: Mapped[str] = mapped_column(Text, nullable=False)
    deadline_text_ne: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    deadline_kind: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    deadline_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    due_date_bs: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    due_date_ad: Mapped[Optional[date]] = mapped_column(Date, nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="announced", server_default="announced", index=True)
    evidence_strength: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    notes_internal: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_seed_payload: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now(), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
        onupdate=func.now(),
    )

    item: Mapped["CabinetActionItem"] = relationship("CabinetActionItem", back_populates="milestones")
    evidence_entries: Mapped[list["CabinetActionEvidence"]] = relationship(
        "CabinetActionEvidence",
        back_populates="milestone",
        cascade="all, delete-orphan",
        order_by="CabinetActionEvidence.published_at.desc()",
    )

    __table_args__ = (
        UniqueConstraint("item_id", "milestone_order", name="uq_cabinet_action_item_milestone_order"),
    )


class CabinetActionReview(Base):
    """Human moderation layer for cabinet action content and status."""

    __tablename__ = "cabinet_action_reviews"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    cabinet_action_item_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("cabinet_action_items.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    workflow_status: Mapped[str] = mapped_column(String(30), nullable=False, default="approved", server_default="approved", index=True)
    final_section_key: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    final_section_title_en: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    final_title_en: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    final_summary_en: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    final_lead_institution: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    final_supporting_institutions: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    final_action_type: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    final_trackability_class: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    final_status: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    final_evidence_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    final_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    final_is_public: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    final_manifesto_promise_ids: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    milestone_overrides: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
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

    item: Mapped["CabinetActionItem"] = relationship("CabinetActionItem", back_populates="review")
    approved_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[approved_by_id])
    rejected_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[rejected_by_id])
    rerun_requested_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[rerun_requested_by_id])


class CabinetActionEvidence(Base):
    """Evidence entries linked to parent items or milestones."""

    __tablename__ = "cabinet_action_evidence"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    item_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("cabinet_action_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    milestone_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("cabinet_action_milestones.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    source_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    source_title: Mapped[str] = mapped_column(Text, nullable=False)
    source_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    source_story_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    source_announcement_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    is_official: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    extracted_status: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    evidence_note_en: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    is_applied: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    raw_model_payload: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now(), server_default=func.now())

    item: Mapped["CabinetActionItem"] = relationship("CabinetActionItem", back_populates="evidence_entries")
    milestone: Mapped[Optional["CabinetActionMilestone"]] = relationship("CabinetActionMilestone", back_populates="evidence_entries")


class CabinetActionPromiseLink(Base):
    """Crosswalk row between cabinet actions and manifesto promises."""

    __tablename__ = "cabinet_action_promise_links"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    item_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("cabinet_action_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    manifesto_promise_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("manifesto_promises.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now(), server_default=func.now())

    item: Mapped["CabinetActionItem"] = relationship("CabinetActionItem", back_populates="promise_links")
    manifesto_promise: Mapped["ManifestoPromise"] = relationship("ManifestoPromise")

    __table_args__ = (
        UniqueConstraint("item_id", "manifesto_promise_id", name="uq_cabinet_action_promise_link"),
    )
