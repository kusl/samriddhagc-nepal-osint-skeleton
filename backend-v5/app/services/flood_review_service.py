"""
VERIFICATION DESK — the analyst's queue over the extractor's facts.

Every auto fact is shown with its sentence, its reading (type, figure, place)
and the seed sites near it; the analyst confirms, corrects-and-confirms, or
rejects with a reason. The row keeps the extracted reading in `original` so
the trail shows what the machine said and what the analyst changed. Verified
facts feed the boards as verified rows; rejected readings stop the extractor
from storing the same reading again.
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import func, select, text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.flood_event import FloodFact

logger = logging.getLogger(__name__)

REJECT_REASONS = {
    "dateline": "Place is the dateline, not where it happened",
    "national_toll": "A national running total, not a site figure",
    "wrong_place": "Wrong place",
    "wrong_figure": "Wrong figure",
    "duplicate": "Duplicate of a fact already on the board",
    "not_this_event": "Not about this event",
    "other": "Other",
}


def _km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    p = math.pi / 180
    a = 0.5 - math.cos((lat2 - lat1) * p) / 2 + math.cos(lat1 * p) * math.cos(lat2 * p) * (1 - math.cos((lng2 - lng1) * p)) / 2
    return 12742 * math.asin(math.sqrt(a))


def _row(r: FloodFact) -> dict[str, Any]:
    return {
        "id": str(r.id), "fact_type": r.fact_type, "subject": r.subject, "subject_code": r.subject_code,
        "place_text": r.place_text, "district": r.district, "lat": r.place_lat, "lng": r.place_lng,
        "place_confidence": r.place_confidence, "figure": r.figure, "unit": r.unit, "quote": r.quote,
        "language": r.language, "outlet": r.outlet, "url": r.story_url,
        "published_at": r.published_at.isoformat() if r.published_at else None,
        "extractor": r.extractor, "confidence": r.confidence, "status": r.status,
        "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None, "reviewer": r.reviewer,
        "review_note": r.review_note, "review_reason": r.review_reason, "original": r.original,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


async def _seed_sites() -> list[dict[str, Any]]:
    try:
        from app.services import flood_sites_service
        t = flood_sites_service.load_truth()
        return [{"key": s["key"], "name": s["name"], "kind": s["kind"], "lat": s["lat"], "lng": s["lng"]} for s in t.get("sites", [])]
    except Exception:  # noqa: BLE001
        return []


async def queue(db: AsyncSession, event_key: str, status: str = "auto", limit: int = 60,
                fact_type: Optional[str] = None) -> dict[str, Any]:
    stmt = select(FloodFact).where(FloodFact.event_key == event_key, FloodFact.status == status)
    if fact_type:
        stmt = stmt.where(FloodFact.fact_type == fact_type)
    # Placed site facts first (they change the map), then by confidence, newest last.
    stmt = stmt.order_by(
        (FloodFact.fact_type == "toll").asc(),
        FloodFact.place_lat.is_(None).asc(),
        FloodFact.confidence.desc(),
        FloodFact.created_at.desc(),
    ).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()
    seeds = await _seed_sites()
    story_titles: dict[str, str] = {}
    urls = [r.story_url for r in rows if r.story_url]
    if urls:
        res = await db.execute(sql_text("SELECT url, title FROM stories WHERE url = ANY(:urls)"), {"urls": urls})
        story_titles = {u: t for u, t in res.all()}
    items = []
    for r in rows:
        d = _row(r)
        d["story_title"] = story_titles.get(r.story_url or "")
        d["nearby_seeds"] = (
            sorted(
                ({**s, "km": round(_km(r.place_lat, r.place_lng, s["lat"], s["lng"]), 1)} for s in seeds),
                key=lambda s: s["km"],
            )[:3]
            if r.place_lat is not None else []
        )
        items.append(d)
    counts = dict((await db.execute(
        select(FloodFact.status, func.count()).where(FloodFact.event_key == event_key).group_by(FloodFact.status)
    )).all())
    return {"count": len(items), "items": items, "counts": {k: int(v) for k, v in counts.items()},
            "reject_reasons": REJECT_REASONS}


async def decide(db: AsyncSession, fact_id: UUID, action: str, reviewer: str,
                 note: Optional[str] = None, reason: Optional[str] = None,
                 corrections: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    r = await db.get(FloodFact, fact_id)
    if r is None:
        raise KeyError("fact not found")
    if action not in ("verify", "reject", "reopen"):
        raise ValueError("action must be verify, reject or reopen")
    if r.original is None:
        r.original = {"fact_type": r.fact_type, "figure": r.figure, "unit": r.unit, "place_text": r.place_text,
                      "lat": r.place_lat, "lng": r.place_lng, "subject_code": r.subject_code}
    if action == "verify":
        c = corrections or {}
        if c.get("fact_type"):
            r.fact_type = str(c["fact_type"])[:24]
        if "figure" in c and c["figure"] is not None:
            r.figure = float(c["figure"])
        if c.get("unit"):
            r.unit = str(c["unit"])[:24]
        if c.get("place_text"):
            r.place_text = str(c["place_text"])[:200]
        if isinstance(c.get("lat"), (int, float)) and isinstance(c.get("lng"), (int, float)):
            r.place_lat, r.place_lng = float(c["lat"]), float(c["lng"])
            r.place_confidence = "analyst"
        if c.get("subject_code"):
            r.subject_code = str(c["subject_code"])[:32]
        r.status = "verified"
        r.confidence = 1.0
    elif action == "reject":
        r.status = "rejected"
        r.review_reason = reason if reason in REJECT_REASONS else "other"
    else:
        r.status = "auto"
        r.review_reason = None
    r.reviewed_at = datetime.now(timezone.utc)
    r.reviewer = reviewer
    r.review_note = (note or "")[:500] or None
    await db.commit()
    # The boards cache five minutes; a decision should show at once.
    for mod in ("flood_sites_service", "flood_assistance_service", "flood_hydropower_service"):
        try:
            m = __import__(f"app.services.{mod}", fromlist=["_cache"])
            with m._lock:
                m._cache["payload"] = None
        except Exception:  # noqa: BLE001
            pass
    return _row(r)


async def stats(db: AsyncSession, event_key: str) -> dict[str, Any]:
    since = datetime.now(timezone.utc) - timedelta(days=1)
    rows = (await db.execute(
        select(FloodFact.status, func.count()).where(FloodFact.event_key == event_key).group_by(FloodFact.status)
    )).all()
    new24 = (await db.execute(
        select(func.count()).where(FloodFact.event_key == event_key, FloodFact.created_at > since)
    )).scalar() or 0
    reviewed24 = (await db.execute(
        select(func.count()).where(FloodFact.event_key == event_key, FloodFact.reviewed_at > since)
    )).scalar() or 0
    return {"counts": {k: int(v) for k, v in rows}, "new_24h": int(new24), "reviewed_24h": int(reviewed24)}
