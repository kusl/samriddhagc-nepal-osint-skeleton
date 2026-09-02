"""
TUNNEL RESCUE · HYDROPOWER — the per-project ledger behind GET /flood/hydropower.

Three layers, each kept apart so a reader can see which is which:

1. The truth file `app/data/flood_hydropower_trishuli_2026.json`: every project
   on the corridor with the figures, teams and notes that were read from a
   named document (each row carries the document's URL). Hand-verified; the
   desk never invents a per-project number.
2. The Ministry of Foreign Affairs' daily press briefing, taken automatically
   from nepal.gov.np's updates feed (already fetched by nepalgov_service). The
   newest briefing's "Tunnel Rescue Operations" and "Forensic Works" sections
   are lifted verbatim and the per-project lines are matched to projects by
   alias, so a change in who is digging where shows up the day MoFA says so.
3. Press evidence: the desk's own story store scanned for each project's
   aliases (English and Nepali) over the last days, with any figures in the
   sentence surfaced beside the headline. Labelled UNVERIFIED in the client —
   it is where to look, not what to believe.

A figure that no layer has published is returned absent, never as zero.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

TRUTH_PATH = (Path(__file__).resolve().parent.parent
              / "data" / "flood_hydropower_trishuli_2026.json")

_CACHE_TTL_S = 300
_cache: dict[str, Any] = {"at": 0.0, "payload": None}
_lock = threading.Lock()

_COUNTRY_WORDS = {
    "IN": r"indian?|india|भारत",
    "CN": r"chinese|china|चीन|चिनियाँ",
    "KR": r"korean?|korea|कोरिया|कोरियाली",
    "SG": r"singapore|singaporean|सिंगापुर",
    "NP": r"nepali? army|nepal army|नेपाली सेना",
}


# ------------------------------------------------------------------ truth file

def load_truth() -> dict[str, Any]:
    with TRUTH_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def _num(s: str) -> Optional[int]:
    try:
        return int(s.replace(",", ""))
    except ValueError:
        return None


# ------------------------------------------------------------------ MoFA briefing

_BRIEFING_TITLE_RE = re.compile(r"press\s+briefing", re.I)
# Headings only: the phrase at the start of its own line, ending in a colon.
# The intro paragraph also says "tunnel rescue operations" mid-sentence.
_SECTION_HEADS = [
    ("tunnel_section", re.compile(r"^[ \t]*tunnel\s+rescue\s+operations?\s*:[ \t\xa0]*$", re.I | re.M)),
    ("forensic_section", re.compile(r"^[ \t]*forensic\s+works?\s*:[ \t\xa0]*$", re.I | re.M)),
]
_NEXT_HEAD_RE = re.compile(
    r"\n[ \t]*(?:[A-Z][A-Za-z ,/&\-]{3,60}:)[ \t\xa0]*(?:\n|$)|\n\s*\d+\.\s+[A-Z]", re.M)
_FOREIGN_LINE_RE = re.compile(
    r"[^.\n]*foreign\s+national[^.\n]*\.?", re.I)


def _strip_html(s: str) -> str:
    s = re.sub(r"<br\s*/?>|</p>|</li>|</div>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = s.replace("&nbsp;", " ").replace("&amp;", "&")
    s = s.replace("\r", "").replace("\xa0", " ")
    s = re.sub(r"[ \t]+", " ", s)
    return re.sub(r"\n{3,}", "\n\n", s).strip()


def _section(text: str, head: re.Pattern[str]) -> Optional[str]:
    m = head.search(text)
    if not m:
        return None
    rest = text[m.end():]
    nxt = _NEXT_HEAD_RE.search(rest, 1)
    body = rest[: nxt.start()] if nxt else rest
    body = body.strip()
    return body or None


def _briefing_date(title: str, created: Optional[str]) -> Optional[str]:
    m = re.search(r"(\d{1,2})\s+(Sept?|September|Aug|August|Oct|October)[a-z]*\.?\s+(\d{4})", title, re.I)
    if m:
        mon = {"sep": 9, "aug": 8, "oct": 10}[m.group(2)[:3].lower()]
        return f"{m.group(3)}-{mon:02d}-{int(m.group(1)):02d}"
    if created:
        return created[:10]
    return None


def parse_briefing(updates: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """The newest MoFA press briefing in the updates feed, sectioned."""
    cands = [u for u in updates if _BRIEFING_TITLE_RE.search(u.get("title") or "")]
    if not cands:
        return None
    cands.sort(key=lambda u: u.get("createdAt") or "", reverse=True)
    u = cands[0]
    text = _strip_html(u.get("content") or "")
    out: dict[str, Any] = {
        "title": u.get("title"),
        "date": _briefing_date(u.get("title") or "", u.get("createdAt")),
        "created_at": u.get("createdAt"),
        "author": (u.get("author") or {}).get("department") or (u.get("author") or {}).get("name"),
        "url": "https://nepal.gov.np/",
        "source": "Ministry of Foreign Affairs daily press briefing, via nepal.gov.np updates",
        "tunnel_section": None,
        "forensic_section": None,
        "foreign_nationals_line": None,
    }
    for key, head in _SECTION_HEADS:
        out[key] = _section(text, head)
    fm = _FOREIGN_LINE_RE.search(text)
    out["foreign_nationals_line"] = fm.group(0).strip() if fm else None
    return out


def _plain_name(p: dict[str, Any]) -> str:
    return re.sub(r"\s*(khola|hydro(power|electric)?( project)?|hep|hpp)\s*$", "", (p.get("name") or ""), flags=re.I).strip()


def _teams_from_briefing(briefing: dict[str, Any], projects: list[dict[str, Any]],
                         aliases: dict[str, list[str]]) -> dict[str, list[dict[str, Any]]]:
    """Per-project team lines read out of the tunnel section by alias match.

    Each sentence of the section that names a project and a country becomes a
    team row for that project, attributed to the briefing. Sentences naming no
    project are left alone — the section is shown verbatim anyway.
    """
    sec = briefing.get("tunnel_section") or ""
    if not sec:
        return {}
    found: dict[str, list[dict[str, Any]]] = {}
    sentences = re.split(r"(?<=[.;])\s+|\n+", sec)
    for sent in sentences:
        low = sent.lower()
        # A briefing sentence is short and about tunnels, so the plain project
        # name is safe here (it is not in the story-scan aliases because
        # "Langtang" alone would match every valley story in the store).
        hit_projects = [p["key"] for p in projects
                        if any(a.lower() in low
                               for a in [*aliases.get(p["key"], []), _plain_name(p)]
                               if len(a) >= 4)]
        if not hit_projects:
            continue
        countries = [c for c, pat in _COUNTRY_WORDS.items() if re.search(pat, sent, re.I)]
        if not countries:
            continue
        for pk in hit_projects:
            for c in countries:
                found.setdefault(pk, []).append({
                    "country": c,
                    "unit": sent.strip()[:160],
                    "role": "tunnel rescue",
                    "source": briefing["source"],
                    "url": briefing["url"],
                    "as_of": briefing.get("date"),
                    "auto": True,
                })
    return found


# ------------------------------------------------------------------ press evidence

_NUM_RE = re.compile(r"(?<![\d.])(\d{1,3}(?:,\d{3})+|\d{1,4})(?![\d.])")


async def scan_stories(projects: list[dict[str, Any]], aliases: dict[str, list[str]],
                       days: int = 12, limit: int = 400) -> dict[str, list[dict[str, Any]]]:
    """Stories mentioning any project alias, grouped by project, newest first."""
    try:
        from sqlalchemy import text as sql_text
        from app.core.database import AsyncSessionLocal
    except Exception as e:  # noqa: BLE001
        logger.warning("hydropower story scan unavailable: %s", e)
        return {}
    all_aliases = sorted({a for v in aliases.values() for a in v if len(a) >= 5}, key=len, reverse=True)
    if not all_aliases:
        return {}
    pattern = "|".join(re.escape(a) for a in all_aliases)
    q = sql_text(
        "SELECT title, summary, content, source_name, url, published_at "
        "FROM stories WHERE published_at > now() - make_interval(days => :days) "
        "AND (title ~* :pat OR summary ~* :pat OR content ~* :pat) "
        "ORDER BY published_at DESC LIMIT :lim"
    )
    try:
        async with AsyncSessionLocal() as db:
            rows = (await db.execute(q, {"days": days, "pat": pattern, "lim": limit})).all()
    except Exception as e:  # noqa: BLE001
        logger.warning("hydropower story scan failed: %s", e)
        return {}

    out: dict[str, list[dict[str, Any]]] = {}
    seen: set[tuple[str, str]] = set()
    for title, summary, content, outlet, url, published_at in rows:
        blob = " ".join(x for x in (title, summary, content) if x)
        low = blob.lower()
        for p in projects:
            names = [a for a in aliases.get(p["key"], []) if len(a) >= 4]
            hit = next((a for a in names if a.lower() in low), None)
            if not hit or (p["key"], url) in seen:
                continue
            seen.add((p["key"], url))
            idx = low.find(hit.lower())
            window = blob[max(0, idx - 220): idx + 260]
            nums = []
            for m in _NUM_RE.finditer(window):
                v = _num(m.group(1))
                if v is not None and 1 < v < 5000 and not (1900 < v < 2100):
                    nums.append(v)
            snippet = re.sub(r"\s+", " ", window).strip()
            out.setdefault(p["key"], []).append({
                "title": title,
                "outlet": outlet,
                "url": url,
                "published_at": published_at.isoformat() if isinstance(published_at, datetime) else published_at,
                "snippet": snippet[:320],
                "numbers": nums[:6],
                "matched_alias": hit,
            })
    return out


# ------------------------------------------------------------------ assembly

def _latest_by_kind(figures: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One figure per kind — the newest as_of wins; ties keep file order."""
    best: dict[str, dict[str, Any]] = {}
    for f in figures:
        k = f.get("kind")
        if not k:
            continue
        if k not in best or (f.get("as_of") or "") > (best[k].get("as_of") or ""):
            best[k] = f
    return list(best.values())


