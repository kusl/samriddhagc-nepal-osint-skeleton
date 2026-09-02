"""DHM gauge-site photographs, verified before they are offered.

river_stations.image_url has been populated for 264 of 281 stations since the
BIPAD ingest was written and has never been surfaced. Two things stand between
the column and an <img>, and this module is both of them.

First, the URLs are http:// on a host that serves the bytes as
application/octet-stream. A content-type test would reject every real
photograph on this feed, and the desk is https, so the browser would refuse the
mixed-content load anyway. Verification is therefore by magic bytes and the
image is served through our own proxy.

Second, DHM's newer asset route (/api/images/<hash>) answers 401, and a portal
that starts returning its app shell on the open route would hand the desk 850
bytes of HTML that an <img> renders as a broken icon. Every URL is probed and
only bytes that begin with a real image header are ever called a photograph.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

ATTRIBUTION = "DHM gauge-site photograph · via BIPAD Portal"

_UA = "NepalOSINT-FloodDesk/1.0 (nepalosint.com; contact via site)"
_PROBE_TIMEOUT = 6.0
_FETCH_TIMEOUT = 20.0
_TTL_SECONDS = 21600  # 6 h: a gauge photograph is not a live feed.
_CONCURRENCY = 8
# A probe pass is bounded so a slow or half-dead DHM cannot hold the request
# open; whatever did not resolve stays unknown and is retried next call.
_PASS_DEADLINE = 20.0
_MAX_BYTES = 12 * 1024 * 1024

# Magic numbers, because the upstream content-type is octet-stream for every
# file it serves — the header says nothing, the first four bytes say everything.
_SIGNATURES: list[tuple[bytes, str]] = [
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
]

_verdicts: dict[int, dict[str, Any]] = {}
_lock = asyncio.Lock()


def media_type_of(head: bytes) -> Optional[str]:
    """The image type these opening bytes declare, or None if they declare none.

    HTML, JSON and a 401 body all fall through to None, which is the whole
    point: an HTTP 200 from this host is not evidence of a photograph.
    """
    for signature, media_type in _SIGNATURES:
        if head.startswith(signature):
            return media_type
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    return None


def _fresh(verdict: Optional[dict[str, Any]]) -> bool:
    return bool(verdict and time.time() - verdict["at"] < _TTL_SECONDS)


async def _probe(client: httpx.AsyncClient, bipad_id: int, url: str,
                 sem: asyncio.Semaphore) -> dict[str, Any]:
    """Read only as far as the file header, then hang up."""
    async with sem:
        try:
            # The Range ask is a courtesy; DHM ignores it, so the stream is also
            # abandoned after the first chunk rather than downloading a 800 KB
            # photograph to look at four bytes of it.
            headers = {"User-Agent": _UA, "Range": "bytes=0-1023"}
            async with client.stream("GET", url, headers=headers) as response:
                if response.status_code not in (200, 206):
                    return {"verified": False, "media_type": None, "at": time.time(),
                            "reason": f"http {response.status_code}"}
                head = b""
                async for chunk in response.aiter_bytes():
                    head += chunk
                    if len(head) >= 16:
                        break
        except Exception as exc:
            logger.debug("DHM probe %s failed: %s", bipad_id, exc)
            return {"verified": False, "media_type": None, "at": time.time(),
                    "reason": "unreachable"}

    media_type = media_type_of(head)
    return {
        "verified": media_type is not None,
        "media_type": media_type,
        "at": time.time(),
        "reason": "ok" if media_type else "not image bytes",
    }


async def verdicts(stations: list[tuple[int, str]]) -> dict[int, dict[str, Any]]:
    """Cached verdicts for these stations, probing the ones we have no fresh one for."""
    async with _lock:
        stale = [(bipad_id, url) for bipad_id, url in stations
                 if not _fresh(_verdicts.get(bipad_id))]
        if stale:
            sem = asyncio.Semaphore(_CONCURRENCY)
            async with httpx.AsyncClient(timeout=_PROBE_TIMEOUT,
                                         follow_redirects=True) as client:
                tasks = [asyncio.ensure_future(_probe(client, bipad_id, url, sem))
                         for bipad_id, url in stale]
                done, pending = await asyncio.wait(tasks, timeout=_PASS_DEADLINE)
                for task in pending:
                    task.cancel()
                for (bipad_id, _), task in zip(stale, tasks):
                    if task in done and not task.cancelled():
                        try:
                            _verdicts[bipad_id] = task.result()
                        except Exception:
                            pass
                if pending:
                    logger.info("DHM probe pass left %d stations unresolved",
                                len(pending))
        return {bipad_id: _verdicts[bipad_id] for bipad_id, _ in stations
                if bipad_id in _verdicts}


async def fetch(url: str) -> Optional[tuple[bytes, str]]:
    """The photograph itself, or None if what came back is not one.

    The header is re-checked on the way through rather than trusted from the
    probe: the proxy is the last place that can stop an HTML error page from
    reaching an <img>, and the upstream can change under a cached verdict.
    """
    try:
        async with httpx.AsyncClient(timeout=_FETCH_TIMEOUT,
                                     follow_redirects=True) as client:
            response = await client.get(url, headers={"User-Agent": _UA})
            if response.status_code != 200:
                return None
            body = response.content
    except Exception as exc:
        logger.warning("DHM image fetch failed for %s: %s", url, exc)
        return None

    media_type = media_type_of(body[:16])
    if not media_type or len(body) > _MAX_BYTES:
        return None
    return body, media_type
