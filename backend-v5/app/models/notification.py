"""User notification model for in-app notifications."""
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import String, DateTime, Text, Boolean, func, Index
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class NotificationType(str, Enum):
    """Notification types for workflow + consumer alerts."""
    MAJOR_ALERT = "major_alert"
    PLACE_ALERT = "place_alert"
    TOPIC_ALERT = "topic_alert"
    CORRECTION_APPROVED = "correction_approved"
    CORRECTION_REJECTED = "correction_rejected"
    CORRECTION_ROLLED_BACK = "correction_rolled_back"
    BULK_UPLOAD_COMPLETE = "bulk_upload_complete"


class UserNotification(Base):
    """In-app notification for users."""

    __tablename__ = "user_notifications"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    category: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="workflow",
        server_default="workflow",
    )
    severity: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
    )
    reason_code: Mapped[Optional[str]] = mapped_column(
        String(40),
        nullable=True,
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    data: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
    )
    topic_id: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    province_name: Mapped[Optional[str]] = mapped_column(
        String(80),
        nullable=True,
    )
    district_name: Mapped[Optional[str]] = mapped_column(
        String(80),
        nullable=True,
    )
    source_kind: Mapped[Optional[str]] = mapped_column(
        String(30),
        nullable=True,
    )
    source_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    deeplink_url: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    dedupe_key: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    is_read: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    archived_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    delivered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_user_notifications_user_created", "user_id", "created_at"),
        Index("ix_user_notifications_user_type", "user_id", "type"),
        Index("ix_user_notifications_user_read", "user_id", "is_read"),
        Index("ix_user_notifications_user_dedupe", "user_id", "dedupe_key"),
    )

    def __repr__(self) -> str:
        read = "read" if self.is_read else "unread"
        return f"<Notification [{self.type}] to {self.user_id} ({read})>"
