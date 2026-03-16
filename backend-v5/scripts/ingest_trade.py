#!/usr/bin/env python3
"""Ingest trade data from Excel workbooks into the database.

Reads all .xlsx files from trade_data/ (6 fiscal years: 2077-78 through 2082-83)
and populates TradeReport + TradeFact records.

Skips KB graph object emission for speed — the graph service queries
trade_facts/trade_reports directly.

Usage:
    cd backend-v5
    venv/bin/python3 scripts/ingest_trade.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import delete
from app.core.database import AsyncSessionLocal
from app.services.trade import TradeIngestionService
from app.models.connected_analyst import TradeFact, TradeReport, TradeAnomaly


async def ingest():
    print("=" * 70)
    print("Trade Data Ingestion (fast mode — skip KB emission)")
    print("=" * 70)

    repo_root = Path(__file__).resolve().parents[2]
    data_root = repo_root / "trade_data"

    if not data_root.exists():
        print(f"  ERROR: trade_data directory not found at {data_root}")
        sys.exit(1)

    fy_dirs = sorted([d.name for d in data_root.iterdir() if d.is_dir() and not d.name.startswith(".")])
    print(f"  Found fiscal year directories: {', '.join(fy_dirs)}")

    files = sorted(data_root.glob("**/*.xlsx"))
    # Filter out temp files
    files = [f for f in files if not f.name.startswith("~$")]
    print(f"  Valid .xlsx files: {len(files)}")
    print()

    async with AsyncSessionLocal() as db:
        # Clear existing trade data for clean re-import
        print("  Clearing existing trade data...")
        await db.execute(delete(TradeAnomaly))
        await db.execute(delete(TradeFact))
        await db.execute(delete(TradeReport))
        await db.commit()
        print("  Cleared.")

        service = TradeIngestionService(db)
        processed = 0
        total_facts = 0

        for i, file_path in enumerate(files, 1):
            parsed = service._parse_trade_workbook(file_path)
            if not parsed:
                print(f"  [{i}/{len(files)}] SKIP {file_path.name} (no match)")
                continue

            report_meta, fact_rows = parsed
            report = await service._upsert_report(report_meta)

            # Delete existing facts for this report
            await db.execute(delete(TradeFact).where(TradeFact.report_id == report.id))

            # Insert new facts
            for row in fact_rows:
                fact = TradeFact(
                    report_id=report.id,
                    table_name=row["table_name"],
                    direction=row["direction"],
                    hs_code=row.get("hs_code"),
                    commodity_description=row.get("commodity_description"),
                    partner_country=row.get("partner_country"),
                    customs_office=row.get("customs_office"),
                    unit=row.get("unit"),
                    quantity=row.get("quantity"),
                    value_npr_thousands=row.get("value_npr_thousands") or 0.0,
                    revenue_npr_thousands=row.get("revenue_npr_thousands"),
                    cumulative_value_npr_thousands=row.get("cumulative_value_npr_thousands"),
                    delta_value_npr_thousands=row.get("delta_value_npr_thousands"),
                    record_key=row["record_key"],
                    fact_metadata=row.get("metadata") or {},
                )
                db.add(fact)

            await db.flush()
            total_facts += len(fact_rows)
            processed += 1
            print(f"  [{i}/{len(files)}] {file_path.name}: {len(fact_rows)} facts (total: {total_facts})")

            # Commit every 11 files (~1 fiscal year) for resilience
            if processed % 11 == 0:
                await db.commit()
                print(f"  --- committed {processed} files ---")

        # Final commit for remaining files
        await db.commit()
        print(f"  --- committed all {processed} files ---")

        print()
        print("  Recomputing monthly deltas...")
        delta_updates = await service._recompute_monthly_deltas()
        print(f"  Delta rows updated: {delta_updates}")

        print("  Recomputing anomalies...")
        anomaly_count = await service._recompute_anomalies()
        print(f"  Anomalies found: {anomaly_count}")

        print("  Committing deltas + anomalies...")
        await db.commit()

    print()
    print("=" * 70)
    print("Ingestion Summary")
    print("=" * 70)
    print(f"  Files processed: {processed}")
    print(f"  Total facts:     {total_facts}")
    print(f"  Delta updates:   {delta_updates}")
    print(f"  Anomalies:       {anomaly_count}")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(ingest())
