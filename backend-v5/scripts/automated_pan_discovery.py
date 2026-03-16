#!/usr/bin/env python3
"""
Automated PAN discovery for active old companies.

Searches IRD website by company name to discover PANs automatically.

Strategy:
1. Query active old companies without PAN
2. Search IRD by company name (English and Nepali)
3. Match results and update database
4. Optionally run IRD enrichment

Usage:
    # Discover PANs (dry run - show what would be found)
    python scripts/automated_pan_discovery.py --dry-run --limit 10

    # Discover and update PANs
    python scripts/automated_pan_discovery.py --limit 100

    # Discover, update PANs, and enrich with IRD data
    python scripts/automated_pan_discovery.py --enrich --limit 50

    # Process all active old companies (careful - 17,868 companies!)
    python scripts/automated_pan_discovery.py --all
"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict
import json

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, and_, or_, update
from sqlalchemy.orm import selectinload
from app.core.database import AsyncSessionLocal
from app.models.company import CompanyRegistration, IRDEnrichment
from app.ingestion.ird_name_search_client import IRDNameSearchClient
from app.ingestion.ird_client import IRDClient
from app.ingestion.privacy_hasher import hash_phone


def clean_name_for_search(name: str) -> str:
    """Clean company name for better search results."""
    if not name:
        return ""

    # Remove common suffixes that might interfere with search
    suffixes_to_remove = [
        " pvt ltd", " pvt. ltd.", " private limited",
        " ltd", " ltd.", " limited",
        " प्रा लि", " प्रा.लि.",
    ]

    cleaned = name.lower()
    for suffix in suffixes_to_remove:
        cleaned = cleaned.replace(suffix, "")

    return cleaned.strip()


def calculate_match_score(
    company_name: str,
    search_result_name: str,
) -> float:
    """Calculate match score between company name and search result.

    Returns score from 0.0 to 1.0 (1.0 = perfect match)
    """
    if not company_name or not search_result_name:
        return 0.0

    # Normalize names
    comp_clean = clean_name_for_search(company_name)
    result_clean = clean_name_for_search(search_result_name)

    # Exact match
    if comp_clean == result_clean:
        return 1.0

    # Check if one contains the other
    if comp_clean in result_clean or result_clean in comp_clean:
        return 0.85

    # Calculate word overlap
    comp_words = set(comp_clean.split())
    result_words = set(result_clean.split())

    if not comp_words or not result_words:
        return 0.0

    overlap = len(comp_words & result_words)
    total = len(comp_words | result_words)

    return overlap / total if total > 0 else 0.0


async def discover_pan_for_company(
    company: CompanyRegistration,
    name_client: IRDNameSearchClient,
    min_match_score: float = 0.6,
) -> Optional[Dict[str, any]]:
    """Discover PAN for a single company.

    Returns dict with PAN and match info, or None if not found.
    """
    print(f"\n{'='*80}")
    print(f"Company #{company.registration_number}")
    print(f"  English: {company.name_english}")
    print(f"  Nepali: {company.name_nepali}")
    print(f"  District: {company.district}")

    # Try English name first
    results_en = []
    if company.name_english:
        print(f"\n  🔍 Searching by English name...")
        try:
            results_en = await name_client.search_by_name(company.name_english)
            print(f"     Found {len(results_en)} results")
        except Exception as e:
            print(f"     ❌ Error: {e}")

    # Try Nepali name
    results_np = []
    if company.name_nepali:
        print(f"\n  🔍 Searching by Nepali name...")
        try:
            results_np = await name_client.search_by_name(company.name_nepali)
            print(f"     Found {len(results_np)} results")
        except Exception as e:
            print(f"     ❌ Error: {e}")

    # Combine and deduplicate results by PAN
    all_results = results_en + results_np
    unique_results = {}
    for result in all_results:
        pan = result.get("pan")
        if pan and pan not in unique_results:
            unique_results[pan] = result

    if not unique_results:
        print(f"\n  ⚠️  No results found")
        return None

    # Calculate match scores
    scored_results = []
    for pan, result in unique_results.items():
        result_name = result.get("name", "")

        # Try matching against both English and Nepali
        score_en = 0.0
        score_np = 0.0

        if company.name_english:
            score_en = calculate_match_score(company.name_english, result_name)

        if company.name_nepali:
            score_np = calculate_match_score(company.name_nepali, result_name)

        best_score = max(score_en, score_np)

        scored_results.append({
            "pan": pan,
            "name": result_name,
            "score": best_score,
            "confidence": result.get("match_confidence", "medium"),
        })

    # Sort by score
    scored_results.sort(key=lambda x: x["score"], reverse=True)

    # Show top matches
    print(f"\n  📊 Top matches:")
    for idx, match in enumerate(scored_results[:3], 1):
        print(f"     {idx}. PAN: {match['pan']} (score: {match['score']:.2f})")
        print(f"        {match['name'][:100]}")

    # Select best match if score is high enough
    best_match = scored_results[0]
    if best_match["score"] >= min_match_score:
        print(f"\n  ✅ Selected: PAN {best_match['pan']} (score: {best_match['score']:.2f})")
        return {
            "pan": best_match["pan"],
            "matched_name": best_match["name"],
            "match_score": best_match["score"],
            "source": "automated_name_search",
        }
    else:
        print(f"\n  ⚠️  Best match score {best_match['score']:.2f} below threshold {min_match_score}")
        return None


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="Automated PAN discovery")
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Number of companies to process (default: 10 for safety)"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Process ALL active old companies (17,868) - use with caution!"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be discovered without updating database"
    )
    parser.add_argument(
        "--enrich",
        action="store_true",
        help="Also run IRD enrichment after discovering PANs"
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=0.6,
        help="Minimum match score to accept (0.0-1.0, default: 0.6)"
    )
    parser.add_argument(
        "--district",
        type=str,
        help="Only process companies in this district (e.g., 'काठमाण्डौ')"
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        default=True,
        help="Run browser in headless mode (default: True)"
    )

    args = parser.parse_args()

    # Safety check
    if args.all:
        print("⚠️  WARNING: You are about to process 17,868 companies!")
        print("⚠️  This will take many hours and make thousands of requests to IRD.")
        response = input("Are you sure? Type 'YES' to continue: ")
        if response != "YES":
            print("Cancelled.")
            return
        limit = None
    else:
        limit = args.limit

    print("="*100)
    print("AUTOMATED PAN DISCOVERY")
    print("="*100)
    print()
    if args.dry_run:
        print("🔍 DRY RUN MODE - No database updates")
        print()

    # Query companies
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
                )
            )
            .order_by(CompanyRegistration.last_communication_bs.desc())
        )

        if args.district:
            stmt = stmt.where(CompanyRegistration.district == args.district)

        if limit:
            stmt = stmt.limit(limit)

        result = await db.execute(stmt)
        companies = list(result.scalars().all())

    print(f"📋 Processing {len(companies)} companies")
    print()

    # Statistics
    discovered_count = 0
    updated_count = 0
    enriched_count = 0
    failed_count = 0

    discoveries = []  # Store for summary

    # Initialize clients
    async with IRDNameSearchClient(max_concurrency=1, headless=args.headless) as name_client:
        ird_client = None
        if args.enrich and not args.dry_run:
            ird_client = await IRDClient(max_concurrency=1, headless=args.headless).__aenter__()

        try:
            for idx, company in enumerate(companies, 1):
                print(f"\n[{idx}/{len(companies)}]", end=" ")

                try:
                    # Discover PAN
                    discovery = await discover_pan_for_company(
                        company,
                        name_client,
                        min_match_score=args.min_score,
                    )

                    if discovery:
                        discovered_count += 1
                        discoveries.append({
                            "registration_number": company.registration_number,
                            "name_english": company.name_english,
                            "pan": discovery["pan"],
                            "match_score": discovery["match_score"],
                        })

                        if not args.dry_run:
                            # Update database with PAN
                            async with AsyncSessionLocal() as db:
                                stmt = (
                                    update(CompanyRegistration)
                                    .where(CompanyRegistration.registration_number == company.registration_number)
                                    .values(
                                        pan=discovery["pan"],
                                        updated_at=datetime.utcnow(),
                                    )
                                )
                                await db.execute(stmt)
                                await db.commit()
                                updated_count += 1
                                print(f"  💾 Database updated")

                            # IRD enrichment
                            if args.enrich and ird_client:
                                try:
                                    print(f"  🌐 Fetching IRD data...")
                                    ird_data = await ird_client.search_pan(discovery["pan"])

                                    if ird_data and ird_data.get("panDetails"):
                                        detail = ird_data["panDetails"][0]

                                        # Hash phone numbers
                                        phone_h = hash_phone(detail.get("telephone"))
                                        mobile_h = hash_phone(detail.get("mobile"))

                                        # Upsert enrichment
                                        from sqlalchemy.dialects.postgresql import insert as pg_insert

                                        async with AsyncSessionLocal() as db:
                                            enrichment_data = {
                                                "pan": discovery["pan"],
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

                                            # Mark company as enriched
                                            stmt = (
                                                update(CompanyRegistration)
                                                .where(CompanyRegistration.registration_number == company.registration_number)
                                                .values(
                                                    ird_enriched=True,
                                                    ird_enriched_at=datetime.utcnow(),
                                                )
                                            )
                                            await db.execute(stmt)
                                            await db.commit()
                                            enriched_count += 1
                                            print(f"  ✅ IRD enrichment completed")

                                except Exception as e:
                                    print(f"  ⚠️  IRD enrichment failed: {e}")
                    else:
                        failed_count += 1

                    # Be polite - pause between requests
                    await asyncio.sleep(2)

                except Exception as e:
                    print(f"\n  ❌ Error processing company: {e}")
                    failed_count += 1

        finally:
            if ird_client:
                await ird_client.close()

    # Summary
    print()
    print("="*100)
    print("DISCOVERY SUMMARY")
    print("="*100)
    print()
    print(f"📊 Processed: {len(companies)} companies")
    print(f"✅ Discovered PANs: {discovered_count}")
    if not args.dry_run:
        print(f"💾 Database updated: {updated_count}")
        if args.enrich:
            print(f"🌐 IRD enriched: {enriched_count}")
    print(f"❌ Failed: {failed_count}")
    print()

    # Save discoveries to file
    if discoveries:
        output_dir = Path(__file__).parent.parent / "investigation_output"
        output_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = output_dir / f"pan_discoveries_{timestamp}.json"

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(discoveries, f, indent=2, ensure_ascii=False)

        print(f"📄 Discoveries saved to: {output_file}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
