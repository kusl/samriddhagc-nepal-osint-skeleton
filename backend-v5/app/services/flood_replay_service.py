"""The animation script behind the 3D operational replay, plus its live merge.

The replay widget draws WHAT happened, WHEN and WHERE. Every fact it animates
has to be traceable to something somebody published, so the script itself is a
data file (``app/data/flood_replay_trishuli_2026.json``) rather than code, and
this module does exactly three things with it:

1. **Reads it, cached on mtime.** The file is read-only input: nothing here
   writes it, and a redeploy is not needed to correct a beat — touching the
   file is enough, the next request picks it up.
2. **Validates it on load.** A malformed script must fail loudly at the API
   boundary (503 with the reason) rather than reach the map as a half-drawn
   timeline. A keyframe pointing at a place that does not exist, a beat with no
   source URL, a timestamp that will not parse — each is named, with its index.
3. **Merges it with what the desk holds live.** The script's toll marks were
   transcribed from bulletins; the same figures also arrive through the toll
   pipeline as ``official.trajectory``. Where the two meet, the live published
   series wins, because that is the one a new bulletin updates.

Nothing in here queries the database. The route gathers the live pieces from
the services the other flood handlers already use and hands them to
:func:`build_payload`, which is pure assembly — so the merge rules are
testable, and the replay can never disagree with the widgets it sits beside.
"""
from __future__ import annotations

import json
import logging
import math
import re
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

NPT = timezone(timedelta(hours=5, minutes=45))

SCRIPT_PATH = (Path(__file__).resolve().parent.parent
               / "data" / "flood_replay_trishuli_2026.json")

# The corridor's own box, from the contract: the Lhende/Bhote Koshi/Trishuli/
# Narayani run from the Tibet border down to the Terai. A gauge outside it is
# not reporting on this flood, whatever its basin says.
CORRIDOR_BBOX = {"lat_min": 27.4, "lat_max": 28.4, "lng_min": 84.3, "lng_max": 85.8}

# ...except downstream: the Narayani carries this surge out of the box, and a
# station on it belongs in the picture wherever it stands.
_BASIN_RE = re.compile(r"narayani", re.I)

# A DHM gauge and the script's gauge place are the same structure named twice.
# Matched by distance, not by name — the bulletin, the station registry and the
# script spell these places three ways — and only when they are close enough
# that no other station could be meant.
GAUGE_MATCH_KM = 4.0

_ROLES = {"origin", "corridor", "impact", "response", "gauge", "district"}
_CONFIDENCE = {"published", "derived", "estimated"}


class ReplayScriptError(RuntimeError):
    """The script file is missing, unreadable, or does not hold a valid replay."""


# --------------------------------------------------------------- file loading

_cache_lock = threading.Lock()
_cache: Optional[tuple[tuple[str, int, int], dict[str, Any]]] = None


def load_script(path: Path = SCRIPT_PATH) -> dict[str, Any]:
    """The validated script, re-read only when the file on disk changes.

    Keyed on (path, mtime_ns, size) so an edit that lands inside the same clock
    tick still invalidates, and a second script cannot answer for the first.
    Raises :class:`ReplayScriptError` — never returns a partially-valid script,
    because a timeline missing its middle is worse than no timeline at all.
    """
    global _cache

    try:
        stat = path.stat()
    except OSError as exc:
        raise ReplayScriptError(f"replay script not readable at {path.name}: {exc}") from exc

    stamp = (str(path), stat.st_mtime_ns, stat.st_size)
    with _cache_lock:
        if _cache is not None and _cache[0] == stamp:
            return _cache[1]

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReplayScriptError(f"replay script {path.name} is not valid JSON: {exc}") from exc

    script = validate(raw)
    with _cache_lock:
        _cache = (stamp, script)
    logger.info("flood replay script loaded: %s keyframes, %s beats, %s places",
                len(script["keyframes"]), len(script["beats"]), len(script["places"]))
    return script


# ----------------------------------------------------------------- validation

