"""Esri Disaster Response Program image service, framed onto the damage sites.

vantor_service indexes the event's 16 scenes as STAC metadata — footprints,
acquisition datetimes, cloud figures — but this deployment has no tile server,
so the only pixels it could put on screen were 512 px browse strips that are
not registered to map coordinates. Esri's DRP ImageServer holds those same 16
rasters and exposes exportImage, which renders any bbox at native resolution.
The two halves fit: Esri renders, our STAC says what was rendered.

The DRP catalog is used for exactly one thing beyond naming the holdings —
lowps, the service's own lowest pixel size, which is the field the mosaic rule
sorts on and therefore decides which raster lands on top of a frame. Coverage
is computed here from our own footprints, never from the service: /query
returns all 16 rows for every geometry filter tried on 2026-09-01, so asking it
"what covers this point" gets an answer that is not about the point.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlencode

import httpx

from app.services.vantor_service import (ATTRIBUTION as STAC_ATTRIBUTION,
                                         LICENSE, LICENSE_URL, SITES,
                                         km_to_ring, point_in_ring, scenes)

logger = logging.getLogger(__name__)

DRP_URL = ("https://di-disasterresponse.img.arcgis.com/arcgis/rest/services/"
           "drp_imagery/ImageServer")
DRP_EVENT = "Nepal-Flooding-Aug-2026"
ATTRIBUTION = ("Satellite imagery © 2026 Vantor (formerly Maxar), Open Data "
               "program · served via Esri Disaster Response Program · CC BY-NC 4.0")

_UA = "NepalOSINT-FloodDesk/1.0 (nepalosint.com; contact via site)"
_TIMEOUT = 8.0
_TTL_SECONDS = 3600
_STALE_GRACE_SECONDS = 86400
# A catalog that came back short is a broken read, not a shrunken holding.
_MIN_LIVE_RASTERS = 8

# Rendered frame, 5:3. 1600 px wide is well under the service's 5000 px cap and
# is more pixels than any pane on the desk has, so the comparator is never
# upscaling.
EXPORT_W = 1600
EXPORT_H = 960
_ASPECT = EXPORT_H / EXPORT_W

# Ground width in metres per zoom level. Named rather than numbered so a client
# can label the buttons without knowing the metres.
_LEVEL_ORDER = ["context", "site", "detail"]

# Curated frames only. Every one of these has had its coverage, top raster,
# acquisition date and cloud figure computed before it reaches a screen; a
# freely panned frame would carry a caption nobody verified.
_FRAMES: dict[str, dict[str, int]] = {
    "rasuwagadhi": {"detail": 600, "site": 1200, "context": 3000},
    "timure": {"detail": 600, "site": 1200, "context": 3000},
    "syabrubesi": {"detail": 800, "site": 1800, "context": 4000},
    "betrawati": {"site": 1500, "context": 4000},
    "trishuli_bazar": {"site": 1500, "context": 4000},
    # No frames: the collapse origin sits east of every post-event footprint, so
    # a comparator here would be a before against a blank.
    "langtang_origin": {},
}

# Corridor kilometre marks and the one-line finding, both from the event record
# the desk already serves at /flood/districts/geo. Sites the record places but
# makes no damage claim about carry finding None rather than a filled-in one.
_SITE_RECORD: dict[str, dict[str, Any]] = {
    "rasuwagadhi": {"km_mark": 0, "finding": "Border post destroyed"},
    "timure": {"km_mark": 2, "finding": None},
    "syabrubesi": {
        "km_mark": 16,
        "finding": "240+ buildings destroyed",
        "finding_source": ("Copernicus EMS EMSR927, WorldView-3 "
                           "27 Aug 2026 05:05 UTC"),
    },
    "betrawati": {"km_mark": 45, "finding": None},
    "trishuli_bazar": {"km_mark": 53, "finding": None},
    "langtang_origin": {
        "km_mark": None,
        "finding": "Collapse origin — no published post-event pass",
    },
}

# Downstream of Trishuli Bazar the event record names Galchhi, Devghat and
# Narayanghat, and 639 workers are missing across 12 hydropower projects. None
# of them get a site here: Vantor imaged none of that ground, and no verified
# coordinate for any of the named projects exists in the record. A frame we
# cannot fill and a pin we cannot place are both worse than an absence.

_CATALOG_PATH = Path(__file__).resolve().parent.parent / "data" / "drp_catalog.json"
_catalog_fallback: Optional[list[dict[str, Any]]] = None

_cache: dict[str, Any] = {"rasters": None, "fetched_at": 0.0}
_lock = asyncio.Lock()


def _parse_raster(attrs: dict[str, Any]) -> Optional[dict[str, Any]]:
    """One catalog row, keyed to the STAC id the desk already indexes.

    `name` is NepalFloodingAug2026_<STAC id>_<YYYYMMDD>; the middle token is the
    join. The trailing date is not read as an acquisition date — the STAC item
    carries the acquisition instant, to the second, and is the authority for it.
    """
    name = attrs.get("name") or ""
    parts = name.split("_")
    if len(parts) < 3:
        logger.warning("DRP raster name not in the expected shape: %r", name)
        return None
    lowps = attrs.get("lowps")
    if not isinstance(lowps, (int, float)):
        return None
    return {
        "objectid": attrs.get("objectid"),
        "name": name,
        "stac_id": parts[1],
        "image_type": attrs.get("image_type"),
        "gsd_m": round(float(lowps), 3),
        "lowps": float(lowps),
        "platform": attrs.get("platform"),
        "provider": attrs.get("provider"),
    }


def _fallback_rasters() -> list[dict[str, Any]]:
    global _catalog_fallback
    if _catalog_fallback is None:
        raw = json.loads(_CATALOG_PATH.read_text())
        _catalog_fallback = [r for r in (_parse_raster(a) for a in raw["rasters"]) if r]
    return _catalog_fallback


async def _fetch_catalog() -> list[dict[str, Any]]:
    query = {
        "where": f"event='{DRP_EVENT}'",
        "outFields": "objectid,name,lowps,image_type,platform,provider",
        "returnGeometry": "false",
        "f": "json",
    }
    async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
        response = await client.get(f"{DRP_URL}/query", params=query,
                                    headers={"User-Agent": _UA})
        response.raise_for_status()
        body = response.json()

    # ArcGIS reports failures inside a 200, so a missing features list is an
    # error even though the request succeeded.
    if "error" in body:
        raise ValueError(f"DRP query returned an error: {body['error']}")
    features = body.get("features")
    if not isinstance(features, list):
        raise ValueError("DRP query returned no feature list")

    rasters = [r for r in (_parse_raster(f.get("attributes") or {}) for f in features) if r]
    if len(rasters) < _MIN_LIVE_RASTERS:
        raise ValueError(f"DRP query returned only {len(rasters)} usable rasters")
    rasters.sort(key=lambda r: r["objectid"] or 0)
    return rasters


async def catalog() -> tuple[list[dict[str, Any]], str, Optional[float]]:
    """Cached raster list, plus where this answer came from and when."""
    async with _lock:
        now = time.time()
        age = now - (_cache["fetched_at"] or 0.0)
        if _cache["rasters"] is not None and age < _TTL_SECONDS:
            return _cache["rasters"], "live", _cache["fetched_at"]
        try:
            rasters = await _fetch_catalog()
        except Exception as exc:
            logger.warning("DRP catalog fetch failed, serving %s: %s",
                           "cache" if _cache["rasters"] is not None else "vendored", exc)
            if _cache["rasters"] is not None and age < _STALE_GRACE_SECONDS:
                return _cache["rasters"], "cache", _cache["fetched_at"]
            return _fallback_rasters(), "fallback", None
        _cache["rasters"] = rasters
        _cache["fetched_at"] = now
        return rasters, "live", now


def frame_bbox(lat: float, lng: float, width_m: int) -> list[float]:
    """Ground box of `width_m` centred on the site, in EPSG:4326 degrees."""
    dlng = (width_m / 2.0) / (111320.0 * math.cos(math.radians(lat)))
    dlat = (width_m * _ASPECT / 2.0) / 110570.0
    return [round(lng - dlng, 6), round(lat - dlat, 6),
            round(lng + dlng, 6), round(lat + dlat, 6)]


def export_url(bbox: list[float], phase: str) -> str:
    """exportImage URL a browser can put straight in an <img src>.

    PRE and POST differ only in the mosaic's where-clause: identical bbox,
    identical size, so the service's own aspect padding is identical too and the
    two renders are the same frame of ground pixel for pixel. That registration
    is the whole point of going through exportImage instead of browse strips.
    """
    mosaic = {
        "mosaicMethod": "esriMosaicAttribute",
        "where": f"event='{DRP_EVENT}' AND image_type='{phase}'",
        "sortField": "lowps",
        "ascending": True,
    }
    params = {
        "bbox": ",".join(str(c) for c in bbox),
        "bboxSR": "4326",
        "imageSR": "3857",
        "size": f"{EXPORT_W},{EXPORT_H}",
        "format": "jpgpng",
        "f": "image",
        "mosaicRule": json.dumps(mosaic, separators=(",", ":")),
    }
    return f"{DRP_URL}/exportImage?{urlencode(params)}"


def _outer_ring(item: dict[str, Any]) -> Optional[list[list[float]]]:
    geometry = item.get("geometry") or {}
    if geometry.get("type") != "Polygon":
        return None
    rings = geometry.get("coordinates") or []
    if not rings:
        return None
    return [c for c in rings[0] if len(c) >= 2]


def _segments_cross(a: list[float], b: list[float],
                    c: list[float], d: list[float]) -> bool:
    def side(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    d1, d2 = side(c, d, a), side(c, d, b)
    d3, d4 = side(a, b, c), side(a, b, d)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))


def _ring_meets_bbox(ring: list[list[float]], bbox: list[float]) -> bool:
    """Does this footprint put any pixels inside the frame?

    Three tests because none alone is enough: a strip can swallow the frame
    whole (corner inside ring), the frame can swallow a footprint corner (vertex
    inside bbox), or a strip edge can slice across the frame with neither
    (segment crossing). Frames here are hundreds of metres and strips are tens
    of kilometres, so the first test carries almost every case — the other two
    exist so the edge of a footprint is never silently claimed as coverage or
    silently missed.
    """
    minx, miny, maxx, maxy = bbox
    corners = [[minx, miny], [maxx, miny], [maxx, maxy], [minx, maxy]]
    if any(point_in_ring(x, y, ring) for x, y in corners):
        return True
    if point_in_ring((minx + maxx) / 2, (miny + maxy) / 2, ring):
        return True
    if any(minx <= v[0] <= maxx and miny <= v[1] <= maxy for v in ring):
        return True
    edges = list(zip(corners, corners[1:] + corners[:1]))
    for i in range(len(ring)):
        a, b = ring[i], ring[(i + 1) % len(ring)]
        if any(_segments_cross(a, b, c, d) for c, d in edges):
            return True
    return False


# A footprint polygon is the scene outline, and the raster's valid pixels stop a
# little short of it: at Rasuwagadhi's 600 m detail frame the two eastern corners
# sit 19 m and 29 m inside the 2021 footprint and the render still carries a
# no-data wedge there. Corners are therefore only counted as covered with this
# much room to spare, so `edge` warns about the wedge instead of denying it.
_EDGE_MARGIN_KM = 0.05


def _fully_inside(rings: list[list[list[float]]], bbox: list[float]) -> bool:
    """Every frame corner well inside at least one footprint."""
    minx, miny, maxx, maxy = bbox
    corners = [(minx, miny), (maxx, miny), (maxx, maxy), (minx, maxy)]
    return all(
        any(point_in_ring(x, y, ring) and km_to_ring(x, y, ring) > _EDGE_MARGIN_KM
            for ring in rings)
        for x, y in corners)


def _acq_date(item: dict[str, Any]) -> Optional[str]:
    stamp = item.get("datetime")
    return stamp[:10] if isinstance(stamp, str) and len(stamp) >= 10 else None


def _phase_view(items: list[dict[str, Any]], by_stac: dict[str, dict[str, Any]],
                phase: str, bbox: list[float]) -> dict[str, Any]:
    """What the mosaic will actually paint into this frame for this phase."""
    # Restricted to scenes the DRP catalog holds: a STAC scene the service has
    # not ingested cannot appear in an export, so counting it as coverage would
    # promise ground the render will leave blank.
    in_view: list[tuple[dict[str, Any], list[list[float]], dict[str, Any]]] = []
    for item in items:
        if item.get("phase") != phase:
            continue
        raster = by_stac.get(item["id"])
        if not raster:
            continue
        ring = _outer_ring(item)
        if ring and _ring_meets_bbox(ring, bbox):
            in_view.append((item, ring, raster))

    if not in_view:
        # A frame with no footprint still exports 200 OK, as a fully transparent
        # PNG. onError never fires on it, so the null has to be decided here.
        return {"export_url": None, "top": None, "in_view": 0,
                "dates": [], "edge": True}

    # The caption is about the middle of the frame, so the top raster is chosen
    # among the footprints that actually reach the centre. Without this a strip
    # that grazes one corner of a 4 km context box wins on lowps and dates the
    # whole frame to a pass that covers a sliver of it.
    minx, miny, maxx, maxy = bbox
    centre = (minx + maxx) / 2, (miny + maxy) / 2
    over_centre = [row for row in in_view if point_in_ring(*centre, row[1])]
    item, ring, raster = min(over_centre or in_view, key=lambda row: row[2]["lowps"])
    dates = sorted({d for d in (_acq_date(i) for i, _, _ in in_view) if d})
    return {
        "export_url": export_url(bbox, phase),
        # The mosaic sorts ascending on lowps, so among the footprints over the
        # centre the lowest-lowps one is the raster on top there.
        "top": {
            "id": item["id"],
            "datetime": item.get("datetime"),
            "cloud": item.get("cloud"),
            "off_nadir": item.get("off_nadir"),
            "gsd_m": raster["gsd_m"],
            "platform": raster["platform"],
            "item_url": item.get("item_url"),
            "visual": item.get("visual"),
            # False when the labelled raster does not reach every corner: the
            # rest of the frame is other passes, on other dates, and the caption
            # speaks only for the middle of it.
            "full_frame": _fully_inside([ring], bbox),
        },
        "in_view": len(in_view),
        "dates": dates,
        "edge": not _fully_inside([r for _, r, _ in in_view], bbox),
    }


def _iso(fetched_at: Optional[float]) -> Optional[str]:
    if not fetched_at:
        return None
    return datetime.fromtimestamp(fetched_at, tz=timezone.utc).isoformat()


def build_sites(items: list[dict[str, Any]],
                rasters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_stac = {r["stac_id"]: r for r in rasters}
    out: list[dict[str, Any]] = []
    for site in SITES:
        record = _SITE_RECORD.get(site["key"], {})
        levels = []
        widths = _FRAMES.get(site["key"], {})
        for level in _LEVEL_ORDER:
            width = widths.get(level)
            if not width:
                continue
            bbox = frame_bbox(site["lat"], site["lng"], width)
            levels.append({
                "level": level,
                "width_m": width,
                "bbox": bbox,
                "pre": _phase_view(items, by_stac, "pre", bbox),
                "post": _phase_view(items, by_stac, "post", bbox),
            })
        out.append({
            "key": site["key"],
            "name": site["name"],
            "lat": site["lat"],
            "lng": site["lng"],
            "km_mark": record.get("km_mark"),
            "finding": record.get("finding"),
            "finding_source": record.get("finding_source"),
            "levels": levels,
        })
    return out


def catalog_summary(items: list[dict[str, Any]],
                    rasters: list[dict[str, Any]]) -> dict[str, Any]:
    """What the mosaic is rendering, named raster by raster.

    Acquisition date and cloud are joined in from the STAC item, never from the
    catalog: the service stamps every raster with event_start_date, which is the
    26 Aug event date and identical across all 16 rows.
    """
    by_stac = {i["id"]: i for i in items}
    holdings = []
    for raster in rasters:
        item = by_stac.get(raster["stac_id"])
        holdings.append({
            "objectid": raster["objectid"],
            "stac_id": raster["stac_id"],
            "image_type": raster["image_type"],
            "gsd_m": raster["gsd_m"],
            "platform": raster["platform"],
            "provider": raster["provider"],
            "acquired": item.get("datetime") if item else None,
            "cloud": item.get("cloud") if item else None,
            "covers": item.get("covers") if item else None,
            # Named so a raster the STAC has not got is visible as such rather
            # than reading as a scene with no date.
            "stac_matched": item is not None,
        })
    gsds = [r["gsd_m"] for r in rasters]
    return {
        "count": len(rasters),
        "pre": sum(1 for r in rasters if r["image_type"] == "pre"),
        "post": sum(1 for r in rasters if r["image_type"] == "post"),
        "gsd_range_m": [min(gsds), max(gsds)] if gsds else None,
        "platforms": sorted({r["platform"] for r in rasters if r["platform"]}),
        "providers": sorted({r["provider"] for r in rasters if r["provider"]}),
        "rasters": holdings,
    }


PROVENANCE_NOTE = (
    "The DRP catalog stamps event_start_date 2026-08-26 on every raster: that "
    "is the event date, not an acquisition date, and it is not surfaced as one. "
    "Acquisition instants and cloud figures here come from the Vantor STAC "
    "items themselves. Pre-event frames are 2021-2024 archive baselines, years "
    "before the flood; post-event passes carry 71-94% monsoon cloud, so an "
    "obscured frame is unassessed ground, not undamaged ground — though cloud "
    "is a whole-scene figure and says nothing about any one frame: the 79% "
    "27 Aug pass is cloud-free over Rasuwagadhi. Coverage per "
    "frame is computed from the STAC footprints — the DRP catalog query returns "
    "all 16 rasters for any geometry filter and cannot answer it.")


def _envelope(stac_source: str, catalog_source: str,
              catalog_fetched_at: Optional[float]) -> dict[str, Any]:
    """Licence, service identity and provenance — obligations on every payload."""
    return {
        "service_url": DRP_URL,
        "event": DRP_EVENT,
        "license": LICENSE,
        "license_url": LICENSE_URL,
        "attribution": ATTRIBUTION,
        "stac_attribution": STAC_ATTRIBUTION,
        "source": {"stac": stac_source, "drp_catalog": catalog_source},
        "catalog_fetched_at": _iso(catalog_fetched_at),
    }


def payload(items: list[dict[str, Any]], rasters: list[dict[str, Any]],
            stac_source: str, catalog_source: str,
            catalog_fetched_at: Optional[float]) -> dict[str, Any]:
    return {
        **_envelope(stac_source, catalog_source, catalog_fetched_at),
        "export": {"width": EXPORT_W, "height": EXPORT_H,
                   "bbox_sr": 4326, "image_sr": 3857, "format": "jpgpng"},
        "catalog": catalog_summary(items, rasters),
        "sites": build_sites(items, rasters),
        "note": PROVENANCE_NOTE,
    }


async def damage_sites() -> dict[str, Any]:
    items, stac_source, _ = await scenes()
    rasters, catalog_source, fetched_at = await catalog()
    return payload(items, rasters, stac_source, catalog_source, fetched_at)


async def holdings() -> dict[str, Any]:
    """The catalog on its own, for a client that wants to name the rasters."""
    items, stac_source, _ = await scenes()
    rasters, catalog_source, fetched_at = await catalog()
    return {
        **_envelope(stac_source, catalog_source, fetched_at),
        **catalog_summary(items, rasters),
        "note": PROVENANCE_NOTE,
    }
