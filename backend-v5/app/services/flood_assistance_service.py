"""
INTERNATIONAL ASSISTANCE — who sent what, behind GET /flood/assistance.

Four layers, kept apart in the payload so the client can grade each:

1. Truth file `app/data/flood_assistance_trishuli_2026.json`: per-country teams
   (kind, size, site, since), materials, money, flights — every row with the
   document it was read from. Hand-verified.
2. The newest MoFA press briefing (nepal.gov.np updates): the tunnel and
   forensic sections are read sentence by sentence; a sentence naming a country
   becomes an `auto` team row for that country (kind tunnel/forensic/dvi by the
   section and wording, personnel by the first "N-member" figure), so the board
   moves the day the ministry's wording does. The "requested" sentence is
   lifted verbatim.
3. IFRC GO (public API, no key): rapid-response personnel deployed to the event
   grouped by sending country, the surge alerts, and the emergency appeal's
   requested/funded amounts.
4. Press evidence: the desk's story store scanned for country aliases together
   with assistance words, grouped by country, newest first. Where to look, not
   what to believe.

Nothing here is summed across currencies. A country with no published figure
is returned with none.
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

import httpx

from app.services import flood_hydropower_service as hydro

logger = logging.getLogger(__name__)

TRUTH_PATH = (Path(__file__).resolve().parent.parent
              / "data" / "flood_assistance_trishuli_2026.json")

IFRC_EVENT_ID = 8073
IFRC_APPEAL_CODE = "MDRNP022"
IFRC_BASE = "https://goadmin.ifrc.org/api/v2"
IFRC_EVENT_URL = f"https://go.ifrc.org/emergencies/{IFRC_EVENT_ID}"

_CACHE_TTL_S = 300
_cache: dict[str, Any] = {"at": 0.0, "payload": None}
_lock = threading.Lock()

_MEMBER_RE = re.compile(r"(\d{1,3})[- ]?(?:member|person|people|individuals?|experts?|officers?)", re.I)
_REQUESTED_RE = re.compile(r"[^.\n]*\brequested the supply of\b[^.\n]*\.?", re.I)
_TEAM_KIND_WORDS = [
    ("dvi", re.compile(r"disaster victim identification|\bdvi\b", re.I)),
    ("forensic", re.compile(r"forensic|dna", re.I)),
    ("tunnel", re.compile(r"tunnel", re.I)),
    ("sar", re.compile(r"search and rescue|rescue team", re.I)),
]

# ISO code -> name for countries the truth file does not list but a feed may.
_NAMES = {
    "GB": "United Kingdom", "DK": "Denmark", "NL": "Netherlands", "ID": "Indonesia", "QA": "Qatar",
    "NZ": "New Zealand", "MY": "Malaysia", "BD": "Bangladesh", "PK": "Pakistan", "MM": "Myanmar",
    "CH": "Switzerland", "DE": "Germany", "FR": "France", "TR": "Türkiye", "CA": "Canada", "NO": "Norway",
    "SE": "Sweden", "FI": "Finland", "IE": "Ireland", "ES": "Spain", "IT": "Italy", "BE": "Belgium",
    "AT": "Austria", "PH": "Philippines", "TH": "Thailand", "VN": "Viet Nam", "LK": "Sri Lanka",
    "BT": "Bhutan", "IL": "Israel", "SA": "Saudi Arabia", "KW": "Kuwait", "OM": "Oman", "EG": "Egypt",
    "ZA": "South Africa", "BR": "Brazil", "MX": "Mexico", "RU": "Russia", "UA": "Ukraine", "PL": "Poland",
    "CZ": "Czechia", "HK": "Hong Kong", "TW": "Taiwan", "MN": "Mongolia", "KZ": "Kazakhstan",
    "IN": "India", "CN": "China", "KR": "Republic of Korea", "SG": "Singapore", "US": "United States",
    "AU": "Australia", "AE": "United Arab Emirates", "JP": "Japan", "NP": "Nepal",
}
_IFRC_NAME_TO_CODE = {v.lower(): k for k, v in _NAMES.items()}
_IFRC_NAME_TO_CODE.update({
    "united states of america": "US", "korea, republic of": "KR", "south korea": "KR",
    "united kingdom of great britain and northern ireland": "GB", "britain": "GB",
    "russian federation": "RU", "viet nam": "VN", "vietnam": "VN", "turkey": "TR",
})


def load_truth() -> dict[str, Any]:
    with TRUTH_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


# ------------------------------------------------------------------ MoFA briefing

def _country_hits(sentence: str, aliases: dict[str, list[str]]) -> list[str]:
    low = sentence.lower()
    return [code for code, names in aliases.items()
            if any(re.search(r"(?<![a-z])" + re.escape(a.lower()) + r"(?![a-z])", low) for a in names)]


def _teams_from_briefing(briefing: dict[str, Any], aliases: dict[str, list[str]],
                         hydro_aliases: dict[str, list[str]]) -> dict[str, list[dict[str, Any]]]:
    found: dict[str, list[dict[str, Any]]] = {}
    for section_key, default_kind in (("tunnel_section", "tunnel"), ("forensic_section", "forensic")):
        sec = briefing.get(section_key) or ""
        for sent in re.split(r"(?<=[.;])\s+|\n+", sec):
            codes = _country_hits(sent, aliases)
            if not codes:
                continue
            kind = default_kind
            for k, pat in _TEAM_KIND_WORDS:
                if pat.search(sent):
                    kind = k
                    break
            m = _MEMBER_RE.search(sent)
            personnel = int(m.group(1)) if m else None
            low = sent.lower()
            sites = [pk for pk, names in hydro_aliases.items()
                     if any(a.lower() in low for a in names if len(a) >= 4)]
            for c in codes:
                if c == "NP":
                    continue
                found.setdefault(c, []).append({
                    "kind": kind,
                    "personnel": personnel,
                    "sites": sites,
                    "since": briefing.get("date"),
                    "source": briefing["source"],
                    "url": briefing["url"],
                    "note": sent.strip()[:220],
                    "auto": True,
                })
    return found


# ------------------------------------------------------------------ IFRC GO

async def _ifrc(client: httpx.AsyncClient, path: str, **params: Any) -> Optional[dict[str, Any]]:
    try:
        r = await client.get(f"{IFRC_BASE}/{path}", params=params,
                             headers={"Accept": "application/json"})
        r.raise_for_status()
        return r.json()
    except Exception as e:  # noqa: BLE001
        logger.warning("IFRC GO %s failed: %s", path, e)
        return None


async def fetch_ifrc() -> dict[str, Any]:
    out: dict[str, Any] = {"event_url": IFRC_EVENT_URL, "fetched_at": None,
                           "appeal": None, "personnel": [], "surge_alerts": [], "num_affected": None}
    async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
        ev, appeal, pers, surge = await asyncio.gather(
            _ifrc(client, f"event/{IFRC_EVENT_ID}/"),
            _ifrc(client, "appeal/", code=IFRC_APPEAL_CODE),
            _ifrc(client, "personnel/", event_deployed_to=IFRC_EVENT_ID, limit=200),
            _ifrc(client, "surge_alert/", event=IFRC_EVENT_ID, limit=100),
        )
    out["fetched_at"] = datetime.now(timezone.utc).isoformat()
    if ev:
        out["num_affected"] = ev.get("num_affected")
        out["event_name"] = ev.get("name")
    if appeal and appeal.get("results"):
        a = appeal["results"][0]
        out["appeal"] = {
            "code": a.get("code"), "name": a.get("name"), "type": a.get("atype_display"),
            "amount_requested_chf": a.get("amount_requested"), "amount_funded_chf": a.get("amount_funded"),
            "beneficiaries": a.get("num_beneficiaries"), "status": a.get("status_display"),
            "url": f"https://go.ifrc.org/emergencies/{IFRC_EVENT_ID}",
        }
    if pers:
        by: dict[str, dict[str, Any]] = {}
        for r in pers.get("results", []):
            cf = (r.get("country_from") or {})
            name = cf.get("name") or "Unstated"
            code = cf.get("iso") or _IFRC_NAME_TO_CODE.get(name.lower()) or name[:2].upper()
            row = by.setdefault(code, {"code": code, "name": name, "personnel": 0, "roles": []})
            row["personnel"] += 1
            role = (r.get("role") or "").split(",")[0].strip()
            if role and role not in row["roles"]:
                row["roles"].append(role)
            start = (r.get("start_date") or "")[:10]
            if start and (not row.get("since") or start < row["since"]):
                row["since"] = start
        out["personnel"] = sorted(by.values(), key=lambda x: -x["personnel"])
    if surge:
        out["surge_alerts"] = [
            {"message": (s.get("message") or "")[:90], "opens": (s.get("opens") or "")[:10],
             "status": s.get("molnix_status")}
            for s in surge.get("results", [])
        ]
    return out


# ------------------------------------------------------------------ press evidence

_ASSIST_WORDS = r"team|assistance|aid|relief|rescue|helicopter|drone|forensic|dna|donat|supplies|tonnes?|tons?|aircraft|plane|grant|million"


async def scan_stories(aliases: dict[str, list[str]], days: int = 10, limit: int = 300) -> dict[str, list[dict[str, Any]]]:
    try:
        from sqlalchemy import text as sql_text
        from app.core.database import AsyncSessionLocal
    except Exception as e:  # noqa: BLE001
        logger.warning("assistance story scan unavailable: %s", e)
        return {}
    q = sql_text(
        "SELECT title, summary, source_name, url, published_at FROM stories "
        "WHERE published_at > now() - make_interval(days => :days) "
        "AND title ~* :words AND (title ~* 'flood|rasuwa|trishuli|trisuli|bhote ?koshi|disaster|tunnel|बाढी|रसुवा|विपद') "
        "ORDER BY published_at DESC LIMIT :lim"
    )
    try:
        async with AsyncSessionLocal() as db:
            rows = (await db.execute(q, {"days": days, "words": _ASSIST_WORDS, "lim": limit})).all()
    except Exception as e:  # noqa: BLE001
        logger.warning("assistance story scan failed: %s", e)
        return {}
    out: dict[str, list[dict[str, Any]]] = {}
    for title, summary, outlet, url, published_at in rows:
        blob = f"{title} {summary or ''}"
        for code in _country_hits(title or "", aliases):
            nums = [int(m.group(1).replace(",", "")) for m in re.finditer(r"(\d{1,3}(?:,\d{3})+|\d{1,4})", blob)]
            out.setdefault(code, []).append({
                "title": title, "outlet": outlet, "url": url,
                "published_at": published_at.isoformat() if isinstance(published_at, datetime) else published_at,
                "numbers": [n for n in nums if 1 < n < 100000 and not 1900 < n < 2100][:5],
            })
    return out


# ------------------------------------------------------------------ assembly

def _country_row(code: str, truth_by: dict[str, dict[str, Any]], capitals: dict[str, list[float]]) -> dict[str, Any]:
    base = truth_by.get(code)
    if base:
        return {**base, "teams": list(base.get("teams") or []), "materials": list(base.get("materials") or []),
                "money": list(base.get("money") or []), "flights": list(base.get("flights") or []),
                "in_truth_file": True}
    cap = capitals.get(code)
    return {"code": code, "name": _NAMES.get(code, code), "lat": cap[0] if cap else None,
            "lng": cap[1] if cap else None, "teams": [], "materials": [], "money": [], "flights": [],
            "in_truth_file": False}


async def assistance(days: int = 10) -> dict[str, Any]:
    now = time.monotonic()
    with _lock:
        if _cache["payload"] is not None and now - _cache["at"] < _CACHE_TTL_S:
            return _cache["payload"]

    truth = load_truth()
    aliases: dict[str, list[str]] = truth.get("country_aliases", {})
    capitals: dict[str, list[float]] = truth.get("capitals", {})
    truth_by = {c["code"]: c for c in truth.get("countries", [])}

    hydro_truth = hydro.load_truth()
    hydro_aliases = hydro_truth.get("aliases", {})

    briefing: Optional[dict[str, Any]] = None
    ifrc: dict[str, Any] = {}
    evidence: dict[str, list[dict[str, Any]]] = {}

    async def _briefing() -> Optional[dict[str, Any]]:
        from app.services import nepalgov_service
        gov = await nepalgov_service.government()
        return hydro.parse_briefing(gov.get("updates") or [])

    results = await asyncio.gather(_briefing(), fetch_ifrc(), scan_stories(aliases, days=days),
                                   return_exceptions=True)
    if isinstance(results[0], dict):
        briefing = results[0]
    elif isinstance(results[0], Exception):
        logger.warning("assistance: briefing layer failed: %s", results[0])
    if isinstance(results[1], dict):
        ifrc = results[1]
    if isinstance(results[2], dict):
        evidence = results[2]

    auto_teams = _teams_from_briefing(briefing, aliases, hydro_aliases) if briefing else {}
    requested = None
    if briefing:
        full = " ".join(x for x in (briefing.get("tunnel_section"), briefing.get("forensic_section")) if x)
        m = _REQUESTED_RE.search(full)
        requested = m.group(0).strip() if m else None

    codes: list[str] = list(truth_by.keys())
    for c in list(auto_teams.keys()) + [p["code"] for p in ifrc.get("personnel", [])] + list(evidence.keys()):
        if c not in codes and c != "NP":
            codes.append(c)

    countries = []
    for code in codes:
        row = _country_row(code, truth_by, capitals)
        # Briefing teams: confirm what the file has (mark confirmed) or add.
        for t in auto_teams.get(code, []):
            same = next((x for x in row["teams"] if x.get("kind") == t["kind"]), None)
            if same:
                same["confirmed_by_briefing"] = briefing.get("date") if briefing else None
                if t.get("personnel") and not same.get("personnel"):
                    same["personnel"] = t["personnel"]
                    same["personnel_source"] = t["source"]
                if t.get("sites") and not same.get("sites"):
                    same["sites"] = t["sites"]
            else:
                row["teams"].append(t)
        ifrc_row = next((p for p in ifrc.get("personnel", []) if p["code"] == code), None)
        if ifrc_row:
            row["teams"].append({
                "kind": "ifrc_rr", "personnel": ifrc_row["personnel"], "sites": [],
                "since": ifrc_row.get("since"), "source": "IFRC GO personnel deployments",
                "url": IFRC_EVENT_URL, "note": ", ".join(ifrc_row["roles"][:4]), "auto": True,
            })
        row["evidence"] = evidence.get(code, [])[:8]
        row["evidence_count"] = len(evidence.get(code, []))
        row["personnel_total"] = sum(t.get("personnel") or 0 for t in row["teams"])
        row["personnel_unstated"] = sum(1 for t in row["teams"] if not t.get("personnel"))
        row["kinds"] = sorted({t["kind"] for t in row["teams"]})
        row["in_briefing"] = code in auto_teams
        latest = max([t.get("since") or "" for t in row["teams"]]
                     + [m.get("date") or "" for m in row["materials"]]
                     + [m.get("date") or "" for m in row["money"]]
                     + [f.get("date") or "" for f in row["flights"]]
                     + [(e.get("published_at") or "")[:10] for e in row["evidence"]], default="")
        # A planned IFRC rotation can carry a start date in the future; the
        # board's "latest" is the newest thing that has happened, not planned.
        today = datetime.now(timezone.utc).date().isoformat()
        row["latest"] = min(latest, today) if latest else None
        countries.append(row)

    def _rank(r: dict[str, Any]) -> tuple:
        return (-(1 if "tunnel" in r["kinds"] else 0), -r["personnel_total"], -len(r["materials"]), -len(r["money"]), r["name"])
    countries.sort(key=_rank)

    payload = {
        "event_key": truth.get("event_key", "trishuli_2026"),
        "as_of": datetime.now(timezone.utc).isoformat(),
        "truth_verified_on": truth.get("verified_on"),
        "kathmandu": truth.get("kathmandu"),
        "countries": countries,
        "announced_only": truth.get("announced_only", []),
        "announced_only_source": truth.get("announced_only_source"),
        "briefing": briefing,
        "requested_by_nepal": requested,
        "ifrc": ifrc,
        "counts": {
            "countries": len(countries),
            "with_teams": sum(1 for c in countries if c["teams"]),
            "tunnel_countries": sorted(c["code"] for c in countries if "tunnel" in c["kinds"]),
            "forensic_countries": sorted(c["code"] for c in countries if {"forensic", "dvi"} & set(c["kinds"])),
            "personnel_stated": sum(c["personnel_total"] for c in countries),
            "evidence": sum(len(v) for v in evidence.values()),
        },
        "note": truth.get("note"),
    }
    with _lock:
        _cache["at"] = now
        _cache["payload"] = payload
    return payload
