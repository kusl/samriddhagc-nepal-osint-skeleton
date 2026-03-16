"""Signal Intelligence (SIGINT) API endpoints.

Provides actionable intelligence for:
  - Stock traders (NEPSE) via /economic
  - Political/security analysts via /security
  - Cross-source narrative convergence via /convergence
  - Novel/emerging signals via /novel
  - Topic intensity heatmap via /heatmap
  - Full combined briefing via /briefing
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.exc import ProgrammingError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_dev
from app.models.sigint_triage import SigintTriage
from app.schemas.sigint import (
    BriefingSummary,
    ConvergenceItem,
    ConvergenceResponse,
    NovelSignalItem,
    NovelSignalResponse,
    SIGINTBriefingResponse,
    SignalListResponse,
    SignalResponse,
    SignalSourceItem,
    TopicCategoryHeatmap,
    TopicHeatmapResponse,
    TopicIntensityItem,
)
from app.services.sigint_service import SIGINTService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sigint", tags=["sigint"])


# ============================================================
# Helper: convert service dicts to response schemas
# ============================================================


def _signal_dict_to_response(d: dict) -> SignalResponse:
    """Convert a Signal.to_dict() result to a SignalResponse."""
    sources = [
        SignalSourceItem(
            source_type=s.get("source_type", "story"),
            id=s.get("id", ""),
            title=s.get("title"),
            source_name=s.get("source_name"),
            author=s.get("author"),
            similarity=s.get("similarity"),
            published_at=s.get("published_at"),
        )
        for s in d.get("sources", [])
    ]
    return SignalResponse(
        signal_type=d["signal_type"],
        title=d["title"],
        severity=d["severity"],
        confidence=d["confidence"],
        summary=d["summary"],
        sources=sources,
        tags=d.get("tags", []),
        first_seen=d.get("first_seen"),
        source_count=d.get("source_count", 0),
    )


def _convergence_dict_to_item(d: dict) -> ConvergenceItem:
    return ConvergenceItem(
        cluster_id=d["cluster_id"],
        title=d["title"],
        sources=d.get("sources", []),
        source_count=d.get("source_count", 0),
        avg_similarity=d.get("avg_similarity", 0.0),
        max_similarity=d.get("max_similarity", 0.0),
        first_seen=d.get("first_seen"),
    )


def _novel_dict_to_item(d: dict) -> NovelSignalItem:
    return NovelSignalItem(
        source_type=d.get("source_type", "story"),
        id=d.get("id", ""),
        title=d.get("title", ""),
        source_name=d.get("source_name"),
        author=d.get("author"),
        published_at=d.get("published_at"),
        max_similarity_to_past=d.get("max_similarity_to_past", 0.0),
    )


def _heatmap_category_to_schema(d: dict) -> TopicCategoryHeatmap:
    topics = [
        TopicIntensityItem(
            seed_query=t["seed_query"],
            count=t["count"],
            intensity=t["intensity"],
        )
        for t in d.get("topics", [])
    ]
    return TopicCategoryHeatmap(
        category=d["category"],
        topics=topics,
        max_intensity=d.get("max_intensity", "NONE"),
        total_matches=d.get("total_matches", 0),
    )


# ============================================================
# Endpoints
# ============================================================


@router.get("/briefing", response_model=SIGINTBriefingResponse)
async def get_sigint_briefing(
    hours: int = Query(48, ge=1, le=168, description="Time window in hours"),
    db: AsyncSession = Depends(get_db),
):
    """Full SIGINT briefing with all signal types.

    Combines economic signals, security signals, cross-source convergence,
    novel signal detection, and topic intensity heatmap into a single
    intelligence product.
    """
    try:
        service = SIGINTService(db)
        briefing = await service.generate_full_briefing(hours=hours)
    except Exception as exc:
        logger.exception("SIGINT briefing generation failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Briefing generation failed: {exc}")

    return SIGINTBriefingResponse(
        generated_at=briefing["generated_at"],
        period_hours=briefing["period_hours"],
        economic_signals=[
            _signal_dict_to_response(s) for s in briefing["economic_signals"]
        ],
        security_signals=[
            _signal_dict_to_response(s) for s in briefing["security_signals"]
        ],
        cross_source_convergence=[
            _convergence_dict_to_item(c) for c in briefing["cross_source_convergence"]
        ],
        novel_signals=[
            _novel_dict_to_item(n) for n in briefing["novel_signals"]
        ],
        topic_heatmap=[
            _heatmap_category_to_schema(h) for h in briefing["topic_heatmap"]
        ],
        summary=BriefingSummary(**briefing["summary"]),
    )


@router.get("/economic", response_model=SignalListResponse)
async def get_economic_signals(
    hours: int = Query(48, ge=1, le=168, description="Time window in hours"),
    min_similarity: float = Query(
        0.60, ge=0.4, le=1.0, description="Minimum embedding similarity threshold"
    ),
    db: AsyncSession = Depends(get_db),
):
    """Economic signals for stock traders.

    Detects monetary policy changes, market-moving news, IPO announcements,
    company results, budget signals, trade/customs changes, and infrastructure
    project developments relevant to NEPSE-listed companies.
    """
    try:
        service = SIGINTService(db)
        signals = await service.generate_economic_signals(
            hours=hours, min_similarity=min_similarity
        )
    except Exception as exc:
        logger.exception("Economic signal generation failed: %s", exc)
        raise HTTPException(
            status_code=500, detail=f"Economic signal generation failed: {exc}"
        )

    signal_responses = [_signal_dict_to_response(s.to_dict()) for s in signals]
    return SignalListResponse(
        signals=signal_responses,
        period_hours=hours,
        generated_at=datetime.now(timezone.utc).isoformat(),
        total=len(signal_responses),
    )


@router.get("/security", response_model=SignalListResponse)
async def get_security_signals(
    hours: int = Query(48, ge=1, le=168, description="Time window in hours"),
    min_similarity: float = Query(
        0.60, ge=0.4, le=1.0, description="Minimum embedding similarity threshold"
    ),
    db: AsyncSession = Depends(get_db),
):
    """Political/security signals for analysts.

    Detects protest/bandh early warnings (Twitter-first detection), political
    instability indicators, security incidents, judicial decisions, border
    incidents, and civil unrest signals.
    """
    try:
        service = SIGINTService(db)
        signals = await service.generate_security_signals(
            hours=hours, min_similarity=min_similarity
        )
    except Exception as exc:
        logger.exception("Security signal generation failed: %s", exc)
        raise HTTPException(
            status_code=500, detail=f"Security signal generation failed: {exc}"
        )

    signal_responses = [_signal_dict_to_response(s.to_dict()) for s in signals]
    return SignalListResponse(
        signals=signal_responses,
        period_hours=hours,
        generated_at=datetime.now(timezone.utc).isoformat(),
        total=len(signal_responses),
    )


@router.get("/convergence", response_model=ConvergenceResponse)
async def get_convergence(
    hours: int = Query(72, ge=1, le=168, description="Time window in hours"),
    min_similarity: float = Query(
        0.70, ge=0.5, le=1.0, description="Minimum pair similarity threshold"
    ),
    limit: int = Query(50, ge=1, le=200, description="Max clusters to return"),
    db: AsyncSession = Depends(get_db),
):
    """Cross-source narrative convergence.

    Finds stories covered by multiple independent news sources. High convergence
    (many sources covering the same event) indicates high-confidence signals.
    Results are grouped into narrative clusters and ranked by source diversity.
    """
    try:
        service = SIGINTService(db)
        clusters = await service.cross_source_convergence(
            hours=hours, min_similarity=min_similarity, limit=limit
        )
    except Exception as exc:
        logger.exception("Convergence analysis failed: %s", exc)
        raise HTTPException(
            status_code=500, detail=f"Convergence analysis failed: {exc}"
        )

    cluster_items = [_convergence_dict_to_item(c) for c in clusters]

    # Count total pairs (sum of all similarities across clusters)
    total_pairs = sum(
        len(c.get("sources", [])) * (len(c.get("sources", [])) - 1) // 2
        for c in clusters
    )

    return ConvergenceResponse(
        clusters=cluster_items,
        period_hours=hours,
        generated_at=datetime.now(timezone.utc).isoformat(),
        total_pairs=total_pairs,
        total_clusters=len(cluster_items),
    )


@router.get("/novel", response_model=NovelSignalResponse)
async def get_novel_signals(
    hours: int = Query(48, ge=1, le=168, description="Recent window in hours"),
    lookback_hours: int = Query(
        168, ge=24, le=720, description="Lookback window for precedent check"
    ),
    limit: int = Query(30, ge=1, le=100, description="Max novel signals to return"),
    db: AsyncSession = Depends(get_db),
):
    """Novel/emerging signals with no precedent.

    Finds stories and tweets from the last {hours} that have NO similar content
    in the previous {lookback_hours} window. These are potential emerging threats
    or opportunities that represent genuinely new topics.
    """
    try:
        service = SIGINTService(db)
        novel = await service.novel_signal_detection(
            hours=hours, lookback_hours=lookback_hours, limit=limit
        )
    except Exception as exc:
        logger.exception("Novel signal detection failed: %s", exc)
        raise HTTPException(
            status_code=500, detail=f"Novel signal detection failed: {exc}"
        )

    return NovelSignalResponse(
        signals=[_novel_dict_to_item(n) for n in novel],
        period_hours=hours,
        lookback_hours=lookback_hours,
        generated_at=datetime.now(timezone.utc).isoformat(),
        total=len(novel),
    )


@router.get("/heatmap", response_model=TopicHeatmapResponse)
async def get_topic_heatmap(
    hours: int = Query(168, ge=1, le=720, description="Time window in hours"),
    db: AsyncSession = Depends(get_db),
):
    """Topic intensity heatmap across economic, political, security, and social categories.

    For each predefined topic seed query, counts matching content in the time window
    and assigns an intensity level: NONE (0), LOW (1-3), MEDIUM (4-9),
    HIGH (10-19), CRITICAL (20+).
    """
    try:
        service = SIGINTService(db)
        heatmap = await service.topic_intensity_heatmap(hours=hours)
    except Exception as exc:
        logger.exception("Topic heatmap generation failed: %s", exc)
        raise HTTPException(
            status_code=500, detail=f"Topic heatmap generation failed: {exc}"
        )

    return TopicHeatmapResponse(
        categories=[_heatmap_category_to_schema(h) for h in heatmap],
        period_hours=hours,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


# ============================================================
# Triage: interpreted signal intelligence from local Haiku agent
# ============================================================


class TriageInterpretation(BaseModel):
    signal_title: str
    signal_type: str  # economic, security
    severity: str  # HIGH, CRITICAL
    interpretation: str
    source_count: int = 0
    generated_at: datetime


class TriageIngestRequest(BaseModel):
    interpretations: list[TriageInterpretation] = []


class TriageIngestResponse(BaseModel):
    ingested: int = 0
    total: int = 0


class TriageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    signal_title: str
    signal_type: str
    severity: str
    interpretation: str
    source_count: int = 0
    generated_at: datetime
    created_at: Optional[datetime] = None


@router.post("/triage", response_model=TriageIngestResponse)
async def ingest_triage(
    payload: TriageIngestRequest,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_dev),
):
    """Ingest SIGINT triage interpretations from local agent (dev role required)."""
    ingested = 0
    for item in payload.interpretations:
        triage = SigintTriage(
            id=uuid4(),
            signal_title=item.signal_title,
            signal_type=item.signal_type,
            severity=item.severity,
            interpretation=item.interpretation,
            source_count=item.source_count,
            generated_at=item.generated_at,
        )
        db.add(triage)
        ingested += 1

    if ingested:
        await db.commit()

    logger.info("SIGINT triage ingest: %d interpretations stored", ingested)
    return TriageIngestResponse(ingested=ingested, total=len(payload.interpretations))


@router.get("/triage", response_model=list[TriageResponse])
async def get_triage(
    hours: int = Query(24, ge=1, le=168),
    db: AsyncSession = Depends(get_db),
):
    """Get recent SIGINT triage interpretations."""
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        result = await db.execute(
            select(SigintTriage)
            .where(SigintTriage.created_at >= cutoff)
            .order_by(SigintTriage.created_at.desc())
            .limit(200)
        )
        items = result.scalars().all()
        return [
            TriageResponse(
                id=str(t.id),
                signal_title=t.signal_title,
                signal_type=t.signal_type,
                severity=t.severity,
                interpretation=t.interpretation,
                source_count=t.source_count,
                generated_at=t.generated_at,
                created_at=t.created_at,
            )
            for t in items
        ]
    except (ProgrammingError, OperationalError):
        logger.warning("sigint_triage table not found — run migration 072")
        return []
