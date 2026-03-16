"""Notification repository for data access."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import UserNotification
from app.models.user import User
from app.models.user_notification_preferences import UserNotificationPreferences


DEFAULT_FOLLOWED_TOPICS = ["disasters", "elections"]


class NotificationRepository:
    """Data access for user notifications and preferences."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        user_id: UUID,
        type: str,
        title: str,
        message: str | None = None,
        data: dict | None = None,
        *,
        category: str = "workflow",
        severity: str | None = None,
        reason_code: str | None = None,
        topic_id: str | None = None,
        province_name: str | None = None,
        district_name: str | None = None,
        source_kind: str | None = None,
        source_id: str | None = None,
        deeplink_url: str | None = None,
        dedupe_key: str | None = None,
        commit: bool = True,
    ) -> UserNotification:
        """Create a notification."""
        notification = UserNotification(
            user_id=user_id,
            type=type,
            category=category,
            severity=severity,
            reason_code=reason_code,
            title=title,
            message=message,
            data=data,
            topic_id=topic_id,
            province_name=province_name,
            district_name=district_name,
            source_kind=source_kind,
            source_id=source_id,
            deeplink_url=deeplink_url,
            dedupe_key=dedupe_key,
            delivered_at=datetime.now(timezone.utc),
        )
        self.db.add(notification)
        if commit:
            await self.db.commit()
            await self.db.refresh(notification)
        return notification

    async def find_recent_unread_by_dedupe(
        self,
        user_id: UUID,
        dedupe_key: str,
        *,
        hours: int = 24,
    ) -> UserNotification | None:
        """Find a recent unread notification for dedupe merging."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        result = await self.db.execute(
            select(UserNotification)
            .where(
                and_(
                    UserNotification.user_id == user_id,
                    UserNotification.dedupe_key == dedupe_key,
                    UserNotification.is_read.is_(False),
                    UserNotification.archived_at.is_(None),
                    UserNotification.created_at >= cutoff,
                )
            )
            .order_by(UserNotification.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_feed_for_user(
        self,
        user_id: UUID,
        *,
        tab: str = "all",
        unread_only: bool = False,
        limit: int = 25,
        cursor: str | None = None,
    ) -> tuple[list[UserNotification], int, Optional[str]]:
        """Get a feed page for the current user."""
        base_conditions = [
            UserNotification.user_id == user_id,
            UserNotification.archived_at.is_(None),
        ]
        if unread_only:
            base_conditions.append(UserNotification.is_read.is_(False))
        if tab == "major":
            base_conditions.append(UserNotification.type == "major_alert")
        elif tab == "for_you":
            base_conditions.append(
                or_(
                    UserNotification.category == "personalized",
                    UserNotification.type == "major_alert",
                )
            )

        if cursor:
            try:
                cursor_dt = datetime.fromisoformat(cursor.replace("Z", "+00:00"))
                base_conditions.append(UserNotification.created_at < cursor_dt)
            except ValueError:
                pass

        result = await self.db.execute(
            select(UserNotification)
            .where(and_(*base_conditions))
            .order_by(UserNotification.created_at.desc(), UserNotification.id.desc())
            .limit(limit + 1)
        )
        rows = list(result.scalars().all())
        next_cursor = None
        if len(rows) > limit:
            next_cursor = rows[limit - 1].created_at.isoformat()
            rows = rows[:limit]

        unread_result = await self.db.execute(
            select(func.count())
            .where(
                and_(
                    UserNotification.user_id == user_id,
                    UserNotification.is_read.is_(False),
                    UserNotification.archived_at.is_(None),
                )
            )
        )
        unread_count = unread_result.scalar() or 0
        return rows, unread_count, next_cursor

    async def get_for_user(
        self,
        user_id: UUID,
        limit: int = 50,
    ) -> tuple[list[UserNotification], int]:
        """Legacy list API for user. Returns (items, unread_count)."""
        items, unread_count, _ = await self.get_feed_for_user(user_id, tab="all", limit=limit)
        return items, unread_count

    async def mark_read(self, notification_id: UUID, user_id: UUID) -> bool:
        """Mark a single notification as read."""
        result = await self.db.execute(
            update(UserNotification)
            .where(
                and_(
                    UserNotification.id == notification_id,
                    UserNotification.user_id == user_id,
                )
            )
            .values(is_read=True)
        )
        await self.db.commit()
        return result.rowcount > 0

    async def mark_all_read(self, user_id: UUID) -> int:
        """Mark all notifications as read for a user."""
        result = await self.db.execute(
            update(UserNotification)
            .where(
                and_(
                    UserNotification.user_id == user_id,
                    UserNotification.is_read.is_(False),
                    UserNotification.archived_at.is_(None),
                )
            )
            .values(is_read=True)
        )
        await self.db.commit()
        return result.rowcount

    async def get_unread_count(self, user_id: UUID) -> int:
        """Get count of unread notifications."""
        result = await self.db.execute(
            select(func.count()).where(
                and_(
                    UserNotification.user_id == user_id,
                    UserNotification.is_read.is_(False),
                    UserNotification.archived_at.is_(None),
                )
            )
        )
        return result.scalar() or 0

    async def get_notification_for_user(self, notification_id: UUID, user_id: UUID) -> UserNotification | None:
        """Fetch a single notification owned by a user."""
        result = await self.db.execute(
            select(UserNotification).where(
                and_(
                    UserNotification.id == notification_id,
                    UserNotification.user_id == user_id,
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_preferences(self, user_id: UUID) -> UserNotificationPreferences | None:
        """Fetch stored notification preferences for a user."""
        result = await self.db.execute(
            select(UserNotificationPreferences).where(UserNotificationPreferences.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def upsert_preferences(
        self,
        user_id: UUID,
        *,
        notifications_enabled: bool | None = None,
        include_major_alerts: bool | None = None,
        min_severity: str | None = None,
        home_district: str | None = None,
        followed_districts: list[str] | None = None,
        followed_provinces: list[str] | None = None,
        followed_topics: list[str] | None = None,
        muted_districts: list[str] | None = None,
        muted_provinces: list[str] | None = None,
        muted_topics: list[str] | None = None,
        commit: bool = True,
    ) -> tuple[UserNotificationPreferences, bool]:
        """Create or update preferences for a user."""
        preferences = await self.get_preferences(user_id)
        created = preferences is None
        if preferences is None:
            preferences = UserNotificationPreferences(user_id=user_id)
            self.db.add(preferences)

        if notifications_enabled is not None:
            preferences.notifications_enabled = notifications_enabled
        if include_major_alerts is not None:
            preferences.include_major_alerts = include_major_alerts
        if min_severity is not None:
            preferences.min_severity = min_severity
        if home_district is not None or created:
            preferences.home_district = home_district
        if followed_districts is not None:
            preferences.followed_districts = followed_districts
        if followed_provinces is not None:
            preferences.followed_provinces = followed_provinces
        if followed_topics is not None:
            preferences.followed_topics = followed_topics or DEFAULT_FOLLOWED_TOPICS.copy()
        if muted_districts is not None:
            preferences.muted_districts = muted_districts
        if muted_provinces is not None:
            preferences.muted_provinces = muted_provinces
        if muted_topics is not None:
            preferences.muted_topics = muted_topics

        if commit:
            await self.db.commit()
            await self.db.refresh(preferences)
        return preferences, created

    async def list_registered_users(self) -> list[User]:
        """List active non-guest users for alert matching."""
        result = await self.db.execute(
            select(User)
            .where(
                and_(
                    User.is_active.is_(True),
                    User.auth_provider != "guest",
                )
            )
        )
        return list(result.scalars().all())
