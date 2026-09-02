"""Flood situation aggregation for the live flood desk.

Everything here answers one of four operational questions:

* How bad is it right now, nationally? (`get_overview`)
* Which rivers are over their lines, and are they still rising? (`get_rivers`)
* Where is it worst? (`get_district_rollup`)
* What happened, incident by incident? (`get_incidents`)

Two honesty rules run through all of it, because this feeds rescue decisions:

1. **Never imply an assessment exists when it does not.** BIPAD publishes an
   incident immediately and fills in casualties later, so every total is
   reported alongside how many incidents are still unassessed. A "0 deaths"
   that means "nobody has counted yet" is presented as exactly that.
2. **Never turn a broken or silent sensor into an alarm.** DHM gauges emit
   ±100000-offset sentinel readings when faulty, and BIPAD serves a dead
   gauge's final reading indefinitely — so a river that ran high in 2024 still
   reports "above danger" today. Both are surfaced as instrument states
   (`sensor_fault`, `offline`), never as danger.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import Numeric, Select, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.disaster import DisasterIncident
from app.models.market_data import MarketData, MarketDataType
from app.models.river import RiverReading, RiverStation

logger = logging.getLogger(__name__)

# Water-driven hazards that constitute "the flood situation". Landslides belong
# here: in Nepal's monsoon they are rainfall-triggered and are handled by the
# same responders, and excluding them would understate the emergency badly.
FLOOD_HAZARDS = ("flood", "landslide", "heavy_rainfall")

# A gauge reading further than this from its own reference is a sensor fault,
# not a flood. DHM encodes faults as the true value ±100000.
SENSOR_FAULT_ABS = 10_000.0
SENSOR_FAULT_OVER_REFERENCE = 1_000.0

# Gauge freshness. BIPAD returns each station's *last known* reading forever,
# so a decommissioned gauge keeps serving whatever it read the day it died —
# and Nepal has plenty of those. Measured 2026-09-01: of 281 stations, 177 had
# reported within 6h and NONE of those were above danger, while every single
# "above danger" reading came from a gauge that had been silent for a day to
# two years. Classifying those as danger would send responders to a river that
# was high in November 2024. So freshness is checked before level, always.
READING_FRESH_HOURS = 6      # reporting normally
READING_STALE_HOURS = 24     # beyond this the reading says nothing about now


def _is_sensor_fault(level: Optional[float], warning: Optional[float],
                     danger: Optional[float]) -> bool:
    """True when a water level cannot be a real river stage."""
    if level is None:
        return True
    if abs(level) > SENSOR_FAULT_ABS:
        return True
    # Kathmandu valley gauges are metres-above-sea-level (~1300 m), which is
    # legitimate — but only ever a little above their own warning line. A
    # reading a kilometre above its reference is a fault in any datum.
    reference = danger or warning
    if reference and level > reference + SENSOR_FAULT_OVER_REFERENCE:
        return True
    return False


class FloodService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ---------------------------------------------------------------- helpers

    def _window(self, days: int) -> datetime:
        return datetime.now(timezone.utc) - timedelta(days=days)

    def _flood_incidents(self, days: int) -> Select:
        return select(DisasterIncident).where(
            DisasterIncident.hazard_type.in_(FLOOD_HAZARDS),
            DisasterIncident.incident_on >= self._window(days),
        )

    async def get_usd_rate(self) -> Optional[float]:
        """Latest NPR-per-USD from NRB, or None if we have no rate.

        Returning None rather than a hardcoded guess is deliberate: the desk
        shows damage in NPR only when it cannot convert honestly.
        """
        stmt = (
            select(MarketData)
            .where(MarketData.data_type == MarketDataType.FOREX_USD)
            .order_by(MarketData.created_at.desc())
            .limit(1)
        )
        row = (await self.db.execute(stmt)).scalar_one_or_none()
        if row is None or not row.value:
            return None
        try:
            rate = float(row.value)
        except (TypeError, ValueError):
            return None
        return rate if rate > 0 else None

    # --------------------------------------------------------------- overview

    async def get_overview(self, days: int = 7) -> dict[str, Any]:
        """National flood picture for the last `days` days."""
        since = self._window(days)

        totals = (await self.db.execute(
            select(
                func.count(DisasterIncident.id),
                func.coalesce(func.sum(DisasterIncident.deaths), 0),
                func.coalesce(func.sum(DisasterIncident.missing), 0),
                func.coalesce(func.sum(DisasterIncident.injured), 0),
                func.coalesce(func.sum(DisasterIncident.affected_families), 0),
                func.coalesce(func.sum(DisasterIncident.people_affected), 0),
                func.coalesce(func.sum(DisasterIncident.families_evacuated), 0),
                func.coalesce(func.sum(DisasterIncident.houses_destroyed), 0),
                func.coalesce(func.sum(DisasterIncident.houses_affected), 0),
                func.coalesce(func.sum(DisasterIncident.roads_destroyed), 0),
                func.coalesce(func.sum(DisasterIncident.bridges_destroyed), 0),
                func.coalesce(func.sum(DisasterIncident.livestock_destroyed), 0),
                func.coalesce(func.sum(DisasterIncident.estimated_loss), 0.0),
                func.coalesce(func.sum(DisasterIncident.infrastructure_loss_npr), 0.0),
                func.coalesce(func.sum(DisasterIncident.agriculture_loss_npr), 0.0),
                func.count(DisasterIncident.id).filter(
                    DisasterIncident.loss_synced_at.is_(None)),
                func.count(func.distinct(DisasterIncident.district)),
            ).where(
                DisasterIncident.hazard_type.in_(FLOOD_HAZARDS),
                DisasterIncident.incident_on >= since,
            )
        )).one()

        (incidents, deaths, missing, injured, families, people, evacuated,
         houses_destroyed, houses_affected, roads, bridges, livestock,
         estimated_loss, infra_loss, agri_loss, unassessed, districts) = totals

        # BIPAD often reports the components without a headline estimate, so the
        # damage figure is the larger of the two rather than one or the other.
        damage_npr = max(float(estimated_loss or 0), float(infra_loss or 0) + float(agri_loss or 0))
        usd_rate = await self.get_usd_rate()

        by_hazard = {
            hazard: count
            for hazard, count in (await self.db.execute(
                select(DisasterIncident.hazard_type, func.count(DisasterIncident.id))
                .where(
                    DisasterIncident.hazard_type.in_(FLOOD_HAZARDS),
                    DisasterIncident.incident_on >= since,
                )
                .group_by(DisasterIncident.hazard_type)
            )).all()
        }

        rivers = await self.get_rivers()
        # danger/warning are counted from reporting gauges only — see the
        # freshness note at the top of this module.
        river_counts = {
            "danger": sum(1 for r in rivers if r["alert"] == "danger"),
            "warning": sum(1 for r in rivers if r["alert"] == "warning"),
            "rising_at_risk": sum(
                1 for r in rivers
                if r["alert"] in ("danger", "warning") and r["trend"] == "RISING"
            ),
            "sensor_faults": sum(1 for r in rivers if r["alert"] == "sensor_fault"),
            "offline": sum(1 for r in rivers if r["alert"] == "offline"),
            "reporting": sum(
                1 for r in rivers if r["alert"] in ("danger", "warning", "normal")
            ),
            "total": len(rivers),
        }

        return {
            "window_days": days,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "casualties": {
                "deaths": int(deaths),
                "missing": int(missing),
                "injured": int(injured),
                "affected_families": int(families),
                "people_affected": int(people),
                "families_evacuated": int(evacuated),
            },
            "damage": {
                "npr": damage_npr,
                "usd": (damage_npr / usd_rate) if usd_rate else None,
                "usd_npr_rate": usd_rate,
                "infrastructure_npr": float(infra_loss or 0),
                "agriculture_npr": float(agri_loss or 0),
                "houses_destroyed": int(houses_destroyed),
                "houses_affected": int(houses_affected),
                "roads_destroyed": int(roads),
                "bridges_destroyed": int(bridges),
                "livestock_destroyed": int(livestock),
            },
            "incidents": {
                "total": int(incidents),
                "by_hazard": by_hazard,
                "districts_affected": int(districts),
                # The credibility line: how much of the above is still uncounted.
                "awaiting_assessment": int(unassessed),
            },
            "rivers": river_counts,
        }

    # ----------------------------------------------------------------- rivers

    async def get_rivers(self, alerts_only: bool = False) -> list[dict[str, Any]]:
        """Every station with its latest reading, classified honestly."""
        # Latest reading per station, via a window function so this stays one
        # query rather than one per station.
        ranked = (
            select(
                RiverReading.station_id,
                RiverReading.water_level,
                RiverReading.status,
                RiverReading.trend,
                RiverReading.reading_at,
                func.row_number().over(
                    partition_by=RiverReading.station_id,
                    order_by=RiverReading.reading_at.desc(),
                ).label("rn"),
            ).subquery()
        )
        latest = select(ranked).where(ranked.c.rn == 1).subquery()

        stmt = select(
            RiverStation.bipad_id,
            RiverStation.title,
            RiverStation.basin,
            RiverStation.latitude,
            RiverStation.longitude,
            RiverStation.warning_level,
            RiverStation.danger_level,
            latest.c.water_level,
            latest.c.status,
            latest.c.trend,
            latest.c.reading_at,
        ).join(latest, latest.c.station_id == RiverStation.id)

        now = datetime.now(timezone.utc)

        out: list[dict[str, Any]] = []
        for row in (await self.db.execute(stmt)).all():
            level = row.water_level
            warning, danger = row.warning_level, row.danger_level

            reading_at = row.reading_at
            age_hours = (
                (now - reading_at).total_seconds() / 3600.0 if reading_at else None
            )
            is_offline = age_hours is None or age_hours > READING_STALE_HOURS
            is_stale = bool(age_hours is not None and age_hours > READING_FRESH_HOURS)

            # Order matters. A broken or silent gauge can never raise an alarm,
            # however high its last number was.
            if _is_sensor_fault(level, warning, danger):
                alert = "sensor_fault"
            elif is_offline:
                alert = "offline"
            elif danger and level >= danger:
                alert = "danger"
            elif warning and level >= warning:
                alert = "warning"
            else:
                alert = "normal"

            # How far under the danger line, in metres — the number that tells a
            # responder how much headroom is left.
            headroom = None
            if danger and alert in ("danger", "warning", "normal"):
                headroom = round(danger - level, 2)

            record = {
                "station_id": row.bipad_id,
                "name": row.title,
                "basin": row.basin,
                "lat": row.latitude,
                "lon": row.longitude,
                "water_level": level,
                "warning_level": warning,
                "danger_level": danger,
                "alert": alert,
                "trend": row.trend or "UNKNOWN",
                "headroom_m": headroom,
                "reading_at": reading_at.isoformat() if reading_at else None,
                "age_hours": round(age_hours, 1) if age_hours is not None else None,
                "stale": is_stale,
                # The combination responders act on first: over the line, still
                # climbing, and the gauge is actually reporting.
                "critical": alert == "danger" and row.trend == "RISING",
            }
            if alerts_only and alert not in ("danger", "warning"):
                continue
            out.append(record)

        # Worst first: danger before warning, rising before steady.
        severity = {"danger": 0, "warning": 1, "normal": 2,
                    "sensor_fault": 3, "offline": 4}
        trend_rank = {"RISING": 0, "STEADY": 1, "FALLING": 2}
        out.sort(key=lambda r: (severity.get(r["alert"], 9),
                                trend_rank.get(r["trend"], 9),
                                -(r["water_level"] or 0)))
        return out

    # -------------------------------------------------------------- districts

    async def get_district_rollup(self, days: int = 7) -> list[dict[str, Any]]:
        """Per-district totals, worst first — the triage list."""
        stmt = (
            select(
                DisasterIncident.district,
                func.count(DisasterIncident.id).label("incidents"),
                func.coalesce(func.sum(DisasterIncident.deaths), 0).label("deaths"),
                func.coalesce(func.sum(DisasterIncident.missing), 0).label("missing"),
                func.coalesce(func.sum(DisasterIncident.injured), 0).label("injured"),
                func.coalesce(func.sum(DisasterIncident.affected_families), 0).label("families"),
                func.coalesce(func.sum(DisasterIncident.estimated_loss), 0.0).label("loss"),
            )
            .where(
                DisasterIncident.hazard_type.in_(FLOOD_HAZARDS),
                DisasterIncident.incident_on >= self._window(days),
                DisasterIncident.district.is_not(None),
            )
            .group_by(DisasterIncident.district)
            .order_by(
                func.coalesce(func.sum(DisasterIncident.deaths), 0).desc(),
                func.count(DisasterIncident.id).desc(),
            )
        )
        return [
            {
                "district": r.district,
                "incidents": int(r.incidents),
                "deaths": int(r.deaths),
                "missing": int(r.missing),
                "injured": int(r.injured),
                "affected_families": int(r.families),
                "estimated_loss_npr": float(r.loss),
            }
            for r in (await self.db.execute(stmt)).all()
        ]

    # -------------------------------------------------------------- incidents

    async def get_incidents(self, days: int = 7, limit: int = 200,
                            district: Optional[str] = None,
                            hazard: Optional[str] = None) -> list[dict[str, Any]]:
        stmt = self._flood_incidents(days)
        if district:
            stmt = stmt.where(DisasterIncident.district == district)
        if hazard:
            stmt = stmt.where(DisasterIncident.hazard_type == hazard)
        stmt = stmt.order_by(
            DisasterIncident.deaths.desc(),
            DisasterIncident.incident_on.desc(),
        ).limit(limit)

        rows = (await self.db.execute(stmt)).scalars().all()
        return [
            {
                "id": str(i.id),
                "bipad_id": i.bipad_id,
                "title": i.title,
                "title_ne": i.title_ne,
                "hazard": i.hazard_type,
                "district": i.district,
                "lat": i.latitude,
                "lon": i.longitude,
                "deaths": i.deaths,
                "missing": i.missing,
                "injured": i.injured,
                "affected_families": i.affected_families,
                "houses_destroyed": i.houses_destroyed,
                "estimated_loss_npr": i.estimated_loss,
                "severity": i.severity,
                "verified": i.verified,
                "incident_on": i.incident_on.isoformat() if i.incident_on else None,
                # Distinguishes "assessed, nothing to report" from "not yet counted".
                "assessed": i.loss_synced_at is not None,
                "source_url": f"https://bipadportal.gov.np/incidents/{i.bipad_id}",
            }
            for i in rows
        ]

    # ------------------------------------------------------------- timeseries

    async def get_daily_series(self, days: int = 30) -> list[dict[str, Any]]:
        """Daily incident and death counts, for the trend chart."""
        day = func.date_trunc("day", DisasterIncident.incident_on)
        stmt = (
            select(
                day.label("day"),
                func.count(DisasterIncident.id).label("incidents"),
                func.coalesce(func.sum(DisasterIncident.deaths), 0).label("deaths"),
            )
            .where(
                DisasterIncident.hazard_type.in_(FLOOD_HAZARDS),
                DisasterIncident.incident_on >= self._window(days),
            )
            .group_by(day)
            .order_by(day)
        )
        return [
            {
                "date": r.day.date().isoformat(),
                "incidents": int(r.incidents),
                "deaths": int(r.deaths),
            }
            for r in (await self.db.execute(stmt)).all()
        ]


# The active event this desk leads with. A named mega-disaster is not something
# the incident pipeline can discover on its own — see app/models/flood_event.py.
ACTIVE_EVENT_KEY = "trishuli-2026-08"

ACTIVE_EVENT_META = {
    "key": ACTIVE_EVENT_KEY,
    "name": "Trishuli glacier-collapse flood",
    "started_on": "2026-08-26",
    "cause": "Glacier collapse on Langtang Lirung sent a debris flow down the "
             "Trishuli, registering as an Ms 5.2 seismic signal at 02:52 UTC. "
             "Water rose as much as 9 m in 30 minutes and the surge ran roughly 100 km down the Lende Khola and Trishuli, destroying the Gyirong Port / Rasuwagadhi border crossing on the way.",
    "districts": ["Rasuwa", "Nuwakot", "Dhading", "Gorkha", "Chitwan",
                  "Nawalparasi East", "Nawalparasi West", "Tanahun"],
    "rivers": ["Trishuli", "Bhote Koshi"],
    "status": "active",
}
