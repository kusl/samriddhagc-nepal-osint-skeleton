"""Live flood desk API.

Read-only endpoints backing the flood monitoring page: national casualty and
damage totals from BIPAD, river gauge status with trend, district triage
rollup, incident list, and satellite imagery layer descriptors.
"""
from __future__ import annotations

import asyncio
import hashlib
import html
import logging
import re
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.data.district_geo import district_at, district_geometry
from app.models.flood_event import (FloodLiveSnapshot, FloodMediaItem,
                                    FloodSitrep)
from app.models.river import RiverStation
from app.models.story import Story
from app.services import (dhm_photo_service, drp_service, flood_assistance_service,
                          flood_hydropower_service, flood_replay_service,
                          flood_sites_service, nepalgov_service)
from app.services.flood_intel_service import (CHARTER_ACTIVATION,
                                              CITE_TIER_NOTE,
                                              CITED_REPORTING,
                                              FloodIntelService)
from app.services.flood_live_sync_service import FLOOD_TERMS
from app.services.flood_service import ACTIVE_EVENT_KEY, ACTIVE_EVENT_META, FloodService
from app.services.official_toll_service import OfficialTollService
from app.services.vantor_service import scenes as vantor_scenes
from app.services.vantor_service import payload as vantor_payload_for

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/flood", tags=["flood"])

# Image proxies are mounted WITHOUT the router's auth dependency: an <img src>
# cannot carry a bearer token, so a photograph the desk is allowed to show must
# be fetchable anonymously. Both routes take an id, never a URL, and only serve
# bytes for rows the sync already stored — there is nothing to protect that the
# public /photos listing does not already reveal.
public_router = APIRouter(prefix="/flood", tags=["flood"])


@router.get("/overview")
async def flood_overview(
    days: int = Query(default=7, ge=1, le=365,
                      description="Reporting window in days"),
    db: AsyncSession = Depends(get_db),
):
    """National flood situation: casualties, damage (NPR + USD), rivers."""
    return await FloodService(db).get_overview(days=days)


@router.get("/official")
async def flood_official(
    event: str = Query(default=ACTIVE_EVENT_KEY,
                       description="Event key, e.g. trishuli-2026-08"),
    days: int = Query(default=7, ge=1, le=365,
                      description="Window for the BIPAD cross-check"),
    db: AsyncSession = Depends(get_db),
):
    """Official disaster-authority figures for the active flood event.

    Returned alongside what BIPAD's incident feed independently holds for the
    same period. The gap is not incidental: on 2026-09-01 NDRRMA reported 987
    dead from this event while BIPAD's incident API carried 7 deaths across all
    hazards nationwide. Publishing both, labelled, is the only honest way to
    show a figure the platform's own pipeline cannot see.
    """
    official = await OfficialTollService(db).get_event(event)
    bipad = await FloodService(db).get_overview(days=days)

    return {
        "event": ACTIVE_EVENT_META if event == ACTIVE_EVENT_KEY else {"key": event},
        "official": official,
        "bipad_cross_check": {
            "window_days": days,
            "deaths": bipad["casualties"]["deaths"],
            "incidents": bipad["incidents"]["total"],
            "note": "BIPAD's incident feed is compiled from local disaster "
                    "reports and does not currently carry this event. Treat it "
                    "as routine-incident coverage, not the disaster toll.",
        },
    }


@router.get("/imagery")
async def flood_imagery(
    event: str = Query(default=ACTIVE_EVENT_KEY,
                       description="Event key, e.g. trishuli-2026-08"),
    db: AsyncSession = Depends(get_db),
):
    """Catalogued satellite imagery products for the event.

    Separate from /satellite/layers: that returns live tile services answering
    "where is the water today", while these are fixed analytical artefacts —
    Charter impact maps, before/after acquisition pairs — each citable at its
    publisher. The Charter activation is returned alongside because it is the
    authority behind a third of the catalogue.
    """
    products = await FloodIntelService(db).get_imagery(event)
    return {
        "event_key": event,
        "activation": CHARTER_ACTIVATION,
        "count": len(products),
        "products": products,
    }


@router.get("/chronology")
async def flood_chronology(
    event: str = Query(default=ACTIVE_EVENT_KEY,
                       description="Event key, e.g. trishuli-2026-08"),
    db: AsyncSession = Depends(get_db),
):
    """Dated narrative beats for the event, oldest first.

    Every entry carries its own source rather than inheriting one from the
    event: a seismic timestamp, a border-post image and an NDRRMA bulletin are
    three different authorities and should read as such.
    """
    events = await FloodIntelService(db).get_chronology(event)
    return {"event_key": event, "count": len(events), "events": events}


@router.get("/rivers")
async def flood_rivers(
    alerts_only: bool = Query(default=False,
                              description="Only stations at warning or danger"),
    db: AsyncSession = Depends(get_db),
):
    """River gauges with alert level, trend, and headroom to danger."""
    stations = await FloodService(db).get_rivers(alerts_only=alerts_only)
    return {"count": len(stations), "stations": stations}


