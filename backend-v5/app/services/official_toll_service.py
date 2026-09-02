"""Reads official disaster-authority figures for named flood events.

Deliberately does no reconciliation. When two authorities publish different
tolls for the same day — NDRRMA's 987 against the wires' 1,010 on 1 September
2026 — both are returned and the desk shows the disagreement. Averaging them,
or silently preferring one, would manufacture a number nobody published.
"""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.flood_event import FloodOfficialToll, FloodSituationPanel

# The authority whose figures lead the desk. Nepal's designated disaster
# authority is the right default; other sources are shown as cross-checks.
PRIMARY_AUTHORITY = "NDRRMA"


class OfficialTollService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _tolls(self, event_key: str) -> list[FloodOfficialToll]:
        stmt = (
            select(FloodOfficialToll)
            .where(FloodOfficialToll.event_key == event_key)
            .order_by(FloodOfficialToll.as_of.asc())
        )
        return list((await self.db.execute(stmt)).scalars().all())

    @staticmethod
    def _serialise_toll(t: FloodOfficialToll) -> dict[str, Any]:
        return {
            "as_of": t.as_of.isoformat(),
            "authority": t.authority,
            "deaths": t.deaths,
            "missing": t.missing,
            "injured": t.injured,
            "rescued": t.rescued,
            "people_affected": t.people_affected,
            "foreign_nationals_missing": t.foreign_nationals_missing,
            "damage_npr": t.damage_npr,
            "damage_usd": t.damage_usd,
            "damage_note": t.damage_note,
            "district_tolls": t.district_tolls,
            "source_url": t.source_url,
            "source_title": t.source_title,
            "note": t.note,
        }

    async def get_event(self, event_key: str) -> dict[str, Any]:
        """Latest primary figures, the full toll trajectory, and any conflicts."""
        tolls = await self._tolls(event_key)
        if not tolls:
            return {"available": False, "tolls": [], "panels": []}

        primary = [t for t in tolls if t.authority == PRIMARY_AUTHORITY]
        latest = primary[-1] if primary else tolls[-1]

        # Anything from another authority carrying a different death count for
        # the same date is a disagreement worth surfacing, not resolving.
        conflicts = [
            self._serialise_toll(t) for t in tolls
            if t.as_of == latest.as_of
            and t.authority != latest.authority
            and t.deaths is not None
            and t.deaths != latest.deaths
        ]

        panels = list((await self.db.execute(
            select(FloodSituationPanel)
            .where(FloodSituationPanel.event_key == event_key)
            .order_by(FloodSituationPanel.display_order.asc())
        )).scalars().all())

        return {
            "available": True,
            "latest": self._serialise_toll(latest),
            "conflicting_reports": conflicts,
            # Only the primary authority's series, so the trajectory chart is
            # one consistent measurement rather than a mix of methodologies.
            "trajectory": [
                {"as_of": t.as_of.isoformat(), "deaths": t.deaths, "missing": t.missing}
                for t in primary if t.deaths is not None
            ],
            "panels": [
                {
                    "key": p.panel_key,
                    "title": p.title,
                    "subtitle": p.subtitle,
                    "headline_value": p.headline_value,
                    "headline_label": p.headline_label,
                    "rows": p.rows or [],
                    "note": p.note,
                    "source": p.source,
                    "as_of": p.as_of.isoformat() if p.as_of else None,
                }
                for p in panels
            ],
        }

    async def district_snapshots(self, event_key: str) -> list[dict[str, Any]]:
        """Every published per-district breakdown, oldest first.

        The authority publishes a district split only occasionally — twice so
        far on this event, 29 August and 1 September — while the national toll
        moves daily. Returning the snapshots as a series lets the replay STEP
        between the breakdowns that were actually published instead of
        interpolating a district's dead across days nobody counted them.

        Callers must not assume two: another bulletin adds a third.
        """
        return [
            {
                "as_of": t.as_of.isoformat(),
                "authority": t.authority,
                "district_tolls": t.district_tolls,
            }
            for t in await self._tolls(event_key)
            if t.authority == PRIMARY_AUTHORITY and t.district_tolls
        ]

    async def latest_deaths(self, event_key: str) -> Optional[int]:
        """Primary authority's most recent death toll, for cross-checks."""
        tolls = [t for t in await self._tolls(event_key)
                 if t.authority == PRIMARY_AUTHORITY and t.deaths is not None]
        return tolls[-1].deaths if tolls else None
