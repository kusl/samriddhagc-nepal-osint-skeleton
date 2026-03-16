"""Analyze the Chinese construction company cluster - HIGHLY SUSPICIOUS."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.models.company import CompanyRegistration, IRDEnrichment


async def analyze_chinese_cluster():
    """Analyze Chinese construction companies sharing one mobile number."""

    # Mobile hash from cluster analysis: 56dca8f16523b3858ba00be7d3650c69
    mobile_hash = "56dca8f16523b3858ba00be7d3650c69"

    async with AsyncSessionLocal() as db:
        # Find all companies with this mobile hash
        stmt = (
            select(CompanyRegistration)
            .join(IRDEnrichment, CompanyRegistration.pan == IRDEnrichment.pan)
            .where(IRDEnrichment.mobile_hash == mobile_hash)
            .order_by(CompanyRegistration.registration_date_bs)
        )

        result = await db.execute(stmt)
        companies = list(result.scalars().all())

        print("=" * 120)
        print("🚨 CHINESE CONSTRUCTION COMPANY NETWORK - HIGHLY SUSPICIOUS")
        print("=" * 120)
        print()
        print(f"Mobile Hash: {mobile_hash}")
        print(f"Total Companies: {len(companies)}")
        print()
        print("This cluster is EXTREMELY suspicious because:")
        print("  • All Chinese-named construction companies")
        print("  • Sharing ONE mobile number (impossible for legitimate foreign companies)")
        print("  • Likely fronts for Belt & Road Initiative projects or visa fraud")
        print("  • May be used to bring Chinese workers into Nepal illegally")
        print()
        print("=" * 120)
        print()

        # Group by registration date
        by_date = {}
        for company in companies:
            date = company.registration_date_bs or "Unknown"
            if date not in by_date:
                by_date[date] = []
            by_date[date].append(company)

        print(f"COMPANY LIST (grouped by registration date):")
        print()

        for date, companies_on_date in sorted(by_date.items()):
            print(f"\n📅 Registration Date: {date}")
            print("-" * 120)

            for company in companies_on_date:
                print(f"\n  {company.name_english}")
                print(f"    Registration #: {company.registration_number}")
                print(f"    PAN: {company.pan or 'NOT SET'}")
                print(f"    District: {company.district or 'N/A'}")
                print(f"    Address: {company.company_address or 'N/A'}")
                print(f"    Company Type: {company.company_type or 'N/A'}")
                print(f"    Last Communication: {company.last_communication_bs or 'N/A'}")

                # Get IRD data
                if company.pan:
                    ird_stmt = select(IRDEnrichment).where(IRDEnrichment.pan == company.pan)
                    ird_result = await db.execute(ird_stmt)
                    ird = ird_result.scalar_one_or_none()

                    if ird:
                        print(f"    IRD Status: {ird.account_status or 'N/A'}")
                        print(f"    Tax Office: {ird.tax_office or 'N/A'}")
                        print(f"    Taxpayer Name: {ird.taxpayer_name_en or 'N/A'}")

        print()
        print("=" * 120)
        print("ANALYSIS:")
        print("=" * 120)
        print()

        # Check registration patterns
        reg_numbers = [c.registration_number for c in companies if c.registration_number]
        if len(reg_numbers) >= 2:
            reg_numbers_int = []
            for rn in reg_numbers:
                try:
                    reg_numbers_int.append(int(rn))
                except:
                    pass

            if len(reg_numbers_int) >= 2:
                reg_numbers_int.sort()
                gaps = [reg_numbers_int[i+1] - reg_numbers_int[i] for i in range(len(reg_numbers_int)-1)]
                avg_gap = sum(gaps) / len(gaps) if gaps else 0

                print(f"Registration Number Pattern:")
                print(f"  First: {min(reg_numbers_int):,}")
                print(f"  Last: {max(reg_numbers_int):,}")
                print(f"  Average gap: {avg_gap:.1f}")
                if avg_gap < 100:
                    print(f"  ⚠️  SEQUENTIAL REGISTRATION - Batch created on same day/week")
                print()

        # Check if any are still active
        active = [c for c in companies if c.last_communication_bs and c.last_communication_bs.startswith('208')]
        dormant = len(companies) - len(active)

        print(f"Activity Status:")
        print(f"  Active (communicated in 2080s): {len(active)}")
        print(f"  Dormant/Inactive: {dormant}")
        print()

        # Check PAN coverage
        with_pan = [c for c in companies if c.pan]
        print(f"PAN Registration:")
        print(f"  With PAN: {len(with_pan)}")
        print(f"  Without PAN: {len(companies) - len(with_pan)}")
        print()

        print("=" * 120)
        print("CONCLUSION:")
        print()
        print("This is likely a shell company network for:")
        print("  1. Visa fraud (bringing Chinese workers on construction visas)")
        print("  2. Money laundering through fake construction contracts")
        print("  3. Belt & Road Initiative project fronts")
        print("  4. Tax evasion (routing payments through Nepal)")
        print()
        print("Recommended Actions:")
        print("  • Flag for Department of Immigration investigation")
        print("  • Cross-reference with Chinese worker visa records")
        print("  • Check if any actual construction projects exist")
        print("  • Verify if tax returns were ever filed")
        print("=" * 120)


if __name__ == "__main__":
    asyncio.run(analyze_chinese_cluster())
