"""Source health endpoints — which configured feeds are actually delivering data."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.services.source_health_service import SourceHealthService

router = APIRouter(prefix="/source-health", tags=["source-health"])


@router.get("")
async def get_source_health(db: AsyncSession = Depends(get_db)):
    """Full per-source health report.

    Status is derived from the data each source has actually written, so a broken
    scraper cannot report itself healthy.
    """
    service = SourceHealthService(db)
    return await service.get_report()


@router.get("/summary")
async def get_source_health_summary(db: AsyncSession = Depends(get_db)):
    """Counts plus the worst offenders — cheap enough to poll from a dashboard."""
    service = SourceHealthService(db)
    report = await service.get_report()
    return {
        "generated_at": report["generated_at"],
        "summary": report["summary"],
        "by_kind": report["by_kind"],
        "top_problems": report["problems"][:15],
    }
