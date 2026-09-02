"""Async readers for the official feeds carrying the Trishuli flood response.

Every source here is a government publication or a transcription of one, and
each is fetched on its own terms rather than through a shared client, because
they disagree about almost everything: NDRRMA serves DRF-style JSON envelopes,
the OPMCM rescue portal wraps everything in ``{success, data}``, and the citizen
bulletin is a static HTML page carrying Devanagari numerals.

Two rules run through the module.

**Nothing raises past its own boundary.** Each fetcher returns ``None`` on any
failure and logs it. One ministry's outage must never stop the sync writing the
other five feeds; a live desk that goes blank because a single upstream 502'd is
worse than a desk with one stale panel.

**Filings are not people.** The OPMCM portal counts reports the public filed —
one missing person is routinely filed by several relatives, and a found person
is rarely closed — so those figures are read and stored, but never added to or
reconciled against the disaster authority's toll. That separation is enforced
at the service layer; it is stated here because this is where the numbers enter
the system.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

NDRRMA_API = "https://ndrrma.gov.np/api/v1"
OPMCM_API = "https://rescue.opmcm.gov.np/api"
OPMCM_ORIGIN = "https://rescue.opmcm.gov.np"
BULLETIN_BASE = "https://nirajbhusal.github.io/rasuwa-flood-bulletin"

USER_AGENT = "NepalOSINT/5.0 (flood desk; +https://nepalosint.com)"
TIMEOUT = 20.0

# Nepal is UTC+05:45. Every published stamp on this event is local, and the
# gap to UTC is wide enough to move a bulletin across a date boundary, so the
# offset is explicit everywhere rather than left to the host clock.
NPT = timezone(timedelta(hours=5, minutes=45))

_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")


def to_ascii_digits(value: str) -> str:
    """Devanagari numerals to ASCII, leaving everything else alone."""
    return (value or "").translate(_DEVANAGARI_DIGITS)


def parse_number(value: Optional[str]) -> Optional[int]:
    """A published figure like '१,०५०' or '2,498' as an int.

    Returns None rather than 0 when nothing numeric is present: a missing
    figure and a figure of zero are different claims, and on a casualty board
    the difference matters.
    """
    if value is None:
        return None
    digits = re.sub(r"[^0-9]", "", to_ascii_digits(str(value)))
    return int(digits) if digits else None


async def _get_json(url: str, label: str) -> Optional[Any]:
    """One GET returning parsed JSON, with a single retry, or None."""
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    for attempt in (1, 2):
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True,
                                         headers=headers) as client:
                response = await client.get(url)
                response.raise_for_status()
                return response.json()
        except Exception as exc:  # noqa: BLE001 — boundary: never propagate
            if attempt == 2:
                logger.warning("Flood feed %s failed (%s): %s", label, url, exc)
            else:
                logger.debug("Flood feed %s retrying after %s", label, exc)
    return None


async def _get_text(url: str, label: str) -> Optional[str]:
    headers = {"User-Agent": USER_AGENT}
    for attempt in (1, 2):
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True,
                                         headers=headers) as client:
                response = await client.get(url)
                response.raise_for_status()
                return response.text
        except Exception as exc:  # noqa: BLE001
            if attempt == 2:
                logger.warning("Flood feed %s failed (%s): %s", label, url, exc)
    return None


async def fetch_pdf(url: str) -> Optional[bytes]:
    """A sitrep PDF's bytes. Large files, so a longer timeout and no retry."""
    try:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True,
                                     headers={"User-Agent": USER_AGENT}) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.content
    except Exception as exc:  # noqa: BLE001
        logger.warning("Sitrep PDF fetch failed (%s): %s", url, exc)
        return None


# ---------------------------------------------------------------------------
# NDRRMA
# ---------------------------------------------------------------------------


SITREP_PUB_TYPE = "Situation Report"


async def fetch_ndrrma_sitreps(limit: int = 50) -> Optional[list[dict]]:
    """The Rasuwa situation reports, newest id first, from BOTH lists NDRRMA
    has used: the dedicated `rasuwa-sitrep` list (reports #01–#11) and, from
    2 Sep 2026, the general `publications` list filtered to the Situation
    Report type (Nepali #12, English SitRep 02 …). Merged by id."""
    data = await _get_json(
        f"{NDRRMA_API}/publication/rasuwa-sitrep/?limit={limit}&offset=0",
        "ndrrma_sitreps")
    merged: dict[int, dict] = {}
    if isinstance(data, dict) and isinstance(data.get("results"), list):
        for item in data["results"]:
            if item.get("id") is not None:
                merged[int(item["id"])] = item
    general = await _get_json(
        f"{NDRRMA_API}/publication/publications/?limit={limit}&ordering=-id",
        "ndrrma_publications")
    if isinstance(general, dict) and isinstance(general.get("results"), list):
        for item in general["results"]:
            ptype = item.get("publication_type") or {}
            if (ptype.get("pub_type") if isinstance(ptype, dict) else ptype) != SITREP_PUB_TYPE:
                continue
            title = (item.get("title") or "") + " " + (item.get("title_ne") or "")
            if not re.search(r"rasuwa|रसुवा|bhote|भोटे|sitrep", title, re.I):
                continue
            # The general list re-lists the older reports under new ids; the
            # same PDF must not become two sitreps, so the file name decides.
            pdf = (item.get("pdffile") or "").rsplit("/", 1)[-1].lower()
            known = {(x.get("pdffile") or "").rsplit("/", 1)[-1].lower() for x in merged.values()}
            norm = lambda t: re.sub(r"[\s#:;,\-_()]+", "", (t or "").lower())  # noqa: E731
            known_titles = {norm(x.get("title")) for x in merged.values()} | {norm(x.get("title_ne")) for x in merged.values()}
            if (pdf and pdf in known) or (norm(item.get("title")) in known_titles and norm(item.get("title"))):
                continue
            if item.get("id") is not None:
                merged.setdefault(int(item["id"]), item)
    if not merged:
        return None
    return [merged[k] for k in sorted(merged, reverse=True)]


