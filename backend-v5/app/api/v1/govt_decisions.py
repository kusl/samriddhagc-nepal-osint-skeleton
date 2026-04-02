"""Public government decisions feed."""
import json

from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.redis import get_redis
from app.services.govt_decision_service import GovtDecisionService

router = APIRouter(prefix="/govt-decisions", tags=["Government Decisions"])


@router.get("/latest")
async def get_latest_govt_decisions(
    limit: int = Query(default=25, ge=1, le=500),
    cursor: str | None = Query(default=None),
    dedupe: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
):
    redis = await get_redis()
    cache_key = json.dumps(
        {
            "route": "govt-decisions:latest:v1",
            "limit": limit,
            "cursor": cursor,
            "dedupe": dedupe,
        },
        sort_keys=True,
    )

    try:
        cached = await redis.get(cache_key)
        if cached:
            return json.loads(cached)
    except Exception:
        pass

    service = GovtDecisionService(db)
    payload = await service.list_public(limit=limit, cursor=cursor, dedupe=dedupe)

    try:
        await redis.set(cache_key, json.dumps(jsonable_encoder(payload)), ex=300)
    except Exception:
        pass

    return payload
