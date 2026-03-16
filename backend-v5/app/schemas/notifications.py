"""Pydantic schemas for notification endpoints."""
from datetime import datetime, time
from typing import Literal, Optional

from pydantic import BaseModel, Field


NotificationSeverity = Literal["low", "medium", "high", "critical"]
NotificationReasonCode = Literal[
    "major_nepal",
    "followed_topic",
    "followed_district",
    "followed_province",
    "home_district",
]
NotificationTab = Literal["all", "for_you", "major"]


class NotificationResponse(BaseModel):
    """Single notification."""

    id: str
    type: str
    category: str
    severity: Optional[str] = None
    title: str
    message: Optional[str] = None
    data: Optional[dict] = None
    reason_code: Optional[str] = None
    reason_label: Optional[str] = None
    topic_id: Optional[str] = None
    province_name: Optional[str] = None
    district_name: Optional[str] = None
    source_kind: Optional[str] = None
    source_id: Optional[str] = None
    deeplink_url: Optional[str] = None
    is_read: bool
    created_at: datetime


class NotificationListResponse(BaseModel):
    """List of notifications with unread count."""

    items: list[NotificationResponse]
    unread_count: int = 0


class NotificationFeedResponse(NotificationListResponse):
    """Cursor-paginated notification feed response."""

    next_cursor: Optional[str] = None
    tab: NotificationTab = "all"


class NotificationPreferencesResponse(BaseModel):
    """Server-side notification preferences."""

    notifications_enabled: bool = True
    include_major_alerts: bool = True
    min_severity: NotificationSeverity = "high"
    home_district: Optional[str] = None
    followed_districts: list[str] = []
    followed_provinces: list[str] = []
    followed_topics: list[str] = []
    muted_districts: list[str] = []
    muted_provinces: list[str] = []
    muted_topics: list[str] = []
    quiet_hours_start: Optional[time] = None
    quiet_hours_end: Optional[time] = None
    has_saved_preferences: bool = False


class NotificationPreferencesUpdate(BaseModel):
    """Update request for notification preferences."""

    notifications_enabled: Optional[bool] = None
    include_major_alerts: Optional[bool] = None
    min_severity: Optional[NotificationSeverity] = None
    home_district: Optional[str] = None
    followed_districts: Optional[list[str]] = None
    followed_provinces: Optional[list[str]] = None
    followed_topics: Optional[list[str]] = None


class NotificationFollowSimilarResponse(BaseModel):
    """Result of follow-similar or mute actions."""

    success: bool = True
    preferences: NotificationPreferencesResponse


class MarkReadResponse(BaseModel):
    """Response after marking notification(s) as read."""

    success: bool = True
    marked_read: int = 0


class NotificationSeedRequest(BaseModel):
    """Dev-only helper payload for seeding test notifications."""

    count: int = Field(default=3, ge=1, le=10)
