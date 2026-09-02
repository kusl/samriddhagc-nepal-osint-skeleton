"""
RESPONSE SITES — the points on the impact map that are not districts or river:
burial grounds, DNA hubs, mortuaries, body-transfer points, recovery reaches,
the highway cut, the airhead, and the flooded tunnels.

Layers, kept apart in the payload:
1. Truth file `app/data/flood_sites_trishuli_2026.json` — every figure and note
   with the document it was read from; coordinates carry a confidence word.
2. Tunnels — the hydropower ledger's projects (its own truth file + the MoFA
   briefing), so a tunnel's status here is the same one the ledger shows.
3. Photographs — the event's media items (OPMCM / NDRRMA photographs at tier
   `display`, press leads at tier `link_preview`) matched to a site by its
   `photo_terms`; a match is a caption match, never a geotag, and says so.
4. Press evidence — story titles matching the site's aliases, newest first.
"""
from __future__ import annotations

import logging
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.flood_event import FloodMediaItem
from app.services import flood_hydropower_service as hydro

logger = logging.getLogger(__name__)

TRUTH_PATH = (Path(__file__).resolve().parent.parent
              / "data" / "flood_sites_trishuli_2026.json")

_CACHE_TTL_S = 300
_cache: dict[str, Any] = {"at": 0.0, "payload": None}
_lock = threading.Lock()

STATUS_TO_TUNNEL_KIND = {"active": "tunnel_active", "suspended": "tunnel_suspended", "unreported": "tunnel_unreported"}


def load_truth() -> dict[str, Any]:
    import json
    with TRUTH_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def _photo_row(row: FloodMediaItem) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "title": row.title,
        "title_ne": row.title_ne,
        "credit": row.credit,
        "outlet": row.outlet,
        "page_url": row.page_url,
        "image_url": f"/api/v1/flood/photos/{row.id}/image",
        "licence_tier": row.licence_tier,
        "published_at": row.published_at.isoformat() if row.published_at else None,
        "match": "caption",
    }


