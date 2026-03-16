"""Deterministic consumer-notification matching service."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.curfew_alert import get_province_for_district
from app.models.notification import NotificationType, UserNotification
from app.models.province_anomaly import ProvinceAnomaly, ProvinceAnomalyRun
from app.models.situation_brief import SituationBrief
from app.models.story import Story
from app.models.user import User
from app.models.user_notification_preferences import UserNotificationPreferences
from app.repositories.notification_repository import DEFAULT_FOLLOWED_TOPICS, NotificationRepository

settings = get_settings()

SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}
MAJOR_STORY_CATEGORIES = {"security", "disaster", "political", "economic"}


@dataclass
class NotificationCandidate:
    """Normalized event candidate for notification matching."""

    source_kind: str
    source_id: str
    title: str
    message: str
    severity: str
    districts: list[str] = field(default_factory=list)
    provinces: list[str] = field(default_factory=list)
    topic_id: Optional[str] = None
    deeplink_url: str = "/"
    is_major: bool = False
    data: dict | None = None


@dataclass
class PreferenceSnapshot:
    """Effective notification preferences for a user."""

    user_id: UUID
    notifications_enabled: bool = True
    include_major_alerts: bool = True
    min_severity: str = "high"
    home_district: Optional[str] = None
    followed_districts: list[str] = field(default_factory=list)
    followed_provinces: list[str] = field(default_factory=list)
    followed_topics: list[str] = field(default_factory=lambda: DEFAULT_FOLLOWED_TOPICS.copy())
    muted_districts: list[str] = field(default_factory=list)
    muted_provinces: list[str] = field(default_factory=list)
    muted_topics: list[str] = field(default_factory=list)


def _normalize_text(value: str | None) -> str:
    return (value or "").strip().lower().replace("_", " ")


def _normalize_district(value: str | None) -> str:
    normalized = _normalize_text(value)
    return " ".join(normalized.split())


def _normalize_province(value: str | None) -> str:
    normalized = _normalize_text(value)
    aliases = {
        "province 1": "koshi",
        "province 2": "madhesh",
        "province 3": "bagmati",
        "province 4": "gandaki",
        "province 5": "lumbini",
        "province 6": "karnali",
        "province 7": "sudurpashchim",
        "sudurpaschim": "sudurpashchim",
    }
    return aliases.get(normalized, normalized)


def _district_to_province(district: str | None) -> Optional[str]:
    if not district:
        return None
    province = get_province_for_district(district)
    return province if province else None


def _dedupe_scope(reason_code: str, topic_id: str | None, district_name: str | None, province_name: str | None) -> str:
    if reason_code in {"followed_district", "home_district"} and district_name:
        return f"district:{_normalize_district(district_name)}"
    if reason_code == "followed_province" and province_name:
        return f"province:{_normalize_province(province_name)}"
    if reason_code == "followed_topic" and topic_id:
        return f"topic:{topic_id}"
    return "major:nepal"


def _time_bucket(now: datetime) -> str:
    return now.astimezone(timezone.utc).strftime("%Y%m%d%H")


def _story_topic(story: Story) -> Optional[str]:
    category = (story.category or "").strip().lower()
    if category == "political":
        return "elections"
    if category == "security":
        return "crime"
    if category == "economic":
        return "economy"
    if category == "disaster":
        return "disasters"
    text = " ".join(filter(None, [story.title, story.summary, story.content])).lower()
    if any(token in text for token in ("outbreak", "hospital", "health", "disease", "virus", "cholera")):
        return "health"
    if any(token in text for token in ("road", "bridge", "power", "electricity", "water supply", "building", "infrastructure")):
        return "infrastructure"
    if any(token in text for token in ("school", "campus", "university", "exam", "education")):
        return "education"
    if any(token in text for token in ("pollution", "climate", "forest", "conservation", "environment", "air quality")):
        return "environment"
    return None


class NotificationMatchingService:
    """Generates high-signal in-app notifications for registered users."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = NotificationRepository(db)

    def default_preferences(self, user_id: UUID) -> PreferenceSnapshot:
        return PreferenceSnapshot(user_id=user_id)

    def serialize_preferences(self, preferences: UserNotificationPreferences | None, user_id: UUID) -> PreferenceSnapshot:
        if preferences is None:
            return self.default_preferences(user_id)
        return PreferenceSnapshot(
            user_id=user_id,
            notifications_enabled=preferences.notifications_enabled,
            include_major_alerts=preferences.include_major_alerts,
            min_severity=preferences.min_severity,
            home_district=preferences.home_district,
            followed_districts=list(preferences.followed_districts or []),
            followed_provinces=list(preferences.followed_provinces or []),
            followed_topics=list(preferences.followed_topics or DEFAULT_FOLLOWED_TOPICS),
            muted_districts=list(preferences.muted_districts or []),
            muted_provinces=list(preferences.muted_provinces or []),
            muted_topics=list(preferences.muted_topics or []),
        )

    def _severity_at_least(self, actual: str, minimum: str) -> bool:
        return SEVERITY_ORDER.get(actual, 0) >= SEVERITY_ORDER.get(minimum, 0)

    def _is_muted(self, prefs: PreferenceSnapshot, candidate: NotificationCandidate) -> bool:
        districts = {_normalize_district(item) for item in candidate.districts}
        provinces = {_normalize_province(item) for item in candidate.provinces}
        if any(d in {_normalize_district(item) for item in prefs.muted_districts} for d in districts):
            return True
        if any(p in {_normalize_province(item) for item in prefs.muted_provinces} for p in provinces):
            return True
        if candidate.topic_id and candidate.topic_id in set(prefs.muted_topics):
            return True
        return False

    def _match_place_reason(self, prefs: PreferenceSnapshot, candidate: NotificationCandidate) -> tuple[str | None, str | None, str | None]:
        candidate_districts = {_normalize_district(item) for item in candidate.districts if item}
        followed_districts = {_normalize_district(item) for item in prefs.followed_districts if item}
        if prefs.home_district and _normalize_district(prefs.home_district) in candidate_districts:
            return "home_district", prefs.home_district, _district_to_province(prefs.home_district)
        for district in candidate.districts:
            if _normalize_district(district) in followed_districts:
                return "followed_district", district, _district_to_province(district)

        candidate_provinces = {_normalize_province(item) for item in candidate.provinces if item}
        followed_provinces = {_normalize_province(item) for item in prefs.followed_provinces if item}
        for province in candidate.provinces:
            if _normalize_province(province) in followed_provinces:
                return "followed_province", None, province
        return None, None, None

    async def _create_or_merge_notification(
        self,
        user_id: UUID,
        *,
        type: str,
        category: str,
        severity: str,
        reason_code: str,
        title: str,
        message: str,
        topic_id: str | None,
        district_name: str | None,
        province_name: str | None,
        source_kind: str,
        source_id: str,
        deeplink_url: str,
        data: dict | None,
    ) -> UserNotification:
        now = datetime.now(timezone.utc)
        scope = _dedupe_scope(reason_code, topic_id, district_name, province_name)
        dedupe_key = f"{source_kind}:{source_id}:{scope}:{_time_bucket(now)}"
        existing = await self.repo.find_recent_unread_by_dedupe(user_id, dedupe_key)
        if existing:
            existing.title = title
            existing.message = message
            existing.severity = severity
            existing.category = category
            existing.reason_code = reason_code
            existing.topic_id = topic_id
            existing.district_name = district_name
            existing.province_name = province_name
            existing.data = data
            existing.deeplink_url = deeplink_url
            existing.delivered_at = now
            await self.db.flush()
            return existing
        return await self.repo.create(
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
            commit=False,
        )

    async def _users_with_preferences(self) -> list[tuple[User, PreferenceSnapshot]]:
        users = await self.repo.list_registered_users()
        if not users:
            return []
        user_ids = [user.id for user in users]
        result = await self.db.execute(
            select(UserNotificationPreferences).where(UserNotificationPreferences.user_id.in_(user_ids))
        )
        pref_map = {pref.user_id: pref for pref in result.scalars().all()}
        return [(user, self.serialize_preferences(pref_map.get(user.id), user.id)) for user in users]

    async def process_candidate(self, candidate: NotificationCandidate) -> int:
        """Match a normalized candidate against registered users."""
        if not settings.consumer_notifications_enabled:
            return 0

        created = 0
        for user, prefs in await self._users_with_preferences():
            if not prefs.notifications_enabled:
                continue
            if not self._severity_at_least(candidate.severity, prefs.min_severity):
                continue
            if self._is_muted(prefs, candidate):
                continue

            reason_code = None
            district_name = None
            province_name = None
            topic_id = None
            notification_type = None
            category = "personalized"

            place_reason, matched_district, matched_province = self._match_place_reason(prefs, candidate)
            topic_match = candidate.topic_id and candidate.topic_id in set(prefs.followed_topics)

            if candidate.is_major and prefs.include_major_alerts:
                notification_type = NotificationType.MAJOR_ALERT.value
                reason_code = place_reason or ("followed_topic" if topic_match else "major_nepal")
                district_name = matched_district
                province_name = matched_province or (candidate.provinces[0] if candidate.provinces else None)
                topic_id = candidate.topic_id if topic_match else None
                category = "personalized" if reason_code != "major_nepal" else "system"
            elif place_reason:
                notification_type = NotificationType.PLACE_ALERT.value
                reason_code = place_reason
                district_name = matched_district
                province_name = matched_province or (candidate.provinces[0] if candidate.provinces else None)
            elif topic_match:
                notification_type = NotificationType.TOPIC_ALERT.value
                reason_code = "followed_topic"
                topic_id = candidate.topic_id

            if not notification_type or not reason_code:
                continue

            await self._create_or_merge_notification(
                user_id=user.id,
                type=notification_type,
                category=category,
                severity=candidate.severity,
                reason_code=reason_code,
                title=candidate.title,
                message=candidate.message,
                topic_id=topic_id,
                district_name=district_name,
                province_name=province_name,
                source_kind=candidate.source_kind,
                source_id=candidate.source_id,
                deeplink_url=candidate.deeplink_url,
                data=candidate.data,
            )
            created += 1

        if created:
            await self.db.commit()
        return created

    async def process_story(self, story: Story) -> int:
        """Generate notifications from a high-signal story."""
        severity = (story.severity or "").lower()
        if severity not in {"high", "critical"}:
            return 0
        districts = list(story.districts or [])
        provinces = list(story.provinces or [])
        if not provinces and districts:
            provinces = [province for district in districts if (province := _district_to_province(district))]
        candidate = NotificationCandidate(
            source_kind="story",
            source_id=str(story.id),
            title=story.title,
            message=(story.summary or f"{story.source_name or 'Source'} reported a {severity} story.").strip(),
            severity=severity,
            districts=districts,
            provinces=provinces,
            topic_id=_story_topic(story),
            deeplink_url="/",
            is_major=severity == "critical" and (story.category or "").lower() in MAJOR_STORY_CATEGORIES,
            data={
                "story_id": str(story.id),
                "source_name": story.source_name,
                "category": story.category,
                "severity": story.severity,
            },
        )
        return await self.process_candidate(candidate)

    async def process_brief(self, brief: SituationBrief) -> int:
        """Generate notifications from a situation brief if it contains strong hotspots."""
        hotspots = brief.hotspots or []
        high_hotspots = [
            hotspot for hotspot in hotspots
            if (hotspot.get("severity") or "").strip().lower() in {"high", "critical"}
        ]
        if not high_hotspots:
            return 0
        provinces = list({hotspot.get("province") for hotspot in high_hotspots if hotspot.get("province")})
        districts = list({hotspot.get("district") for hotspot in high_hotspots if hotspot.get("district")})
        candidate = NotificationCandidate(
            source_kind="brief",
            source_id=str(brief.id),
            title=f"National Assessment #{brief.run_number}",
            message=(brief.key_judgment or brief.national_summary or "New national assessment highlights elevated hotspots.").strip(),
            severity="critical" if any((hotspot.get("severity") or "").lower() == "critical" for hotspot in high_hotspots) else "high",
            districts=districts,
            provinces=provinces,
            topic_id="elections" if "politic" in (brief.national_summary or "").lower() else None,
            deeplink_url="/",
            is_major=True,
            data={
                "brief_id": str(brief.id),
                "run_number": brief.run_number,
                "hotspots": high_hotspots,
            },
        )
        return await self.process_candidate(candidate)

    async def process_province_anomalies(self, run: ProvinceAnomalyRun, anomalies: list[ProvinceAnomaly]) -> int:
        """Generate notifications from province anomaly ingest."""
        total = 0
        for anomaly in anomalies:
            level = (anomaly.threat_level or "").strip().lower()
            if level not in {"elevated", "critical"}:
                continue
            severity = "critical" if level == "critical" else "high"
            anomaly_districts = [
                item.get("district")
                for item in (anomaly.anomalies_data or [])
                if item.get("district")
            ]
            candidate = NotificationCandidate(
                source_kind="anomaly",
                source_id=str(anomaly.id),
                title=f"{anomaly.province_name}: {anomaly.threat_level.title()} conditions",
                message=(anomaly.summary or f"{anomaly.province_name} showed {anomaly.threat_level.lower()} anomaly pressure.").strip(),
                severity=severity,
                districts=anomaly_districts,
                provinces=[anomaly.province_name],
                topic_id="crime" if anomaly.security else None,
                deeplink_url="/",
                is_major=True,
                data={
                    "run_id": str(run.id),
                    "province_id": anomaly.province_id,
                    "province_name": anomaly.province_name,
                    "threat_level": anomaly.threat_level,
                    "threat_trajectory": anomaly.threat_trajectory,
                },
            )
            total += await self.process_candidate(candidate)
        return total

    async def seed_recent_for_user(self, user_id: UUID, limit: int = 10) -> int:
        """Backfill recent high-signal story notifications for a new user."""
        if not settings.consumer_notifications_enabled:
            return 0
        preferences = await self.repo.get_preferences(user_id)
        prefs = self.serialize_preferences(preferences, user_id)
        if not prefs.notifications_enabled:
            return 0
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        result = await self.db.execute(
            select(Story)
            .where(
                Story.created_at >= cutoff,
                Story.severity.in_(["high", "critical"]),
            )
            .order_by(Story.created_at.desc())
            .limit(limit)
        )
        stories = list(result.scalars().all())
        created = 0
        for story in reversed(stories):
            districts = list(story.districts or [])
            provinces = list(story.provinces or [])
            if not provinces and districts:
                provinces = [province for district in districts if (province := _district_to_province(district))]
            candidate = NotificationCandidate(
                source_kind="story",
                source_id=str(story.id),
                title=story.title,
                message=(story.summary or f"{story.source_name or 'Source'} reported a {(story.severity or 'high').lower()} story.").strip(),
                severity=(story.severity or "high").lower(),
                districts=districts,
                provinces=provinces,
                topic_id=_story_topic(story),
                deeplink_url="/",
                is_major=(story.severity or "").lower() == "critical" and (story.category or "").lower() in MAJOR_STORY_CATEGORIES,
                data={"story_id": str(story.id)},
            )

            if not self._severity_at_least(candidate.severity, prefs.min_severity):
                continue
            if self._is_muted(prefs, candidate):
                continue

            place_reason, matched_district, matched_province = self._match_place_reason(prefs, candidate)
            topic_match = candidate.topic_id and candidate.topic_id in set(prefs.followed_topics)
            if candidate.is_major and prefs.include_major_alerts:
                await self._create_or_merge_notification(
                    user_id=user_id,
                    type=NotificationType.MAJOR_ALERT.value,
                    category="system",
                    severity=candidate.severity,
                    reason_code=place_reason or ("followed_topic" if topic_match else "major_nepal"),
                    title=candidate.title,
                    message=candidate.message,
                    topic_id=candidate.topic_id if topic_match else None,
                    district_name=matched_district,
                    province_name=matched_province or (candidate.provinces[0] if candidate.provinces else None),
                    source_kind=candidate.source_kind,
                    source_id=candidate.source_id,
                    deeplink_url=candidate.deeplink_url,
                    data=candidate.data,
                )
                created += 1
            elif place_reason:
                await self._create_or_merge_notification(
                    user_id=user_id,
                    type=NotificationType.PLACE_ALERT.value,
                    category="personalized",
                    severity=candidate.severity,
                    reason_code=place_reason,
                    title=candidate.title,
                    message=candidate.message,
                    topic_id=None,
                    district_name=matched_district,
                    province_name=matched_province or (candidate.provinces[0] if candidate.provinces else None),
                    source_kind=candidate.source_kind,
                    source_id=candidate.source_id,
                    deeplink_url=candidate.deeplink_url,
                    data=candidate.data,
                )
                created += 1
            elif topic_match:
                await self._create_or_merge_notification(
                    user_id=user_id,
                    type=NotificationType.TOPIC_ALERT.value,
                    category="personalized",
                    severity=candidate.severity,
                    reason_code="followed_topic",
                    title=candidate.title,
                    message=candidate.message,
                    topic_id=candidate.topic_id,
                    district_name=None,
                    province_name=None,
                    source_kind=candidate.source_kind,
                    source_id=candidate.source_id,
                    deeplink_url=candidate.deeplink_url,
                    data=candidate.data,
                )
                created += 1

        if created:
            await self.db.commit()
        return created
