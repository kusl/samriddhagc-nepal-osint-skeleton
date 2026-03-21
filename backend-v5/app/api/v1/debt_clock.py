"""Debt clock API endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import require_dev
from app.core.redis import get_redis
from app.services.debt_clock_service import DebtClockService

router = APIRouter(prefix="/debt-clock", tags=["Debt Clock"])


class DebtClockSummaryResponse(BaseModel):
    country: str
    flag: str
    currency_code: str
    source_label: str
    updated_at: str
    updated_label: str
    snapshot_year: Optional[int] = None
    debt_now_npr: float
    debt_now_usd: float
    debt_nominal_npr: float
    debt_nominal_usd: float
    debt_gdp_pct: float
    gdp_nominal_npr: float
    gdp_nominal_usd: float
    population: int
    population_year: Optional[int] = None
    interest_per_year_npr: float
    interest_per_year_usd: float
    flow_per_second_npr: float
    flow_per_second_usd: float
    debt_per_citizen_npr: float
    debt_per_citizen_usd: float
    inflation_pct: Optional[float] = None
    inflation_year: Optional[int] = None
    gdp_growth_pct: Optional[float] = None
    gdp_growth_year: Optional[int] = None
    unemployment_pct: Optional[float] = None
    unemployment_year: Optional[int] = None
    budget_balance_pct: Optional[float] = None
    budget_balance_year: Optional[int] = None
    debt_as_of_label: Optional[str] = None
    debt_ratio_label: Optional[str] = None
    gdp_nominal_label: Optional[str] = None
    population_label: Optional[str] = None
    interest_label: Optional[str] = None
    inflation_label: Optional[str] = None
    growth_label: Optional[str] = None
    budget_balance_label: Optional[str] = None
    unemployment_label: Optional[str] = None
    methodology_note: Optional[str] = None
    domestic_debt_npr: Optional[float] = None
    external_debt_npr: Optional[float] = None
    fx_usd_per_lcy: float
    fetched_at: str


@router.get("/nepal", response_model=DebtClockSummaryResponse)
async def get_nepal_debt_clock() -> DebtClockSummaryResponse:
    """Get the live Nepal debt clock summary."""
    redis = await get_redis()
    service = DebtClockService(redis)
    try:
        summary = await service.get_nepal_summary()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Debt clock data unavailable") from exc
    return DebtClockSummaryResponse(**summary)


@router.post("/refresh", response_model=DebtClockSummaryResponse, dependencies=[Depends(require_dev)])
async def refresh_nepal_debt_clock() -> DebtClockSummaryResponse:
    """Force-refresh Nepal debt clock data."""
    redis = await get_redis()
    service = DebtClockService(redis)
    try:
        summary = await service.get_nepal_summary(force_refresh=True)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Debt clock refresh failed") from exc
    return DebtClockSummaryResponse(**summary)
