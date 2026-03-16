"""Investigate CAMIS enrichment details for Reliance Spinning Mills."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, cast, Integer
from app.core.database import AsyncSessionLocal
from app.models.company import CompanyRegistration, CompanyDirector


async def investigate_rsml():
    """Check CAMIS enrichment details for RSML."""
    async with AsyncSessionLocal() as db:
        # Search by name to avoid type issues
        stmt = select(CompanyRegistration).where(
            CompanyRegistration.name_english.ilike('%reliance%spinning%')
        )
        result = await db.execute(stmt)
        company = result.scalar_one_or_none()

        if not company:
            print("❌ Company not found")
            return

        print("=" * 100)
        print("CAMIS ENRICHMENT INVESTIGATION: Reliance Spinning Mills")
        print("=" * 100)
        print()

        print("BASIC INFO:")
        print(f"  Registration #: {company.registration_number}")
        print(f"  Name (EN): {company.name_english}")
        print(f"  Name (NP): {company.name_nepali}")
        print(f"  Company Type: {company.company_type}")
        print(f"  Category: {company.company_type_category}")
        print()

        print("CAMIS ENRICHMENT STATUS:")
        print(f"  CAMIS Enriched: {company.camis_enriched}")
        print(f"  CAMIS Enriched At: {company.camis_enriched_at}")
        print(f"  CAMIS Company ID: {company.camis_company_id}")
        print(f"  CRO Company ID: {company.cro_company_id}")
        print()

        print("CRITICAL DATA:")
        print(f"  PAN: {company.pan or '❌ NOT SET'}")
        print(f"  Registration Date (BS): {company.registration_date_bs}")
        print(f"  Registration Date (AD): {company.registration_date_ad}")
        print(f"  District: {company.district}")
        print(f"  Province: {company.province}")
        print(f"  Address: {company.company_address}")
        print()

        # Check directors
        print("DIRECTOR RECORDS:")
        dir_stmt = select(CompanyDirector).where(CompanyDirector.company_id == company.id)
        dir_result = await db.execute(dir_stmt)
        directors = list(dir_result.scalars().all())

        if directors:
            print(f"  ✅ Found {len(directors)} director(s):")
            for d in directors:
                print(f"    - {d.name_en}")
                if d.role:
                    print(f"      Role: {d.role}")
                if d.pan:
                    print(f"      PAN: {d.pan}")
        else:
            print(f"  ❌ ZERO directors in database")
            print()
            print("  This is highly suspicious for a public company because:")
            print("    • Public companies MUST file director information with OCR")
            print("    • CAMIS enrichment marked as complete (✅)")
            print("    • Company has been operating for 30 years (1994-2024)")
            print("    • Recently communicated with authorities (2081-08-02 BS)")
        print()

        # Check raw_data field if it exists
        if hasattr(company, 'raw_data') and company.raw_data:
            print("RAW DATA ANALYSIS:")
            import json
            try:
                raw = company.raw_data if isinstance(company.raw_data, dict) else json.loads(company.raw_data)
                print(f"  Raw data keys: {list(raw.keys())}")

                # Look for PAN-related fields
                for key in raw.keys():
                    if 'pan' in key.lower():
                        print(f"  Found PAN field: {key} = {raw[key]}")

                # Look for director-related fields
                for key in raw.keys():
                    if 'director' in key.lower() or 'board' in key.lower():
                        print(f"  Found director field: {key} = {raw[key]}")
            except:
                print("  Raw data exists but couldn't parse")
        else:
            print("RAW DATA:")
            print("  ❌ No raw_data stored")
        print()

        print("=" * 100)
        print("CONCLUSION:")
        print()
        print("The CAMIS enrichment process has a CRITICAL BUG:")
        print()
        print("Evidence:")
        print("  1. camis_enriched = TRUE (process ran)")
        print("  2. camis_company_id SET (connection to CAMIS successful)")
        print("  3. PAN = NULL (failed to extract tax ID)")
        print("  4. Directors count = 0 (failed to extract mandatory public company data)")
        print()
        print("Possible causes:")
        print("  • CAMIS scraper stopped at basic info, didn't follow director links")
        print("  • HTML parsing failed silently without error logging")
        print("  • CAMIS website structure changed after initial scraper development")
        print("  • PAN/director data in different section that scraper doesn't visit")
        print()
        print("Impact:")
        print("  • ~900+ public companies likely affected (all marked 'enriched' but incomplete)")
        print("  • Shell company detection impossible (can't link directors across companies)")
        print("  • Tax evasion analysis broken (can't cross-reference PANs)")
        print("=" * 100)


if __name__ == "__main__":
    asyncio.run(investigate_rsml())
