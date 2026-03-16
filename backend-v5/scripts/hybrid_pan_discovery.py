#!/usr/bin/env python3
"""
Hybrid PAN discovery for active old companies.

Multi-strategy approach:
1. Check if directors have PANs - link to companies
2. Look for PAN patterns in raw company data
3. Validate discovered PANs with IRD
4. Export remaining companies for manual lookup

Usage:
    # Strategy 1: Link from directors
    python scripts/hybrid_pan_discovery.py --strategy directors --limit 100

    # Strategy 2: Mine PANs from raw data
    python scripts/hybrid_pan_discovery.py --strategy mine --limit 100

    # Strategy 3: Validate and enrich
    python scripts/hybrid_pan_discovery.py --strategy validate --limit 50

    # All strategies
    python scripts/hybrid_pan_discovery.py --all-strategies --limit 100
"""
import asyncio
import re
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict
import json

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, and_, or_, update, func
from sqlalchemy.orm import selectinload
from app.core.database import AsyncSessionLocal
from app.models.company import CompanyRegistration, CompanyDirector, IRDEnrichment
from app.ingestion.ird_client import IRDClient
from app.ingestion.privacy_hasher import hash_phone


def extract_pan_candidates(text: str) -> List[str]:
    """Extract 9-digit numbers that could be PANs."""
    if not text:
        return []

    # PANs are 9-digit numbers
    pattern = re.compile(r'\b(\d{9})\b')
    return pattern.findall(text)


async def strategy_director_pan_linking(limit: Optional[int] = None, dry_run: bool = False):
    """Strategy 1: Link PANs from directors to companies."""

    print()
    print("=" * 100)
    print("STRATEGY 1: DIRECTOR PAN LINKING")
    print("=" * 100)
    print()
    print("Finding companies where directors have PANs...")
    print()

    async with AsyncSessionLocal() as db:
        # Find companies without PAN that have directors with PANs
        stmt = (
            select(CompanyRegistration)
            .join(CompanyDirector, CompanyRegistration.id == CompanyDirector.company_id)
            .where(
                and_(
                    CompanyRegistration.registration_number < 100000,
                    or_(
                        CompanyRegistration.pan.is_(None),
                        CompanyRegistration.pan == "",
                    ),
                    CompanyRegistration.last_communication_bs >= "2080",
                    CompanyDirector.pan.isnot(None),
                    CompanyDirector.pan != "",
                )
            )
            .options(selectinload(CompanyRegistration.directors))
            .distinct()
        )

        if limit:
            stmt = stmt.limit(limit)

        result = await db.execute(stmt)
        companies = list(result.scalars().all())

    print(f"Found {len(companies)} companies with director PANs")
    print()

    if not companies:
        print("No companies found with director PANs")
        return 0

    discovered = 0
    updated = 0

    for idx, company in enumerate(companies, 1):
        # Get directors with PANs
        directors_with_pan = [d for d in company.directors if d.pan]

        if not directors_with_pan:
            continue

        # Use the first director's PAN (or could ask user to choose)
        director = directors_with_pan[0]

        print(f"[{idx}/{len(companies)}] Company #{company.registration_number}: {company.name_english}")
        print(f"  Director: {director.name_en} (PAN: {director.pan})")

        if len(directors_with_pan) > 1:
            print(f"  ℹ️  {len(directors_with_pan)} directors have PANs, using first one")

        # This PAN belongs to the director, not the company
        # But we can note it for investigation
        print(f"  ⚠️  PAN belongs to director, not company - needs manual verification")

        discovered += 1

    print()
    print(f"Summary: {discovered} companies have directors with PANs (needs manual verification)")
    print()

    return discovered


async def strategy_mine_raw_data(limit: Optional[int] = None, dry_run: bool = False):
    """Strategy 2: Mine PANs from raw company data."""

    print()
    print("=" * 100)
    print("STRATEGY 2: MINE PANs FROM RAW DATA")
    print("=" * 100)
    print()

    async with AsyncSessionLocal() as db:
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
                    CompanyRegistration.raw_data.isnot(None),
                )
            )
            .order_by(CompanyRegistration.last_communication_bs.desc())
        )

        if limit:
            stmt = stmt.limit(limit)

        result = await db.execute(stmt)
        companies = list(result.scalars().all())

    print(f"Mining {len(companies)} company records...")
    print()

    discovered = 0
    updated = 0

    for idx, company in enumerate(companies, 1):
        # Extract PAN candidates from raw data
        raw_text = str(company.raw_data) if company.raw_data else ""
        pan_candidates = extract_pan_candidates(raw_text)

        if not pan_candidates:
            continue

        print(f"[{idx}/{len(companies)}] Company #{company.registration_number}: {company.name_english}")
        print(f"  Found {len(pan_candidates)} PAN candidate(s): {', '.join(pan_candidates[:3])}")

        # Use the first candidate (most likely to be correct)
        candidate_pan = pan_candidates[0]

        if dry_run:
            print(f"  [DRY RUN] Would update PAN to: {candidate_pan}")
            discovered += 1
        else:
            # Update database
            async with AsyncSessionLocal() as db_update:
                stmt = (
                    update(CompanyRegistration)
                    .where(CompanyRegistration.registration_number == company.registration_number)
                    .values(
                        pan=candidate_pan,
                        updated_at=datetime.utcnow(),
                    )
                )
                await db_update.execute(stmt)
                await db_update.commit()

            print(f"  ✅ Updated PAN to: {candidate_pan}")
            discovered += 1
            updated += 1

    print()
    print(f"Summary: Found {discovered} PAN candidates")
    if not dry_run:
        print(f"Updated: {updated} companies")
    print()

    return discovered


