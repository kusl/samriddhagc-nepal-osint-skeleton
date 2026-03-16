"""Analyze NCCS company - find company, directors, related entities, and network."""
import asyncio
import sys
from pathlib import Path
from collections import Counter

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, func, and_, or_
from app.core.database import AsyncSessionLocal
from app.models.company import CompanyRegistration, IRDEnrichment, CompanyDirector


async def analyze_nccs():
    """Comprehensive analysis of NCCS company."""
    async with AsyncSessionLocal() as db:
        print("="*120)
        print("NCCS COMPANY ANALYSIS")
        print("="*120)
        print()

        # 1. Find companies matching "NCCS"
        print("### 1. SEARCHING FOR NCCS COMPANIES ###\n")

        search_stmt = (
            select(CompanyRegistration)
            .where(
                or_(
                    CompanyRegistration.name_english.ilike('%nccs%'),
                    CompanyRegistration.name_nepali.ilike('%nccs%'),
                )
            )
            .order_by(CompanyRegistration.name_english)
        )

        result = await db.execute(search_stmt)
        companies = list(result.scalars().all())

        if not companies:
            print("No companies found matching 'NCCS'")
            return

        print(f"Found {len(companies)} company/companies matching 'NCCS'\n")

        # Display all matches
        for idx, company in enumerate(companies, 1):
            print(f"{idx}. {company.name_english}")
            print(f"   PAN: {company.pan or 'N/A'}")
            print(f"   Registration #: {company.registration_number}")
            print(f"   District: {company.district or 'N/A'}")
            print()

        # Focus on the primary match (first one)
        company = companies[0]

        print("="*120)
        print(f"DETAILED ANALYSIS: {company.name_english}")
        print("="*120)
        print()

        # 2. Basic Company Information
        print("### 2. COMPANY REGISTRATION DETAILS ###\n")
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
        print(f"CAMIS Enriched: {company.camis_enriched}")
        print(f"IRD Enriched: {company.ird_enriched}")
        print()

        # 3. IRD Information
        if company.pan:
            print("### 3. IRD TAX INFORMATION ###\n")
            ird_stmt = select(IRDEnrichment).where(IRDEnrichment.pan == company.pan)
            ird_result = await db.execute(ird_stmt)
            ird = ird_result.scalar_one_or_none()

            if ird:
                print(f"IRD Status: {ird.account_status or 'N/A'}")
                print(f"Taxpayer Name (EN): {ird.taxpayer_name_en or 'N/A'}")
                print(f"Taxpayer Name (NP): {ird.taxpayer_name_np or 'N/A'}")
                print(f"Account Type: {ird.account_type or 'N/A'}")
                print(f"Tax Office: {ird.tax_office or 'N/A'}")
                print(f"Registration Date (BS): {ird.registration_date_bs or 'N/A'}")
                print(f"VDC/Municipality: {ird.vdc_municipality or 'N/A'}")
                print(f"Ward No: {ird.ward_no or 'N/A'}")
                print(f"Latest Tax Clearance FY: {ird.latest_tax_clearance_fy or 'N/A'}")
                print(f"Tax Clearance Verified: {ird.tax_clearance_verified}")
                print(f"Phone Hash: {ird.phone_hash[:32] + '...' if ird.phone_hash else 'N/A'}")
                print(f"Mobile Hash: {ird.mobile_hash[:32] + '...' if ird.mobile_hash else 'N/A'}")
                print()

                # Check for phone/mobile linked companies
                if ird.phone_hash:
                    print("### 4. PHONE-LINKED COMPANIES ###\n")
                    phone_stmt = (
                        select(CompanyRegistration, IRDEnrichment)
                        .join(IRDEnrichment, CompanyRegistration.pan == IRDEnrichment.pan)
                        .where(
                            and_(
                                IRDEnrichment.phone_hash == ird.phone_hash,
                                CompanyRegistration.id != company.id
                            )
                        )
                        .order_by(CompanyRegistration.name_english)
                    )
                    phone_result = await db.execute(phone_stmt)
                    phone_linked = phone_result.all()

                    if phone_linked:
                        print(f"Found {len(phone_linked)} companies sharing same phone number:\n")
                        for c, i in phone_linked:
                            print(f"  - {c.name_english}")
                            print(f"    PAN: {c.pan or 'N/A'}, District: {c.district or 'N/A'}")
                            print(f"    IRD Status: {i.account_status or 'N/A'}")
                    else:
                        print("No other companies share this phone number")
                    print()

                if ird.mobile_hash:
                    print("### 5. MOBILE-LINKED COMPANIES ###\n")
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
                        print(f"Found {len(mobile_linked)} companies sharing same mobile number:\n")
                        for c, i in mobile_linked:
                            print(f"  - {c.name_english}")
                            print(f"    PAN: {c.pan or 'N/A'}, District: {c.district or 'N/A'}")
                            print(f"    IRD Status: {i.account_status or 'N/A'}")
                    else:
                        print("No other companies share this mobile number")
                    print()
            else:
                print("No IRD enrichment data found")
                print()

        # 4. Directors
        print("### 6. DIRECTORS ###\n")
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
                    print(f"   Nepali Name: {d.name_np}")
                if d.role:
                    print(f"   Role: {d.role}")
                if d.pan:
                    print(f"   PAN: {d.pan}")
                if d.citizenship_no:
                    print(f"   Citizenship: {d.citizenship_no}")
                if d.appointed_date:
                    print(f"   Appointed: {d.appointed_date.strftime('%Y-%m-%d')}")
                if d.resigned_date:
                    print(f"   Resigned: {d.resigned_date.strftime('%Y-%m-%d')}")
                print(f"   Source: {d.source}")
                print(f"   Confidence: {d.confidence}")
                print()
        else:
            print("No director information available")
            print()

        # 5. Find other companies with shared directors
        if directors:
            print("### 7. DIRECTOR NETWORK (Companies with shared directors) ###\n")

            director_names = [d.name_en for d in directors if d.name_en]
            citizenship_nos = [d.citizenship_no for d in directors if d.citizenship_no]

            if director_names or citizenship_nos:
                # Search for other companies with same directors
                shared_companies = set()

                for director_name in director_names:
                    shared_stmt = (
                        select(CompanyRegistration)
                        .join(CompanyDirector, CompanyDirector.company_id == CompanyRegistration.id)
                        .where(
                            and_(
                                CompanyDirector.name_en == director_name,
                                CompanyRegistration.id != company.id
                            )
                        )
                        .distinct()
                    )
                    shared_result = await db.execute(shared_stmt)
                    shared_list = list(shared_result.scalars().all())

                    if shared_list:
                        print(f"Director '{director_name}' also serves in {len(shared_list)} other company/companies:")
                        for c in shared_list:
                            print(f"  - {c.name_english} (PAN: {c.pan or 'N/A'})")
                            shared_companies.add(c.id)
                        print()

                if not shared_companies:
                    print("No other companies found with shared directors")
                    print()
        else:
            print("### 7. DIRECTOR NETWORK ###\nNo directors available to analyze\n")

        # 6. Address clustering
        if company.company_address:
            print("### 8. ADDRESS CLUSTERING ###\n")
            address_stmt = (
                select(CompanyRegistration)
                .where(
                    and_(
                        CompanyRegistration.company_address == company.company_address,
                        CompanyRegistration.id != company.id
                    )
                )
                .order_by(CompanyRegistration.name_english)
                .limit(20)
            )
            address_result = await db.execute(address_stmt)
            address_companies = list(address_result.scalars().all())

            # Get total count
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
            total_count = count_result.scalar()

            if address_companies:
                print(f"Found {total_count} other companies at same address (showing first 20):\n")
                for c in address_companies:
                    print(f"  - {c.name_english} (PAN: {c.pan or 'N/A'})")
                print()
            else:
                print("No other companies at this address")
                print()

        # 7. PAN sharing
        if company.pan:
            print("### 9. PAN SHARING ###\n")
            pan_stmt = (
                select(CompanyRegistration)
                .where(
                    and_(
                        CompanyRegistration.pan == company.pan,
                        CompanyRegistration.id != company.id
                    )
                )
                .order_by(CompanyRegistration.name_english)
            )
            pan_result = await db.execute(pan_stmt)
            pan_companies = list(pan_result.scalars().all())

            if pan_companies:
                print(f"⚠️  WARNING: Found {len(pan_companies)} other companies sharing same PAN:\n")
                for c in pan_companies:
                    print(f"  - {c.name_english}")
                    print(f"    Registration: {c.registration_number}")
                print()
            else:
                print("✓ No PAN sharing detected")
                print()

        # 8. Summary & Risk Assessment
        print("="*120)
        print("RISK ASSESSMENT")
        print("="*120)
        print()

        risk_flags = []

        # Check IRD status
        if company.pan and ird:
            if ird.account_status and 'non-filer' in ird.account_status.lower():
                risk_flags.append(("HIGH", "IRD Non-filer status"))

        # Check PAN sharing
        if company.pan and pan_companies:
            risk_flags.append(("HIGH", f"PAN shared by {len(pan_companies) + 1} companies"))

        # Check address clustering
        if company.company_address and total_count and total_count >= 20:
            risk_flags.append(("MEDIUM", f"Address shared by {total_count + 1} companies"))

        # Check director network size
        if directors and shared_companies:
            if len(shared_companies) >= 5:
                risk_flags.append(("MEDIUM", f"Directors serve in {len(shared_companies)} other companies"))

        # Check phone/mobile clustering
        if company.pan and ird:
            if ird.phone_hash and phone_linked and len(phone_linked) >= 5:
                risk_flags.append(("MEDIUM", f"Phone number shared by {len(phone_linked) + 1} companies"))
            if ird.mobile_hash and mobile_linked and len(mobile_linked) >= 5:
                risk_flags.append(("MEDIUM", f"Mobile number shared by {len(mobile_linked) + 1} companies"))

        if risk_flags:
            print("🚩 Risk Flags Detected:\n")
            for severity, flag in risk_flags:
                print(f"  [{severity}] {flag}")
        else:
            print("✓ No significant risk flags detected")

        print("\n" + "="*120)
        print()


if __name__ == "__main__":
    asyncio.run(analyze_nccs())
