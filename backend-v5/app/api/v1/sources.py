"""Dynamic source reliability API endpoints."""
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_dev
from app.models.annotation import SourceReliability
from app.models.user import User
from app.schemas.collaboration import (
    SourceRatingCreate,
    SourceRecomputeResponse,
    SourceReliabilityResponse,
)
from app.services.source_reliability_service import SourceReliabilityScoringService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sources", tags=["sources"])

VALID_RELIABILITY_RATINGS = {"A", "B", "C", "D", "E"}


def _serialize_source(source: SourceReliability) -> SourceReliabilityResponse:
    metrics = source.automation_metrics or {}
    return SourceReliabilityResponse(
        source_id=source.source_id,
        source_name=source.source_name,
        source_type=source.source_type,
        reliability_rating=source.reliability_rating,
        credibility_rating=source.credibility_rating,
        confidence_score=source.confidence_score,
        admiralty_code=source.admiralty_code,
        total_stories=source.total_stories,
        verified_true=source.verified_true,
        verified_false=source.verified_false,
        total_ratings=source.total_ratings,
        average_user_rating=source.average_user_rating,
        notes=source.override_notes if source.override_pinned and source.override_notes else source.notes,
        rating_origin="manual_override" if source.override_pinned else "automated",
        provisional=bool(metrics.get("provisional", False)),
        sample_size=int(metrics.get("sample_size", 0) or 0),
        confidence_band=metrics.get("confidence_band"),
        automation_updated_at=source.automation_updated_at,
        score_breakdown=metrics.get("score_breakdown"),
    )


async def _ensure_source_profiles(db: AsyncSession, *, limit: int) -> None:
    service = SourceReliabilityScoringService(db)
    await service.ensure_source_rows(limit=max(limit, 20), lookback_days=90)

    missing_count = (
        await db.execute(
            select(func.count())
            .select_from(SourceReliability)
            .where(SourceReliability.automation_updated_at.is_(None), SourceReliability.total_stories > 0)
        )
    ).scalar() or 0
    if missing_count:
        await service.recompute_active_sources(limit=max(limit, 20), lookback_days=90, force=False)


async def _get_source_or_404(db: AsyncSession, source_id: str) -> SourceReliability:
    result = await db.execute(select(SourceReliability).where(SourceReliability.source_id == source_id))
    source = result.scalar_one_or_none()
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")
    return source


