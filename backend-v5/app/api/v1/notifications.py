"""In-app notification endpoints."""
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_dev
from app.models.user import User
from app.schemas.notifications import (
    MarkReadResponse,
    NotificationFeedResponse,
    NotificationFollowSimilarResponse,
    NotificationListResponse,
    NotificationPreferencesResponse,
    NotificationPreferencesUpdate,
    NotificationSeedRequest,
    NotificationTab,
)
from app.services.notification_service import NotificationService

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("/", response_model=NotificationListResponse)
async def get_notifications(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Legacy notifications list endpoint."""
    service = NotificationService(db)
    return await service.get_notifications(user.id)


@router.get("/feed", response_model=NotificationFeedResponse)
async def get_notification_feed(
    tab: NotificationTab = Query("all"),
    unread_only: bool = Query(False),
    limit: int = Query(25, ge=1, le=50),
    cursor: str | None = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a paginated notification feed for the current user."""
    service = NotificationService(db)
    return await service.get_feed(user, tab=tab, unread_only=unread_only, limit=limit, cursor=cursor)


@router.get("/preferences", response_model=NotificationPreferencesResponse)
async def get_notification_preferences(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get effective notification preferences for the current user."""
    service = NotificationService(db)
    return await service.get_preferences(user)


@router.put("/preferences", response_model=NotificationPreferencesResponse)
async def update_notification_preferences(
    payload: NotificationPreferencesUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update server-side notification preferences."""
    service = NotificationService(db)
    return await service.update_preferences(user, payload.model_dump(exclude_unset=True))


@router.post("/{notification_id}/read", response_model=MarkReadResponse)
async def mark_notification_read(
    notification_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark a single notification as read."""
    service = NotificationService(db)
    return await service.mark_read(notification_id, user.id)


@router.post("/read-all", response_model=MarkReadResponse)
async def mark_all_read(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark all notifications as read."""
    service = NotificationService(db)
    return await service.mark_all_read(user.id)


@router.post("/{notification_id}/mute", response_model=NotificationFollowSimilarResponse)
async def mute_notification_scope(
    notification_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mute the scope implied by a notification."""
    service = NotificationService(db)
    return await service.mute_from_notification(user, notification_id)


@router.post("/{notification_id}/follow-similar", response_model=NotificationFollowSimilarResponse)
async def follow_similar_from_notification(
    notification_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Follow a notification's place or topic for future alerts."""
    service = NotificationService(db)
    return await service.follow_similar_from_notification(user, notification_id)


@router.post("/test-seed")
async def seed_test_notifications(
    payload: NotificationSeedRequest,
    user: User = Depends(require_dev),
    db: AsyncSession = Depends(get_db),
):
    """Dev-only helper for seeding sample notifications."""
    service = NotificationService(db)
    return await service.seed_test_notifications(user, payload.count)
