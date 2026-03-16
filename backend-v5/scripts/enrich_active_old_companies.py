#!/usr/bin/env python3
"""
Enrich active old companies (pre-100k registration) with PAN data.

Strategy:
1. Export active old companies to CSV for manual PAN lookup
2. Try alternative PAN discovery methods
3. Import discovered PANs and run IRD enrichment

Phase 1: Identification and Export
Phase 2: Manual PAN discovery (using IRD website name search)
Phase 3: Import and enrich

Usage:
    # Phase 1: Export companies needing PAN
    python scripts/enrich_active_old_companies.py --export

    # Phase 3: Import PANs from CSV and enrich
    python scripts/enrich_active_old_companies.py --import pan_discoveries.csv
"""
import asyncio
import csv
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, and_, or_, update
from app.core.database import AsyncSessionLocal
from app.models.company import CompanyRegistration, IRDEnrichment
from app.ingestion.ird_client import IRDClient
from app.ingestion.privacy_hasher import hash_phone


async def export_active_old_companies(output_file: str = "active_old_companies.csv"):
    """Export active old companies without PAN to CSV for manual lookup."""

    print("=" * 100)
    print("ACTIVE OLD COMPANIES - PAN DISCOVERY EXPORT")
    print("=" * 100)
    print()

    async with AsyncSessionLocal() as db:
        # Find active old companies without PAN
        stmt = (
            select(CompanyRegistration)
            .where(
                and_(
                    CompanyRegistration.registration_number < 100000,
                    or_(
                        CompanyRegistration.pan.is_(None),
                        CompanyRegistration.pan == "",
                    ),
                    CompanyRegistration.last_communication_bs >= "2080",
                )
            )
            .order_by(CompanyRegistration.last_communication_bs.desc())
        )

        result = await db.execute(stmt)
        companies = list(result.scalars().all())

    print(f"Found {len(companies)} active old companies without PAN")
    print()

    # Export to CSV
    output_path = Path(__file__).parent.parent / "investigation_output" / output_file
    output_path.parent.mkdir(exist_ok=True)

    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'registration_number',
            'name_english',
            'name_nepali',
            'registration_date_bs',
            'last_communication_bs',
            'district',
            'company_address',
            'company_type',
            'discovered_pan',  # Leave empty for manual fill
            'notes',           # Leave empty for manual notes
        ])
        writer.writeheader()

        for company in companies:
            writer.writerow({
                'registration_number': company.registration_number,
                'name_english': company.name_english or '',
                'name_nepali': company.name_nepali or '',
                'registration_date_bs': company.registration_date_bs or '',
                'last_communication_bs': company.last_communication_bs or '',
                'district': company.district or '',
                'company_address': company.company_address or '',
                'company_type': company.company_type or '',
                'discovered_pan': '',  # To be filled manually
                'notes': '',
            })

    print(f"✅ Exported to: {output_path}")
    print()
    print("=" * 100)
    print("NEXT STEPS:")
    print("=" * 100)
    print()
    print("1. Open the CSV file in Excel/Google Sheets")
    print("2. For each company, search on IRD website:")
    print("   https://ird.gov.np/pan-search/")
    print("   Use the NAME field to search (not PAN)")
    print()
    print("3. Fill in the 'discovered_pan' column with found PANs")
    print("4. Save the file and run:")
    print(f"   python scripts/enrich_active_old_companies.py --import {output_file}")
    print()
    print("=" * 100)

    # Also create a summary by district for prioritization
    summary_file = output_path.parent / f"summary_{output_file}"

    district_counts = {}
    for company in companies:
        district = company.district or "Unknown"
        district_counts[district] = district_counts.get(district, 0) + 1

    with open(summary_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['District', 'Company Count', 'Priority'])

        for district, count in sorted(district_counts.items(), key=lambda x: x[1], reverse=True):
            priority = "HIGH" if count > 1000 else "MEDIUM" if count > 500 else "LOW"
            writer.writerow([district, count, priority])

    print(f"📊 District summary: {summary_file}")
    print()


