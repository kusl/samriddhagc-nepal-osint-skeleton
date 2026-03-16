"""Get PAN numbers for Reliance Spinning Mills and Shivam Plastic Industries."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, or_
from app.core.database import AsyncSessionLocal
from app.models.company import CompanyRegistration, IRDEnrichment


async def get_pan_numbers():
    """Search for PAN numbers."""
    async with AsyncSessionLocal() as db:
        print("=" * 100)
        print("SEARCHING FOR PAN NUMBERS")
        print("=" * 100)
        print()

        # Search for both companies
        companies_to_search = [
            ("Reliance Spinning Mills", "%reliance%spinning%"),
            ("Shivam Plastic Industries", "%shivam%plastic%"),
        ]

        for company_name, pattern in companies_to_search:
            print("-" * 100)
            print(f"COMPANY: {company_name}")
            print("-" * 100)

            stmt = select(CompanyRegistration).where(
                CompanyRegistration.name_english.ilike(pattern)
            )
            result = await db.execute(stmt)
            companies = list(result.scalars().all())

            if not companies:
                print(f"❌ NOT FOUND in database")
                print()
                continue

            for company in companies:
                print(f"\nFound: {company.name_english}")
                print(f"  Registration #: {company.registration_number}")
                print(f"  District: {company.district or 'N/A'}")
                print(f"  Address: {company.company_address or 'N/A'}")

                # Check PAN from company_registrations
                if company.pan:
                    print(f"  ✅ PAN (from CAMIS): {company.pan}")
                else:
                    print(f"  ❌ PAN: NOT SET in company_registrations table")

                # Check IRD enrichment
                if company.pan:
                    ird_stmt = select(IRDEnrichment).where(IRDEnrichment.pan == company.pan)
                    ird_result = await db.execute(ird_stmt)
                    ird = ird_result.scalar_one_or_none()

                    if ird:
                        print(f"  ✅ IRD Status: {ird.account_status or 'N/A'}")
                        print(f"  ✅ Tax Office: {ird.tax_office or 'N/A'}")
                        print(f"  ✅ Taxpayer Name: {ird.taxpayer_name_en or 'N/A'}")
                    else:
                        print(f"  ⚠️  PAN exists but no IRD enrichment data")

                print(f"  CAMIS Enriched: {company.camis_enriched}")
                print(f"  IRD Enriched: {company.ird_enriched}")
                print()

        print("=" * 100)
        print("\nNOTE: If PAN is missing, it means:")
        print("  1. CAMIS CRO API endpoint didn't return panNumber for this company")
        print("  2. Company may not have registered PAN with tax authorities")
        print("  3. PAN data may be in a different CAMIS endpoint that we don't scrape")
        print("=" * 100)


if __name__ == "__main__":
    asyncio.run(get_pan_numbers())