async def hydropower(days: int = 12) -> dict[str, Any]:
    now = time.monotonic()
    with _lock:
        if _cache["payload"] is not None and now - _cache["at"] < _CACHE_TTL_S:
            return _cache["payload"]

    truth = load_truth()
    projects = truth.get("projects", [])
    aliases: dict[str, list[str]] = truth.get("aliases", {})
    for p in projects:
        aliases.setdefault(p["key"], [])
        for n in (p.get("name"), p.get("short")):
            if n and n not in aliases[p["key"]]:
                aliases[p["key"]].append(n)

    briefing: Optional[dict[str, Any]] = None
    evidence: dict[str, list[dict[str, Any]]] = {}
    try:
        from app.services import nepalgov_service
        gov_task = nepalgov_service.government()
        gov, evidence = await asyncio.gather(gov_task, scan_stories(projects, aliases, days=days))
        briefing = parse_briefing(gov.get("updates") or [])
    except Exception as e:  # noqa: BLE001
        logger.warning("hydropower: briefing/evidence layer failed: %s", e)
        try:
            evidence = await scan_stories(projects, aliases, days=days)
        except Exception:  # noqa: BLE001
            evidence = {}

    auto_teams = _teams_from_briefing(briefing, projects, aliases) if briefing else {}

    # AUTO layer: press sentences the extractor tied to a project by alias.
    auto_notes: dict[str, list[dict[str, Any]]] = {}
    try:
        from app.core.database import AsyncSessionLocal
        from app.services import flood_fact_extractor as fx
        async with AsyncSessionLocal() as db:
            fs = [f for f in await fx.facts(db, days=21) if f["fact_type"] == "tunnel" and f["subject_code"]]
        seen_q: set[str] = set()
        for f in fs:
            qk = f["quote"][:80]
            if qk in seen_q:
                continue
            seen_q.add(qk)
            auto_notes.setdefault(f["subject_code"], []).append({
                "t_npt": f["published_at"] or "", "text": f["quote"][:300],
                "source": f"{f['outlet'] or 'press'} (auto-extracted)", "url": f["url"], "auto": True,
                "figure": f["figure"], "unit": f["unit"],
            })
    except Exception as e:  # noqa: BLE001
        logger.warning("hydropower: auto fact layer failed: %s", e)

    out_projects = []
    for p in projects:
        teams = list(p.get("teams") or [])
        # The briefing may confirm a team the file already has; add only the
        # countries the file does not list, so the row never doubles up.
        have = {t.get("country") for t in teams}
        for t in auto_teams.get(p["key"], []):
            if t["country"] not in have:
                teams.append(t)
                have.add(t["country"])
        figs = _latest_by_kind(p.get("figures") or [])
        notes = sorted((p.get("notes") or []) + auto_notes.get(p["key"], [])[:6], key=lambda n: n.get("t_npt") or "", reverse=True)
        status = p.get("status") or ("active" if teams else "unreported")
        status_line = p.get("status_line") or ""
        status_source = "truth file"
        # The newest MoFA briefing outranks the file: a project it names in
        # the tunnel section has a team at work today, whatever an earlier
        # press report said about a suspension — unless a file note is dated
        # after the briefing itself.
        named = auto_teams.get(p["key"], [])
        if named and briefing:
            newest_note = notes[0].get("t_npt", "")[:10] if notes else ""
            if not (newest_note and briefing.get("date") and newest_note > briefing["date"]):
                status = "active"
                status_line = named[0]["unit"]
                status_source = "MoFA briefing " + (briefing.get("date") or "")
        out_projects.append({
            **p,
            "teams": teams,
            "figures": figs,
            "notes": notes,
            "status": status,
            "status_line": status_line,
            "status_source": status_source,
            "in_briefing": bool(named),
            "evidence": evidence.get(p["key"], [])[:12],
            "evidence_count": len(evidence.get(p["key"], [])),
        })
    out_projects.sort(key=lambda p: (p.get("km") if isinstance(p.get("km"), (int, float)) else 1e9))

    ev_total = sum(len(v) for v in evidence.values())
    payload = {
        "event_key": truth.get("event_key", "trishuli_2026"),
        "as_of": datetime.now(timezone.utc).isoformat(),
        "truth_verified_on": truth.get("verified_on"),
        "projects": out_projects,
        "corridor_figures": _latest_by_kind(truth.get("corridor_figures") or []),
        "briefing": briefing,
        "counts": {
            "projects": len(out_projects),
            "active": sum(1 for p in out_projects if p["status"] == "active"),
            "suspended": sum(1 for p in out_projects if p["status"] == "suspended"),
            "unreported": sum(1 for p in out_projects if p["status"] == "unreported"),
            "evidence": ev_total,
            "foreign_countries": sorted({t["country"] for p in out_projects for t in p["teams"]
                                         if t.get("country") and t["country"] != "NP"}),
        },
        "sources": truth.get("sources", []),
        "note": truth.get("note") or (
            "Per-project figures are read from named documents only; a project "
            "without a published figure is returned without one. Team rows "
            "flagged auto were matched from the newest MoFA press briefing by "
            "project alias. Press evidence is where to look, not what to believe."),
    }
    with _lock:
        _cache["at"] = now
        _cache["payload"] = payload
    return payload
