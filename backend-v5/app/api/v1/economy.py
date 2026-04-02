"""Economy snapshot endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import require_dev
from app.core.redis import get_redis
from app.services.economy_snapshot_service import EconomySnapshotService

router = APIRouter(prefix="/economy", tags=["Economy"])


class EconomyMetricResponse(BaseModel):
    key: str
    label: str
    unit: str
    raw_value: Optional[float] = None
    display_value: str
    meta: str
    source_label: Optional[str] = None


class EconomySectionResponse(BaseModel):
    key: str
    label: str
    badge: str
    as_of_label: str
    metrics: list[EconomyMetricResponse]


class EconomySnapshotResponse(BaseModel):
    source_label: str
    workbook_label: str
    workbook_period_label: str
    as_of_label: str
    extracted_at: str
    sections: dict[str, EconomySectionResponse]


@router.get("/nrb-snapshot", response_model=EconomySnapshotResponse)
async def get_nrb_snapshot() -> EconomySnapshotResponse:
    redis = await get_redis()
    service = EconomySnapshotService(redis)
    try:
        payload = await service.get_snapshot()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Economy snapshot unavailable") from exc
    return EconomySnapshotResponse(**payload)


@router.post("/refresh", response_model=EconomySnapshotResponse, dependencies=[Depends(require_dev)])
async def refresh_nrb_snapshot() -> EconomySnapshotResponse:
    redis = await get_redis()
    service = EconomySnapshotService(redis)
    try:
        payload = await service.get_snapshot(force_refresh=True)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Economy snapshot refresh failed") from exc
    return EconomySnapshotResponse(**payload)

