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


def _km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    import math
    p = math.pi / 180
    a = 0.5 - math.cos((lat2 - lat1) * p) / 2 + math.cos(lat1 * p) * math.cos(lat2 * p) * (1 - math.cos((lng2 - lng1) * p)) / 2
    return 12742 * math.asin(math.sqrt(a))


_COMPAT = {
    "burial": {"burial"}, "recovery": {"recovery", "collection", "transfer", "burial"}, "forensic": {"forensic", "mortuary", "burial"},
    "mortuary": {"mortuary", "forensic", "collection", "burial"}, "transfer": {"transfer", "collection"},
}


def _compatible(site_kind: str, fact_type: str) -> bool:
    return site_kind in _COMPAT.get(fact_type, set())


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
    alias_of = {s["key"]: [a for a in (s.get("aliases") or []) if len(a) >= 4] for s in base}
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

    # AUTO layer: facts the extractor read from the press, placed. A fact within
    # 3 km of a seed site of a compatible kind becomes an auto figure on that
    # site; anything else becomes its own auto site, marked unreviewed.
    auto_sites: list[dict[str, Any]] = []
    try:
        from app.services import flood_fact_extractor as fx
        all_facts = await fx.facts(db, days=21)
        # Road facts rarely geocode (a cut is a stretch, not a point): they attach
        # to the road_cut seed whose alias the sentence names, as auto notes.
        for f in all_facts:
            if f["fact_type"] != "road":
                continue
            low = f["quote"].lower()
            for site in base:
                if site["kind"] == "road_cut" and any(a.lower() in low for a in alias_of.get(site["key"], [])):
                    if any(n.get("fact_id") == f["id"] for n in site["notes"]):
                        break
                    site["notes"].append({"t_npt": f["published_at"] or "", "text": f["quote"][:300],
                                          "source": f"{f['outlet'] or 'press'} (auto-extracted) · {f['unit']}",
                                          "url": f["url"], "auto": True, "fact_id": f["id"]})
                    site["auto_figures"] = site.get("auto_figures", 0) + 1
                    break
        fs = [f for f in all_facts
              if f["fact_type"] in ("burial", "recovery", "forensic", "mortuary", "transfer") and f["lat"] is not None]
        for f in fs:
            verified = f["status"] == "verified"
            fig = {"kind": f["fact_type"] if f["unit"] != "identified" else "identified", "value": f["figure"],
                   "as_of": (f["published_at"] or "")[:10],
                   "source": f"{f['outlet'] or 'press'} ({'verified by the desk' if verified else 'auto-extracted'})",
                   "url": f["url"], "note": f["quote"][:240], "auto": not verified, "confidence": f["confidence"], "fact_id": f["id"]}
            host = None
            for site in base:
                if _km(site["lat"], site["lng"], f["lat"], f["lng"]) <= 3.0 and _compatible(site["kind"], f["fact_type"]):
                    host = site
                    break
            if host is not None:
                if not any(x.get("fact_id") == f["id"] for x in host["figures"]):
                    host["figures"].append(fig)
                    host["auto_figures"] = host.get("auto_figures", 0) + 1
                continue
            key = f"auto_{f['id'][:8]}"
            existing = next((a for a in auto_sites if _km(a["lat"], a["lng"], f["lat"], f["lng"]) <= 1.0 and a["kind"] == f["fact_type"]), None)
            if existing:
                existing["figures"].append(fig)
                continue
            auto_sites.append({
                "key": key, "kind": f["fact_type"], "name": f"{f['place_text']} · {'verified' if verified else 'auto-extracted'}",
                "district": f["district"], "lat": f["lat"], "lng": f["lng"],
                "coord_confidence": "verified" if verified else "auto", "figures": [fig], "notes": [], "photos": [],
                "evidence": [{"title": f["quote"][:160], "outlet": f["outlet"], "url": f["url"], "published_at": f["published_at"]}],
                "auto": not verified, "extractor": f["extractor"], "status": f["status"],
            })
    except Exception as e:  # noqa: BLE001
        logger.warning("sites: auto fact layer failed: %s", e)

    for s in base:
        s["notes"] = sorted(s["notes"], key=lambda n: n.get("t_npt") or "", reverse=True)[:8]
    all_sites = base + tunnels + auto_sites
    kinds = truth.get("kinds", {})
    kinds.update({
        "auto": "Auto-extracted from a press sentence by the desk's extractor; unreviewed",
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
            "auto_sites": len(auto_sites),
            "auto_figures": sum(s.get("auto_figures", 0) for s in base) + sum(len(a["figures"]) for a in auto_sites),
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
