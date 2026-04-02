"""Public cabinet 100-day action tracker endpoints."""
from __future__ import annotations

import json
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.redis import get_redis
from app.services.cabinet_action_service import CabinetActionService

router = APIRouter(prefix="/cabinet-actions", tags=["Cabinet Actions"])


@router.get("/summary")
async def get_cabinet_action_summary(
    db: AsyncSession = Depends(get_db),
):
    redis = await get_redis()
    cache_key = "cabinet-actions:summary:v1"
    try:
        cached = await redis.get(cache_key)
        if cached:
            return json.loads(cached)
    except Exception:
        pass

    payload = await CabinetActionService(db).list_public_summary()

    try:
        await redis.set(cache_key, json.dumps(jsonable_encoder(payload)), ex=120)
    except Exception:
        pass

    return payload


@router.get("/items")
async def list_cabinet_action_items(
    limit: int = Query(default=100, ge=1, le=500),
    section_key: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    lead_institution: Optional[str] = Query(default=None),
    trackability_class: Optional[str] = Query(default=None),
    due_bucket: Optional[str] = Query(default=None, pattern="^(due_soon|overdue)?$"),
    db: AsyncSession = Depends(get_db),
):
    redis = await get_redis()
    cache_key = json.dumps(
        {
            "route": "cabinet-actions:items:v1",
            "limit": limit,
            "section_key": section_key,
            "status": status,
            "lead_institution": lead_institution,
            "trackability_class": trackability_class,
            "due_bucket": due_bucket,
        },
        sort_keys=True,
    )

    try:
        cached = await redis.get(cache_key)
        if cached:
            return json.loads(cached)
    except Exception:
        pass

    items = await CabinetActionService(db).list_public(
        limit=limit,
        section_key=section_key,
        status=status,
        lead_institution=lead_institution,
        trackability_class=trackability_class,
        due_bucket=due_bucket,
    )
    payload = {"items": items}

    try:
        await redis.set(cache_key, json.dumps(jsonable_encoder(payload)), ex=120)
    except Exception:
        pass

    return payload


@router.get("/items/{item_id}")
async def get_cabinet_action_item_detail(
    item_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    return await CabinetActionService(db).get_public_item(item_id)


@router.get("/manifesto/{promise_code}")
async def get_cabinet_actions_for_manifesto_promise(
    promise_code: str,
    db: AsyncSession = Depends(get_db),
):
    return {"items": await CabinetActionService(db).list_by_manifesto_promise(promise_code)}