def _parse_npt(value: Any, where: str) -> datetime:
    if not isinstance(value, str):
        raise ReplayScriptError(f"{where}: t_npt must be a string, got {type(value).__name__}")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ReplayScriptError(f"{where}: t_npt {value!r} is not an ISO timestamp ({exc})") from exc
    if parsed.tzinfo is None:
        raise ReplayScriptError(f"{where}: t_npt {value!r} carries no UTC offset; "
                                "a clock without a zone is not a time")
    return parsed


def _require(record: Any, fields: tuple[str, ...], where: str) -> None:
    if not isinstance(record, dict):
        raise ReplayScriptError(f"{where}: expected an object, got {type(record).__name__}")
    missing = [f for f in fields if record.get(f) in (None, "")]
    if missing:
        raise ReplayScriptError(f"{where}: missing {', '.join(missing)}")


def _num(value: Any, where: str, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ReplayScriptError(f"{where}: {field} must be a number, got {value!r}")
    return float(value)


def validate(raw: Any) -> dict[str, Any]:
    """Return the script with its sequences sorted, or raise with the reason.

    Every check names the offending record. "Invalid replay script" on its own
    would send whoever edits the lore hunting through 55 KB of JSON.
    """
    if not isinstance(raw, dict):
        raise ReplayScriptError(f"top level must be an object, got {type(raw).__name__}")

    for key in ("event_key", "title", "t0_npt", "t_end_npt"):
        if not raw.get(key):
            raise ReplayScriptError(f"missing {key}")
    for key in ("places", "keyframes", "beats", "camera", "toll_marks", "sources"):
        if not isinstance(raw.get(key), list):
            raise ReplayScriptError(f"{key} must be a list")
    if not raw["keyframes"]:
        raise ReplayScriptError("keyframes is empty: there is no front to animate")
    if not raw["places"]:
        raise ReplayScriptError("places is empty: nothing can be positioned")

    t0 = _parse_npt(raw["t0_npt"], "t0_npt")
    t_end = _parse_npt(raw["t_end_npt"], "t_end_npt")
    if t_end <= t0:
        raise ReplayScriptError(f"t_end_npt ({raw['t_end_npt']}) is not after "
                                f"t0_npt ({raw['t0_npt']})")

    places: dict[str, dict[str, Any]] = {}
    for i, place in enumerate(raw["places"]):
        where = f"places[{i}]"
        _require(place, ("key", "name", "role"), where)
        _num(place.get("lat"), where, "lat")
        _num(place.get("lng"), where, "lng")
        if place["key"] in places:
            raise ReplayScriptError(f"{where}: duplicate place key {place['key']!r}")
        if place["role"] not in _ROLES:
            raise ReplayScriptError(f"{where}: role {place['role']!r} is not one of "
                                    f"{', '.join(sorted(_ROLES))}")
        if place.get("km") is not None:
            _num(place["km"], where, "km")
        places[place["key"]] = place

    for i, kf in enumerate(raw["keyframes"]):
        where = f"keyframes[{i}]"
        _require(kf, ("t_npt", "place_key", "confidence", "source", "source_url"), where)
        _parse_npt(kf["t_npt"], where)
        _num(kf.get("km"), where, "km")
        if kf["place_key"] not in places:
            raise ReplayScriptError(f"{where}: place_key {kf['place_key']!r} is not in places")
        if kf["confidence"] not in _CONFIDENCE:
            raise ReplayScriptError(f"{where}: confidence {kf['confidence']!r} is not one of "
                                    f"{', '.join(sorted(_CONFIDENCE))}")

    for i, beat in enumerate(raw["beats"]):
        where = f"beats[{i}]"
        _require(beat, ("t_npt", "kind", "headline", "source", "source_url"), where)
        _parse_npt(beat["t_npt"], where)
        if not isinstance(beat.get("time_published"), bool):
            raise ReplayScriptError(f"{where}: time_published must be true or false")
        if beat.get("place_key") and beat["place_key"] not in places:
            raise ReplayScriptError(f"{where}: place_key {beat['place_key']!r} is not in places")
        if beat.get("confidence") and beat["confidence"] not in _CONFIDENCE:
            raise ReplayScriptError(f"{where}: confidence {beat['confidence']!r} is not one of "
                                    f"{', '.join(sorted(_CONFIDENCE))}")

    for i, shot in enumerate(raw["camera"]):
        where = f"camera[{i}]"
        _require(shot, ("t_npt", "center"), where)
        _parse_npt(shot["t_npt"], where)
        center = shot["center"]
        if not isinstance(center, (list, tuple)) or len(center) != 2:
            raise ReplayScriptError(f"{where}: center must be [lng, lat]")
        _num(center[0], where, "center[0] (lng)")
        _num(center[1], where, "center[1] (lat)")
        for field in ("zoom", "pitch", "bearing", "hold_s"):
            if shot.get(field) is not None:
                _num(shot[field], where, field)

    for i, mark in enumerate(raw["toll_marks"]):
        where = f"toll_marks[{i}]"
        _require(mark, ("t_npt", "source", "source_url"), where)
        _parse_npt(mark["t_npt"], where)
        if mark.get("deaths") is None:
            raise ReplayScriptError(f"{where}: a toll mark with no death figure marks nothing")
        for field in ("deaths", "missing", "rescued"):
            if mark.get(field) is not None:
                _num(mark[field], where, field)

    for i, source in enumerate(raw["sources"]):
        _require(source, ("label", "url"), f"sources[{i}]")

    film = raw.get("film")
    if film is not None:
        if not isinstance(film, dict) or not isinstance(film.get("scenes"), list):
            raise ValueError("film must be an object with a scenes list")
        prev_to = None
        for i, sc in enumerate(film["scenes"]):
            where = f"film.scenes[{i}]"
            _require(sc, ("key", "title", "t_from", "t_to", "duration_s"), where)
            t_from = _parse_npt(sc["t_from"], where); t_to = _parse_npt(sc["t_to"], where)
            if t_to < t_from:
                raise ValueError(f"{where}: t_to before t_from")
            if prev_to is not None and t_from < prev_to:
                raise ValueError(f"{where}: scenes must not run backwards in event time")
            prev_to = t_to
            if not (sc.get("camera") or sc.get("follow")):
                raise ValueError(f"{where}: needs camera or follow")
            for j, n in enumerate(sc.get("narration") or []):
                if "beat" in n:
                    if not isinstance(n["beat"], int) or n["beat"] < 0 or n["beat"] >= len(raw["beats"]):
                        raise ValueError(f"{where}.narration[{j}]: beat index out of range")
                elif not (n.get("text") and n.get("source_url")):
                    raise ValueError(f"{where}.narration[{j}]: free text needs source_url")
            for j, c in enumerate(sc.get("cards") or []):
                if c.get("kind") not in ("commons", "video", "photo", "vantor", "cite", "end"):
                    raise ValueError(f"{where}.cards[{j}]: unknown kind")

    script = dict(raw)
    script["places"] = list(raw["places"])
    for key in ("keyframes", "beats", "camera", "toll_marks"):
        script[key] = sorted(raw[key], key=lambda r: _parse_npt(r["t_npt"], key))
    return script


# ------------------------------------------------------------------ geography

def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def in_corridor(lat: Optional[float], lng: Optional[float]) -> bool:
    if lat is None or lng is None:
        return False
    return (CORRIDOR_BBOX["lat_min"] <= lat <= CORRIDOR_BBOX["lat_max"]
            and CORRIDOR_BBOX["lng_min"] <= lng <= CORRIDOR_BBOX["lng_max"])


def select_gauges(stations: list[dict[str, Any]],
                  places: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The gauges that watch this corridor, tied to the script where they match.

    Two admissions, either of which puts a station in: it stands inside the
    corridor box, or it is on the Narayani, which carries the surge past the
    box's southern edge. ``corridor_km`` is attached only when a script gauge
    place sits within :data:`GAUGE_MATCH_KM` — a derived join, labelled as such,
    never a distance invented for a station nobody placed.
    """
    gauge_places = [p for p in places if p.get("role") == "gauge" and p.get("km") is not None]

    out: list[dict[str, Any]] = []
    for station in stations:
        lat, lng = station.get("lat"), station.get("lon")
        by_box = in_corridor(lat, lng)
        by_basin = bool(_BASIN_RE.search(station.get("basin") or ""))
        if not (by_box or by_basin):
            continue

        matched: Optional[dict[str, Any]] = None
        distance: Optional[float] = None
        if lat is not None and lng is not None:
            for place in gauge_places:
                d = _haversine_km(lat, lng, place["lat"], place["lng"])
                if d <= GAUGE_MATCH_KM and (distance is None or d < distance):
                    matched, distance = place, d

        out.append({
            **station,
            "in_corridor_bbox": by_box,
            "narayani_basin": by_basin,
            # Which of the script's gauge places this station is, if any.
            "place_key": matched["key"] if matched else None,
            "corridor_km": matched.get("km") if matched else None,
            "match_distance_km": round(distance, 2) if distance is not None else None,
        })

    out.sort(key=lambda s: (s.get("corridor_km") is None, s.get("corridor_km") or 0,
                            s.get("name") or ""))
    return out


# ----------------------------------------------------------------- toll merge

def merge_toll_marks(marks: list[dict[str, Any]],
                     trajectory: list[dict[str, Any]],
                     authority: Optional[str] = None) -> dict[str, Any]:
    """The script's timed toll marks reconciled with the live official series.

    The script carries clocks the trajectory does not: NDRRMA published 987 dead
    at 09:00 on 1 September and 1,050 on the 18:00 board the same day, and a
    replay that steps by date can only show one of them. So the marks keep the
    timeline's shape, and the live series — the one a new bulletin updates —
    wins on the figures:

    * a day the trajectory holds and the script does not is added at 09:00 NPT;
    * a day both hold keeps the script's clocks, and if the day's last mark
      disagrees with the trajectory it is overwritten and flagged ``superseded``
      with what the script had said;
    * a day only the script holds is kept and flagged ``script`` — the desk
      transcribed a bulletin the toll pipeline has not ingested.

    Nothing is interpolated: a day nobody published stays absent.
    """
    by_day: dict[str, list[dict[str, Any]]] = {}
    for mark in marks:
        record = {**mark, "origin": "script", "confidence": "published"}
        by_day.setdefault(mark["t_npt"][:10], []).append(record)

    official_days: set[str] = set()
    superseded = 0
    added = 0

    for row in trajectory:
        day = str(row.get("as_of") or "")[:10]
        if not day or row.get("deaths") is None:
            continue
        official_days.add(day)
        same_day = by_day.get(day)
        if not same_day:
            by_day[day] = [{
                "t_npt": f"{day}T09:00:00+05:45",
                "deaths": row.get("deaths"),
                "missing": row.get("missing"),
                "source": (f"{authority} situation update, {day} "
                           "(desk official toll series)" if authority
                           else f"Official toll series, {day}"),
                "source_url": None,
                "note": "Clock not published with this figure; placed at 09:00 NPT, "
                        "the hour the authority's daily update carries.",
                "origin": "official",
                "confidence": "published",
            }]
            added += 1
            continue

        last = same_day[-1]
        if last.get("deaths") == row.get("deaths") and last.get("missing") == row.get("missing"):
            last["origin"] = "script+official"
            continue
        # The live series wins, and says so rather than quietly replacing.
        last["superseded"] = {"deaths": last.get("deaths"), "missing": last.get("missing"),
                              "source": last.get("source")}
        last["deaths"] = row.get("deaths")
        if row.get("missing") is not None:
            last["missing"] = row.get("missing")
        last["origin"] = "official"
        superseded += 1

    merged = sorted((m for day in by_day.values() for m in day), key=lambda m: m["t_npt"])
    script_only = sorted({m["t_npt"][:10] for m in merged if m["origin"] == "script"}
                         - official_days)

    return {
        "marks": merged,
        "merge": {
            "rule": "The live official toll series wins on figures; the script "
                    "supplies the clocks it publishes and any bulletin the toll "
                    "pipeline has not ingested. No day is interpolated.",
            "official_days": len(official_days),
            "script_marks": len(marks),
            "added_from_official": added,
            "superseded_by_official": superseded,
            "script_only_days": script_only,
            "authority": authority,
        },
    }


# -------------------------------------------------------------- payload build

# ------------------------------------------------------------------ river path

RIVER_PATH = SCRIPT_PATH.parent / "flood_river_path_trishuli_2026.json"
_river_cache: dict[str, Any] = {}

# A place further than this from the channel is not ON the channel: it keeps
# its script km (if any) and is not re-projected. Galchhi, the town, sits
# 1.5 km from the water and must still project; a district HQ must not.
RIVER_SNAP_KM = 2.5


def load_river_path(path: Path = RIVER_PATH) -> Optional[dict[str, Any]]:
    """The vendored channel (see scripts/build_river_path.py), cached on mtime.

    None when the file is absent: the replay then falls back to the schematic
    corridor between named places and says so in `river`.
    """
    try:
        st = path.stat()
    except OSError:
        return None
    key = f"{path}:{st.st_mtime_ns}:{st.st_size}"
    if _river_cache.get("key") == key:
        return _river_cache["value"]
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        verts = raw.get("vertices") or []
        if not verts or any(len(v) != 3 for v in verts):
            raise ValueError("vertices must be [lng, lat, km] triples")
        raw["_lat"] = [float(v[1]) for v in verts]
        raw["_lng"] = [float(v[0]) for v in verts]
        raw["_km"] = [float(v[2]) for v in verts]
    except (OSError, ValueError, TypeError) as exc:
        logger.warning("river path unreadable (%s): %s", path, exc)
        _river_cache.update(key=key, value=None)
        return None
    _river_cache.update(key=key, value=raw)
    return raw


def project_km(river: dict[str, Any], lat: Any, lng: Any) -> tuple[Optional[float], Optional[float]]:
    """(km along the channel, distance off the channel) for a coordinate, by
    nearest densified vertex. 100 m vertex spacing bounds the km error at 50 m."""
    if river is None or not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)):
        return None, None
    lats, lngs, kms = river["_lat"], river["_lng"], river["_km"]
    best_i, best_d = -1, float("inf")
    for i in range(len(kms)):
        d = _haversine_km(lat, lng, lats[i], lngs[i])
        if d < best_d:
            best_d, best_i = d, i
    if best_i < 0:
        return None, None
    return round(kms[best_i], 2), round(best_d, 3)


def river_corridor(river: dict[str, Any], waypoints: list[dict[str, Any]],
                   places: Optional[list[dict[str, Any]]] = None) -> list[dict[str, Any]]:
    """The channel as the corridor list the client already understands: one
    entry per densified vertex, named only where a published waypoint projects
    onto it. The origin waypoint (no km) is carried through unchanged so the
    client can still draw the collapse marker off the km axis."""
    verts = [{"name": "", "lat": lat, "lng": lng, "km": km, "kind": "channel"}
             for lat, lng, km in zip(river["_lat"], river["_lng"], river["_km"])]
    origin_entries = []
    for w in waypoints or []:
        if not isinstance(w.get("km"), (int, float)) and "origin" in str(w.get("kind", "")).lower():
            origin_entries.append(dict(w))
            continue
        km, off = project_km(river, w.get("lat"), w.get("lng"))
        if km is None or off is None or off > RIVER_SNAP_KM:
            continue
        i = min(range(len(verts)), key=lambda i: abs(verts[i]["km"] - km))
        verts[i]["name"] = w.get("name") or verts[i]["name"]
        verts[i]["kind"] = w.get("kind") or "waypoint"
        verts[i]["km_script"] = w.get("km")
    # Script places on the run (Timure, Dhunche, Mailung, Malekhu, Mugling …)
    # become anchors too, so the HUD can name where the front is between the
    # district map's own waypoints. A place within 500 m of an existing anchor
    # does not overwrite it.
    for p in places or []:
        if str(p.get("role")) not in ("impact", "corridor", "response") or not p.get("name"):
            continue
        km, off = project_km(river, p.get("lat"), p.get("lng"))
        if km is None or off is None or off > RIVER_SNAP_KM:
            continue
        i = min(range(len(verts)), key=lambda i: abs(verts[i]["km"] - km))
        near_named = any(verts[j]["name"] for j in range(max(0, i - 5), min(len(verts), i + 6)))
        if near_named:
            continue
        verts[i]["name"] = p["name"]
        verts[i]["kind"] = p.get("role") or "place"
        verts[i]["km_script"] = p.get("km")
    # The upstream end is the NDRRMA source zone: name it so the HUD can say so.
    if verts and not verts[0]["name"]:
        cut = river.get("upstream_cut") or {}
        verts[0]["name"] = "Lhende source zone (NDRRMA, ~20 km upstream)"
        verts[0]["kind"] = "source_zone"
        verts[0]["source_url"] = cut.get("source_url")
    return verts + origin_entries


def reproject_script(river: dict[str, Any], places: list[dict[str, Any]],
                     keyframes: list[dict[str, Any]], damage_sites: list[dict[str, Any]],
                     gauges: list[dict[str, Any]]) -> dict[str, Any]:
    """Re-express every km the script states as km along the real channel.

    The script's km were measured on chords between places; the channel is
    longer (Devghat is ~180 km of river from Rasuwagadhi, not 150). Every
    rewritten value keeps its script figure beside it as km_script, and the
    keyframe order is asserted to survive: a projection that reorders the
    front's fixes is a data error, not something to paper over.
    """
    by_key = {p.get("key"): p for p in places}
    out_places = []
    for p in places:
        q = dict(p)
        km, off = project_km(river, p.get("lat"), p.get("lng"))
        if km is not None and off is not None and off <= RIVER_SNAP_KM and (
                isinstance(p.get("km"), (int, float)) or str(p.get("role")) in ("origin", "corridor", "impact", "gauge")):
            q["km_script"] = p.get("km")
            q["km"] = km
            q["off_channel_km"] = off
        out_places.append(q)
    by_key = {p.get("key"): p for p in out_places}

    start_km = river["_km"][0]
    out_kf = []
    for k in keyframes:
        q = dict(k)
        place = by_key.get(k.get("place_key")) or {}
        q["km_script"] = k.get("km")
        if str(place.get("role")) == "origin" or (isinstance(k.get("km"), (int, float)) and k["km"] <= start_km):
            # The source zone is where the channel record begins; the collapse
            # marker itself sits off the channel and is drawn separately.
            q["km"] = start_km
        elif isinstance(place.get("km"), (int, float)):
            q["km"] = place["km"]
        out_kf.append(q)
    kms = [k["km"] for k in out_kf if isinstance(k.get("km"), (int, float))]
    if any(b <= a for a, b in zip(kms, kms[1:])):
        raise ValueError(f"keyframe km not increasing after river projection: {kms}")

    out_sites = []
    for site in damage_sites:
        q = dict(site)
        km, off = project_km(river, site.get("lat"), site.get("lng"))
        if km is not None and off is not None and off <= RIVER_SNAP_KM:
            q["km_mark_script"] = site.get("km_mark")
            q["km_mark"] = km
            q["off_channel_km"] = off
        out_sites.append(q)

    out_gauges = []
    for g in gauges:
        q = dict(g)
        km, off = project_km(river, g.get("lat"), g.get("lon", g.get("lng")))
        if km is not None and off is not None and off <= 1.5:
            q["corridor_km"] = km
            q["off_channel_km"] = off
        out_gauges.append(q)

    return {"places": out_places, "keyframes": out_kf, "damage_sites": out_sites, "gauges": out_gauges}


def build_payload(*, script: dict[str, Any], geo: dict[str, Any],
                  damage: dict[str, Any], chronology: list[dict[str, Any]],
                  official: dict[str, Any],
                  stations: list[dict[str, Any]]) -> dict[str, Any]:
    """The script and the live desk, assembled into one replay payload.

    Pure: everything it needs has already been fetched by the caller, which is
    what lets the merge rules above be reasoned about without a database.
    """
    places = script["places"]
    latest = (official or {}).get("latest") or {}
    tolls = merge_toll_marks(script["toll_marks"],
                             (official or {}).get("trajectory") or [],
                             authority=latest.get("authority"))

    gauges = select_gauges(stations, places)
    damage_sites = (damage or {}).get("sites") or []
    corridor = (geo or {}).get("corridor") or []
    keyframes = script["keyframes"]

    river = load_river_path()
    river_meta: dict[str, Any]
    if river is not None:
        projected = reproject_script(river, places, keyframes, damage_sites, gauges)
        places, keyframes = projected["places"], projected["keyframes"]
        damage_sites, gauges = projected["damage_sites"], projected["gauges"]
        corridor = river_corridor(river, corridor, places)
        river_meta = {
            "available": True,
            "source": river.get("source"),
            "attribution": river.get("attribution"),
            "fetched_at": river.get("fetched_at"),
            "length_km": river.get("length_km"),
            "step_m": river.get("step_m"),
            "km_range": [river["_km"][0], river["_km"][-1]],
            "upstream_cut": river.get("upstream_cut"),
            "channel_names": river.get("channel_names"),
            "osm_way_count": len(river.get("osm_way_ids") or []),
        }
    else:
        river_meta = {"available": False,
                      "note": "flood_river_path_trishuli_2026.json missing; corridor is the schematic chord path"}

    return {
        "event_key": script["event_key"],
        "title": script["title"],
        "t0_npt": script["t0_npt"],
        "t_end_npt": script["t_end_npt"],
        "notes": script.get("notes") or [],

        # ---- the script (read from the data file, never typed in a widget)
        "places": places,
        "keyframes": keyframes,
        "beats": script["beats"],
        "camera": script["camera"],
        "sources": script["sources"],
        "film": script.get("film"),

        # ---- merged with what the desk holds live
        "toll_marks": tolls["marks"],
        "toll_merge": tolls["merge"],
        "toll_latest": {
            "as_of": latest.get("as_of"),
            "authority": latest.get("authority"),
            "deaths": latest.get("deaths"),
            "missing": latest.get("missing"),
            "rescued": latest.get("rescued"),
            "source_url": latest.get("source_url"),
        } if latest else None,
        "corridor": corridor,
        "river": river_meta,
        "districts": (geo or {}).get("districts") or {"type": "FeatureCollection", "features": []},
        "toll_snapshots": (geo or {}).get("toll_snapshots") or [],
        "damage_sites": damage_sites,
        "damage_catalog": (damage or {}).get("catalog"),
        "gauges": gauges,
        "chronology": chronology or [],

        "counts": {
            "places": len(places),
            "keyframes": len(keyframes),
            "beats": len(script["beats"]),
            "camera": len(script["camera"]),
            "toll_marks": len(tolls["marks"]),
            "sources": len(script["sources"]),
            "corridor": len(corridor),
            "damage_sites": len(damage_sites),
            "gauges": len(gauges),
            "chronology": len(chronology or []),
            "districts": len(((geo or {}).get("districts") or {}).get("features") or []),
        },
        "note": (
            "The replay script is a read-only data file: every keyframe, beat "
            "and toll mark carries its own source and confidence, and the front "
            "position between two published fixes is interpolated by the client "
            "and must be drawn as estimated. Toll figures are reconciled with "
            "the live official series (see toll_merge). Gauges are the stations "
            "inside the corridor box "
            f"({CORRIDOR_BBOX['lat_min']}–{CORRIDOR_BBOX['lat_max']}N, "
            f"{CORRIDOR_BBOX['lng_min']}–{CORRIDOR_BBOX['lng_max']}E) plus the "
            "Narayani basin; corridor_km on a gauge is a derived join to the "
            "script's gauge places, not a published distance. No elevation "
            "model is served by this desk, so elev_m is whatever the script "
            "carries. When `river.available` is true the corridor is the real "
            "channel (OpenStreetMap, ODbL) densified to river.step_m, and every "
            "km — places, keyframes, damage sites, gauges — is re-expressed along "
            "it with the script's own figure kept as km_script; otherwise it is "
            "a schematic path between named places."
        ),
    }
