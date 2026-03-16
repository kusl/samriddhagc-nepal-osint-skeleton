"""Analyze the specific NATIONAL COLLEGE OF COMPUTER STUDIES company."""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, func, and_, or_
from app.core.database import AsyncSessionLocal
from app.models.company import CompanyRegistration, IRDEnrichment, CompanyDirector


async def analyze_nccs_specific():
    """Analyze NATIONAL COLLEGE OF COMPUTER STUDIES."""
    async with AsyncSessionLocal() as db:
        # Search for exact match
        search_stmt = (
            select(CompanyRegistration)
            .where(CompanyRegistration.name_english == 'NATIONAL COLLEGE OF COMPUTER STUDIES')
        )

        result = await db.execute(search_stmt)
        company = result.scalar_one_or_none()

        if not company:
            print("Company 'NATIONAL COLLEGE OF COMPUTER STUDIES' not found")
            return

        print("="*120)
        print("NATIONAL COLLEGE OF COMPUTER STUDIES (NCCS) - DETAILED ANALYSIS")
        print("="*120)
        print()

        # Basic info
        print("### 1. COMPANY REGISTRATION DETAILS ###\n")
        print(f"Company Name (EN): {company.name_english}")
        print(f"Company Name (NP): {company.name_nepali or 'N/A'}")
        print(f"PAN: {company.pan or 'NOT REGISTERED'}")
        print(f"Registration Number: {company.registration_number}")
        print(f"Registration Date (BS): {company.registration_date_bs or 'N/A'}")
        print(f"Registration Date (AD): {company.registration_date_ad.strftime('%Y-%m-%d') if company.registration_date_ad else 'N/A'}")
        print(f"Company Type: {company.company_type or 'N/A'}")
        print(f"Company Type Category: {company.company_type_category or 'N/A'}")
        print(f"District: {company.district or 'N/A'}")
        print(f"Province: {company.province or 'N/A'}")
        print(f"Address: {company.company_address or 'N/A'}")
        print(f"Last Communication (BS): {company.last_communication_bs or 'N/A'}")
        print(f"CAMIS Enriched: {company.camis_enriched}")
        print(f"IRD Enriched: {company.ird_enriched}")
        print()

        # IRD info
        print("### 2. TAX COMPLIANCE STATUS ###\n")
        if company.pan:
            ird_stmt = select(IRDEnrichment).where(IRDEnrichment.pan == company.pan)
            ird_result = await db.execute(ird_stmt)
            ird = ird_result.scalar_one_or_none()

            if ird:
                print(f"IRD Status: {ird.account_status or 'N/A'}")
                print(f"Taxpayer Name: {ird.taxpayer_name_en or 'N/A'}")
                print(f"Tax Office: {ird.tax_office or 'N/A'}")
                print(f"Latest Tax Clearance: {ird.latest_tax_clearance_fy or 'N/A'}")
            else:
                print("⚠️  PAN exists but no IRD enrichment data available")
        else:
            print("❌ NO PAN NUMBER REGISTERED")
            print("   This company does not have a PAN number, which means:")
            print("   - Not registered with Inland Revenue Department")
            print("   - Cannot legally conduct taxable business")
            print("   - May be dormant or non-operational")
        print()

        # Directors
        print("### 3. DIRECTORS & OWNERSHIP ###\n")
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
                print(f"{idx}. {d.name_en}")
                if d.name_np:
                    print(f"   Nepali: {d.name_np}")
                if d.role:
                    print(f"   Role: {d.role}")
                if d.pan:
                    print(f"   Director PAN: {d.pan}")
                if d.citizenship_no:
                    print(f"   Citizenship: {d.citizenship_no}")
                if d.appointed_date:
                    print(f"   Appointed: {d.appointed_date.strftime('%Y-%m-%d')}")
                print(f"   Source: {d.source}, Confidence: {d.confidence}")
                print()

            # Find other companies with same directors
            print("### 4. DIRECTOR NETWORK ###\n")
            director_companies = {}

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
                        .order_by(CompanyRegistration.name_english)
                        .limit(20)
                    )
                    shared_result = await db.execute(shared_stmt)
                    shared_companies = list(shared_result.scalars().all())

                    if shared_companies:
                        director_companies[director.name_en] = shared_companies

            if director_companies:
                for dir_name, companies in director_companies.items():
                    print(f"Director '{dir_name}' also serves in {len(companies)} other companies:")
                    for c in companies[:10]:  # Show first 10
                        print(f"  - {c.name_english} (PAN: {c.pan or 'N/A'})")
                    if len(companies) > 10:
                        print(f"  ... and {len(companies) - 10} more")
                    print()
            else:
                print("Directors don't serve in any other companies")
                print()
        else:
            print("❌ NO DIRECTOR INFORMATION AVAILABLE")
            print("   This is unusual and suggests incomplete company records")
            print()

        # Address clustering
        print("### 5. ADDRESS CLUSTERING ###\n")
        if company.company_address:
            # Get count
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

            print(f"Address: {company.company_address}")
            print(f"Companies at this address: {address_count + 1} (including NCCS)")
            print()

            if address_count >= 1000:
                print("🚨 CRITICAL: This is a MASS REGISTRATION ADDRESS")
                print("   This address is shared by 1000+ companies")
                print("   Likely a virtual office or company formation service")
            elif address_count >= 100:
                print("⚠️  HIGH: This address is shared by 100+ companies")
                print("   Likely a virtual office or shared business center")
            elif address_count >= 20:
                print("⚠️  MEDIUM: This address is shared by 20+ companies")
                print("   Possibly a shared office or business center")

            # Get sample companies at same address
            if address_count > 0:
                print(f"\nSample companies at same address (showing first 10):")
                sample_stmt = (
                    select(CompanyRegistration)
                    .where(
                        and_(
                            CompanyRegistration.company_address == company.company_address,
                            CompanyRegistration.id != company.id
                        )
                    )
                    .order_by(CompanyRegistration.name_english)
                    .limit(10)
                )
                sample_result = await db.execute(sample_stmt)
                sample_companies = list(sample_result.scalars().all())

                for c in sample_companies:
                    print(f"  - {c.name_english}")
        else:
            print("No address information available")
        print()

        # Summary
        print("="*120)
        print("SUMMARY & RISK ASSESSMENT")
        print("="*120)
        print()

        print("Status: ", end="")
        if not company.pan:
            print("❌ INACTIVE/NON-OPERATIONAL")
        elif company.ird_enriched:
            print("✓ ACTIVE & TAX COMPLIANT")
        else:
            print("⚠️  UNCERTAIN")
        print()

        print("Key Findings:")
        findings = []

        if not company.pan:
            findings.append("❌ No PAN number - not registered for taxation")

        if not directors:
            findings.append("❌ No director information - incomplete records")

        if address_count and address_count >= 100:
            findings.append(f"⚠️  Registered at virtual office address ({address_count + 1} companies)")

        if not company.last_communication_bs:
            findings.append("⚠️  No recent communication with Company Registrar")

        if not findings:
            findings.append("✓ No major red flags detected")

        for finding in findings:
            print(f"  {finding}")

        print()
        print("Conclusion:")
        if not company.pan and not directors:
            print("  This company appears to be DORMANT or NON-OPERATIONAL.")
            print("  It was registered in 2063 BS (~2006-2007 AD) but never obtained a PAN number.")
            print("  The company is likely inactive and may have never conducted business.")
        elif not company.pan:
            print("  This company is registered but NOT TAX-COMPLIANT.")
            print("  Without a PAN number, it cannot legally conduct taxable business in Nepal.")
        else:
            print("  Company is registered and has a PAN number.")

        print("="*120)
        print()


if __name__ == "__main__":
    asyncio.run(analyze_nccs_specific())