@router.get("/districts")
async def flood_districts(
    days: int = Query(default=7, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    """Per-district totals, worst first."""
    rows = await FloodService(db).get_district_rollup(days=days)
    return {"count": len(rows), "districts": rows}


# NDRRMA's bulletin and the Survey Department reference geojson spell two of
# this event's districts differently, and each mismatch would silently drop a
# district off the map: "Nawalparasi East" is the pre-2015 name of Nawalpur
# (NP0447) and the second-worst district at 216 recovered, and "Makwanpur" is
# a transliteration of Makawanpur (NP0331), the only district that appears in
# the missing panel with no recovered figure. Resolved server-side so the join
# key travelling to the frontend stays the NDRRMA name the figures are
# published under.
_NDRRMA_TO_GEOJSON = {
    "Nawalparasi East": "Nawalpur",
    "Makwanpur": "Makawanpur",
}

# The bedrock collapse beneath Langtang Lirung, 26 Aug 08:37 NPT, from the
# event record. Which district counts as "at the source" is resolved by
# point-in-polygon against this coordinate rather than asserted in a list, so
# the flag cannot drift from the boundaries the map actually draws.
_COLLAPSE_ORIGIN = (85.517, 28.256)  # (lon, lat)

# Named settlements and confluences down the Lende Khola / Trishuli / Narayani
# run, with the downstream distances carried in the event record (Chitwan at
# roughly 160 km). Shipped by the API so the map hardcodes no geography. The
# line a client draws between these points is a schematic surge path, NOT the
# river course — we have no river centreline and will not invent one.
_CORRIDOR = [
    {"name": "Langtang Lirung collapse origin", "lat": 28.256, "lng": 85.517, "kind": "origin", "km": None},
    {"name": "Rasuwagadhi / Gyirong Port", "lat": 28.278, "lng": 85.379, "kind": "waypoint", "km": 0},
    {"name": "Syabrubesi", "lat": 28.160, "lng": 85.348, "kind": "waypoint", "km": 16},
    {"name": "Betrawati", "lat": 27.976, "lng": 85.187, "kind": "waypoint", "km": 45},
    {"name": "Trishuli Bazar", "lat": 27.921, "lng": 85.144, "kind": "waypoint", "km": 53},
    {"name": "Galchhi", "lat": 27.833, "lng": 84.999, "kind": "waypoint", "km": 75},
    {"name": "Devghat confluence", "lat": 27.717, "lng": 84.415, "kind": "waypoint", "km": 150},
    {"name": "Narayanghat (Chitwan)", "lat": 27.690, "lng": 84.428, "kind": "waypoint", "km": 160},
    {"name": "Narayani through Nawalparasi", "lat": 27.560, "lng": 84.100, "kind": "waypoint", "km": 200},
]


def _geo_name(ndrrma_name: str) -> Optional[str]:
    """The geojson district this NDRRMA label names, or None if it names none.

    Exact equality after aliasing, never a substring test: the missing panel
    lists categories beside districts ("Linked to hydropower projects"), and a
    loose match would put a category on the map as a place.
    """
    candidate = _NDRRMA_TO_GEOJSON.get(ndrrma_name, ndrrma_name)
    return candidate if district_geometry(candidate) else None


def _panel_int(value) -> Optional[int]:
    """'3,916' -> 3916. None for anything that is not a plain published count."""
    if value is None:
        return None
    try:
        return int(str(value).replace(",", "").strip())
    except ValueError:
        return None


async def _affected_district_names(db: AsyncSession,
                                  event: str = ACTIVE_EVENT_KEY) -> set[str]:
    """Geojson names of the districts this event touched.

    Derived from the same bulletin /flood/districts/geo draws, so a station is
    called "in the affected area" by exactly the polygons the map fills and a
    district NDRRMA adds tomorrow is included tomorrow.
    """
    official = await OfficialTollService(db).get_event(event)
    latest = official.get("latest") or {}
    labels = list((latest.get("district_tolls") or {}).keys())
    panels = {p["key"]: p for p in official.get("panels") or []}
    labels += [(row.get("label") or "").strip()
               for row in (panels.get("missing") or {}).get("rows") or []]
    return {name for name in (_geo_name(label) for label in labels if label) if name}


@router.get("/districts/geo")
async def flood_district_geo(
    event: str = Query(default=ACTIVE_EVENT_KEY,
                       description="Event key, e.g. trishuli-2026-08"),
    db: AsyncSession = Depends(get_db),
):
    """Boundaries of the districts this event touched, figures joined on.

    Only the geometry is local to this endpoint. Every number is read live from
    the same FloodOfficialToll row and situation panels that /flood/official
    serves, so a choropleth built on this can never disagree with the toll
    widgets, and a bulletin revision needs no geometry redeploy.

    The set of districts is derived from the bulletin too, not hardcoded: the
    district_tolls keys plus any missing-panel row whose label is exactly a
    district name. A district NDRRMA adds tomorrow appears on the map tomorrow,
    and one we cannot place is returned in `unresolved` rather than dropped.
    """
    official = await OfficialTollService(db).get_event(event)
    latest = official.get("latest") or {}
    tolls = latest.get("district_tolls") or {}
    panels = {p["key"]: p for p in official.get("panels") or []}

    missing_by_district: dict[str, int] = {}
    unresolved: list[str] = []
    for row in (panels.get("missing") or {}).get("rows") or []:
        label = (row.get("label") or "").strip()
        count = _panel_int(row.get("value"))
        if count is None or not label:
            continue
        if _geo_name(label):
            missing_by_district[label] = count

    # Worst-hit first, then the districts published as missing-only, so a client
    # that draws in order draws the deepest fill first.
    recovered = {name: (figures or {}).get("bodies_recovered")
                 for name, figures in tolls.items()}
    ordered = sorted(recovered, key=lambda n: (-(recovered[n] or 0), n))
    ordered += sorted(n for n in missing_by_district if n not in recovered)

    # Point-in-polygon, so "source" is a fact about the geometry served.
    source_district = district_at(*_COLLAPSE_ORIGIN)

    features = []
    for name in ordered:
        geo_name = _geo_name(name)
        if not geo_name:
            unresolved.append(name)
            continue
        stored = district_geometry(geo_name)
        props = stored["properties"]
        features.append({
            "type": "Feature",
            "properties": {
                # The NDRRMA name is the join key everywhere the figures travel.
                "name": name,
                "geo_name": geo_name,
                "province": props.get("province"),
                "code": props.get("code"),
                "centroid": props.get("centroid"),
                "bodies_recovered": recovered.get(name),
                # null, not 0: NDRRMA breaks missing out for three districts
                # only, and "not published" is not "none missing".
                "missing": missing_by_district.get(name),
                # Only two positions are defensible from the record: the district
                # containing the collapse, and the districts NDRRMA reports
                # recoveries from along the Trishuli-Narayani run. A district that
                # appears solely in the missing rows (Makwanpur, in the Bagmati
                # basin) is on neither footing, so it is left unpositioned rather
                # than asserted to be downstream of a river it does not sit on.
                "position": (
                    "source" if geo_name == source_district
                    else "downstream" if name in tolls
                    else None
                ),
                "authority": latest.get("authority"),
                "as_of": latest.get("as_of"),
            },
            "geometry": stored["geometry"],
        })

    river = flood_replay_service.load_river_path()
    if river:
        corridor = flood_replay_service.river_corridor(river, _CORRIDOR)
        corridor_kind = "channel"
    else:
        corridor = _CORRIDOR
        corridor_kind = "schematic"

    return {
        "event_key": event,
        "count": len(features),
        "districts": {"type": "FeatureCollection", "features": features},
        # The real channel when the vendored OSM river is present: one entry
        # per 100 m vertex, named where a published waypoint projects onto it,
        # with the collapse origin carried through off the km axis. The
        # schematic chord list is the fallback, and `corridor_kind` says which.
        "corridor": corridor,
        "corridor_kind": corridor_kind,
        # Named so nobody has to guess whether a district went missing between
        # the bulletin and the map.
        "unresolved": unresolved,
        # Every published district breakdown, so a replay can step between the
        # bulletins that exist rather than implying one for every day.
        "toll_snapshots": await OfficialTollService(db).district_snapshots(event),
        "note": "District boundaries: Survey Department reference geojson, "
                "passed through with coordinates trimmed to 5 decimal places "
                "(~1 m); no vertices removed. Figures are NDRRMA's, read live "
                "from the same record /flood/official serves. No river distance "
                "is published per district: the polygons carry no river "
                "centreline, so a downstream kilometre figure could only be "
                "estimated, and the corridor's own km marks are the event "
                "record's. When corridor_kind is 'channel' the corridor is the "
                "OpenStreetMap river channel (ODbL) densified to 100 m with the "
                "published places projected onto it; 'schematic' means the "
                "chord path between named places.",
    }


@router.get("/incidents")
async def flood_incidents(
    days: int = Query(default=7, ge=1, le=365),
    limit: int = Query(default=200, ge=1, le=1000),
    district: Optional[str] = None,
    hazard: Optional[str] = Query(default=None,
                                  description="flood | landslide | heavy_rainfall"),
    db: AsyncSession = Depends(get_db),
):
    """Flood-family incidents with per-incident casualty and damage figures."""
    rows = await FloodService(db).get_incidents(
        days=days, limit=limit, district=district, hazard=hazard)
    return {"count": len(rows), "incidents": rows}


@router.get("/timeline")
async def flood_timeline(
    days: int = Query(default=30, ge=7, le=365),
    db: AsyncSession = Depends(get_db),
):
    """Daily incident and death counts for the trend chart."""
    return {"days": days, "series": await FloodService(db).get_daily_series(days=days)}


# NASA GIBS serves daily global imagery over open WMTS with no API key and no
# registration, which is what makes it usable here — Sentinel Hub and Earth
# Engine both need credentials this deployment does not have. Imagery is served
# in EPSG:3857, so it overlays the Leaflet basemap directly.
_GIBS_WMTS = (
    "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/"
    "{layer}/default/{{time}}/GoogleMapsCompatible_Level{levels}/{{z}}/{{y}}/{{x}}.{fmt}"
)

_SATELLITE_LAYERS = [
    # Flood-extent products first: these are the actual answer to "where is the
    # water", derived by NASA from the raw bands rather than left to the eye.
    # They are transparent PNG overlays, so they sit on top of the basemap.
    {
        "id": "viirs_flood_3day",
        "name": "VIIRS Flood Extent (3-day composite)",
        "layer": "VIIRS_Combined_Flood_3-Day",
        "levels": 9, "format": "png", "kind": "overlay",
        "description": "NASA's mapped flood water over a 3-day window. The "
                       "composite fills single-day cloud gaps, which matters in "
                       "monsoon — best default for seeing current extent. Roughly 250 m per "
                       "pixel: regional extent, not building-level damage.",

    },
    {
        "id": "viirs_flood_1day",
        "name": "VIIRS Flood Extent (1-day)",
        "layer": "VIIRS_Combined_Flood_1-Day",
        "levels": 9, "format": "png", "kind": "overlay",
        "description": "Single-day flood mapping — sharper timing than the "
                       "composite, but cloud cover leaves holes. Roughly 250 m per pixel: regional extent, not building-level damage.",
    },
    {
        "id": "modis_flood_2day",
        "name": "MODIS Flood Extent (2-day)",
        "layer": "MODIS_Combined_Flood_2-Day",
        "levels": 9, "format": "png", "kind": "overlay",
        "description": "Independent flood mapping from MODIS. Useful as a "
                       "cross-check when VIIRS and MODIS disagree. Roughly 250 m per pixel: regional extent, not building-level damage.",
    },
    # Raw imagery underneath, for judging the flood products against what the
    # sensor actually saw.
    {
        "id": "viirs_false_color",
        "name": "VIIRS False Colour (M11-I2-I1)",
        "layer": "VIIRS_NOAA20_CorrectedReflectance_BandsM11-I2-I1",
        "levels": 9, "format": "jpg", "kind": "base",
        "description": "Shortwave-infrared composite: standing water is near-"
                       "black, vegetation bright green. Reads through haze far "
                       "better than true colour.",
    },
    {
        "id": "viirs_true_color",
        "name": "VIIRS True Colour",
        "layer": "VIIRS_NOAA20_CorrectedReflectance_TrueColor",
        "levels": 9, "format": "jpg", "kind": "base",
        "description": "What the ground looked like from orbit that day.",
    },
    {
        "id": "modis_true_color",
        "name": "MODIS Terra True Colour",
        "layer": "MODIS_Terra_CorrectedReflectance_TrueColor",
        "levels": 9, "format": "jpg", "kind": "base",
        "description": "A second overpass at a different time of day — often "
                       "clear when the VIIRS pass was clouded out.",
    },
]


@router.get("/satellite/layers")
async def satellite_layers(
    days_back: int = Query(default=7, ge=1, le=30,
                           description="How many past days to offer"),
):
    """Keyless NASA GIBS imagery layers and the dates available for them.

    GIBS publishes each day's imagery a few hours after the satellite overpass,
    so 'today' is frequently not ready yet. We offer yesterday as the newest
    safe default and let the caller step back from there.
    """
    today = date.today()
    # Yesterday is the newest date reliably published for all three layers.
    newest = today - timedelta(days=1)
    dates = [(newest - timedelta(days=i)).isoformat() for i in range(days_back)]

    layers = [
        {
            "id": spec["id"],
            "name": spec["name"],
            "description": spec["description"],
            "tile_url_template": _GIBS_WMTS.format(
                layer=spec["layer"], levels=spec["levels"], fmt=spec["format"]),
            "kind": spec["kind"],
            "max_zoom": spec["levels"],
            "attribution": "NASA EOSDIS GIBS",
        }
        for spec in _SATELLITE_LAYERS
    ]
    return {
        "dates": dates,
        "default_date": newest.isoformat(),
        "layers": layers,
        # Event-anchored acquisition dates for the before/after comparison.
        #
        # These are pinned, NOT derived from `dates`. `dates` is a rolling
        # window ending yesterday, so a client that picked its "before" from
        # the oldest entry would, once the window slid past 26 August, be
        # labelling post-event imagery as "PRE" — the comparison would quietly
        # invert while still looking authoritative. The pre-date is a property
        # of the event, so it belongs here and never moves.
        "baseline": {
            "pre_date": "2026-08-12",
            "post_dates": ["2026-08-27", "2026-08-28"],
            "resolution_note": "VIIRS via NASA GIBS, roughly 250 m per pixel. "
                               "Resolves the swollen Trishuli and regional flood "
                               "extent; it cannot resolve buildings, so the "
                               "scouring of the Rasuwagadhi border post is not "
                               "visible at this scale.",
        },
        "note": "Imagery is published a few hours after overpass; the most "
                "recent day may be incomplete or cloud-covered.",
    }


# ---------------------------------------------------------------------------

# Licensed media is proxied rather than fetched from the browser for two
# reasons: Commons wants a descriptive User-Agent that a browser will not let us
# set, and it rate-limits anonymous bursts hard enough that a 429 would blank the
# map at exactly the moment a rescue desk is being refreshed most.
_COMMONS_API = "https://commons.wikimedia.org/w/api.php"
_COMMONS_CATEGORY = "Category:2026 Nepal and Tibet floods"
_COMMONS_CATEGORY_URL = (
    "https://commons.wikimedia.org/wiki/Category:2026_Nepal_and_Tibet_floods")
_COMMONS_UA = "NepalOSINT-FloodDesk/1.0 (nepalosint.com; contact via site)"

_MEDIA_TTL_SECONDS = 3600
# A stale answer from Commons is still a true answer about which files exist;
# only a day-old one stops being worth preferring over the verified seed.
_MEDIA_STALE_GRACE_SECONDS = 86400

# Anchors are looked up in _CORRIDOR rather than restated, so a media pin can
# never end up somewhere the corridor this same endpoint draws does not go.
_MEDIA_ANCHORS = {
    "collapse_origin": _CORRIDOR[0],
    "gyirong_port": _CORRIDOR[1],
}

# The seven files verified against Commons on 2026-09-01, each fetched and
# confirmed to return real bytes. They are the floor: whatever Commons does,
# these are served, in this order, with these credits. `author`/`license` left
# None means the record states nothing, not that nothing applies — a live answer
# is allowed to fill those, and only those.
#
# `available_from` is the date a reader could first have been looking at this
# frame. It drives replay visibility, so it is the capture date wherever one is
# published. The Gyirong before/after composite is dated only "after the flood",
# so it is released on the event day rather than held back to its 28 Aug upload:
# the panel it is read for is the collapse, and holding it later would hide the
# event's own imagery from the hours the event is being replayed.
_MEDIA_SEED = [
    {
        "id": "gyirong-port-before-after",
        "file": "Gyirong Port before and after the flood satellite 2026.png",
        "title": "Gyirong Port before and after the flood",
        "caption": "Site-level satellite pair of the border post itself, before "
                   "and after the surge scoured it. The only building-scale "
                   "before/after of Rasuwagadhi in the open record.",
        "provider": "Wikimedia Commons",
        "author": "Pomoscj3",
        "license": "CC0",
        "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
        "kind": "image", "mime": "image/png",
        "thumb_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/0/0b/Gyirong_Port_before_and_after_the_flood_satellite_2026.png/1280px-Gyirong_Port_before_and_after_the_flood_satellite_2026.png",
        "page_url": "https://commons.wikimedia.org/wiki/File:Gyirong_Port_before_and_after_the_flood_satellite_2026.png",
        "width": 1618, "height": 1324,
        "anchor": "gyirong_port",
        "capture_date": None,
        "available_from": "2026-08-26",
    },
    {
        "id": "gyirong-port-mudslide-screenshot",
        "file": "Mudslide at Gyirong Port 2 (screenshot).png",
        "title": "Mudslide at Gyirong Port (CCTV screenshot)",
        "caption": "Frame at 30 seconds of fixed-camera footage at the border "
                   "post, looking south down the valley as the debris flow "
                   "arrives.",
        "provider": "Gyirong Port fixed camera",
        "author": "Unknown author",
        "license": "Public domain",
        "license_url": None,
        "kind": "image", "mime": "image/png",
        "thumb_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/Mudslide_at_Gyirong_Port_2_%28screenshot%29.png/1280px-Mudslide_at_Gyirong_Port_2_%28screenshot%29.png",
        "page_url": "https://commons.wikimedia.org/wiki/File:Mudslide_at_Gyirong_Port_2_(screenshot).png",
        "width": 1900, "height": 960,
        "anchor": "gyirong_port",
        "capture_date": "2026-08-26",
        "available_from": "2026-08-26",
    },
    {
        "id": "landsat-aftermath-2026-08-26",
        "file": "Landsat Nepal flood 2026-08-26.png",
        "title": "Landsat 9, aftermath on the day of the collapse",
        "caption": "The valley from orbit on 26 August, hours after the "
                   "collapse: the scoured channel and the debris fan below "
                   "Langtang Lirung.",
        "provider": "USGS / Landsat 9",
        "author": "Landsat 9 via USGS, processed by User:Chorchapu",
        "license": "Public domain",
        "license_url": None,
        "kind": "image", "mime": "image/png",
        "thumb_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c3/Landsat_Nepal_flood_2026-08-26.png/1280px-Landsat_Nepal_flood_2026-08-26.png",
        "page_url": "https://commons.wikimedia.org/wiki/File:Landsat_Nepal_flood_2026-08-26.png",
        "width": 1918, "height": 1094,
        "anchor": "collapse_origin",
        "capture_date": "2026-08-26",
        "available_from": "2026-08-26",
    },
    {
        "id": "before-after-animation",
        "file": "Nepal flood 2026 before after.gif",
        "title": "Before and after, 24 vs 26 August",
        "caption": "Animation flipping between the 24 August Sentinel-2 scene "
                   "and the 26 August Landsat scene over the collapse origin.",
        "provider": "Copernicus Sentinel-2 / Landsat 9",
        "author": "European Space Agency / USGS",
        "license": "Public domain",
        "license_url": None,
        "kind": "image", "mime": "image/gif",
        "thumb_url": "https://upload.wikimedia.org/wikipedia/commons/6/6f/Nepal_flood_2026_before_after.gif",
        "page_url": "https://commons.wikimedia.org/wiki/File:Nepal_flood_2026_before_after.gif",
        "width": 1918, "height": 1094,
        "anchor": "collapse_origin",
        "capture_date": None,
        "available_from": "2026-08-26",
    },
    {
        "id": "sentinel2-before-2026-08-24",
        "file": "Nepal flood before 2026-08-24 Copernicus Sentinel2-L1C.png",
        "title": "Sentinel-2, two days before",
        "caption": "The same ground on 24 August, the last clear pre-event "
                   "acquisition — the reference frame for every after image "
                   "here.",
        "provider": "Copernicus Sentinel-2",
        "author": "European Space Agency",
        "license": "CC BY 4.0",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "kind": "image", "mime": "image/png",
        "thumb_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/8f/Nepal_flood_before_2026-08-24_Copernicus_Sentinel2-L1C.png/1280px-Nepal_flood_before_2026-08-24_Copernicus_Sentinel2-L1C.png",
        "page_url": "https://commons.wikimedia.org/wiki/File:Nepal_flood_before_2026-08-24_Copernicus_Sentinel2-L1C.png",
        "width": 2500, "height": 1579,
        "anchor": "collapse_origin",
        "capture_date": "2026-08-24",
        "available_from": "2026-08-24",
    },
    {
        "id": "sentinel2-baseline-2026-08-12",
        "file": "Nepal floods before - 20260812.png",
        "title": "Sentinel-2 baseline, 12 August",
        "caption": "The 12 August baseline scene, two weeks before the "
                   "collapse. Matches the pre-date the GIBS before/after "
                   "comparison is pinned to.",
        "provider": "Copernicus Sentinel-2",
        "author": "Sentinel-2 via Copernicus Browser",
        "license": "Attribution",
        "license_url": None,
        "kind": "image", "mime": "image/png",
        "thumb_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/4/41/Nepal_floods_before_-_20260812.png/1280px-Nepal_floods_before_-_20260812.png",
        "page_url": "https://commons.wikimedia.org/wiki/File:Nepal_floods_before_-_20260812.png",
        "width": 1364, "height": 786,
        "anchor": "collapse_origin",
        "capture_date": "2026-08-12",
        "available_from": "2026-08-12",
    },
    {
        # A multi-page PDF map sheet. No thumbnail is seeded and clients are told
        # not to render it inline — it is a document to open, not a frame to read
        # at widget scale.
        "id": "ecdm-daily-map-2026-08-27",
        "file": "ECDM 20260827 Nepal GLOF.pdf",
        "title": "ECDM daily map, 27 August: Nepal GLOF",
        "caption": "Copernicus Emergency Management daily situation map for the "
                   "outburst flood. Link out — a map sheet, not an image.",
        "provider": "Copernicus Emergency Management Service",
        "author": None,
        "license": None,
        "license_url": None,
        "kind": "pdf", "mime": "application/pdf",
        "thumb_url": None,
        "page_url": "https://commons.wikimedia.org/wiki/File:ECDM_20260827_Nepal_GLOF.pdf",
        "width": None, "height": None,
        "anchor": "collapse_origin",
        "capture_date": "2026-08-27",
        "available_from": "2026-08-27",
    },
    {
        # The CCTV clips are heavier than anything else in the set and one of
        # them 429s under rapid requests, so they are seeded last and a client is
        # expected to treat them as nice-to-have.
        "id": "gyirong-port-mudslide-video-1",
        "file": "Mudslide at Gyirong Port 1.webm",
        "title": "Mudslide at Gyirong Port, camera 1",
        "caption": "Fixed-camera footage of the debris flow passing the border "
                   "post.",
        "provider": "Gyirong Port fixed camera",
        "author": "Unknown author",
        "license": "Public domain",
        "license_url": None,
        "kind": "video", "mime": "video/webm",
        "thumb_url": None,
        "file_url": "https://upload.wikimedia.org/wikipedia/commons/9/9a/Mudslide_at_Gyirong_Port_1.webm",
        "page_url": "https://commons.wikimedia.org/wiki/File:Mudslide_at_Gyirong_Port_1.webm",
        "width": 1280, "height": 720,
        "anchor": "gyirong_port",
        "capture_date": "2026-08-26",
        "available_from": "2026-08-26",
    },
    {
        "id": "gyirong-port-mudslide-video-2",
        "file": "Mudslide at Gyirong Port 2.webm",
        "title": "Mudslide at Gyirong Port, camera 2",
        "caption": "The clip the 30-second screenshot above is taken from.",
        "provider": "Gyirong Port fixed camera",
        "author": "Unknown author",
        "license": "Public domain",
        "license_url": None,
        "kind": "video", "mime": "video/webm",
        "thumb_url": None,
        "file_url": "https://upload.wikimedia.org/wikipedia/commons/f/fe/Mudslide_at_Gyirong_Port_2.webm",
        "page_url": "https://commons.wikimedia.org/wiki/File:Mudslide_at_Gyirong_Port_2.webm",
        "width": 1280, "height": 720,
        "anchor": "gyirong_port",
        "capture_date": "2026-08-26",
        "available_from": "2026-08-26",
    },
]

_MEDIA_MIME_KIND = {"application/pdf": "pdf"}

# (files_by_name, fetched_at, ok) for the whole process. An hour of staleness on
# a media list costs nothing; a second request to a rate-limited API per desk
# refresh costs the images.
_media_cache: dict[str, Any] = {"files": None, "fetched_at": 0.0}
_media_lock = asyncio.Lock()


def _clean_url(url: Optional[str]) -> Optional[str]:
    """Commons tags the URLs it hands back with its own utm_* analytics params.

    They are noise in a stored payload and in every log line that quotes one, and
    dropping them changes nothing about what the URL serves.
    """
    if not url:
        return None
    base, _, query = url.partition("?")
    kept = [p for p in query.split("&") if p and not p.startswith("utm_")]
    return f"{base}?{'&'.join(kept)}" if kept else base


def _strip_html(value: Optional[str]) -> Optional[str]:
    """Commons returns credit fields as rendered HTML; we want the words."""
    if not value:
        return None
    text = re.sub(r"<[^>]+>", " ", value)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def _extmeta(info: dict, key: str) -> Optional[str]:
    return _strip_html(((info.get("extmetadata") or {}).get(key) or {}).get("value"))


async def _fetch_commons_files() -> dict[str, dict]:
    """Every file in the event category, keyed by filename.

    One generator request instead of the category-then-imageinfo pair: it is the
    same two operations server-side but a single round trip, which is the only
    lever we have against a rate limit that counts requests.

    Raises on anything that leaves us without a usable list — including an empty
    category, which for a category known to hold files means we were throttled or
    asked wrongly, not that the imagery stopped existing.
    """
    params = {
        "action": "query",
        "format": "json",
        "formatversion": "2",
        "generator": "categorymembers",
        "gcmtitle": _COMMONS_CATEGORY,
        "gcmtype": "file",
        "gcmlimit": 50,
        "prop": "imageinfo",
        "iiprop": "url|extmetadata|size|mime",
        "iiurlwidth": 1280,
    }
    async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client:
        response = await client.get(
            _COMMONS_API, params=params, headers={"User-Agent": _COMMONS_UA})
        response.raise_for_status()
        pages = ((response.json().get("query") or {}).get("pages")) or []

    files: dict[str, dict] = {}
    for page in pages:
        title = page.get("title") or ""
        if not title.startswith("File:"):
            continue
        infos = page.get("imageinfo") or []
        if not infos:
            continue
        info = infos[0]
        mime = info.get("mime")
        files[title[len("File:"):]] = {
            "title": title[len("File:"):],
            "mime": mime,
            "kind": _MEDIA_MIME_KIND.get(mime or "",
                                         "video" if (mime or "").startswith("video/")
                                         else "image"),
            # thumburl is a rendered still: the image itself for a picture, a
            # poster frame for a video. The playable/original file is url.
            "thumb_url": _clean_url(info.get("thumburl")),
            "file_url": _clean_url(info.get("url")),
            "page_url": info.get("descriptionurl"),
            "width": info.get("thumbwidth") or info.get("width"),
            "height": info.get("thumbheight") or info.get("height"),
            "author": _extmeta(info, "Artist"),
            "license": _extmeta(info, "LicenseShortName"),
            "license_url": _extmeta(info, "LicenseUrl"),
            "date": _extmeta(info, "DateTimeOriginal"),
        }

    if not files:
        raise ValueError("Commons returned no files for a category known to hold them")
    return files


async def _commons_files() -> tuple[Optional[dict[str, dict]], bool, Optional[float]]:
    """Cached category listing, plus whether this call reached Commons."""
    async with _media_lock:
        now = time.time()
        age = now - (_media_cache["fetched_at"] or 0.0)
        if _media_cache["files"] is not None and age < _MEDIA_TTL_SECONDS:
            return _media_cache["files"], True, _media_cache["fetched_at"]
        try:
            files = await _fetch_commons_files()
        except Exception as exc:  # timeout, 429, parse error — all the same here
            logger.warning("Commons media query failed, serving seed: %s", exc)
            # A listing from earlier today still tells the truth about which
            # files exist, so prefer it over dropping to the seed alone.
            if (_media_cache["files"] is not None
                    and age < _MEDIA_STALE_GRACE_SECONDS):
                return _media_cache["files"], False, _media_cache["fetched_at"]
            return None, False, None
        _media_cache["files"] = files
        _media_cache["fetched_at"] = now
        return files, True, now


def _media_id(filename: str) -> str:
    """A stable, readable id — but never a misleading one.

    Slugging is ASCII-only, so a filename written in another script collapses to
    almost nothing ("2026年中尼邊境泥石流災害示意地圖.svg" -> "2026"). When too
    little survives to identify the file, fall back to a digest of the filename
    so the id stays unique and stable rather than plausible.
    """
    stem = filename.rsplit(".", 1)[0]
    slug = re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", stem.lower())).strip("-")
    if len(slug) < 6:
        return "commons-" + hashlib.sha1(filename.encode()).hexdigest()[:10]
    return slug


def _located(anchor: Optional[str]) -> Optional[dict]:
    """The stated place for an anchor, or None.

    Commons carries no coordinates for any of these files. The two that exist
    are asserted in the event record, so a file we did not seed gets no location
    at all rather than a plausible one — the client can list it without pinning
    it somewhere it was never taken.
    """
    waypoint = _MEDIA_ANCHORS.get(anchor or "")
    if not waypoint:
        return None
    return {
        "name": waypoint["name"],
        "lat": waypoint["lat"],
        "lng": waypoint["lng"],
        "district": district_at(waypoint["lng"], waypoint["lat"]),
    }


def _merge_seed(seed: dict, live: Optional[dict], order: int) -> dict:
    """Seed provenance, live delivery.

    The seed wins on everything it actually states — credit, licence, caption,
    coordinates, ordering — because those were verified by hand and must survive
    Commons being unreachable. It loses on two kinds of field: ones it leaves
    null (the ECDM sheet's credit, which the record never stated), and the
    thumbnail URL, which is a delivery detail Commons re-hosts at will. That
    second rule is load-bearing right now: upload.wikimedia.org is returning 429
    to this deployment while the thumb host Commons itself advertises serves
    fine, so preferring the live URL is what keeps the images on screen.
    """
    item = dict(seed)
    item["source"] = "seed"
    item["display_order"] = order
    if live:
        item["source"] = "seed+commons"
        if live.get("thumb_url") and seed.get("kind") == "image":
            item["thumb_url_alt"] = seed.get("thumb_url")
            item["thumb_url"] = live["thumb_url"]
        elif live.get("thumb_url") and seed.get("kind") == "video":
            # A poster is worth having, but it is not the clip: it goes beside
            # file_url, never over it.
            item["thumb_url"] = live["thumb_url"]
        if live.get("file_url"):
            if seed.get("kind") == "video":
                item["file_url_alt"] = seed.get("file_url")
            # For a still, this is the unresized original — what a viewer needs
            # when it drops out of fit-to-widget into 1:1 to read a building.
            item["file_url"] = live["file_url"]
        for field in ("author", "license", "license_url", "mime", "page_url"):
            if item.get(field) is None and live.get(field) is not None:
                item[field] = live[field]
        # Never silently overwrite a hand-verified licence with a changed one:
        # show both and let the desk decide, per the rule that governs the rest
        # of this event's conflicting figures.
        if (seed.get("license") and live.get("license")
                and seed["license"] != live["license"]):
            item["license_conflict"] = {"verified": seed["license"],
                                        "commons_now": live["license"]}
    location = _located(seed.get("anchor"))
    item["location"] = location
    item["lat"] = location["lat"] if location else None
    item["lng"] = location["lng"] if location else None
    return item


def _discovered(live: dict, order: int) -> dict:
    """A category file we never verified: listed, credited, but never pinned."""
    return {
        "id": _media_id(live["title"]),
        "file": live["title"],
        "title": live["title"].rsplit(".", 1)[0].replace("_", " "),
        "caption": None,
        "provider": "Wikimedia Commons",
        "author": live.get("author"),
        "license": live.get("license"),
        "license_url": live.get("license_url"),
        "kind": live.get("kind"),
        "mime": live.get("mime"),
        "thumb_url": live.get("thumb_url"),
        "file_url": live.get("file_url"),
        "page_url": live.get("page_url"),
        "width": live.get("width"),
        "height": live.get("height"),
        "anchor": None,
        "lat": None,
        "lng": None,
        "location": None,
        # Commons' own date string is free text ("Taken on 26 August 2026,
        # 10:59:51"), so it is passed through under its own name rather than
        # parsed into capture_date and pretended to be structured.
        "capture_date": None,
        "commons_date": live.get("date"),
        "available_from": None,
        "source": "commons",
        "display_order": order,
    }


@router.get("/media")
async def flood_media(
    event: str = Query(default=ACTIVE_EVENT_KEY,
                       description="Event key, e.g. trishuli-2026-08"),
):
    """Openly-licensed photography and imagery of the event, located.

    Separate from /imagery, which catalogues published analytical products at
    their publisher, and from /satellite/layers, which serves live tiles. These
    are files we can put on the screen: someone else's copyright, someone else's
    licence, and therefore an attribution obligation that travels with every one
    of them. Author and licence are on every item and are not optional to render
    for the CC BY and Attribution files.

    The two Gyirong Port frames and the Landsat aftermath lead, because they are
    the only imagery in the set that shows the destroyed border post and the
    collapse itself rather than the region around them.
    """
    live_files, ok, fetched_at = await _commons_files()
    files = dict(live_files or {})

    items = [_merge_seed(seed, files.pop(seed["file"], None), order)
             for order, seed in enumerate(_MEDIA_SEED)]
    # Anything else in the category is appended, sorted so the order is stable
    # across refreshes rather than following Commons' page ids.
    for extra in sorted(files.values(), key=lambda f: f["title"]):
        items.append(_discovered(extra, len(items)))

    return {
        "event_key": event,
        "count": len(items),
        "items": items,
        "category_url": _COMMONS_CATEGORY_URL,
        "commons_ok": ok,
        "source": "live" if ok else ("cache" if live_files else "fallback"),
        "commons_fetched_at": (
            datetime.fromtimestamp(fetched_at, tz=timezone.utc).isoformat()
            if fetched_at else None),
        "note": "Files are hosted by Wikimedia Commons and served under their "
                "own licences; author and licence must be displayed wherever a "
                "file is. Commons publishes no coordinates for any of these, so "
                "locations are the event record's own stated places and a file "
                "we did not verify by hand carries location null rather than a "
                "guess. When Commons is unreachable the hand-verified files are "
                "still returned in full, with commons_ok false.",
    }


# ---------------------------------------------------------------------------


async def _vantor_payload(event: str) -> dict:
    items, source, fetched_at = await vantor_scenes()
    return {"event_key": event, **vantor_payload_for(items, source, fetched_at)}


@router.get("/scenes")
async def flood_scenes(
    event: str = Query(default=ACTIVE_EVENT_KEY,
                       description="Event key, e.g. trishuli-2026-08"),
):
    """Vantor Open Data scenes for the event, with the pre/post pair per site.

    The display tier's commercial half. /flood/media serves Commons files we may
    show; this serves 30-50 cm scenes released under CC BY-NC 4.0, which we may
    also show — and which therefore carry the same non-optional attribution
    obligation, plus two caveats the payload states rather than leaves to the
    client: the "before" scenes are 2021-2024 archive baselines, years before the
    flood, and the post-event passes are 71-94% cloud.

    Read live from the STAC collection so a scene tasked tomorrow appears without
    a redeploy, and answered from the hand-verified manifest when S3 is not
    reachable. `source` says which happened; the pairing is the same either way.
    """
    return await _vantor_payload(event)


@router.get("/vantor")
async def flood_vantor(
    event: str = Query(default=ACTIVE_EVENT_KEY,
                       description="Event key, e.g. trishuli-2026-08"),
):
    """Alias of /flood/scenes, kept because the desk widget names the provider."""
    return await _vantor_payload(event)


@router.get("/citations")
async def flood_citations(
    event: str = Query(default=ACTIVE_EVENT_KEY,
                       description="Event key, e.g. trishuli-2026-08"),
):
    """Findings this desk cites but may not reproduce.

    The other half of the rule that governs /flood/media and /flood/scenes: those
    return files we hold a licence to display, this returns claims made in
    copyrighted coverage and rights-reserved map products. Outlet, headline, date
    where one was published, the finding in one sentence, and a link where one was
    verified — no image, no hotlink, no thumbnail.

    Static and editorial by design. Scraping news sites for this would produce a
    list nobody checked, which is the opposite of what a citation is for.
    """
    items = [{**row, "tier": "cite"} for row in CITED_REPORTING]
    return {
        "event_key": event,
        "tier": "cite",
        "count": len(items),
        "items": items,
        "note": CITE_TIER_NOTE,
    }



# ---------------------------------------------------------------------------


@router.get("/imagery-catalog")
async def flood_imagery_catalog():
    """What the DRP image service actually holds for this event.

    /flood/imagery lists analytical products published by others; this names the
    rasters behind our own before/after renders, so the desk can state what it
    is rendering rather than implying a whole-corridor mosaic. Provider,
    platform, pre/post and ground sample distance come from the Esri catalog;
    acquisition instant and cloud come from the Vantor STAC, because the
    catalog's event_start_date is the event date on every row and would read as
    sixteen scenes taken on one morning.
    """
    return await drp_service.holdings()


@router.get("/damage-sites")
async def flood_damage_sites():
    """Named damage sites with a ready-to-use before/after frame at each.

    The pixels the desk could not previously show. Each site carries curated
    ground-width frames, and each frame a pre and a post exportImage URL over an
    identical bbox at identical size — same frame of ground, one archive
    baseline and one post-surge pass, which is the comparison the whole event
    turns on at Rasuwagadhi.

    Everything a caption would claim is computed rather than assumed: which
    footprints fall in the frame, which of them the mosaic paints on top, when
    that one was acquired and how much cloud it carried, and whether the frame
    runs off the edge of coverage. A phase with nothing in view returns
    export_url null, because the service answers such a request with a fully
    transparent PNG and an HTTP 200 — a blank a client can only mistake for
    intact ground.

    The corridor below Trishuli Bazar and the collapse origin itself have no
    post-event coverage and are returned as such rather than filled in.
    """
    return await drp_service.damage_sites()


@router.get("/government")
async def flood_government():
    """Government response services and bulletins, proxied from nepal.gov.np.

    The one endpoint on this desk that answers "what do I do now" rather than
    "what happened": the rescue-request portal, the list of people already
    rescued, the blood-bank and free-health portals, the relief fund, and the
    NDRRMA command centre — plus the government's own dated updates.

    Proxied rather than fetched from the page. The host is http-origin
    sensitive, its rate limits are undocumented, and an outage there must not
    reach a family as a broken widget; the two upstream calls are cached and
    fall back independently, and `source` says per half whether the answer is
    live, a listing from within the stale grace, or the hand-verified snapshot.

    Every portal link carries the result of a live reachability probe, because
    this is the one payload where a dead link costs something. Update
    attachments are a count: nepal.gov.np publishes no URL for them, so the row
    points at the portal and no client is handed a path to guess with.
    """
    return await nepalgov_service.government()


@router.get("/gov-services")
async def flood_gov_services():
    """Alias of /flood/government, kept because the desk widget names services."""
    return await nepalgov_service.government()


@router.get("/station-photos")
async def flood_station_photos(
    affected_only: bool = Query(default=False,
                                description="Only stations in the event's districts"),
    verified_only: bool = Query(default=True,
                                description="Only stations whose photo URL served image bytes"),
    db: AsyncSession = Depends(get_db),
):
    """DHM gauge-site photographs, one per river station that has one.

    Held in our own database since the BIPAD ingest and never surfaced: 264 of
    281 stations carry an image_url. Each row is returned with the gauge's
    current alert state from the same classification /flood/rivers uses, so a
    photograph is always read next to whether that gauge is reporting — an
    offline or faulty gauge is never dressed up as a reading by a picture of it.

    Every URL is probed before it is offered and only bytes that begin with a
    real image header count, because DHM serves photographs as
    application/octet-stream and answers its newer asset route with a 401 JSON
    body; a status code alone would let an error page through as a photograph.
    Verified photographs are served from `photo_url` on this API, not from DHM:
    the upstream is http:// and would be blocked as mixed content.
    """
    stmt = select(
        RiverStation.bipad_id,
        RiverStation.title,
        RiverStation.basin,
        RiverStation.latitude,
        RiverStation.longitude,
        RiverStation.image_url,
        RiverStation.is_active,
    ).where(
        RiverStation.image_url.isnot(None),
        RiverStation.latitude.isnot(None),
        RiverStation.longitude.isnot(None),
    )
    rows = (await db.execute(stmt)).all()

    affected = await _affected_district_names(db)
    rivers = {r["station_id"]: r for r in await FloodService(db).get_rivers()}

    candidates = []
    for row in rows:
        district = district_at(row.longitude, row.latitude)
        if affected_only and district not in affected:
            continue
        candidates.append((row, district))

    verdicts = await dhm_photo_service.verdicts(
        [(row.bipad_id, row.image_url) for row, _ in candidates])

    stations = []
    for row, district in candidates:
        verdict = verdicts.get(row.bipad_id)
        gauge = rivers.get(row.bipad_id)
        stations.append({
            "bipad_id": row.bipad_id,
            "name": row.title,
            "basin": row.basin,
            "lat": row.latitude,
            "lng": row.longitude,
            "district": district,
            "in_affected_district": district in affected,
            "is_active": row.is_active,
            # Null, not false: a station whose probe has not resolved yet is
            # unknown, and unknown is not the same claim as dead.
            "verified": verdict["verified"] if verdict else None,
            "media_type": (verdict or {}).get("media_type"),
            "photo_url": f"/api/v1/flood/station-photos/{row.bipad_id}/image",
            # Provenance only. It is http:// and cannot be loaded by the desk.
            "source_url": row.image_url,
            # The gauge's own state, from /flood/rivers' classification. None
            # when the station has no reading at all rather than a cheerful zero.
            "alert": gauge["alert"] if gauge else None,
            "trend": gauge["trend"] if gauge else None,
            "water_level": gauge["water_level"] if gauge else None,
            "reading_at": gauge["reading_at"] if gauge else None,
            "stale": gauge["stale"] if gauge else None,
        })

    verified_count = sum(1 for s in stations if s["verified"])
    pending = sum(1 for s in stations if s["verified"] is None)
    if verified_only:
        stations = [s for s in stations if s["verified"]]

    stations.sort(key=lambda s: (not s["in_affected_district"], s["name"] or ""))
    return {
        "count": len(stations),
        "candidate_count": len(candidates),
        "verified_count": verified_count,
        "probe_pending": pending,
        "affected_districts": sorted(affected),
        "stations": stations,
        "attribution": dhm_photo_service.ATTRIBUTION,
        "note": "Photographs are DHM's own gauge-site images, held in this "
                "database from the BIPAD Portal ingest. They are undated: DHM "
                "publishes no capture time with them, so none is shown and none "
                "should be read as an image of this flood. A station is listed "
                "as verified only when its URL returned image bytes on the last "
                "probe, which is cached for six hours.",
    }


@public_router.get("/station-photos/{bipad_id}/image")
async def flood_station_photo_image(bipad_id: int, db: AsyncSession = Depends(get_db)):
    """The photograph itself, proxied.

    The only URL the frontend ever puts in an <img>. Upstream is http:// and
    labels every file application/octet-stream, so this is where the scheme is
    fixed and the real media type is determined; anything that is not image
    bytes 404s rather than reaching the browser as a broken icon.
    """
    stmt = select(RiverStation.image_url).where(RiverStation.bipad_id == bipad_id)
    url = (await db.execute(stmt)).scalar_one_or_none()
    if not url:
        raise HTTPException(status_code=404, detail="No photograph for this station")

    fetched = await dhm_photo_service.fetch(url)
    if not fetched:
        raise HTTPException(status_code=404,
                            detail="Upstream did not return image bytes")
    body, media_type = fetched
    return Response(
        content=body,
        media_type=media_type,
        headers={
            "Cache-Control": "public, max-age=86400",
            # ASCII only: header values are latin-1 on the wire and the
            # attribution string's middot garbles in a UTF-8 client.
            "X-Attribution": "DHM gauge-site photograph via BIPAD Portal",
        },
    )


# ---------------------------------------------------------------------------
# Live official feeds (NDRRMA / OPMCM), mirrored by FloodLiveSyncService.
# ---------------------------------------------------------------------------


@router.get("/live")
async def flood_live(
    event: str = Query(default=ACTIVE_EVENT_KEY,
                       description="Event key, e.g. trishuli-2026-08"),
    db: AsyncSession = Depends(get_db),
):
    """The last good payload from each official live feed, with its own age.

    Each feed carries its own `fetched_at` and `ok` rather than one page-level
    timestamp, because they fail independently: the OPMCM portal can be down
    while NDRRMA's rescue register is current, and a single freshness stamp
    would present the stale one as though it were as new as the live one.

    A failed poll leaves the previous payload in place with `ok` false. That is
    deliberate — the figures are stale, not gone, and blanking the panel would
    imply the response itself had stopped.
    """
    rows = list((await db.execute(
        select(FloodLiveSnapshot).where(FloodLiveSnapshot.event_key == event)
    )).scalars().all())

    feeds: dict[str, Any] = {}
    for row in rows:
        feeds[row.feed] = {
            "ok": row.ok,
            "fetched_at": row.fetched_at.isoformat() if row.fetched_at else None,
            "error": row.error,
            "payload": row.payload,
        }

    stamps = [r.fetched_at for r in rows if r.fetched_at]
    return {
        "event_key": event,
        "synced_at": max(stamps).isoformat() if stamps else None,
        "feeds": feeds,
    }


@router.get("/sitreps")
async def flood_sitreps(
    event: str = Query(default=ACTIVE_EVENT_KEY,
                       description="Event key, e.g. trishuli-2026-08"),
    db: AsyncSession = Depends(get_db),
):
    """NDRRMA's situation reports for the event, newest first.

    `extracted` is our reading of the PDF, not the authority's own structured
    data — NDRRMA publishes none. It is null on every report whose figures did
    not parse, which is most of the Nepali series: those PDFs extract with
    broken conjuncts, so the document is listed and linked and nothing is
    claimed from it. A missing key is a figure the report did not print.
    """
    rows = list((await db.execute(
        select(FloodSitrep)
        .where(FloodSitrep.event_key == event)
        .order_by(FloodSitrep.report_date.desc().nullslast(),
                  FloodSitrep.source_id.desc())
    )).scalars().all())

    items = [
        {
            "id": str(row.id),
            "source_id": row.source_id,
            "number": row.number,
            "lang": row.lang,
            "title": row.title,
            "title_ne": row.title_ne,
            "report_date": row.report_date.isoformat() if row.report_date else None,
            "report_time": row.report_time,
            "pdf_url": row.pdf_url,
            "page_url": row.page_url or "https://ndrrma.gov.np/np/rasuwa/situation",
            # An empty dict means "we opened it and nothing parsed"; the desk
            # should read that as no figures, so it is normalised to null here.
            "extracted": row.extracted or None,
            "fetched_at": row.fetched_at.isoformat() if row.fetched_at else None,
        }
        for row in rows
    ]
    return {"event_key": event, "count": len(items), "items": items}


@router.get("/photos")
async def flood_photos(
    event: str = Query(default=ACTIVE_EVENT_KEY,
                       description="Event key, e.g. trishuli-2026-08"),
    db: AsyncSession = Depends(get_db),
):
    """Photographs of the event, each with the terms it may be shown under.

    Two different things, and `licence_tier` is what separates them. Government
    photographs from the OPMCM rescue portal and NDRRMA press notes are
    published for redistribution and are tier `display`: they render full size
    with their credit. A news outlet's photograph is tier `link_preview` and is
    not ours to reproduce — it renders as a small thumbnail beside the outlet's
    name and a link back to their page, which is a citation, not a copy.

    `image_url` always points at this API, never upstream: several sources are
    http-only or CORS-restricted, and the proxy is also where the byte cap and
    the private-address check live.
    """
    rows = list((await db.execute(
        select(FloodMediaItem)
        .where(FloodMediaItem.event_key == event, FloodMediaItem.is_active.is_(True))
    )).scalars().all())

    # Government photographs lead in their published order; press leads follow,
    # newest first, because their value is recency rather than sequence.
    govt = sorted((r for r in rows if r.kind == "govt_photo"),
                  key=lambda r: (r.display_order, r.title or ""))
    leads = sorted((r for r in rows if r.kind != "govt_photo"),
                   key=lambda r: (r.published_at is None,
                                  -(r.published_at.timestamp() if r.published_at else 0)))

    items = [
        {
            "id": str(row.id),
            "source": row.source,
            "kind": row.kind,
            "title": row.title,
            "title_ne": row.title_ne,
            "caption": row.caption,
            "credit": row.credit,
            "outlet": row.outlet,
            "page_url": row.page_url,
            "image_url": f"/api/v1/flood/photos/{row.id}/image",
            "licence_tier": row.licence_tier,
            "published_at": row.published_at.isoformat() if row.published_at else None,
        }
        for row in (govt + leads)
    ]
    return {"event_key": event, "count": len(items), "items": items}


# id -> (bytes, media_type, cached_at). Bounded and hourly: these are a few
# dozen photographs on one event, not a general-purpose image cache.
_PHOTO_CACHE: dict[str, tuple[bytes, str, float]] = {}
_PHOTO_CACHE_TTL = 3600.0
_PHOTO_CACHE_MAX = 64
_PHOTO_MAX_BYTES = 8 * 1024 * 1024


def _is_public_host(host: str) -> bool:
    """False for anything that resolves into a private or loopback range.

    This proxy fetches a URL that came out of the database, and the rows are
    written by an ingest job reading third-party feeds. That is close enough to
    user-controlled to matter: without this check a crafted upstream URL would
    turn the endpoint into a probe of everything reachable from inside the
    cluster.
    """
    import ipaddress
    import socket

    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    if not infos:
        return False
    for info in infos:
        address = info[4][0]
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            return False
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            return False
    return True


@public_router.get("/photos/{photo_id}/image")
async def flood_photo_image(photo_id: str, db: AsyncSession = Depends(get_db)):
    """The photograph itself, proxied from the URL stored for that id.

    Only ids present in `flood_media_items` are ever fetched — the endpoint
    takes an id, never a URL, so it cannot be pointed at an arbitrary host.
    """
    cached = _PHOTO_CACHE.get(photo_id)
    if cached and (time.time() - cached[2]) < _PHOTO_CACHE_TTL:
        return Response(content=cached[0], media_type=cached[1],
                        headers={"Cache-Control": "public, max-age=3600"})

    try:
        from uuid import UUID as _UUID

        key = _UUID(photo_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=404, detail="No such photograph")

    row = (await db.execute(
        select(FloodMediaItem).where(FloodMediaItem.id == key)
    )).scalar_one_or_none()
    if row is None or not row.image_url:
        raise HTTPException(status_code=404, detail="No such photograph")

    from urllib.parse import urlparse

    parsed = urlparse(row.image_url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise HTTPException(status_code=404, detail="Unusable upstream URL")
    if not await asyncio.to_thread(_is_public_host, parsed.hostname):
        logger.warning("Refused flood photo proxy to non-public host %s",
                       parsed.hostname)
        raise HTTPException(status_code=404, detail="Upstream host not permitted")

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            async with client.stream(
                "GET", row.image_url,
                headers={"User-Agent": "NepalOSINT/5.0 (flood desk; "
                                       "+https://nepalosint.com)"},
            ) as response:
                response.raise_for_status()
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > _PHOTO_MAX_BYTES:
                        raise HTTPException(
                            status_code=502,
                            detail="Upstream image exceeds the 8MB cap")
                media_type = (response.headers.get("content-type") or "").split(";")[0]
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("Flood photo proxy failed for %s: %s", row.image_url, exc)
        raise HTTPException(status_code=502, detail="Upstream did not serve the image")

    if not media_type.startswith("image/"):
        # Some of these hosts answer an expired asset with an HTML error page.
        # A non-image body reaching the browser would render as a broken icon
        # with no explanation, so it 502s instead.
        media_type = row.content_type or ""
        if not media_type.startswith("image/"):
            raise HTTPException(status_code=502,
                                detail="Upstream did not return image bytes")

    if len(_PHOTO_CACHE) >= _PHOTO_CACHE_MAX:
        oldest = min(_PHOTO_CACHE, key=lambda k: _PHOTO_CACHE[k][2])
        _PHOTO_CACHE.pop(oldest, None)
    _PHOTO_CACHE[photo_id] = (bytes(body), media_type, time.time())

    return Response(content=bytes(body), media_type=media_type,
                    headers={"Cache-Control": "public, max-age=3600"})


@router.get("/press")
async def flood_press(
    event: str = Query(default=ACTIVE_EVENT_KEY,
                       description="Event key, e.g. trishuli-2026-08"),
    hours: int = Query(default=72, ge=1, le=720,
                       description="Publication window in hours"),
    limit: int = Query(default=40, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Recent news coverage of the event, with a thumbnail where one exists.

    `image_url` is non-null only when a press-lead media row was stored for
    that story, and it points at this API's proxy rather than the outlet's CDN.
    The image is a link preview: it belongs to the outlet, and the desk renders
    it small, credited, and linked back to their page.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    stories = list((await db.execute(
        select(Story)
        .where(Story.published_at.is_not(None), Story.published_at >= cutoff)
        .order_by(Story.published_at.desc())
        .limit(400)
    )).scalars().all())

    matched = []
    for story in stories:
        haystack = " ".join(filter(None, [
            story.title or "", story.summary or "",
            " ".join(story.districts or []) if story.districts else "",
        ])).lower()
        if any(term in haystack for term in FLOOD_TERMS):
            matched.append(story)
        if len(matched) >= limit:
            break

    leads = {
        row.source_id: row for row in (await db.execute(
            select(FloodMediaItem).where(
                FloodMediaItem.event_key == event,
                FloodMediaItem.source == "press_lead",
                FloodMediaItem.is_active.is_(True))
        )).scalars().all()
    }

    items = []
    for story in matched:
        lead = leads.get(str(story.id))
        items.append({
            "id": str(story.id),
            "title": story.title,
            "outlet": story.source_name or story.source_id,
            "url": story.url,
            "published_at": (story.published_at.isoformat()
                             if story.published_at else None),
            "image_url": (f"/api/v1/flood/photos/{lead.id}/image" if lead else None),
            "districts": story.districts or [],
        })

    return {"event_key": event, "count": len(items), "items": items}


# The replay payload is the heaviest read on the desk (five queries plus the
# imagery catalogue) and identical for every viewer for a minute at a time, so
# one assembled copy is served to everyone who asks within that minute.
_REPLAY_TTL_SECONDS = 60
_replay_cache: dict[str, Any] = {}


@router.get("/sites")
async def flood_sites(
    event: str = Query(default=ACTIVE_EVENT_KEY, description="Event key"),
    db: AsyncSession = Depends(get_db),
):
    """Response sites for the impact map: burial grounds, DNA hubs, mortuaries,
    transfer points, recovery reaches, the highway cut, the airhead, and the
    flooded tunnels (from the tunnel ledger). Every figure names its document;
    photographs are matched by caption and say so. Cached five minutes.
    """
    return await flood_sites_service.sites(db, event)


@router.get("/assistance")
async def flood_assistance(days: int = Query(default=10, ge=1, le=60,
                                             description="Press-scan window")):
    """International assistance board: per-country teams, materials, money and
    flights read from named documents; the newest MoFA briefing's tunnel and
    forensic sentences matched to countries automatically; IFRC GO personnel,
    surge alerts and appeal figures; press mentions from the story store.
    Nothing is summed across currencies. Cached five minutes in-process.
    """
    return await flood_assistance_service.assistance(days=days)


@router.get("/hydropower")
async def flood_hydropower(days: int = Query(default=12, ge=1, le=60,
                                             description="Press-scan window")):
    """The tunnel-rescue ledger: every hydropower project on the corridor with
    the figures, teams and notes read from named documents, the newest MoFA
    press briefing's tunnel and forensic sections parsed automatically, and
    press mentions scanned from the story store. Figures nobody has published
    are absent, never zero. Cached five minutes in-process.
    """
    return await flood_hydropower_service.hydropower(days=days)


@router.get("/replay")
async def flood_replay(
    event: str = Query(default=ACTIVE_EVENT_KEY,
                       description="Event key, e.g. trishuli-2026-08"),
    db: AsyncSession = Depends(get_db),
):
    """The 3D operational replay: the event's script, merged with the live desk.

    One request backs the whole widget, because a replay assembled from six
    calls can show a front position from one clock beside a toll from another.
    The script — places, front keyframes, beats, camera, toll marks — is read
    from a data file so no coordinate, date or figure is ever typed into a
    widget; everything else is pulled from the same services the neighbouring
    handlers use, so the replay cannot disagree with the district map, the
    chronology or the toll trajectory sitting next to it.

    What is merged, and how, is stated in the payload rather than assumed:
    `toll_merge` names which marks came from the live official series and which
    the script contributed, and every keyframe carries the confidence that says
    whether a client may draw the front there solid or must draw it dashed.

    503 if the script file is missing or malformed — a half-read timeline would
    animate a story nobody published.
    """
    cached = _replay_cache.get(event)
    if cached and (time.time() - cached["at"]) < _REPLAY_TTL_SECONDS:
        return cached["payload"]

    try:
        script = flood_replay_service.load_script()
    except flood_replay_service.ReplayScriptError as exc:
        logger.error("flood replay script rejected: %s", exc)
        raise HTTPException(
            status_code=503,
            detail=f"Replay script unavailable: {exc}",
        ) from exc

    # The imagery catalogue is HTTP-backed and independent of the session; the
    # rest share one AsyncSession and must run in sequence, since a single
    # connection cannot serve two queries at once.
    damage_task = asyncio.create_task(drp_service.damage_sites())
    try:
        geo = await flood_district_geo(event=event, db=db)
        chronology = await FloodIntelService(db).get_chronology(event)
        official = await OfficialTollService(db).get_event(event)
        stations = await FloodService(db).get_rivers()
    except Exception:
        damage_task.cancel()
        raise
    damage = await damage_task

    payload = flood_replay_service.build_payload(
        script=script,
        geo=geo,
        damage=damage,
        chronology=chronology,
        official=official,
        stations=stations,
    )
    _replay_cache[event] = {"at": time.time(), "payload": payload}
    return payload
