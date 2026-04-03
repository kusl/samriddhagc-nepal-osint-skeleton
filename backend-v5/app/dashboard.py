"""Dashboard bootstrap endpoint for above-the-fold preset hydration."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.v1.analytics import get_developing_stories
from app.api.v1.cabinet_actions import get_cabinet_action_summary
from app.api.v1.debt_clock import get_nepal_debt_clock
from app.api.v1.economy import get_nrb_snapshot
from app.api.v1.govt_decisions import get_latest_govt_decisions
from app.api.v1.kpi import get_hourly_trends, get_kpi_snapshot
from app.api.v1.market import get_market_summary
from app.api.v1.parliament import list_bills
from app.api.v1.province_anomalies import get_latest_province_anomalies
from app.api.v1.promises import promise_summary
from app.api.v1.verbatim import verbatim_summary
from app.core.redis import get_redis

DashboardPreset = Literal["news", "economy", "parliament", "intelligence"]

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


class DashboardBootstrapResponse(BaseModel):
    preset: DashboardPreset
    generated_at: datetime
    queries: dict[str, Any]


def _bootstrap_cache_key(preset: DashboardPreset) -> str:
    return f"dashboard:bootstrap:{preset}"


@router.get("/bootstrap", response_model=DashboardBootstrapResponse)
async def get_dashboard_bootstrap(
    preset: DashboardPreset = Query(default="news"),
    db: AsyncSession = Depends(get_db),
):
    """Return the minimal above-the-fold dataset for the selected preset."""
    redis = await get_redis()
    cache_key = _bootstrap_cache_key(preset)

    try:
        cached = await redis.get(cache_key)
        if cached:
            return DashboardBootstrapResponse.model_validate_json(cached)
    except Exception:
        cached = None

    queries: dict[str, Any] = {}

    if preset in {"news", "intelligence"}:
        queries["kpi_snapshot_24h"] = await get_kpi_snapshot(hours=24, districts=None, force_refresh=False, db=db)
        queries["kpi_hourly_trends_24h"] = await get_hourly_trends(hours=24, districts=None, db=db)
        queries["developing_stories"] = await get_developing_stories(hours=72, limit=15, category=None, refresh=False, db=db)
        queries["province_anomalies_latest"] = await get_latest_province_anomalies(db=db)

    if preset == "economy":
        queries["market_summary"] = await get_market_summary(db=db)
        queries["debt_clock_nepal"] = await get_nepal_debt_clock()
        queries["economy_snapshot"] = await get_nrb_snapshot()

    if preset == "parliament":
        queries["govt_decisions_latest"] = await get_latest_govt_decisions(limit=25, cursor=None, dedupe=False, db=db)
        queries["cabinet_actions_summary"] = await get_cabinet_action_summary(db=db)
        queries["promises_summary_rsp_2082"] = await promise_summary(party="RSP", election_year="2082", db=db)
        queries["parliament_bills_page_1"] = await list_bills(
            status=None,
            bill_type=None,
            chamber=None,
            page=1,
            per_page=50,
            db=db,
        )
        queries["verbatim_summary"] = await verbatim_summary(db=db)

    response = DashboardBootstrapResponse(
        preset=preset,
        generated_at=datetime.now(timezone.utc),
        queries=queries,
    )

    try:
        await redis.set(cache_key, response.model_dump_json(), ex=60)
    except Exception:
        pass

    return response