@router.get("", response_model=list[SourceReliabilityResponse])
async def list_sources(
    source_type: Optional[str] = Query(None, description="Filter by source type: rss, social, government, wire, blog"),
    min_confidence: Optional[int] = Query(None, ge=0, le=100, description="Minimum confidence score"),
    sort_by: str = Query("confidence", description="Sort by: confidence, name, stories"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """List source reliability ratings."""
    await _ensure_source_profiles(db, limit=skip + limit)

    query = select(SourceReliability)
    if source_type:
        query = query.where(SourceReliability.source_type == source_type)
    if min_confidence is not None:
        query = query.where(SourceReliability.confidence_score >= min_confidence)

    if sort_by == "name":
        query = query.order_by(SourceReliability.source_name.asc())
    elif sort_by == "stories":
        query = query.order_by(SourceReliability.total_stories.desc(), SourceReliability.confidence_score.desc())
    else:
        query = query.order_by(SourceReliability.confidence_score.desc(), SourceReliability.total_stories.desc())

    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    return [_serialize_source(source) for source in result.scalars().all()]


@router.get("/stats")
async def get_source_stats(
    db: AsyncSession = Depends(get_db),
):
    """Get aggregate statistics about source reliability."""
    await _ensure_source_profiles(db, limit=50)

    total_sources = (await db.execute(select(func.count()).select_from(SourceReliability))).scalar() or 0

    rating_counts = {}
    for rating in ["A", "B", "C", "D", "E"]:
        count = (
            await db.execute(select(func.count()).where(SourceReliability.reliability_rating == rating))
        ).scalar() or 0
        rating_counts[rating] = count

    avg_confidence = (await db.execute(select(func.avg(SourceReliability.confidence_score)))).scalar() or 0

    type_counts = {}
    for source_type in ["rss", "social", "government", "wire", "blog"]:
        count = (
            await db.execute(select(func.count()).where(SourceReliability.source_type == source_type))
        ).scalar() or 0
        type_counts[source_type] = count

    return {
        "total_sources": total_sources,
        "rating_distribution": rating_counts,
        "average_confidence": round(avg_confidence, 1),
        "type_distribution": type_counts,
    }


@router.post("/recompute", response_model=SourceRecomputeResponse)
async def recompute_sources(
    source_id: Optional[str] = Query(None, description="Recompute a single source if provided"),
    limit: int = Query(20, ge=1, le=100),
    lookback_days: int = Query(90, ge=7, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_dev),
):
    """Manually trigger source reliability recomputation."""
    del current_user
    service = SourceReliabilityScoringService(db)
    stats = await service.recompute_active_sources(
        source_id=source_id,
        limit=limit,
        lookback_days=lookback_days,
        force=True,
    )
    return SourceRecomputeResponse(**stats)


@router.get("/{source_id}", response_model=SourceReliabilityResponse)
async def get_source(
    source_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get a source reliability rating by ID."""
    await _ensure_source_profiles(db, limit=25)
    try:
        source = await _get_source_or_404(db, source_id)
    except HTTPException:
        service = SourceReliabilityScoringService(db)
        await service.recompute_active_sources(source_id=source_id, limit=1, lookback_days=90, force=True)
        source = await _get_source_or_404(db, source_id)

    if source.automation_updated_at is None:
        service = SourceReliabilityScoringService(db)
        await service.recompute_active_sources(source_id=source_id, limit=1, lookback_days=90, force=True)
        source = await _get_source_or_404(db, source_id)

    return _serialize_source(source)


@router.post("/{source_id}/rate", response_model=SourceReliabilityResponse)
async def rate_source(
    source_id: str,
    data: SourceRatingCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_dev),
):
    """Set a pinned manual override for a source's displayed rating."""
    await _ensure_source_profiles(db, limit=25)
    source = await _get_source_or_404(db, source_id)

    if data.reliability_rating not in VALID_RELIABILITY_RATINGS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reliability rating must be A-E",
        )

    source.override_pinned = True
    source.override_reliability_rating = data.reliability_rating
    source.override_credibility_rating = data.credibility_rating
    rel_score = {"A": 95, "B": 84, "C": 70, "D": 55, "E": 38}[data.reliability_rating]
    cred_score = {1: 95, 2: 84, 3: 70, 4: 55}[data.credibility_rating]
    source.override_confidence_score = int(round((rel_score * 0.6) + (cred_score * 0.4)))
    source.override_notes = data.notes or "Pinned manual override from dev console."
    source.override_set_by_id = current_user.id
    source.override_set_at = datetime.now(timezone.utc)

    source.reliability_rating = source.override_reliability_rating
    source.credibility_rating = source.override_credibility_rating
    source.confidence_score = source.override_confidence_score
    source.notes = source.override_notes
    source.total_ratings += 1
    source.last_rated_by_id = current_user.id
    source.last_rated_at = source.override_set_at

    await db.commit()
    await db.refresh(source)
    return _serialize_source(source)


@router.delete("/{source_id}/override", response_model=SourceReliabilityResponse)
async def clear_source_override(
    source_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_dev),
):
    """Clear a pinned manual override and restore the automated rating."""
    del current_user
    await _ensure_source_profiles(db, limit=25)
    source = await _get_source_or_404(db, source_id)

    source.override_pinned = False
    source.override_reliability_rating = None
    source.override_credibility_rating = None
    source.override_confidence_score = None
    source.override_notes = None
    source.override_set_by_id = None
    source.override_set_at = None
    SourceReliabilityScoringService.restore_automated_rating(source)

    await db.commit()
    await db.refresh(source)
    return _serialize_source(source)


@router.post("", response_model=SourceReliabilityResponse, status_code=status.HTTP_201_CREATED)
async def create_source(
    source_id: str = Query(..., description="Unique source identifier"),
    source_name: str = Query(..., description="Display name"),
    source_type: str = Query(..., description="Source type: rss, social, government, wire, blog"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_dev),
):
    """Create a new source reliability entry."""
    del current_user
    existing = await db.execute(select(SourceReliability).where(SourceReliability.source_id == source_id))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Source already exists")

    source = SourceReliability(
        source_id=source_id,
        source_name=source_name,
        source_type=source_type,
        reliability_rating="C",
        credibility_rating=3,
        confidence_score=55,
        notes="Awaiting automated source reliability recompute.",
    )

    db.add(source)
    await db.commit()
    await db.refresh(source)
    return _serialize_source(source)