async def fetch_ndrrma_rescue_stats() -> Optional[dict]:
    """NDRRMA's own rescue counters: rescued, force deployed, out of reach."""
    data = await _get_json(f"{NDRRMA_API}/rescues/rescued-statistics/?limit=-1",
                           "ndrrma_rescue")
    return data if isinstance(data, dict) else None


async def fetch_ndrrma_status_counts() -> Optional[dict]:
    """The named public rescue registry, split Nepali/foreign."""
    data = await _get_json(f"{NDRRMA_API}/rescues/status-counts/?limit=-1",
                           "ndrrma_status")
    return data if isinstance(data, dict) else None


async def fetch_ndrrma_advisories(limit: int = 5) -> Optional[list[dict]]:
    """Standing national advisories — currently the verify-before-sharing note."""
    data = await _get_json(
        f"{NDRRMA_API}/nationalbipadalerts/bipadalert/?limit={limit}",
        "ndrrma_advisory")
    if not isinstance(data, dict):
        return None
    results = data.get("results")
    return results if isinstance(results, list) else None


async def fetch_ndrrma_press_notes(since: date, limit: int = 60) -> Optional[list[dict]]:
    """Official press notes published on or after ``since``.

    Descriptions are omitted upstream: this feed is read for the headline and
    the photograph, and the full HTML body is not something the desk renders.
    """
    data = await _get_json(
        f"{NDRRMA_API}/pressnotenews/newsinfo/?omit=description,description_ne"
        f"&limit={limit}",
        "ndrrma_press")
    if not isinstance(data, dict):
        return None
    results = data.get("results")
    if not isinstance(results, list):
        return None

    kept = []
    for item in results:
        published = item.get("date")
        try:
            when = date.fromisoformat(published) if published else None
        except (TypeError, ValueError):
            when = None
        if when and when >= since:
            kept.append(item)
    return kept


# ---------------------------------------------------------------------------
# OPMCM rescue portal
# ---------------------------------------------------------------------------


async def _opmcm(path: str, label: str) -> Optional[dict]:
    data = await _get_json(f"{OPMCM_API}/{path}", label)
    if not isinstance(data, dict) or not data.get("success"):
        if data is not None:
            logger.warning("OPMCM %s returned an unsuccessful envelope", label)
        return None
    payload = data.get("data")
    return payload if isinstance(payload, dict) else None


async def fetch_opmcm_stats() -> Optional[dict]:
    """Portal counters. FILINGS, not people — see the module docstring."""
    return await _opmcm("stats", "opmcm_stats")


async def fetch_opmcm_carousel() -> Optional[list[dict]]:
    """Official Army/Police rescue photographs, with absolute image URLs."""
    payload = await _opmcm("carousel", "opmcm_carousel")
    if not payload:
        return None
    items = payload.get("items")
    if not isinstance(items, list):
        return None

    for item in items:
        url = item.get("imageUrl") or ""
        if url.startswith("/"):
            item["imageUrl"] = f"{OPMCM_ORIGIN}{url}"
    return items


async def fetch_opmcm_government_efforts(limit: int = 30) -> Optional[list[dict]]:
    """Government response actions as the portal lists them (no images)."""
    payload = await _opmcm(f"government-efforts?limit={limit}",
                           "opmcm_government_efforts")
    if not payload:
        return None
    items = payload.get("items")
    return items if isinstance(items, list) else None


# ---------------------------------------------------------------------------
# Citizen bulletin (a transcription of NDRRMA's published situation board)
# ---------------------------------------------------------------------------

# The KPI strip. Each tile is a button carrying the figure in a <strong class="num">.
# The window used to be 400 chars; on 2 Sep 2026 the bulletin put an inline
# SVG icon inside each KPI button, which is longer than that, and the desk
# stopped reading its own toll. The figure is the first <strong class="num">
# after the id, however much icon sits between them.
_KPI_RE = re.compile(
    r'id="kpi-(dead|injured|miss|air|deploy)"[\s\S]{0,2400}?'
    r'<strong class="num">([^<]*)</strong>')

