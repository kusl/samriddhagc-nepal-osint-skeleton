#!/usr/bin/env python3
"""Backfill bipad_loss_id and district on incidents ingested before the fix.

Rows stored by the old parser have:
  * ``bipad_loss_id`` NULL — so LossSyncService skips them and their casualty
    figures stay at zero forever;
  * ``district`` set to a street address (or NULL) — so district rollups are
    meaningless.

Both are recoverable from ``raw_data``, which keeps BIPAD's full payload.
Idempotent: run it as often as you like.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select  # noqa: E402

from app.core.database import AsyncSessionLocal  # noqa: E402
from app.data.district_geo import district_at  # noqa: E402
from app.models.disaster import DisasterIncident  # noqa: E402


async def main() -> None:
    async with AsyncSessionLocal() as db:
        rows = list((await db.execute(select(DisasterIncident))).scalars().all())
        print(f"scanning {len(rows)} incidents")

        loss_ids = 0
        districts = 0
        cleared = 0

        for incident in rows:
            raw = incident.raw_data or {}

            if incident.bipad_loss_id is None:
                loss = raw.get("loss")
                if isinstance(loss, int):
                    incident.bipad_loss_id = loss
                    loss_ids += 1
                elif isinstance(loss, dict) and isinstance(loss.get("id"), int):
                    incident.bipad_loss_id = loss["id"]
                    loss_ids += 1

            # Resolve the real district from the incident's GPS point. The old
            # parser wrote street_address here, so an existing value is not
            # evidence the field is correct — recompute whenever we have a point.
            resolved = district_at(incident.longitude, incident.latitude)
            if resolved:
                if incident.district != resolved:
                    incident.district = resolved
                    districts += 1
            elif incident.district and incident.district == incident.street_address:
                # No point to resolve from, and the stored value is the known-bad
                # street address. NULL is more honest than a wrong district.
                incident.district = None
                cleared += 1

        await db.commit()
        print(f"  bipad_loss_id set : {loss_ids}")
        print(f"  district corrected: {districts}")
        print(f"  bad district cleared: {cleared}")


if __name__ == "__main__":
    asyncio.run(main())
