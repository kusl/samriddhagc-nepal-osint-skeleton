"""In-app notification service."""
from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import UserNotification
from app.models.user import User
from app.repositories.notification_repository import NotificationRepository
from app.services.notification_matching_service import NotificationMatchingService

logger = logging.getLogger(__name__)

REASON_LABELS = {
    "major_nepal": "Major Nepal alert",
    "followed_topic": "Followed topic",
    "followed_district": "Followed district",
    "followed_province": "Followed province",
    "home_district": "Home district",
}


class NotificationService:
    """Manages workflow + consumer notifications."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = NotificationRepository(db)
        self.matcher = NotificationMatchingService(db)

    def _serialize_notification(self, notification: UserNotification) -> dict:
        return {
            "id": str(notification.id),
            "type": notification.type,
            "category": notification.category,
            "severity": notification.severity,
            "title": notification.title,
            "message": notification.message,
            "data": notification.data,
            "reason_code": notification.reason_code,
            "reason_label": REASON_LABELS.get(notification.reason_code),
            "topic_id": notification.topic_id,
            "province_name": notification.province_name,
            "district_name": notification.district_name,
            "source_kind": notification.source_kind,
            "source_id": notification.source_id,
            "deeplink_url": notification.deeplink_url,
            "is_read": notification.is_read,
            "created_at": notification.created_at,
        }

    def _serialize_preferences(self, user_id: UUID, preferences, *, has_saved_preferences: bool) -> dict:
        snapshot = self.matcher.serialize_preferences(preferences, user_id)
        return {
            "notifications_enabled": snapshot.notifications_enabled,
            "include_major_alerts": snapshot.include_major_alerts,
            "min_severity": snapshot.min_severity,
            "home_district": snapshot.home_district,
            "followed_districts": snapshot.followed_districts,
            "followed_provinces": snapshot.followed_provinces,
            "followed_topics": snapshot.followed_topics,
            "muted_districts": snapshot.muted_districts,
            "muted_provinces": snapshot.muted_provinces,
            "muted_topics": snapshot.muted_topics,
            "quiet_hours_start": getattr(preferences, "quiet_hours_start", None),
            "quiet_hours_end": getattr(preferences, "quiet_hours_end", None),
            "has_saved_preferences": has_saved_preferences,
        }

    async def notify_correction_approved(
        self, user_id: UUID, candidate_name: str, field: str, correction_id: UUID
    ):
        """Notify analyst that their correction was approved."""
        await self.repo.create(
            user_id=user_id,
            type="correction_approved",
            title="Correction Approved",
            message=f"Your correction to {candidate_name}'s {field} was approved",
            data={"correction_id": str(correction_id)},
        )

    async def notify_correction_rejected(
        self, user_id: UUID, candidate_name: str, field: str, correction_id: UUID, reason: str
    ):
        """Notify analyst that their correction was rejected."""
        await self.repo.create(
            user_id=user_id,
            type="correction_rejected",
            title="Correction Rejected",
            message=f"Your correction to {candidate_name}'s {field} was rejected: {reason}",
            data={"correction_id": str(correction_id), "reason": reason},
        )

    async def notify_correction_rolled_back(
        self, user_id: UUID, candidate_name: str, field: str, correction_id: UUID
    ):
        """Notify analyst that their approved correction was rolled back."""
        await self.repo.create(
            user_id=user_id,
            type="correction_rolled_back",
            title="Correction Rolled Back",
            message=f"Your approved correction to {candidate_name}'s {field} was rolled back",
            data={"correction_id": str(correction_id)},
        )

    async def notify_bulk_upload_complete(
        self, user_id: UUID, total: int, valid: int, invalid: int, batch_id: str
    ):
        """Notify dev that bulk upload processing is complete."""
        await self.repo.create(
            user_id=user_id,
            type="bulk_upload_complete",
            title="Bulk Upload Complete",
            message=f"Processed {total} rows: {valid} valid, {invalid} invalid",
            data={"batch_id": batch_id, "total": total, "valid": valid, "invalid": invalid},
        )

    async def get_feed(
        self,
        user: User,
        *,
        tab: str = "all",
        unread_only: bool = False,
        limit: int = 25,
        cursor: str | None = None,
    ) -> dict:
        """Get a paginated feed for a user."""
        if user.auth_provider == "guest":
            return {"items": [], "unread_count": 0, "next_cursor": None, "tab": tab}
        items, unread_count, next_cursor = await self.repo.get_feed_for_user(
            user.id,
            tab=tab,
            unread_only=unread_only,
            limit=limit,
            cursor=cursor,
        )
        return {
            "items": [self._serialize_notification(item) for item in items],
            "unread_count": unread_count,
            "next_cursor": next_cursor,
            "tab": tab,
        }

    async def get_notifications(self, user_id: UUID, limit: int = 50) -> dict:
        """Legacy notifications list for a user."""
        items, unread_count = await self.repo.get_for_user(user_id, limit)
        return {
            "items": [self._serialize_notification(item) for item in items],
            "unread_count": unread_count,
        }

    async def get_preferences(self, user: User) -> dict:
        """Get effective notification preferences for a user."""
        if user.auth_provider == "guest":
            return self._serialize_preferences(user.id, None, has_saved_preferences=False)
        preferences = await self.repo.get_preferences(user.id)
        return self._serialize_preferences(user.id, preferences, has_saved_preferences=preferences is not None)

    async def update_preferences(self, user: User, payload: dict) -> dict:
        """Create or update server-side preferences."""
        if user.auth_provider == "guest":
            return self._serialize_preferences(user.id, None, has_saved_preferences=False)
        update_kwargs = {}
        for key in (
            "notifications_enabled",
            "include_major_alerts",
            "min_severity",
            "home_district",
            "followed_districts",
            "followed_provinces",
            "followed_topics",
        ):
            if key in payload:
                update_kwargs[key] = payload[key]
        preferences, created = await self.repo.upsert_preferences(user.id, **update_kwargs)
        if created and preferences.notifications_enabled:
            await self.matcher.seed_recent_for_user(user.id, limit=10)
            preferences = await self.repo.get_preferences(user.id)
        return self._serialize_preferences(user.id, preferences, has_saved_preferences=True)

    async def mark_read(self, notification_id: UUID, user_id: UUID) -> dict:
        """Mark a single notification as read."""
        success = await self.repo.mark_read(notification_id, user_id)
        return {"success": success}

    async def mark_all_read(self, user_id: UUID) -> dict:
        """Mark all notifications as read."""
        count = await self.repo.mark_all_read(user_id)
        return {"success": True, "marked_read": count}

    async def mute_from_notification(self, user: User, notification_id: UUID) -> dict:
        """Mute the most relevant scope implied by a notification."""
        preferences = await self.repo.get_preferences(user.id)
        snapshot = self.matcher.serialize_preferences(preferences, user.id)
        notification = await self.repo.get_notification_for_user(notification_id, user.id)
        if notification is None:
            return {"success": False, "preferences": self._serialize_preferences(user.id, preferences, has_saved_preferences=preferences is not None)}

        muted_topics = list(snapshot.muted_topics)
        muted_districts = list(snapshot.muted_districts)
        muted_provinces = list(snapshot.muted_provinces)
        if notification.topic_id and notification.topic_id not in muted_topics:
            muted_topics.append(notification.topic_id)
        elif notification.district_name and notification.district_name not in muted_districts:
            muted_districts.append(notification.district_name)
        elif notification.province_name and notification.province_name not in muted_provinces:
            muted_provinces.append(notification.province_name)

        updated, _ = await self.repo.upsert_preferences(
            user.id,
            notifications_enabled=snapshot.notifications_enabled,
            include_major_alerts=snapshot.include_major_alerts,
            min_severity=snapshot.min_severity,
            home_district=snapshot.home_district,
            followed_districts=snapshot.followed_districts,
            followed_provinces=snapshot.followed_provinces,
            followed_topics=snapshot.followed_topics,
            muted_districts=muted_districts,
            muted_provinces=muted_provinces,
            muted_topics=muted_topics,
        )
        return {"success": True, "preferences": self._serialize_preferences(user.id, updated, has_saved_preferences=True)}

    async def follow_similar_from_notification(self, user: User, notification_id: UUID) -> dict:
        """Follow the notification's topic or place for future alerts."""
        preferences = await self.repo.get_preferences(user.id)
        snapshot = self.matcher.serialize_preferences(preferences, user.id)
        notification = await self.repo.get_notification_for_user(notification_id, user.id)
        if notification is None:
            return {"success": False, "preferences": self._serialize_preferences(user.id, preferences, has_saved_preferences=preferences is not None)}

        followed_topics = list(snapshot.followed_topics)
        followed_districts = list(snapshot.followed_districts)
        followed_provinces = list(snapshot.followed_provinces)
        if notification.topic_id and notification.topic_id not in followed_topics:
            followed_topics.append(notification.topic_id)
        if notification.district_name and notification.district_name not in followed_districts:
            followed_districts.append(notification.district_name)
        if notification.province_name and notification.province_name not in followed_provinces:
            followed_provinces.append(notification.province_name)

        updated, _ = await self.repo.upsert_preferences(
            user.id,
            notifications_enabled=snapshot.notifications_enabled,
            include_major_alerts=snapshot.include_major_alerts,
            min_severity=snapshot.min_severity,
            home_district=snapshot.home_district,
            followed_districts=followed_districts,
            followed_provinces=followed_provinces,
            followed_topics=followed_topics,
            muted_districts=snapshot.muted_districts,
            muted_provinces=snapshot.muted_provinces,
            muted_topics=snapshot.muted_topics,
        )
        return {"success": True, "preferences": self._serialize_preferences(user.id, updated, has_saved_preferences=True)}

    async def seed_test_notifications(self, user: User, count: int = 3) -> dict:
        """Dev helper for generating sample notifications in the current inbox."""
        created = 0
        if user.auth_provider == "guest":
            return {"success": True, "created": 0}
        for idx in range(count):
            await self.repo.create(
                user_id=user.id,
                type="major_alert" if idx == 0 else "topic_alert",
                category="personalized" if idx else "system",
                severity="critical" if idx == 0 else "high",
                reason_code="major_nepal" if idx == 0 else "followed_topic",
                title="Fuel pressure alert" if idx == 0 else f"Tracked update #{idx}",
                message="Important movement was detected in a followed place or topic.",
                topic_id="economy" if idx else None,
                source_kind="alert",
                source_id=f"seed-{idx}",
                deeplink_url="/",
                data={"seed": True, "index": idx},
            )
            created += 1
        return {"success": True, "created": created}