async def strategy_validate_and_enrich(limit: Optional[int] = None, enrich: bool = True):
    """Strategy 3: Validate discovered PANs and enrich with IRD data."""

    print()
    print("=" * 100)
    print("STRATEGY 3: VALIDATE & ENRICH")
    print("=" * 100)
    print()

    # Find companies that recently got PANs but aren't enriched yet
    async with AsyncSessionLocal() as db:
        stmt = (
            select(CompanyRegistration)
            .where(
                and_(
                    CompanyRegistration.registration_number < 100000,
                    CompanyRegistration.pan.isnot(None),
                    CompanyRegistration.pan != "",
                    or_(
                        CompanyRegistration.ird_enriched.is_(False),
                        CompanyRegistration.ird_enriched.is_(None),
                    ),
                )
            )
            .order_by(CompanyRegistration.updated_at.desc())
        )

        if limit:
            stmt = stmt.limit(limit)

        result = await db.execute(stmt)
        companies = list(result.scalars().all())

    print(f"Validating {len(companies)} companies with PANs...")
    print()

    if not companies:
        print("No companies need validation")
        return 0

    validated = 0
    enriched = 0
    invalid = 0

    async with IRDClient(max_concurrency=1, headless=True) as ird_client:
        for idx, company in enumerate(companies, 1):
            print(f"[{idx}/{len(companies)}] Company #{company.registration_number}")
            print(f"  PAN: {company.pan}")

            try:
                # Validate PAN with IRD
                ird_data = await ird_client.search_pan(company.pan)

                if not ird_data:
                    print(f"  ❌ Invalid PAN - no data from IRD")
                    invalid += 1

                    # Clear invalid PAN
                    async with AsyncSessionLocal() as db_update:
                        stmt = (
                            update(CompanyRegistration)
                            .where(CompanyRegistration.registration_number == company.registration_number)
                            .values(
                                pan=None,
                                updated_at=datetime.utcnow(),
                            )
                        )
                        await db_update.execute(stmt)
                        await db_update.commit()
                    continue

                validated += 1
                print(f"  ✅ Valid PAN")

                # Extract details
                pan_details = ird_data.get("panDetails", [])
                if not pan_details:
                    print(f"  ⚠️  No panDetails in response")
                    continue

                detail = pan_details[0]
                print(f"     Taxpayer: {detail.get('trade_Name_Eng')}")
                print(f"     Status: {detail.get('account_Status')}")

                if enrich:
                    # Hash phone numbers
                    phone_h = hash_phone(detail.get("telephone"))
                    mobile_h = hash_phone(detail.get("mobile"))

                    # Upsert enrichment
                    from sqlalchemy.dialects.postgresql import insert as pg_insert

                    async with AsyncSessionLocal() as db_update:
                        enrichment_data = {
                            "pan": company.pan,
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
                        await db_update.execute(stmt)

                        # Mark company as enriched
                        stmt = (
                            update(CompanyRegistration)
                            .where(CompanyRegistration.registration_number == company.registration_number)
                            .values(
                                ird_enriched=True,
                                ird_enriched_at=datetime.utcnow(),
                            )
                        )
                        await db_update.execute(stmt)
                        await db_update.commit()

                    enriched += 1
                    print(f"  ✅ IRD enrichment completed")

            except Exception as e:
                print(f"  ❌ Error: {e}")

            # Be polite
            await asyncio.sleep(2)

    print()
    print(f"Summary:")
    print(f"  ✅ Validated: {validated}")
    print(f"  ❌ Invalid: {invalid}")
    if enrich:
        print(f"  🌐 Enriched: {enriched}")
    print()

    return validated


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="Hybrid PAN discovery")
    parser.add_argument(
        "--strategy",
        choices=["directors", "mine", "validate"],
        help="Which strategy to use"
    )
    parser.add_argument(
        "--all-strategies",
        action="store_true",
        help="Run all strategies in sequence"
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit companies per strategy"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't update database"
    )
    parser.add_argument(
        "--no-enrich",
        action="store_true",
        help="Skip IRD enrichment in validate strategy"
    )

    args = parser.parse_args()

    if not args.strategy and not args.all_strategies:
        parser.print_help()
        return

    print("=" * 100)
    print("HYBRID PAN DISCOVERY")
    print("=" * 100)

    total_discovered = 0

    if args.all_strategies or args.strategy == "directors":
        count = await strategy_director_pan_linking(args.limit, args.dry_run)
        total_discovered += count

    if args.all_strategies or args.strategy == "mine":
        count = await strategy_mine_raw_data(args.limit, args.dry_run)
        total_discovered += count

    if args.all_strategies or args.strategy == "validate":
        count = await strategy_validate_and_enrich(args.limit, not args.no_enrich)
        # Don't add to total as this is validation, not discovery

    print("=" * 100)
    print(f"TOTAL DISCOVERED: {total_discovered}")
    print("=" * 100)


if __name__ == "__main__":
    asyncio.run(main())
