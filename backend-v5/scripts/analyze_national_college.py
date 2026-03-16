"""Analyze National College of Computer Studies."""
import asyncio
import sys
from pathlib import Path
from collections import Counter

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, func, and_, or_
from app.core.database import AsyncSessionLocal
from app.models.company import CompanyRegistration, IRDEnrichment, CompanyDirector


async def analyze_national_college():
    """Comprehensive analysis of National College of Computer Studies."""
    async with AsyncSessionLocal() as db:
        print("="*120)
        print("NATIONAL COLLEGE OF COMPUTER STUDIES - ANALYSIS")
        print("="*120)
        print()

        # Search for the college
        print("### SEARCHING ###\n")

        search_stmt = (
            select(CompanyRegistration)
            .where(
                or_(
                    CompanyRegistration.name_english.ilike('%national%college%computer%'),
                    CompanyRegistration.name_english.ilike('%nccs%'),
                    CompanyRegistration.name_english.ilike('%national%computer%'),
                )
            )
            .order_by(CompanyRegistration.name_english)
        )

        result = await db.execute(search_stmt)
        companies = list(result.scalars().all())

        if not companies:
            print("No exact matches found.")
            print("\nTrying broader search for 'National College'...")

            search_stmt2 = (
                select(CompanyRegistration)
                .where(CompanyRegistration.name_english.ilike('%national%college%'))
                .order_by(CompanyRegistration.name_english)
                .limit(20)
            )
            result2 = await db.execute(search_stmt2)
            companies = list(result2.scalars().all())

        if not companies:
            print("No companies found. The company may not be in the database.")
            return

        print(f"Found {len(companies)} matching companies:\n")

        for idx, c in enumerate(companies, 1):
            print(f"{idx}. {c.name_english}")
            print(f"   PAN: {c.pan or 'N/A'}")
            print(f"   District: {c.district or 'N/A'}")
            print()

        # If multiple matches, ask which one or analyze first
        if len(companies) == 1:
            company = companies[0]
        else:
            # Look for the most likely match
            for c in companies:
                if 'computer' in c.name_english.lower() and 'studies' in c.name_english.lower():
                    company = c
                    break
            else:
                company = companies[0]

        print("\n" + "="*120)
        print(f"ANALYZING: {company.name_english}")
        print("="*120)
        print()

        # Run the full analysis (same as NCCS script)
        await full_company_analysis(db, company)


async def full_company_analysis(db, company):
    """Full company analysis."""

    # Basic info
    print("### COMPANY REGISTRATION DETAILS ###\n")
    print(f"Company Name (EN): {company.name_english}")
    print(f"Company Name (NP): {company.name_nepali or 'N/A'}")
    print(f"PAN: {company.pan or 'N/A'}")
    print(f"Registration Number: {company.registration_number}")
    print(f"Registration Date (AD): {company.registration_date_ad.strftime('%Y-%m-%d') if company.registration_date_ad else 'N/A'}")
    print(f"Registration Date (BS): {company.registration_date_bs or 'N/A'}")
    print(f"Company Type: {company.company_type or 'N/A'}")
    print(f"Company Type Category: {company.company_type_category or 'N/A'}")
    print(f"District: {company.district or 'N/A'}")
    print(f"Province: {company.province or 'N/A'}")
    print(f"Address: {company.company_address or 'N/A'}")
    print(f"Last Communication (BS): {company.last_communication_bs or 'N/A'}")
    print()

    # IRD info
    if company.pan:
        print("### IRD TAX INFORMATION ###\n")
        ird_stmt = select(IRDEnrichment).where(IRDEnrichment.pan == company.pan)
        ird_result = await db.execute(ird_stmt)
        ird = ird_result.scalar_one_or_none()

        if ird:
            print(f"IRD Status: {ird.account_status or 'N/A'}")
            print(f"Taxpayer Name: {ird.taxpayer_name_en or 'N/A'}")
            print(f"Tax Office: {ird.tax_office or 'N/A'}")
            print(f"Latest Tax Clearance: {ird.latest_tax_clearance_fy or 'N/A'}")
            print()

            # Phone linked companies
            if ird.mobile_hash:
                print("### MOBILE-LINKED COMPANIES ###\n")
                mobile_stmt = (
                    select(CompanyRegistration, IRDEnrichment)
                    .join(IRDEnrichment, CompanyRegistration.pan == IRDEnrichment.pan)
                    .where(
                        and_(
                            IRDEnrichment.mobile_hash == ird.mobile_hash,
                            CompanyRegistration.id != company.id
                        )
                    )
                    .order_by(CompanyRegistration.name_english)
                )
                mobile_result = await db.execute(mobile_stmt)
                mobile_linked = mobile_result.all()

                if mobile_linked:
                    print(f"Found {len(mobile_linked)} companies sharing same mobile:\n")
                    for c, i in mobile_linked:
                        print(f"  - {c.name_english}")
                        print(f"    PAN: {c.pan}, IRD: {i.account_status or 'N/A'}")
                else:
                    print("No other companies share this mobile number")
                print()
        else:
            print("No IRD data available\n")

    # Directors
    print("### DIRECTORS ###\n")
    directors_stmt = (
        select(CompanyDirector)
        .where(CompanyDirector.company_id == company.id)
        .order_by(CompanyDirector.name_en)
    )
    directors_result = await db.execute(directors_stmt)
    directors = list(directors_result.scalars().all())

    if directors:
        print(f"Found {len(directors)} director(s):\n")
        for idx, d in enumerate(directors, 1):
            print(f"{idx}. {d.name_en} {f'({d.name_np})' if d.name_np else ''}")
            if d.role:
                print(f"   Role: {d.role}")
            if d.pan:
                print(f"   PAN: {d.pan}")
            if d.citizenship_no:
                print(f"   Citizenship: {d.citizenship_no}")
            print()

        # Find other companies with same directors
        print("### DIRECTOR NETWORK ###\n")
        for director in directors:
            if director.name_en:
                shared_stmt = (
                    select(CompanyRegistration)
                    .join(CompanyDirector, CompanyDirector.company_id == CompanyRegistration.id)
                    .where(
                        and_(
                            CompanyDirector.name_en == director.name_en,
                            CompanyRegistration.id != company.id
                        )
                    )
                    .limit(10)
                )
                shared_result = await db.execute(shared_stmt)
                shared_companies = list(shared_result.scalars().all())

                if shared_companies:
                    print(f"'{director.name_en}' also serves in {len(shared_companies)} other companies:")
                    for c in shared_companies:
                        print(f"  - {c.name_english}")
                    print()
    else:
        print("No director information available\n")

    # Address clustering
    if company.company_address:
        print("### ADDRESS CLUSTERING ###\n")
        count_stmt = (
            select(func.count(CompanyRegistration.id))
            .where(
                and_(
                    CompanyRegistration.company_address == company.company_address,
                    CompanyRegistration.id != company.id
                )
            )
        )
        count_result = await db.execute(count_stmt)
        address_count = count_result.scalar()

        if address_count > 0:
            print(f"Found {address_count} other companies at same address")
            if address_count >= 20:
                print("⚠️  HIGH address clustering - potential virtual office")
        else:
            print("No other companies at this address")
        print()

    print("="*120)


if __name__ == "__main__":
    asyncio.run(analyze_national_college())
