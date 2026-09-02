"""Point-in-polygon district lookup for Nepal's 77 districts.

Why this exists: BIPAD's incident payload gives ward ids and a GPS point, but
no district *name* — and the incident parser was assigning `street_address`
(e.g. "Jalbire") to the `district` column, so district rollups were meaningless.
Rescue coordination is organised by district, so the flood desk needs it right.

The polygons come from the same reference geojson the geoint workstation uses
(77 MultiPolygon features, WGS84). Lookup is a plain even-odd ray cast with a
bounding-box pre-filter — no geo dependency, and fast enough that callers can
resolve a whole page of incidents without thinking about it.
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

GEOJSON_PATH = Path(__file__).resolve().parent / "geo" / "nepal-districts.geojson"

# Nepal's bounding box; anything outside cannot be in a district and skips the
# whole scan. Generous on purpose — the ray cast is the real authority.
_NEPAL_BBOX = (79.5, 26.0, 89.0, 31.0)  # (min_lon, min_lat, max_lon, max_lat)


class _District:
    __slots__ = ("name", "province", "rings", "bbox")

    def __init__(self, name: str, province: Optional[str], rings: list[list[tuple[float, float]]]):
        self.name = name
        self.province = province
        self.rings = rings
        lons = [pt[0] for ring in rings for pt in ring]
        lats = [pt[1] for ring in rings for pt in ring]
        self.bbox = (min(lons), min(lats), max(lons), max(lats)) if lons else (0.0, 0.0, 0.0, 0.0)


def _rings_of(geometry: dict) -> list[list[tuple[float, float]]]:
    """Flatten a Polygon/MultiPolygon into a list of exterior rings.

    Interior rings (holes) are ignored: Nepal's district boundaries have none
    that matter at this scale, and treating a hole as solid is safer than
    dropping a district.
    """
    gtype = geometry.get("type")
    coords = geometry.get("coordinates") or []
    rings: list[list[tuple[float, float]]] = []
    if gtype == "Polygon":
        if coords:
            rings.append([(float(x), float(y)) for x, y in coords[0]])
    elif gtype == "MultiPolygon":
        for polygon in coords:
            if polygon:
                rings.append([(float(x), float(y)) for x, y in polygon[0]])
    return rings


@lru_cache(maxsize=1)
def _districts() -> list[_District]:
    try:
        data = json.loads(GEOJSON_PATH.read_text())
    except (OSError, ValueError) as exc:
        logger.error("District geojson unavailable (%s); district lookup disabled", exc)
        return []

    out: list[_District] = []
    for feature in data.get("features", []):
        props = feature.get("properties") or {}
        name = props.get("name")
        rings = _rings_of(feature.get("geometry") or {})
        if name and rings:
            out.append(_District(name, props.get("province"), rings))
    logger.info("Loaded %d district polygons", len(out))
    return out


def _in_ring(lon: float, lat: float, ring: list[tuple[float, float]]) -> bool:
    """Even-odd ray cast: is (lon, lat) inside this ring?"""
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > lat) != (yj > lat):
            # x coordinate where edge (i,j) crosses the horizontal line at lat
            x_cross = (xj - xi) * (lat - yi) / (yj - yi) + xi
            if lon < x_cross:
                inside = not inside
        j = i
    return inside


def district_at(lon: Optional[float], lat: Optional[float]) -> Optional[str]:
    """District name containing this point, or None if outside Nepal/unknown."""
    if lon is None or lat is None:
        return None
    min_lon, min_lat, max_lon, max_lat = _NEPAL_BBOX
    if not (min_lon <= lon <= max_lon and min_lat <= lat <= max_lat):
        return None

    for district in _districts():
        bl, bb, br, bt = district.bbox
        if not (bl <= lon <= br and bb <= lat <= bt):
            continue
        if any(_in_ring(lon, lat, ring) for ring in district.rings):
            return district.name
    return None


def province_of(district_name: Optional[str]) -> Optional[str]:
    """Province name for a district, or None if the district is unknown."""
    if not district_name:
        return None
    for district in _districts():
        if district.name == district_name:
            return district.province
    return None


def all_district_names() -> list[str]:
    return sorted(d.name for d in _districts())


# Serving geometry to a browser is a different job from point-in-polygon, and
# the raw file is not shaped for it: 77 districts at full float precision is
# ~1.0 MB, and the nine districts this event touches are still 129 KB. Every
# coordinate is stored to 15 significant figures, which is ~1e-10 degrees —
# roughly a hundredth of a millimetre on the ground. Truncating to 5 decimals
# (~1.1 m at this latitude) halves the payload and cannot move a district
# boundary by a visible pixel at any zoom Leaflet will render.
#
# Deliberately NOT vertex simplification: no Douglas-Peucker, no dropped
# points. Every vertex in the reference file survives, so the served boundary
# is the Survey Department boundary and not a smoothed approximation of it.
COORD_DECIMALS = 5


def _round_coords(node):
    if isinstance(node, list):
        return [_round_coords(child) for child in node]
    return round(node, COORD_DECIMALS)


@lru_cache(maxsize=1)
def _features_by_name() -> dict:
    """All 77 district features keyed by name, coordinates precision-trimmed."""
    try:
        data = json.loads(GEOJSON_PATH.read_text())
    except (OSError, ValueError) as exc:
        logger.error("District geojson unavailable (%s); geometry serving disabled", exc)
        return {}

    out: dict = {}
    for feature in data.get("features", []):
        props = feature.get("properties") or {}
        name = props.get("name")
        geometry = feature.get("geometry") or {}
        if not name or not geometry.get("coordinates"):
            continue
        out[name] = {
            "properties": dict(props),
            "geometry": {
                "type": geometry.get("type"),
                "coordinates": _round_coords(geometry["coordinates"]),
            },
        }
    return out


def district_geometry(name: Optional[str]) -> Optional[dict]:
    """Geometry + reference properties for one district, or None if unknown.

    The returned dict is the cached object; callers must copy before mutating.
    """
    if not name:
        return None
    return _features_by_name().get(name)
