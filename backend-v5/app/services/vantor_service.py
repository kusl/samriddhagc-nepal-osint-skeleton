"""Vantor (formerly Maxar) Open Data scene index for the active flood event.

Sits beside FloodIntelService, which catalogues imagery *products* published by
someone else and read at their publisher, and beside /flood/media, which serves
openly-licensed ground photography from Commons. This is the third case: a
commercial 30-50 cm archive released under CC BY-NC 4.0 for this event, so the
pixels themselves are ours to put on screen — and the licence, the acquisition
date and the cloud figure are obligations that travel with every one of them.

The collection is read live from its STAC endpoint so scenes tasked after this
code shipped appear without a redeploy; the hand-verified manifest of 1 Sep 2026
is the floor when S3 is unreachable, exactly as the Commons seed is for media.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urljoin

import httpx

logger = logging.getLogger(__name__)

COLLECTION_URL = ("https://vantor-opendata.s3.amazonaws.com/events/"
                  "Nepal-Flooding-Aug-2026/collection.json")
COLLECTION_ID = "Nepal-Flooding-Aug-2026"
ATTRIBUTION = "Vantor Open Data (formerly Maxar Open Data), CC BY-NC 4.0"
LICENSE = "CC-BY-NC-4.0"
LICENSE_URL = "https://creativecommons.org/licenses/by-nc/4.0/"

# The surge entered the Bhote Koshi at 09:15 local on 26 August; a scene from
# that day or later saw the ground after it. Nothing in the collection was taken
# on the day itself, so the boundary never has to arbitrate hours.
EVENT_DATE = date(2026, 8, 26)

_UA = "NepalOSINT-FloodDesk/1.0 (nepalosint.com; contact via site)"
_TIMEOUT = 8.0
_TTL_SECONDS = 3600
# A listing from earlier today still tells the truth about which scenes exist.
_STALE_GRACE_SECONDS = 86400
# A live fetch that returns almost nothing is a broken fetch, not a shrunken
# collection: half an answer must never shadow the complete verified manifest.
_MIN_LIVE_ITEMS = 4
_ITEM_CONCURRENCY = 8
# Each site is one point standing for a settlement several hundred metres wide,
# so a point that lands just outside a strip edge can still be ground the strip
# shows. The skin is calibrated against the hand-checked coverage lists rather
# than chosen: Rasuwagadhi sits 0.79 km outside one 1 Sep strip and was counted,
# Timure 1.00 km outside one 27 Aug strip and was not. Anything beyond it is a
# claim about ground the scene does not hold, and is not made.
_EDGE_TOLERANCE_KM = 0.9

# Ordered north to south down the corridor, the direction the surge ran, so a
# client paging the sites replays the event geographically. The collapse origin
# is last because it is off the corridor and has no post-event pass.
SITES: list[dict[str, Any]] = [
    {"key": "rasuwagadhi", "name": "Rasuwagadhi / Gyirong Port", "lng": 85.379, "lat": 28.278},
    {"key": "timure", "name": "Timure", "lng": 85.372, "lat": 28.263},
    {"key": "syabrubesi", "name": "Syabrubesi", "lng": 85.348, "lat": 28.160},
    {"key": "betrawati", "name": "Betrawati", "lng": 85.187, "lat": 27.976},
    {"key": "trishuli_bazar", "name": "Trishuli Bazar", "lng": 85.144, "lat": 27.921},
    {"key": "langtang_origin", "name": "Langtang Lirung origin", "lng": 85.517, "lat": 28.256},
]

_SITE_BY_NAME = {s["name"]: s for s in SITES}

NOTE = ("Pre-event scenes are archive baselines from 2021-2024, not event-eve. "
        "Post-event passes carry 71-94% monsoon cloud cover. Thumbnails are "
        "512 px browse strips whose black borders are the rotated footprint "
        "inside an axis-aligned frame, so they are not registered to map "
        "coordinates; the full 30-50 cm product is the COG, which this "
        "deployment has no tile server to serve.")

_MANIFEST_PATH = Path(__file__).resolve().parent.parent / "data" / "vantor_trishuli_manifest.json"
_manifest_cache: Optional[list[dict[str, Any]]] = None

_cache: dict[str, Any] = {"items": None, "fetched_at": 0.0}
_lock = asyncio.Lock()


def _manifest_items() -> list[dict[str, Any]]:
    """The 16 scenes verified by hand on 1 Sep 2026, loaded once."""
    global _manifest_cache
    if _manifest_cache is None:
        raw = json.loads(_MANIFEST_PATH.read_text())
        _manifest_cache = [_finish(dict(item)) for item in raw["items"]]
    return _manifest_cache


def point_in_ring(lng: float, lat: float, ring: list[list[float]]) -> bool:
    """Ray cast against a polygon's outer ring.

    Footprints are rotated strips, so a bbox test would claim coverage for
    ground the sensor never saw at the corners. Ten lines here beats a
    dependency for the only geometry question this module asks.
    """
    inside = False
    count = len(ring)
    for i in range(count):
        x1, y1 = ring[i][0], ring[i][1]
        x2, y2 = ring[(i + 1) % count][0], ring[(i + 1) % count][1]
        if (y1 > lat) != (y2 > lat):
            x_at = x1 + (lat - y1) * (x2 - x1) / (y2 - y1)
            if x_at > lng:
                inside = not inside
    return inside


def km_to_ring(lng: float, lat: float, ring: list[list[float]]) -> float:
    """Shortest distance from a point to the ring, in kilometres.

    Flat-earth projection around the point itself: over a 100 km strip in
    Rasuwa the error is metres, well inside the tolerance it feeds.
    """
    scale_x = 111.32 * math.cos(math.radians(lat))
    best = float("inf")
    for i in range(len(ring)):
        ax = (ring[i][0] - lng) * scale_x
        ay = (ring[i][1] - lat) * 110.57
        nxt = ring[(i + 1) % len(ring)]
        bx = (nxt[0] - lng) * scale_x
        by = (nxt[1] - lat) * 110.57
        dx, dy = bx - ax, by - ay
        span = dx * dx + dy * dy
        t = 0.0 if span == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / span))
        best = min(best, math.hypot(ax + t * dx, ay + t * dy))
    return best


# Public since drp_service asks the same coverage questions of the same
# footprints; the private names stay as aliases so nothing else has to move.
_point_in_ring = point_in_ring
_km_to_ring = km_to_ring


def _covered_sites(geometry: Optional[dict]) -> list[str]:
    """Named sites the footprint sees — how a newly tasked scene self-files."""
    if not geometry or geometry.get("type") != "Polygon":
        return []
    rings = geometry.get("coordinates") or []
    if not rings:
        return []
    outer = [c for c in rings[0] if len(c) >= 2]
    return [s["name"] for s in SITES
            if point_in_ring(s["lng"], s["lat"], outer)
            or km_to_ring(s["lng"], s["lat"], outer) <= _EDGE_TOLERANCE_KM]


def _phase(datetime_str: Optional[str]) -> str:
    if not datetime_str:
        return "pre"
    try:
        taken = datetime.fromisoformat(datetime_str.replace("Z", "+00:00")).date()
    except ValueError:
        return "pre"
    return "post" if taken >= EVENT_DATE else "pre"


def _finish(record: dict[str, Any]) -> dict[str, Any]:
    """Fill the derived fields both the live and the vendored path need."""
    record["phase"] = record.get("phase") or _phase(record.get("datetime"))
    record["covers"] = record.get("covers") or []
    record["covers_keys"] = [_SITE_BY_NAME[n]["key"] for n in record["covers"]
                             if n in _SITE_BY_NAME]
    record.setdefault("license", LICENSE)
    record["attribution"] = ATTRIBUTION
    record.setdefault("item_url", urljoin(COLLECTION_URL, f"{record['id']}.json"))
    return record


async def _fetch_item(client: httpx.AsyncClient, url: str,
                      sem: asyncio.Semaphore) -> Optional[dict[str, Any]]:
    async with sem:
        try:
            response = await client.get(url, headers={"User-Agent": _UA})
            response.raise_for_status()
            item = response.json()
        except Exception as exc:
            # One unreadable item is dropped; the caller decides whether what
            # survived is still a collection worth serving.
            logger.warning("Vantor item %s failed: %s", url, exc)
            return None

    props = item.get("properties") or {}
    assets = item.get("assets") or {}
    visual = (assets.get("visual") or {}).get("href")
    thumbnail = (assets.get("thumbnail") or {}).get("href")
    if not item.get("id") or not visual or not thumbnail:
        logger.warning("Vantor item %s missing id or assets", url)
        return None

    cloud = props.get("eo:cloud_cover")
    geometry = item.get("geometry")
    return _finish({
        "id": item["id"],
        "datetime": props.get("datetime"),
        "cloud": round(cloud) if isinstance(cloud, (int, float)) else None,
        "off_nadir": props.get("view:off_nadir"),
        "azimuth": props.get("view:azimuth"),
        "bbox": item.get("bbox"),
        "geometry": geometry,
        "visual": urljoin(url, visual),
        "thumbnail": urljoin(url, thumbnail),
        "license": props.get("license") or LICENSE,
        "covers": _covered_sites(geometry),
        "item_url": url,
    })


async def _fetch_stac() -> list[dict[str, Any]]:
    """The collection and every item it links, read live.

    Raises when too little came back to be the collection, so the caller falls
    through to cache and then to the vendored manifest.
    """
    async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
        response = await client.get(COLLECTION_URL, headers={"User-Agent": _UA})
        response.raise_for_status()
        collection = response.json()

        links = [urljoin(COLLECTION_URL, link["href"])
                 for link in (collection.get("links") or [])
                 if link.get("rel") == "item" and link.get("href")]
        if not links:
            raise ValueError("Vantor collection listed no item links")

        sem = asyncio.Semaphore(_ITEM_CONCURRENCY)
        fetched = await asyncio.gather(*(_fetch_item(client, url, sem) for url in links))

    items = [item for item in fetched if item]
    if len(items) < _MIN_LIVE_ITEMS:
        raise ValueError(
            f"Vantor STAC returned only {len(items)} usable items of {len(links)}")
    items.sort(key=lambda i: (i.get("datetime") or "", i["id"]))
    return items


async def scenes() -> tuple[list[dict[str, Any]], str, Optional[float]]:
    """Cached scene list, plus where this answer came from and when."""
    async with _lock:
        now = time.time()
        age = now - (_cache["fetched_at"] or 0.0)
        if _cache["items"] is not None and age < _TTL_SECONDS:
            return _cache["items"], "live", _cache["fetched_at"]
        try:
            items = await _fetch_stac()
        except Exception as exc:
            logger.warning("Vantor STAC fetch failed, serving %s: %s",
                           "cache" if _cache["items"] is not None else "manifest", exc)
            if _cache["items"] is not None and age < _STALE_GRACE_SECONDS:
                return _cache["items"], "cache", _cache["fetched_at"]
            return _manifest_items(), "fallback", None
        _cache["items"] = items
        _cache["fetched_at"] = now
        return items, "live", now


def _brief(item: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if not item:
        return None
    return {
        "id": item["id"],
        "datetime": item.get("datetime"),
        "cloud": item.get("cloud"),
        "off_nadir": item.get("off_nadir"),
        "thumbnail": item.get("thumbnail"),
        "visual": item.get("visual"),
        "item_url": item.get("item_url"),
        "covers": item.get("covers"),
    }


def _cloud_key(item: dict[str, Any]) -> float:
    """An unstated cloud figure sorts last rather than as a clear sky."""
    cloud = item.get("cloud")
    return float(cloud) if cloud is not None else 999.0


def compute_pairs(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The best pre/post scene per site.

    POST is the clearest post-event pass, ties broken by the earliest date —
    what the ground looked like soonest after the surge.

    PRE prefers a corridor strip (one covering more than one named site) over a
    single-site strip, then the clearest, then the most recent. The corridor
    preference is load-bearing and not a proxy for quality: Trishuli Bazar has a
    cloud-free 2026-02-05 strip that sees Trishuli Bazar alone, and pairing that
    against a post-event scene of the whole corridor would compare two different
    pieces of ground. Between corridor strips it is cloud that decides, which is
    why Betrawati takes the 2024 strip over the wider 2021 one.
    """
    pairs: list[dict[str, Any]] = []
    for site in SITES:
        seen = [i for i in items if site["name"] in (i.get("covers") or [])]
        post = [i for i in seen if i.get("phase") == "post"]
        pre = [i for i in seen if i.get("phase") == "pre"]

        # min() keeps the first of an equal-lowest set, so pre-sorting by date
        # is how the tie-break is expressed: earliest first for post, latest
        # first for pre.
        by_date = sorted(post, key=lambda i: i.get("datetime") or "")
        best_post = min(by_date, key=_cloud_key) if by_date else None

        corridor = [i for i in pre if len(i.get("covers") or []) > 1]
        candidates = sorted(corridor or pre,
                            key=lambda i: i.get("datetime") or "", reverse=True)
        best_pre = min(candidates, key=_cloud_key) if candidates else None

        pairs.append({
            "key": site["key"],
            "name": site["name"],
            "lat": site["lat"],
            "lng": site["lng"],
            "pre": _brief(best_pre),
            "post": _brief(best_post),
            "scene_count": len(seen),
        })
    return pairs


def payload(items: list[dict[str, Any]], source: str,
            fetched_at: Optional[float]) -> dict[str, Any]:
    return {
        "collection": COLLECTION_ID,
        "collection_url": COLLECTION_URL,
        "license": LICENSE,
        "license_url": LICENSE_URL,
        "attribution": ATTRIBUTION,
        "source": source,
        "stac_fetched_at": (
            datetime.fromtimestamp(fetched_at, tz=timezone.utc).isoformat()
            if fetched_at else None),
        "manifest_verified_on": "2026-09-01",
        "count": len(items),
        "items": items,
        "sites": compute_pairs(items),
        "note": NOTE,
    }