async def _photos_by_terms(db: AsyncSession, event: str,
                           sites: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    rows = list((await db.execute(
        select(FloodMediaItem)
        .where(FloodMediaItem.event_key == event, FloodMediaItem.is_active.is_(True))
    )).scalars().all())
    out: dict[str, list[dict[str, Any]]] = {}
    for s in sites:
        terms = [t.lower() for t in (s.get("photo_terms") or []) if len(t) >= 4]
        if not terms:
            continue
        hits = []
        for r in rows:
            blob = " ".join(x for x in (r.title, r.title_ne, r.caption) if x).lower()
            if any(t in blob for t in terms):
                hits.append(r)
        # Government photographs first (display tier), then press leads newest first.
        hits.sort(key=lambda r: (r.licence_tier != "display",
                                 -(r.published_at.timestamp() if r.published_at else 0)))
        out[s["key"]] = [_photo_row(r) for r in hits[:6]]
    return out


async def _evidence(sites: list[dict[str, Any]], days: int = 10) -> dict[str, list[dict[str, Any]]]:
    try:
        from sqlalchemy import text as sql_text
        from app.core.database import AsyncSessionLocal
    except Exception as e:  # noqa: BLE001
        logger.warning("sites evidence unavailable: %s", e)
        return {}
    aliases = {s["key"]: [a for a in (s.get("aliases") or []) if len(a) >= 4] for s in sites}
    all_terms = sorted({a for v in aliases.values() for a in v}, key=len, reverse=True)
    if not all_terms:
        return {}
    pattern = "|".join(re.escape(a) for a in all_terms)
    q = sql_text(
        "SELECT title, source_name, url, published_at FROM stories "
        "WHERE published_at > now() - make_interval(days => :days) AND title ~* :pat "
        "ORDER BY published_at DESC LIMIT 300"
    )
    try:
        async with AsyncSessionLocal() as db:
            rows = (await db.execute(q, {"days": days, "pat": pattern})).all()
    except Exception as e:  # noqa: BLE001
        logger.warning("sites evidence query failed: %s", e)
        return {}
    out: dict[str, list[dict[str, Any]]] = {}
    for title, outlet, url, published_at in rows:
        low = (title or "").lower()
        for key, names in aliases.items():
            if any(a.lower() in low for a in names):
                out.setdefault(key, []).append({
                    "title": title, "outlet": outlet, "url": url,
                    "published_at": published_at.isoformat() if isinstance(published_at, datetime) else published_at,
                })
    return {k: v[:6] for k, v in out.items()}


def _tunnel_sites(hp: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for p in hp.get("projects", []):
        if not isinstance(p.get("lat"), (int, float)):
            continue
        teams = [t.get("country") for t in p.get("teams", []) if t.get("country")]
        figures = [f for f in p.get("figures", []) if f.get("kind") in ("missing", "rescued", "believed_trapped")]
        out.append({
            "key": f"tunnel_{p['key']}",
            "kind": STATUS_TO_TUNNEL_KIND.get(p.get("status"), "tunnel_unreported"),
            "name": f"{p['name']} · {p.get('capacity_mw') or '—'} MW tunnel",
            "district": p.get("district"),
            "lat": p["lat"], "lng": p["lng"],
            "coord_confidence": p.get("coord_confidence", "approximate"),
            "km": p.get("km"),
            "status": p.get("status"),
            "status_line": p.get("status_line"),
            "status_source": p.get("status_source"),
            "teams": teams,
            "figures": figures,
            "notes": (p.get("notes") or [])[:3],
            "photos": [],
            "evidence": (p.get("evidence") or [])[:4],
            "auto": True,
            "source_board": "tunnel_ledger",
        })
    return out


async def sites(db: AsyncSession, event: str) -> dict[str, Any]:
    now = time.monotonic()
    with _lock:
        if _cache["payload"] is not None and now - _cache["at"] < _CACHE_TTL_S:
            return _cache["payload"]

    truth = load_truth()
    base = [dict(s) for s in truth.get("sites", [])]
    photos = await _photos_by_terms(db, event, base)
    evidence = await _evidence(base)
    for s in base:
        s["photos"] = photos.get(s["key"], [])
        s["evidence"] = evidence.get(s["key"], [])
        s["notes"] = sorted(s.get("notes") or [], key=lambda n: n.get("t_npt") or "", reverse=True)
        s["auto"] = False
        s.pop("photo_terms", None)
        s.pop("aliases", None)

    tunnels: list[dict[str, Any]] = []
    try:
        hp = await hydro.hydropower()
        tunnels = _tunnel_sites(hp)
    except Exception as e:  # noqa: BLE001
        logger.warning("sites: tunnel layer failed: %s", e)

    all_sites = base + tunnels
    kinds = truth.get("kinds", {})
    kinds.update({
        "tunnel_active": "Flooded hydropower tunnel with a team digging",
        "tunnel_suspended": "Flooded tunnel where the search is suspended",
        "tunnel_unreported": "Affected hydropower project with no tunnel figures published",
    })
    payload = {
        "event_key": event,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "truth_verified_on": truth.get("verified_on"),
        "kinds": kinds,
        "sites": all_sites,
        "counts": {
            "sites": len(all_sites),
            "burial": sum(1 for s in all_sites if s["kind"] == "burial"),
            "with_photos": sum(1 for s in all_sites if s.get("photos")),
            "photos": sum(len(s.get("photos") or []) for s in all_sites),
            "tunnels": len(tunnels),
            "buried_published": sum(
                f["value"] for s in all_sites if s["kind"] == "burial"
                for f in s.get("figures", []) if f.get("kind") == "buried"),
        },
        "note": truth.get("note"),
    }
    with _lock:
        _cache["at"] = now
        _cache["payload"] = payload
    return payload