async def import_discovered_pans(input_file: str):
    """Import discovered PANs from CSV and run IRD enrichment."""

    print("=" * 100)
    print("IMPORTING DISCOVERED PANs")
    print("=" * 100)
    print()

    input_path = Path(__file__).parent.parent / "investigation_output" / input_file

    if not input_path.exists():
        print(f"❌ File not found: {input_path}")
        return

    # Read CSV
    discoveries = []
    with open(input_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get('discovered_pan') and row['discovered_pan'].strip():
                discoveries.append({
                    'registration_number': int(row['registration_number']),
                    'pan': row['discovered_pan'].strip(),
                    'notes': row.get('notes', ''),
                })

    print(f"Found {len(discoveries)} companies with discovered PANs")
    print()

    if not discoveries:
        print("⚠️  No PANs found in CSV. Make sure 'discovered_pan' column is filled.")
        return

    # Update companies with PANs
    updated_count = 0
    enriched_count = 0

    async with IRDClient(max_concurrency=1, headless=True) as ird_client:
        print("🌐 IRD Client initialized")
        print()

        for idx, discovery in enumerate(discoveries, 1):
            print(f"[{idx}/{len(discoveries)}] Registration #{discovery['registration_number']}")
            print(f"  PAN: {discovery['pan']}")

            async with AsyncSessionLocal() as db:
                # Update company with PAN
                stmt = (
                    update(CompanyRegistration)
                    .where(CompanyRegistration.registration_number == discovery['registration_number'])
                    .values(
                        pan=discovery['pan'],
                        updated_at=datetime.utcnow(),
                    )
                )
                await db.execute(stmt)
                await db.commit()
                updated_count += 1
                print(f"  ✅ PAN updated in database")

                # Now enrich with IRD data
                try:
                    ird_data = await ird_client.search_pan(discovery['pan'])

                    if not ird_data:
                        print(f"  ⚠️  No data from IRD for PAN {discovery['pan']}")
                        continue

                    # Extract IRD details
                    pan_details = ird_data.get("panDetails", [])
                    if not pan_details:
                        print(f"  ⚠️  No panDetails in IRD response")
                        continue

                    detail = pan_details[0]

                    # Hash phone numbers
                    phone_raw = detail.get("telephone")
                    mobile_raw = detail.get("mobile")
                    phone_h = hash_phone(phone_raw)
                    mobile_h = hash_phone(mobile_raw)

                    # Insert/update IRD enrichment
                    from sqlalchemy.dialects.postgresql import insert as pg_insert

                    enrichment_data = {
                        "pan": discovery['pan'],
                        "taxpayer_name_en": detail.get("trade_Name_Eng"),
                        "taxpayer_name_np": detail.get("trade_Name_Nep"),
                        "account_status": detail.get("account_Status"),
                        "tax_office": detail.get("office_Name"),
                        "ward_no": detail.get("ward_No"),
                        "vdc_municipality": detail.get("vdc_Town"),
                        "phone_hash": phone_h,
                        "mobile_hash": mobile_h,
                        "fetched_at": datetime.utcnow(),
                        "updated_at": datetime.utcnow(),
                    }

                    stmt = pg_insert(IRDEnrichment).values(**enrichment_data)
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["pan"],
                        set_={k: v for k, v in enrichment_data.items() if k != "pan"},
                    )
                    await db.execute(stmt)

                    # Mark company as IRD enriched
                    stmt = (
                        update(CompanyRegistration)
                        .where(CompanyRegistration.registration_number == discovery['registration_number'])
                        .values(
                            ird_enriched=True,
                            ird_enriched_at=datetime.utcnow(),
                        )
                    )
                    await db.execute(stmt)
                    await db.commit()

                    enriched_count += 1
                    print(f"  ✅ IRD enrichment completed")
                    print(f"     Taxpayer: {detail.get('trade_Name_Eng')}")
                    print(f"     Status: {detail.get('account_Status')}")

                except Exception as e:
                    print(f"  ❌ Error: {e}")

                print()

                # Brief pause
                await asyncio.sleep(2)

    print("=" * 100)
    print("IMPORT SUMMARY")
    print("=" * 100)
    print()
    print(f"✅ PANs updated: {updated_count}")
    print(f"✅ IRD enriched: {enriched_count}")
    print(f"⚠️  Failed: {len(discoveries) - enriched_count}")
    print()


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="Enrich active old companies with PAN")
    parser.add_argument(
        "--export",
        action="store_true",
        help="Export companies to CSV for manual PAN lookup"
    )
    parser.add_argument(
        "--import",
        dest="import_file",
        type=str,
        help="Import PANs from CSV and enrich (e.g., active_old_companies.csv)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit export to N companies (for testing)"
    )

    args = parser.parse_args()

    if args.export:
        await export_active_old_companies()
    elif args.import_file:
        await import_discovered_pans(args.import_file)
    else:
        parser.print_help()
        print()
        print("Example usage:")
        print("  python scripts/enrich_active_old_companies.py --export")
        print("  python scripts/enrich_active_old_companies.py --import active_old_companies.csv")


if __name__ == "__main__":
    asyncio.run(main())