# The death-by-district pane. Scoped to the ov-pane element, because the same
# data-panel="dead" attribute also appears on the KPI button above it and the
# d_* keys repeat across the injured and rescued panes.
_DEAD_PANE_RE = re.compile(r'<div class="ov-pane"[^>]*data-panel="dead"[^>]*>')
_DISTRICT_ROW_RE = re.compile(
    r'<span data-i18n="(d_[a-z_]+)">([^<]*)</span>[\s\S]{0,160}?'
    r'<em class="num">([^<]*)</em>')

# "१६ भदौ १८:००" — the board's own stamp: Bikram Sambat day, month, clock.
_STAMP_RE = re.compile(r"([०१२३४५६७८९]+\s*भदौ\s*[०१२३४५६७८९]{1,2}:[०१२३४५६७८९]{2})")

# The bulletin labels districts in Nepali; the desk, the toll table and the
# seeded panel rows are all in English, so the mapping is fixed here rather
# than transliterated at read time.
_DISTRICT_KEYS = {
    "d_chitwan": "Chitwan",
    "d_nawal": "Nawalparasi East",
    "d_nawal_w": "Nawalparasi West",
    "d_nuwakot": "Nuwakot",
    "d_gorkha": "Gorkha",
    "d_dhading": "Dhading",
    "d_tanahun": "Tanahun",
    "d_rasuwa": "Rasuwa",
}

_KPI_FIELDS = {
    "dead": "deaths",
    "injured": "injured",
    "miss": "missing",
    "air": "rescued",
    "deploy": "personnel",
}


async def fetch_bulletin_kpi() -> Optional[dict]:
    """The NDRRMA situation board as transcribed by the citizen bulletin.

    Returns the headline figures, the death split by district, and the stamp
    the board itself carries. ``parts_sum_ok`` is computed here and checked by
    the caller before anything is written: a district split that does not add
    up to the published total means the page was caught mid-edit, and half a
    revision is worse than yesterday's complete one.
    """
    latest = await _get_json(f"{BULLETIN_BASE}/latest.json", "bulletin_latest")
    page = await _get_text(f"{BULLETIN_BASE}/index.html", "bulletin_index")
    if not page:
        return None

    figures: dict[str, Optional[int]] = {name: None for name in _KPI_FIELDS.values()}
    for match in _KPI_RE.finditer(page):
        field = _KPI_FIELDS.get(match.group(1))
        if field:
            figures[field] = parse_number(match.group(2))

    district_tolls: dict[str, int] = {}
    pane = _DEAD_PANE_RE.search(page)
    if pane:
        # Up to the next pane, so the injured pane's d_rasuwa cannot leak in.
        rest = page[pane.end():]
        end = rest.find('<div class="ov-pane"')
        segment = rest[:end] if end > 0 else rest
        for match in _DISTRICT_ROW_RE.finditer(segment):
            name = _DISTRICT_KEYS.get(match.group(1))
            count = parse_number(match.group(3))
            if name and count is not None:
                district_tolls[name] = count
    else:
        logger.warning("Bulletin: no death-by-district pane found")

    # The date comes from latest.json, which is machine-written and carries a
    # real offset; the clock comes from the board stamp on the page, which is
    # what NDRRMA actually published the figures as of.
    as_of = None
    updated_at = (latest or {}).get("updated_at") if isinstance(latest, dict) else None
    if updated_at:
        try:
            as_of = datetime.fromisoformat(updated_at).astimezone(NPT)
        except (TypeError, ValueError):
            as_of = None
    if as_of is None:
        as_of = datetime.now(NPT)

    stamp_match = _STAMP_RE.search(page)
    stamp = stamp_match.group(1).strip() if stamp_match else None
    if stamp:
        clock = re.search(r"(\d{1,2}):(\d{2})", to_ascii_digits(stamp))
        if clock:
            as_of = as_of.replace(hour=int(clock.group(1)),
                                  minute=int(clock.group(2)),
                                  second=0, microsecond=0)

    deaths = figures.get("deaths")
    parts_sum_ok = bool(
        district_tolls and deaths is not None
        and sum(district_tolls.values()) == deaths
    )
    if district_tolls and not parts_sum_ok:
        logger.warning("Bulletin district parts sum to %d, headline says %s",
                       sum(district_tolls.values()), deaths)

    return {
        "as_of_npt": as_of,
        "stamp": stamp,
        "deaths": deaths,
        "injured": figures.get("injured"),
        "missing": figures.get("missing"),
        "rescued": figures.get("rescued"),
        "personnel": figures.get("personnel"),
        "district_tolls": district_tolls,
        "parts_sum_ok": parts_sum_ok,
        "source_url": f"{BULLETIN_BASE}/",
        "bulletin_id": (latest or {}).get("id") if isinstance(latest, dict) else None,
    }
