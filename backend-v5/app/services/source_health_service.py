"""Source health — is each configured feed actually delivering data?

Built after the Nitter outage (2026-09): both configured Nitter instances had been
dead for weeks and nothing anywhere said so, while `/api/v1/govt/health` cheerfully
returned "healthy". The first audit of this kind found 38 of 60 configured news
sources had never produced a single story.

The deliberate design choice here is that status is **derived from the data**, not
self-reported by the scrapers. A scraper cannot claim to be healthy while its table
stays empty, which is exactly the failure mode that went unnoticed.

Status values:
  OK      — produced data inside its expected window
  STALE   — has produced data before, but not recently (see caveat per kind)
  NEVER   — configured but has NEVER produced a row: almost always a real defect
  RETIRED — deliberately switched off (e.g. Nitter), reported but not alarming

Caveat on STALE: for high-frequency feeds (news RSS, Reddit) silence is a strong
failure signal. For individual social accounts it is not — a journalist may simply
not have posted — so those get deliberately generous windows and NEVER is the
signal that matters.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse

import yaml
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"
_SOURCES_PATH = _CONFIG_DIR / "sources.yaml"
_GOVT_PATH = _CONFIG_DIR / "govt_sources_registry.yaml"

STATUS_OK = "OK"
STATUS_STALE = "STALE"
STATUS_NEVER = "NEVER"
STATUS_RETIRED = "RETIRED"

# Govt registry groups that are plain lists of sources. `municipalities` and `daos`
# are pattern/template shaped rather than explicit entries, so they are skipped
# instead of guessing at keys that may not match what the scraper writes.
_GOVT_LIST_GROUPS = (
    "federal_ministries",
    "constitutional_bodies",
    "regulatory_bodies",
    "judiciary",
    "security_services",
    "disaster_sources",
    "parliament",
    "provinces",
)


@dataclass
class SourceHealth:
    """Health of one configured source."""

    source_id: str
    name: str
    kind: str                      # news | govt | bluesky | reddit | nitter
    status: str
    rows: int = 0
    last_seen: Optional[datetime] = None
    hours_since: Optional[float] = None
    stale_after_hours: Optional[float] = None
    detail: str = ""

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "name": self.name,
            "kind": self.kind,
            "status": self.status,
            "rows": self.rows,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "hours_since": (
                round(self.hours_since, 1) if self.hours_since is not None else None
            ),
            "stale_after_hours": self.stale_after_hours,
            "detail": self.detail,
        }


@dataclass
class _Probe:
    """Where a group of sources writes, so freshness can be read back out."""

    kind: str
    table: str
    key_column: str
    time_column: str
    stale_after_hours: float
    keys: Dict[str, str] = field(default_factory=dict)      # db key -> display name
    # Extra db keys that satisfy a logical source. Three news scrapers hardcode a
    # source_id that differs from their registry id, so without this the monitor
    # reports working feeds as NEVER — a false alarm in the one tool that exists
    # to stop false health signals.
    aliases: Dict[str, List[str]] = field(default_factory=dict)   # db key -> alias keys


def _load_yaml(path: Path) -> dict:
    try:
        with open(path) as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        logger.error(f"Failed to load {path.name}: {e}")
        return {}


def _hostname(url: str) -> str:
    """govt_announcements.source stores the bare hostname (e.g. 'mof.gov.np')."""
    try:
        host = urlparse(url).netloc.lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""


class SourceHealthService:
    """Reports which configured sources are actually delivering data."""

    def __init__(self, db: AsyncSession):
        self.db = db

    def _build_probes(self) -> List[_Probe]:
        cfg = _load_yaml(_SOURCES_PATH)
        govt = _load_yaml(_GOVT_PATH)
        probes: List[_Probe] = []

        # ── News feeds → stories.source_id ──
        news = _Probe(
            kind="news",
            table="stories",
            key_column="source_id",
            time_column="created_at",
            stale_after_hours=12.0,
        )
        for src in cfg.get("sources") or []:
            sid = src.get("id")
            if not sid:
                continue
            news.keys[sid] = src.get("name") or sid
            extra = src.get("aliases") or []
            if extra:
                news.aliases[sid] = [str(a) for a in extra]
        if news.keys:
            probes.append(news)

        # ── Government portals → govt_announcements.source (hostname) ──
        gov = _Probe(
            kind="govt",
            table="govt_announcements",
            key_column="source",
            time_column="created_at",
            # These publish irregularly; only prolonged silence is meaningful.
            stale_after_hours=96.0,
        )
        for group in _GOVT_LIST_GROUPS:
            for entry in govt.get(group) or []:
                if not isinstance(entry, dict):
                    continue
                host = _hostname(entry.get("base_url") or "")
                if host:
                    gov.keys[host] = entry.get("name") or host
        if gov.keys:
            probes.append(gov)

        # ── Bluesky accounts → tweets.source_query ──
        bsky = _Probe(
            kind="bluesky",
            table="tweets",
            key_column="source_query",
            time_column="tweeted_at",
            # Individual accounts go quiet legitimately — NEVER is the real signal.
            stale_after_hours=21 * 24.0,
        )
        for acct in cfg.get("bluesky_accounts") or []:
            handle = acct.get("handle")
            if handle:
                bsky.keys[f"bluesky:{handle}"] = acct.get("name") or handle
        if bsky.keys:
            probes.append(bsky)

        # ── Reddit subreddits → tweets.source_query ──
        reddit = _Probe(
            kind="reddit",
            table="tweets",
            key_column="source_query",
            time_column="tweeted_at",
            stale_after_hours=24.0,
        )
        for sub in cfg.get("reddit_subreddits") or []:
            name = sub.get("subreddit")
            if name:
                reddit.keys[f"reddit:r/{name}"] = f"r/{name}"
        if reddit.keys:
            probes.append(reddit)

        return probes

    async def _freshness(self, probe: _Probe) -> Dict[str, tuple]:
        """Read row count and newest timestamp per key, in one query per table."""
        keys = list(probe.keys)
        for alias_list in probe.aliases.values():
            keys.extend(alias_list)
        if not keys:
            return {}

        sql = text(
            f"SELECT {probe.key_column} AS k, COUNT(*) AS n, MAX({probe.time_column}) AS newest "
            f"FROM {probe.table} WHERE {probe.key_column} = ANY(:keys) "
            f"GROUP BY {probe.key_column}"
        )
        try:
            result = await self.db.execute(sql, {"keys": keys})
            return {row.k: (row.n, row.newest) for row in result}
        except Exception as e:
            logger.error(f"Source health query failed for {probe.table}: {e}")
            return {}

    async def get_report(self) -> dict:
        """Full per-source health report plus a summary."""
        now = datetime.now(timezone.utc)
        entries: List[SourceHealth] = []

        for probe in self._build_probes():
            observed = await self._freshness(probe)

            for key, name in probe.keys.items():
                rows, newest = observed.get(key, (0, None))

                # Fold in anything written under an alias id.
                alias_hits = []
                for alias in probe.aliases.get(key, []):
                    a_rows, a_newest = observed.get(alias, (0, None))
                    if a_rows:
                        alias_hits.append(alias)
                        rows += a_rows
                        if a_newest and (newest is None or a_newest > newest):
                            newest = a_newest

                if not rows or newest is None:
                    entries.append(
                        SourceHealth(
                            source_id=key,
                            name=name,
                            kind=probe.kind,
                            status=STATUS_NEVER,
                            rows=rows,
                            stale_after_hours=probe.stale_after_hours,
                            detail="Configured but has never produced a row",
                        )
                    )
                    continue

                if newest.tzinfo is None:
                    newest = newest.replace(tzinfo=timezone.utc)
                hours = (now - newest).total_seconds() / 3600.0
                stale = hours > probe.stale_after_hours

                entries.append(
                    SourceHealth(
                        source_id=key,
                        name=name,
                        kind=probe.kind,
                        status=STATUS_STALE if stale else STATUS_OK,
                        rows=rows,
                        last_seen=newest,
                        hours_since=hours,
                        stale_after_hours=probe.stale_after_hours,
                        detail=(
                            f"No new data for {hours:.0f}h "
                            f"(expected within {probe.stale_after_hours:.0f}h)"
                            if stale
                            else (
                                f"delivering under alias id {', '.join(alias_hits)}"
                                if alias_hits else ""
                            )
                        ),
                    )
                )

        # Reverse check: ids that ARE delivering but which no registry entry claims.
        # This is how the ekantipur/himalayan/republica id drift was found, and it
        # makes any future drift announce itself instead of masquerading as NEVER.
        unregistered = await self._unregistered_news_sources()

        # Nitter is reported so it stays visible, but never counted as a failure.
        cfg = _load_yaml(_SOURCES_PATH)
        if not (cfg.get("nitter_config") or {}).get("enabled", False):
            accounts = len(cfg.get("nitter_accounts") or [])
            entries.append(
                SourceHealth(
                    source_id="nitter",
                    name=f"Nitter / X ({accounts} accounts)",
                    kind="nitter",
                    status=STATUS_RETIRED,
                    detail=(
                        "Network shut down after X Corp. cease-and-desist "
                        "(2026-08-24); no instance has served data since. "
                        "Bluesky is the live replacement."
                    ),
                )
            )

        counts: Dict[str, int] = {}
        by_kind: Dict[str, Dict[str, int]] = {}
        for e in entries:
            counts[e.status] = counts.get(e.status, 0) + 1
            by_kind.setdefault(e.kind, {})
            by_kind[e.kind][e.status] = by_kind[e.kind].get(e.status, 0) + 1

        broken = [e for e in entries if e.status in (STATUS_NEVER, STATUS_STALE)]
        # Worst first: never-delivered before stale, then longest silence.
        broken.sort(key=lambda e: (e.status != STATUS_NEVER, -(e.hours_since or 0)))

        healthy = counts.get(STATUS_OK, 0)
        total_live = sum(
            counts.get(s, 0) for s in (STATUS_OK, STATUS_STALE, STATUS_NEVER)
        )

        return {
            "generated_at": now.isoformat(),
            "summary": {
                "total": len(entries),
                "healthy": healthy,
                "stale": counts.get(STATUS_STALE, 0),
                "never": counts.get(STATUS_NEVER, 0),
                "retired": counts.get(STATUS_RETIRED, 0),
                "health_pct": round(100.0 * healthy / total_live, 1) if total_live else 0.0,
            },
            "by_kind": by_kind,
            "problems": [e.to_dict() for e in broken],
            "unregistered": unregistered,
            "sources": [e.to_dict() for e in entries],
        }

    async def _unregistered_news_sources(self) -> List[dict]:
        """Story source_ids that no registry entry (or alias) accounts for."""
        cfg = _load_yaml(_SOURCES_PATH)
        known = set()
        for src in cfg.get("sources") or []:
            sid = src.get("id")
            if sid:
                known.add(sid)
                known.update(str(a) for a in (src.get("aliases") or []))
        if not known:
            return []

        try:
            result = await self.db.execute(
                text(
                    "SELECT source_id, COUNT(*) AS n, MAX(created_at) AS newest "
                    "FROM stories WHERE NOT (source_id = ANY(:known)) "
                    "GROUP BY source_id ORDER BY n DESC"
                ),
                {"known": list(known)},
            )
            return [
                {
                    "source_id": row.source_id,
                    "rows": row.n,
                    "last_seen": row.newest.isoformat() if row.newest else None,
                }
                for row in result
            ]
        except Exception as e:
            logger.error(f"Unregistered-source query failed: {e}")
            return []
