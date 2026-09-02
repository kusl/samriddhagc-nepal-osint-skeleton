"""Reconcile stored disaster incidents with BIPAD's loss records.

BIPAD publishes an incident the moment it is reported, with an empty loss
record attached; the casualty and damage figures are filled in over the
following hours and days as local authorities assess. So a one-shot fetch at
ingest time would permanently record zeros for every event — which is exactly
what the platform was doing.

This service therefore does two things:

* **Backfill** incidents that have never been synced (``loss_synced_at IS NULL``).
* **Re-check** recent incidents whose assessment is still likely to move, so a
  death toll that rises from 2 to 9 is reflected rather than frozen.

Figures are only ever written when BIPAD reports something; a transient empty
response can never zero out numbers we already hold.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.bipad_fetcher import BIPADFetcher
from app.models.disaster import DisasterIncident

logger = logging.getLogger(__name__)

# Assessments keep moving for roughly a fortnight after an event; past that,
# re-fetching every incident forever would be wasted requests.
RECHECK_WINDOW_DAYS = 14
# How stale a synced record may be before we re-check it.
RECHECK_AFTER_HOURS = 6

_LOSS_FIELDS = (
    "deaths",
    "injured",
    "missing",
    "affected_families",
    "people_affected",
    "families_relocated",
    "families_evacuated",
    "houses_destroyed",
    "houses_affected",
    "roads_destroyed",
    "bridges_destroyed",
    "livestock_destroyed",
    "infrastructure_loss_npr",
    "agriculture_loss_npr",
    "estimated_loss",
)


@dataclass
class LossSyncResult:
    considered: int = 0
    fetched: int = 0
    updated: int = 0
    deaths_added: int = 0
    loss_npr_added: float = 0.0


class LossSyncService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _candidates(self, limit: int) -> list[DisasterIncident]:
        """Incidents worth asking BIPAD about, never-synced first."""
        now = datetime.now(timezone.utc)
        recheck_cutoff = now - timedelta(days=RECHECK_WINDOW_DAYS)
        stale_cutoff = now - timedelta(hours=RECHECK_AFTER_HOURS)

        stmt = (
            select(DisasterIncident)
            .where(DisasterIncident.bipad_loss_id.is_not(None))
            .where(
                or_(
                    # Never synced — these are the ones showing zeros.
                    DisasterIncident.loss_synced_at.is_(None),
                    # Recent enough that the assessment may still be revised.
                    (DisasterIncident.incident_on >= recheck_cutoff)
                    & (DisasterIncident.loss_synced_at < stale_cutoff),
                )
            )
            # Never-synced first, then oldest sync.
            .order_by(DisasterIncident.loss_synced_at.asc().nullsfirst(),
                      DisasterIncident.incident_on.desc())
            .limit(limit)
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def sync(self, limit: int = 400) -> LossSyncResult:
        """Fetch loss records for pending incidents and apply any real figures."""
        result = LossSyncResult()
        incidents = await self._candidates(limit)
        result.considered = len(incidents)
        if not incidents:
            return result

        loss_ids = [i.bipad_loss_id for i in incidents if i.bipad_loss_id]
        async with BIPADFetcher(max_concurrent=5) as fetcher:
            records = await fetcher.fetch_loss_details(loss_ids)
        result.fetched = len(records)

        now = datetime.now(timezone.utc)
        for incident in incidents:
            fields = records.get(incident.bipad_loss_id)
            if fields is None:
                # Request failed — leave loss_synced_at alone so it is retried.
                continue

            changed = False
            for name in _LOSS_FIELDS:
                new_value = fields.get(name) or 0
                old_value = getattr(incident, name) or 0
                # Only ever move figures upward or onto a real value. BIPAD
                # occasionally serves an empty record for an incident it has
                # already assessed; that must not erase what we hold.
                if new_value and new_value != old_value:
                    if name == "deaths" and new_value > old_value:
                        result.deaths_added += new_value - old_value
                    if name == "estimated_loss" and new_value > old_value:
                        result.loss_npr_added += new_value - old_value
                    setattr(incident, name, new_value)
                    changed = True

            incident.loss_synced_at = now
            if changed:
                # Severity is derived from casualties/loss, so it must be
                # recomputed now that the real figures have landed.
                incident.severity = DisasterIncident.calculate_severity(
                    deaths=incident.deaths,
                    injured=incident.injured,
                    estimated_loss=incident.estimated_loss,
                )
                result.updated += 1

        await self.db.commit()
        logger.info(
            "Loss sync: %d considered, %d fetched, %d updated (+%d deaths, +%.0f NPR)",
            result.considered, result.fetched, result.updated,
            result.deaths_added, result.loss_npr_added,
        )
        return result
