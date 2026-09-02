"""
CHANGE DETECTION + ALERTS — the desk notices when a watched figure moves and
says so, on the desk and to the owner.

Every run (10 min, after the feeds sync) reads the current state of a fixed
set of keys — the official toll, each tunnel's status and teams, each
country's stated personnel and consignments, the road-cut notes, the burial
grounds and their published figures, the count of unreviewed facts — and
compares each to the last snapshot. A difference becomes a `flood_changes`
row with a one-line summary, the before/after values and the source, and the
owner is told through whichever channels are configured (Telegram, email).
Nothing is inferred: a change is a difference between two published states.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.flood_event import FloodChange, FloodStateSnapshot

logger = logging.getLogger(__name__)

EVENT_KEY = "trishuli-2026-08"


def _fmt(v: Any) -> str:
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return f"{v:,.0f}" if float(v).is_integer() else f"{v:,.1f}"
    return str(v)


async def _current_state(db: AsyncSession) -> list[dict[str, Any]]:
    """The watched keys and their present values. Each entry: kind, key, value, summary_fn."""
    out: list[dict[str, Any]] = []

    # 1. Official toll
    latest = None
    try:
        from app.services.official_toll_service import OfficialTollService
        off = await OfficialTollService(db).get_event(EVENT_KEY)
        latest = off.get("latest") if isinstance(off, dict) else None
    except Exception as e:  # noqa: BLE001
        logger.warning("changes: toll read failed: %s", e)
    if latest:
        for k in ("deaths", "missing", "rescued", "injured"):
            if latest.get(k) is not None:
                out.append({"kind": "toll", "key": k, "value": {"n": latest[k], "as_of": latest.get("as_of"), "authority": latest.get("authority")},
                            "source": latest.get("authority"), "url": latest.get("source_url"), "severity": "high" if k in ("deaths", "missing") else "info"})

    # 2. Tunnels
    try:
        from app.services import flood_hydropower_service as hydro
        hp = await hydro.hydropower()
        for p in hp.get("projects", []):
            out.append({"kind": "tunnel", "key": p["key"], "value": {"status": p.get("status"), "teams": sorted({t.get("country") for t in p.get("teams", []) if t.get("country")}),
                                                                     "missing": next((f["value"] for f in p.get("figures", []) if f.get("kind") == "missing"), None),
                                                                     "rescued": next((f["value"] for f in p.get("figures", []) if f.get("kind") == "rescued"), None),
                                                                     "name": p.get("name")},
                        "source": p.get("status_source"), "url": None, "severity": "high"})
    except Exception as e:  # noqa: BLE001
        logger.warning("changes: tunnel read failed: %s", e)

    # 3. Assistance
    try:
        from app.services import flood_assistance_service as assist
        a = await assist.assistance()
        for c in a.get("countries", []):
            out.append({"kind": "assistance", "key": c["code"], "value": {"name": c["name"], "kinds": c.get("kinds", []), "personnel": c.get("personnel_total", 0),
                                                                          "materials": len(c.get("materials", [])), "money": len(c.get("money", []))},
                        "source": "assistance board", "url": None, "severity": "info"})
        out.append({"kind": "assistance", "key": "_countries", "value": {"codes": sorted(c["code"] for c in a.get("countries", []))}, "source": "assistance board", "url": None, "severity": "info"})
    except Exception as e:  # noqa: BLE001
        logger.warning("changes: assistance read failed: %s", e)

    # 4. Sites (burials, road cuts) + unreviewed facts
    try:
        from app.services import flood_sites_service
        s = await flood_sites_service.sites(db, EVENT_KEY)
        for site in s.get("sites", []):
            if site["kind"] in ("burial", "road_cut", "recovery", "mortuary"):
                figs = {f["kind"]: f["value"] for f in site.get("figures", []) if not f.get("auto")}
                out.append({"kind": "site", "key": site["key"], "value": {"name": site["name"], "kind": site["kind"], "figures": figs,
                                                                          "notes": len(site.get("notes", [])), "auto": bool(site.get("auto"))},
                            "source": site.get("figures", [{}])[0].get("source") if site.get("figures") else None, "url": None, "severity": "high" if site["kind"] == "burial" else "info"})
        out.append({"kind": "site", "key": "_burial_sites", "value": {"keys": sorted(x["key"] for x in s.get("sites", []) if x["kind"] == "burial")}, "source": "sites board", "url": None, "severity": "high"})
    except Exception as e:  # noqa: BLE001
        logger.warning("changes: sites read failed: %s", e)

    try:
        from app.services import flood_review_service
        st = await flood_review_service.stats(db, EVENT_KEY)
        out.append({"kind": "facts", "key": "_pending", "value": {"auto": st["counts"].get("auto", 0)}, "source": "extractor", "url": None, "severity": "info"})
    except Exception as e:  # noqa: BLE001
        logger.warning("changes: facts read failed: %s", e)
    return out


def _diff_summary(kind: str, key: str, before: Optional[dict[str, Any]], after: dict[str, Any]) -> Optional[tuple[str, str]]:
    """(summary, severity) or None when nothing worth saying changed."""
    if kind == "toll":
        b = before.get("n") if before else None
        a = after.get("n")
        if b == a:
            return None
        label = {"deaths": "Confirmed dead", "missing": "Missing", "rescued": "Rescued", "injured": "Hospitalised"}[key]
        delta = (a - b) if isinstance(a, (int, float)) and isinstance(b, (int, float)) else None
        d = f" ({'+' if delta > 0 else ''}{_fmt(delta)})" if delta is not None else ""
        return (f"{label}: {_fmt(b) if b is not None else '—'} → {_fmt(a)}{d} · {after.get('authority') or 'bulletin'} {str(after.get('as_of') or '')[:10]}",
                "critical" if key == "deaths" else "high")
    if kind == "tunnel":
        if before is None:
            return None
        parts = []
        if before.get("status") != after.get("status"):
            parts.append(f"status {before.get('status')} → {after.get('status')}")
        if before.get("teams") != after.get("teams"):
            parts.append(f"teams {'+'.join(before.get('teams') or []) or '—'} → {'+'.join(after.get('teams') or []) or '—'}")
        for f in ("missing", "rescued"):
            if before.get(f) != after.get(f) and after.get(f) is not None:
                parts.append(f"{f} {_fmt(before.get(f)) if before.get(f) is not None else '—'} → {_fmt(after.get(f))}")
        if not parts:
            return None
        return (f"{after.get('name')} tunnel: " + "; ".join(parts), "high")
    if kind == "assistance":
        if key == "_countries":
            if before is None:
                return None
            new = sorted(set(after.get("codes", [])) - set(before.get("codes", [])))
            return (f"New country on the assistance board: {', '.join(new)}", "high") if new else None
        if before is None:
            return None
        parts = []
        if after.get("personnel", 0) != before.get("personnel", 0):
            parts.append(f"stated personnel {_fmt(before.get('personnel', 0))} → {_fmt(after.get('personnel', 0))}")
        if set(after.get("kinds", [])) - set(before.get("kinds", [])):
            parts.append(f"new team kind {', '.join(sorted(set(after['kinds']) - set(before.get('kinds', []))))}")
        if after.get("materials", 0) > before.get("materials", 0):
            parts.append(f"consignments {before.get('materials', 0)} → {after.get('materials', 0)}")
        if after.get("money", 0) > before.get("money", 0):
            parts.append(f"pledges {before.get('money', 0)} → {after.get('money', 0)}")
        if not parts:
            return None
        return (f"{after.get('name')}: " + "; ".join(parts), "info")
    if kind == "site":
        if key == "_burial_sites":
            if before is None:
                return None
            new = sorted(set(after.get("keys", [])) - set(before.get("keys", [])))
            return (f"New burial ground on the map: {', '.join(new)}", "critical") if new else None
        if before is None:
            return (f"New {after.get('kind', 'site').replace('_', ' ')} on the map: {after.get('name')}{' (auto-extracted, unreviewed)' if after.get('auto') else ''}",
                    "high" if after.get("kind") == "burial" else "info")
        parts = []
        for fk, fv in (after.get("figures") or {}).items():
            bv = (before.get("figures") or {}).get(fk)
            if bv != fv:
                parts.append(f"{fk.replace('_', ' ')} {_fmt(bv) if bv is not None else '—'} → {_fmt(fv)}")
        if after.get("notes", 0) > before.get("notes", 0):
            parts.append(f"{after['notes'] - before.get('notes', 0)} new note{'s' if after['notes'] - before.get('notes', 0) != 1 else ''}")
        if not parts:
            return None
        return (f"{after.get('name')}: " + "; ".join(parts), "high" if after.get("kind") == "burial" else "info")
    if kind == "facts":
        if before is None:
            return None
        a, b = after.get("auto", 0), before.get("auto", 0)
        if a > b:
            return (f"{a - b} new auto-extracted fact{'s' if a - b != 1 else ''} awaiting review ({a} pending)", "info")
        return None
    return None


async def detect(db: AsyncSession, event_key: str = EVENT_KEY) -> dict[str, Any]:
    state = await _current_state(db)
    changes: list[FloodChange] = []
    # First run on a fresh table: everything is "new" only because nothing was
    # watched before. Record the baseline silently and report from the next run.
    baseline = (await db.execute(
        select(FloodStateSnapshot.id).where(FloodStateSnapshot.event_key == event_key).limit(1)
    )).first() is None
    for entry in state:
        prev = (await db.execute(
            select(FloodStateSnapshot).where(FloodStateSnapshot.event_key == event_key, FloodStateSnapshot.kind == entry["kind"], FloodStateSnapshot.key == entry["key"])
            .order_by(FloodStateSnapshot.taken_at.desc()).limit(1)
        )).scalar_one_or_none()
        before = prev.value if prev else None
        if before == entry["value"]:
            continue
        summary = None if baseline else _diff_summary(entry["kind"], entry["key"], before, entry["value"])
        if summary:
            text, sev = summary
            changes.append(FloodChange(event_key=event_key, kind=entry["kind"], key=entry["key"], severity=sev, summary=text,
                                       before=before, after=entry["value"], source=entry.get("source"), url=entry.get("url")))
        db.add(FloodStateSnapshot(event_key=event_key, kind=entry["kind"], key=entry["key"], value=entry["value"]))
    for c in changes:
        db.add(c)
    await db.commit()
    notified = await notify(db, changes) if changes else []
    return {"watched": len(state), "changes": len(changes), "notified": notified, "baseline": baseline,
            "summaries": [c.summary for c in changes]}


# ------------------------------------------------------------------ channels

async def _telegram(text: str) -> bool:
    s = get_settings()
    if not (s.telegram_bot_token and s.telegram_chat_id):
        return False
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(f"https://api.telegram.org/bot{s.telegram_bot_token}/sendMessage",
                                  json={"chat_id": s.telegram_chat_id, "text": text, "disable_web_page_preview": True})
            r.raise_for_status()
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("telegram alert failed: %s", e)
        return False


async def _email(subject: str, text: str) -> bool:
    s = get_settings()
    if not (s.resend_api_key and s.alert_email_to):
        return False
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post("https://api.resend.com/emails",
                                  headers={"Authorization": f"Bearer {s.resend_api_key}"},
                                  json={"from": s.resend_from_email, "to": [s.alert_email_to], "subject": subject, "text": text})
            r.raise_for_status()
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("email alert failed: %s", e)
        return False


async def notify(db: AsyncSession, changes: list[FloodChange]) -> list[str]:
    s = get_settings()
    lines = [f"[{c.severity.upper()}] {c.summary}" for c in changes]
    head = f"NepalOSINT flood desk · {len(changes)} change{'s' if len(changes) != 1 else ''} · {datetime.now(timezone.utc).strftime('%d %b %H:%MZ')}"
    body = head + "\n" + "\n".join(lines) + f"\n{s.public_base_url}/"
    used = []
    if await _telegram(body):
        used.append("telegram")
    if await _email(head, body):
        used.append("email")
    if used:
        now = datetime.now(timezone.utc)
        for c in changes:
            c.notified_at = now
            c.channels = ",".join(used)
        await db.commit()
    return used


async def recent(db: AsyncSession, event_key: str = EVENT_KEY, hours: int = 24, limit: int = 60) -> dict[str, Any]:
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    rows = (await db.execute(
        select(FloodChange).where(FloodChange.event_key == event_key, FloodChange.detected_at > since)
        .order_by(FloodChange.detected_at.desc()).limit(limit)
    )).scalars().all()
    s = get_settings()
    return {
        "hours": hours,
        "count": len(rows),
        "channels": {"telegram": bool(s.telegram_bot_token and s.telegram_chat_id), "email": bool(s.resend_api_key and s.alert_email_to)},
        "changes": [
            {"id": str(r.id), "kind": r.kind, "key": r.key, "severity": r.severity, "summary": r.summary,
             "before": r.before, "after": r.after, "source": r.source, "url": r.url,
             "detected_at": r.detected_at.isoformat(), "notified_at": r.notified_at.isoformat() if r.notified_at else None,
             "channels": r.channels}
            for r in rows
        ],
    }
