"""nepal.gov.np response services and government updates for the active event.

Every other flood source on this desk answers "what happened". This one answers
"what do I do now": where a family registers a rescue request, checks the list of
people already rescued, finds a blood bank, or donates. That makes reachability
part of the payload rather than a detail — a dead link on a rescue desk during an
emergency is worse than no link at all — so the seven portals are probed on the
same clock as the listings and every row says when it was last seen alive.

Two undocumented public JSON endpoints, no auth, verified live on 1 Sep 2026. The
browser never calls them: the host is http-origin sensitive, its rate limits are
unknown, and an outage there must degrade to a labelled snapshot rather than to a
broken widget. The two halves are cached and fall back independently, because a
timeout on one is no reason to serve yesterday's other.

Attachments on an update are NOT fetchable. The objects carry {id, filename,
mimeType, size} and no URL, and nine plausible routes were probed and 404'd. They
are reduced to a count here so no client can be tempted to construct one.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

PORTAL_URL = "https://nepal.gov.np"
NOTICES_URL = "https://nepal.gov.np/api/notices"
UPDATES_URL = "https://nepal.gov.np/api/updates"
SNAPSHOT_VERIFIED_ON = "2026-09-01"

_UA = "NepalOSINT-FloodDesk/1.0 (nepalosint.com; contact via site)"
_TIMEOUT = 8.0
_TTL_SECONDS = 900
# A listing fetched an hour ago still names the right portals; the government
# does not stand up a rescue site and take it down within the day.
_STALE_GRACE_SECONDS = 86400
_LINK_CONCURRENCY = 4

_MANIFEST_PATH = Path(__file__).resolve().parent.parent / "data" / "nepalgov_manifest.json"
_manifest_cache: Optional[dict[str, Any]] = None

# One cache per half: the notices call and the updates call fail independently
# upstream, so they recover independently here too.
_cache: dict[str, dict[str, Any]] = {
    "notices": {"rows": None, "fetched_at": 0.0},
    "updates": {"rows": None, "fetched_at": 0.0},
}
_links: dict[str, Any] = {"probes": None, "checked_at": 0.0}
_lock = asyncio.Lock()


def _manifest() -> dict[str, Any]:
    """The hand-verified payloads of 1 Sep 2026, loaded once."""
    global _manifest_cache
    if _manifest_cache is None:
        _manifest_cache = json.loads(_MANIFEST_PATH.read_text())
    return _manifest_cache


def _iso(value: Optional[float]) -> Optional[str]:
    if not value:
        return None
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()


def _text(value: Any) -> Optional[str]:
    """Upstream writes an absent English title as null and sometimes as "".

    Both mean "there is no English here", and a client that tests truthiness on
    one but not the other would render an empty line instead of the Nepali.
    """
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _notice(raw: dict[str, Any], order: int) -> Optional[dict[str, Any]]:
    """One response service.

    Upstream field names are kept verbatim so this payload can be diffed against
    theirs; fields we derive are snake_case and are ours to answer for. A notice
    with no link is dropped: the entire point of the row is the destination.
    """
    source_url = _text(raw.get("sourceUrl"))
    if not source_url or not raw.get("id"):
        return None
    return {
        "id": raw["id"],
        "titleEn": _text(raw.get("titleEn")),
        "titleNe": _text(raw.get("titleNe")),
        "contentEn": _text(raw.get("contentEn")),
        "contentNe": _text(raw.get("contentNe")),
        "type": _text(raw.get("type")),
        "priority": raw.get("priority"),
        "issuingAgency": _text(raw.get("issuingAgency")),
        "sourceUrl": source_url,
        "publishedAt": raw.get("publishedAt"),
        "updatedAtSource": raw.get("updatedAtSource"),
        # Empty in all seven today. Carried rather than dropped so the field is
        # already flowing on the day an agency fills it in.
        "emergencyContacts": raw.get("emergencyContacts") or [],
        # The position upstream listed it in, kept so a client can restore
        # their order and see that the sort below is ours and reversible.
        "source_order": order,
    }


def _sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
    """Priority first, then newest.

    The integer's semantics are undocumented upstream. Ascending is what matches
    operational weight in the data we have: it puts the NDRRMA command centre,
    the relief fund and the list of rescued persons above the standing health
    portals. If a later reading of the field contradicts that, the fix is to
    negate this one term.
    """
    priority = row.get("priority")
    return (
        # A notice with no priority sorts last rather than as the most urgent.
        priority if isinstance(priority, int) else 99,
        # Negated because within one priority the newest notice leads; a notice
        # with no date sorts to the bottom of its band.
        -_epoch(row.get("publishedAt")),
        row["source_order"],
    )


def _epoch(value: Any) -> float:
    """ISO-8601 to seconds, 0 when upstream published no timestamp."""
    if not isinstance(value, str):
        return 0.0
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _update(raw: dict[str, Any]) -> Optional[dict[str, Any]]:
    """One government update, with its attachments reduced to a count.

    likes/dislikes/comments are dropped on the way through: engagement counters
    on a disaster bulletin are not intelligence, and shipping them invites a
    client to rank by them.
    """
    if not raw.get("id"):
        return None
    author = raw.get("author") or {}
    return {
        "id": raw["id"],
        "title": _text(raw.get("title")),
        "content": _text(raw.get("content")),
        "status": _text(raw.get("status")),
        "author": {
            "name": _text(author.get("name")),
            "department": _text(author.get("department")),
        },
        "createdAt": raw.get("createdAt"),
        # A count, never the objects: they carry no URL and nine plausible
        # routes 404'd, so there is nothing here a client could link to.
        "attachments": len(raw.get("attachments") or []),
        "tags": [name for name in
                 (_text(((t or {}).get("tag") or {}).get("name"))
                  for t in (raw.get("tags") or []))
                 if name],
    }


async def _fetch_json(client: httpx.AsyncClient, url: str) -> Any:
    response = await client.get(url, headers={"User-Agent": _UA})
    response.raise_for_status()
    return response.json()


async def _fetch_notices(client: httpx.AsyncClient) -> list[dict[str, Any]]:
    body = await _fetch_json(client, NOTICES_URL)
    if not isinstance(body, list):
        raise ValueError("nepal.gov.np/api/notices did not return a list")
    rows = [n for n in (_notice(r, i) for i, r in enumerate(body)) if n]
    if not rows:
        # An empty answer from an endpoint known to publish seven response
        # services is a broken fetch, not a country with no rescue portals.
        raise ValueError("nepal.gov.np returned no usable notices")
    return rows


async def _fetch_updates(client: httpx.AsyncClient) -> list[dict[str, Any]]:
    body = await _fetch_json(client, UPDATES_URL)
    items = body.get("items") if isinstance(body, dict) else None
    if not isinstance(items, list):
        raise ValueError("nepal.gov.np/api/updates did not return items[]")
    rows = [u for u in (_update(r) for r in items) if u]
    if not rows:
        raise ValueError("nepal.gov.np returned no usable updates")
    return rows


async def _half(client: httpx.AsyncClient, name: str,
                fetch, fallback: list[dict[str, Any]],
                ) -> tuple[list[dict[str, Any]], str, Optional[float]]:
    """Live, else a listing from within the grace window, else the snapshot."""
    slot = _cache[name]
    now = time.time()
    age = now - (slot["fetched_at"] or 0.0)
    if slot["rows"] is not None and age < _TTL_SECONDS:
        return slot["rows"], "live", slot["fetched_at"]
    try:
        rows = await fetch(client)
    except Exception as exc:  # timeout, 5xx, parse error — all the same here
        logger.warning("nepal.gov.np %s fetch failed, serving %s: %s", name,
                       "cache" if slot["rows"] is not None else "snapshot", exc)
        if slot["rows"] is not None and age < _STALE_GRACE_SECONDS:
            return slot["rows"], "cache", slot["fetched_at"]
        return fallback, "fallback", None
    slot["rows"] = rows
    slot["fetched_at"] = now
    return rows, "live", now


async def _probe(client: httpx.AsyncClient, url: str,
                 sem: asyncio.Semaphore) -> dict[str, Any]:
    """Is this portal answering?

    A one-byte range request rather than a full GET: these are the sites a
    rescue desk is pointing people at, and we are asking whether they are up,
    not reading them. A transport failure leaves `reachable` null, not false —
    when our own egress is down every portal looks dead, and saying so on the
    page would send a family away from a service that is actually running.
    """
    async with sem:
        try:
            response = await client.get(
                url, headers={"User-Agent": _UA, "Range": "bytes=0-0"})
        except Exception as exc:
            logger.warning("Portal probe failed for %s: %s", url, exc)
            return {"reachable": None, "status": None}
        return {"reachable": response.status_code < 400,
                "status": response.status_code}


async def _probe_links(client: httpx.AsyncClient,
                       urls: list[str]) -> tuple[dict[str, Any], Optional[float]]:
    now = time.time()
    if (_links["probes"] is not None
            and now - (_links["checked_at"] or 0.0) < _TTL_SECONDS):
        return _links["probes"], _links["checked_at"]
    sem = asyncio.Semaphore(_LINK_CONCURRENCY)
    results = await asyncio.gather(*(_probe(client, url, sem) for url in urls))
    probes = dict(zip(urls, results))
    if all(p["reachable"] is None for p in results):
        # Every probe erroring is a statement about us, not about them: keep
        # whatever the last real sweep found rather than blanking the column.
        logger.warning("All %d portal probes failed; keeping previous sweep",
                       len(urls))
        if _links["probes"] is not None:
            return _links["probes"], _links["checked_at"]
        return probes, None
    _links["probes"] = probes
    _links["checked_at"] = now
    return probes, now


async def government() -> dict[str, Any]:
    """Response services and government updates, with provenance on each half."""
    manifest = _manifest()
    notice_fallback = [n for n in
                       (_notice(r, i) for i, r in enumerate(manifest["notices"]))
                       if n]
    update_fallback = [u for u in (_update(r) for r in manifest["updates"]) if u]

    async with _lock:
        async with httpx.AsyncClient(timeout=_TIMEOUT,
                                     follow_redirects=True) as client:
            (notices, notices_source, notices_at), (updates, updates_source, updates_at) = (
                await asyncio.gather(
                    _half(client, "notices", _fetch_notices, notice_fallback),
                    _half(client, "updates", _fetch_updates, update_fallback),
                ))
            notices = sorted(notices, key=_sort_key)
            probes, checked_at = await _probe_links(
                client, [n["sourceUrl"] for n in notices])

    checked_iso = _iso(checked_at)
    notices = [{**n,
                "reachable": probes.get(n["sourceUrl"], {}).get("reachable"),
                "link_status": probes.get(n["sourceUrl"], {}).get("status"),
                "link_checked_at": checked_iso}
               for n in notices]

    freshest = max((t for t in (notices_at, updates_at) if t), default=None)
    return {
        "portal_url": PORTAL_URL,
        "endpoints": {"notices": NOTICES_URL, "updates": UPDATES_URL},
        "source": {"notices": notices_source, "updates": updates_source},
        "fetched": {"notices": _iso(notices_at), "updates": _iso(updates_at)},
        "fetched_at": _iso(freshest),
        "links_checked_at": checked_iso,
        "snapshot_verified_on": SNAPSHOT_VERIFIED_ON,
        "counts": {"notices": len(notices), "updates": len(updates)},
        "notices": notices,
        "updates": updates,
        "note": "Notices are the government's own response services, sorted by "
                "the portal's priority field ascending and then newest first; "
                "each carries the result of a live reachability probe, and "
                "reachable null means our own check could not run rather than "
                "that the portal is down. Update attachments are a count: "
                "nepal.gov.np publishes no URL for them, so the row links to "
                "the portal and never to a constructed file path. Titles are "
                "largely Nepali and are passed through untranslated. When "
                "either half is `fallback` it is the hand-verified snapshot of "
                f"{SNAPSHOT_VERIFIED_ON}, whose portal links were each "
                "confirmed reachable independently of nepal.gov.np itself.",
    }
