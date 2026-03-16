"""Search for Reliance Spinning Mills and Shivam Plastic Industries in the database."""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, or_
from app.core.database import AsyncSessionLocal
from app.models.company import CompanyRegistration, IRDEnrichment, CompanyDirector


async def search_companies():
    """Search for Reliance Spinning Mills and Shivam Plastic Industries."""
    async with AsyncSessionLocal() as db:
        # Define companies to search
        companies_to_search = [
            {
                "name": "RELIANCE SPINNING MILLS LTD (RSML)",
                "patterns": [
                    CompanyRegistration.name_english.ilike('%reliance%spinning%'),
                    CompanyRegistration.name_english.ilike('%rsml%'),
                    CompanyRegistration.name_nepali.ilike('%reliance%'),
                ]
            },
            {
                "name": "SHIVAM PLASTIC INDUSTRIES (Golyan Group)",
                "patterns": [
                    CompanyRegistration.name_english.ilike('%shivam%plastic%'),
                ]
            }
        ]

        for company_search in companies_to_search:
            print("="*120)
            print(f"SEARCHING: {company_search['name']}")
            print("="*120)
            print()

            # Search for the company
            search_stmt = (
                select(CompanyRegistration)
                .where(or_(*company_search['patterns']))
                .order_by(CompanyRegistration.name_english)
            )

            result = await db.execute(search_stmt)
            companies = list(result.scalars().all())

            if not companies:
                print("❌ NOT FOUND in database")
                print("\nThis could mean:")
                print("  - Company not yet scraped from OCR")
                print("  - Different name in Nepali registry")
                print("  - Registered under different legal name")
                print()
                continue

            print(f"✅ Found {len(companies)} matching company/companies:\n")

            for idx, company in enumerate(companies, 1):
                print(f"{'-'*120}")
                print(f"MATCH #{idx}: {company.name_english}")
                print(f"{'-'*120}")
                print(f"Company Name (EN): {company.name_english}")
                print(f"Company Name (NP): {company.name_nepali or 'N/A'}")

                # Highlight PAN status
                if company.pan:
                    print(f"✅ PAN: {company.pan}")
                else:
                    print(f"❌ PAN: NOT REGISTERED")

                print(f"Registration #: {company.registration_number}")
                print(f"Registration Date (BS): {company.registration_date_bs or 'N/A'}")
                print(f"Registration Date (AD): {company.registration_date_ad.strftime('%Y-%m-%d') if company.registration_date_ad else 'N/A'}")
                print(f"Company Type: {company.company_type or 'N/A'}")
                print(f"Company Type Category: {company.company_type_category or 'N/A'}")
                print(f"District: {company.district or 'N/A'}")
                print(f"Province: {company.province or 'N/A'}")
                print(f"Address: {company.company_address or 'N/A'}")
                print(f"Last Communication (BS): {company.last_communication_bs or 'N/A'}")
                print(f"CAMIS Enriched: {'✅' if company.camis_enriched else '❌'}")
                print(f"IRD Enriched: {'✅' if company.ird_enriched else '❌'}")
                print()

                # IRD data
                if company.pan:
                    print("IRD TAX INFORMATION:")
                    ird_stmt = select(IRDEnrichment).where(IRDEnrichment.pan == company.pan)
                    ird_result = await db.execute(ird_stmt)
                    ird = ird_result.scalar_one_or_none()

                    if ird:
                        print(f"  ✅ IRD Status: {ird.account_status or 'N/A'}")
                        print(f"  Taxpayer Name: {ird.taxpayer_name_en or 'N/A'}")
                        print(f"  Tax Office: {ird.tax_office or 'N/A'}")
                        print(f"  Registration Date (BS): {ird.registration_date_bs or 'N/A'}")
                        print(f"  Latest Tax Clearance: {ird.latest_tax_clearance_fy or 'N/A'}")
                        print(f"  Phone Hash: {'✅ Found' if ird.phone_hash else '❌ None'}")
                        print(f"  Mobile Hash: {'✅ Found' if ird.mobile_hash else '❌ None'}")
                    else:
                        print(f"  ⚠️  PAN exists but no IRD enrichment data yet")
                else:
                    print("❌ NO PAN NUMBER")
                    print("  Likely reasons:")
                    print("    - CAMIS CRO API didn't return PAN for this company")
                    print("    - Company hasn't registered with tax authorities")
                    print("    - PAN data in different CAMIS endpoint (not scraped)")
                print()

                # Directors
                print("DIRECTORS:")
                directors_stmt = (
                    select(CompanyDirector)
                    .where(CompanyDirector.company_id == company.id)
                    .order_by(CompanyDirector.name_en)
                )
                directors_result = await db.execute(directors_stmt)
                directors = list(directors_result.scalars().all())

                if directors:
                    print(f"  ✅ Found {len(directors)} director(s):")
                    for d in directors:
                        print(f"    - {d.name_en}")
                        if d.role:
                            print(f"      Role: {d.role}")
                        if d.pan:
                            print(f"      PAN: {d.pan}")
                        if d.citizenship_no:
                            print(f"      Citizenship: {d.citizenship_no}")
                else:
                    print(f"  ❌ No director information available")
                print()

            print("="*120)
            print()


if __name__ == "__main__":
    asyncio.run(search_companies())
