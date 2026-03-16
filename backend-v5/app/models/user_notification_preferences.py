"""Server-side preferences for consumer notifications."""
from datetime import datetime, time
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import Boolean, String, Time, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class UserNotificationPreferences(Base, TimestampMixin):
    """Server-side notification preferences for registered users."""

    __tablename__ = "user_notification_preferences"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    notifications_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )
    include_major_alerts: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )
    min_severity: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="high",
        server_default="high",
    )
    home_district: Mapped[Optional[str]] = mapped_column(
        String(80),
        nullable=True,
    )
    followed_districts: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
    )
    followed_provinces: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
    )
    followed_topics: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=lambda: ["disasters", "elections"],
        server_default='["disasters","elections"]',
    )
    muted_districts: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
    )
    muted_provinces: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
    )
    muted_topics: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
    )
    quiet_hours_start: Mapped[Optional[time]] = mapped_column(
        Time(timezone=False),
        nullable=True,
    )
    quiet_hours_end: Mapped[Optional[time]] = mapped_column(
        Time(timezone=False),
        nullable=True,
    )
    last_digest_sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    def __repr__(self) -> str:
        return f"<UserNotificationPreferences user={self.user_id} enabled={self.notifications_enabled}>"
