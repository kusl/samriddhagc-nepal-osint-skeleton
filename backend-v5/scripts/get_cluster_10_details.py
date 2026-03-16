"""Get detailed information for mobile cluster #10 (Golyan Group cluster)."""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, func, and_
from app.core.database import AsyncSessionLocal
from app.models.company import CompanyRegistration, IRDEnrichment, CompanyDirector


async def get_cluster_10_details():
    """Get full details of the Golyan Group mobile cluster (11 companies)."""
    async with AsyncSessionLocal() as db:
        # Find the mobile hash for cluster with ~11 companies (Golyan Group)
        # Based on previous output, this should be the hash starting with 693724bb

        mobile_counts = (
            select(
                IRDEnrichment.mobile_hash,
                func.count(IRDEnrichment.id).label("company_count"),
            )
            .where(
                and_(
                    IRDEnrichment.mobile_hash.isnot(None),
                    IRDEnrichment.mobile_hash != "",
                )
            )
            .group_by(IRDEnrichment.mobile_hash)
            .having(func.count(IRDEnrichment.id) >= 10)
            .order_by(func.count(IRDEnrichment.id).desc())
        )

        result = await db.execute(mobile_counts)
        mobile_clusters = result.all()

        # Get the cluster with 11 companies (should be around position 10)
        target_cluster = None
        for mobile_hash, count in mobile_clusters:
            if count == 11:
                target_cluster = (mobile_hash, count)
                break

        if not target_cluster:
            # If exact match not found, use the last cluster from our list
            print("Looking for clusters with 11 companies...")
            for mobile_hash, count in mobile_clusters:
                print(f"Found cluster with {count} companies, hash: {mobile_hash[:32]}...")
            target_cluster = mobile_clusters[-1] if mobile_clusters else None

        if not target_cluster:
            print("Could not find cluster #10")
            return

        mobile_hash, count = target_cluster

        print("="*120)
        print(f"MOBILE CLUSTER #10: {count} COMPANIES (GOLYAN GROUP)")
        print("="*120)
        print(f"Mobile Hash: {mobile_hash}")
        print("="*120)
        print()

        # Get all companies in this cluster with full details
        companies_stmt = (
            select(CompanyRegistration, IRDEnrichment)
            .join(IRDEnrichment, CompanyRegistration.pan == IRDEnrichment.pan)
            .where(IRDEnrichment.mobile_hash == mobile_hash)
            .order_by(CompanyRegistration.name_english)
        )
        companies_result = await db.execute(companies_stmt)
        companies_data = companies_result.all()

        print(f"{'#':<4} {'Company Name':<50} {'PAN':<15} {'IRD Status':<20} {'Type':<30}")
        print("-" * 120)

        for idx, (company, ird) in enumerate(companies_data, 1):
            company_name = company.name_english or "(unnamed)"
            pan = company.pan or "N/A"
            ird_status = ird.account_status or "N/A"
            company_type = company.company_type or "N/A"

            print(f"{idx:<4} {company_name[:50]:<50} {pan:<15} {ird_status:<20} {company_type[:30]:<30}")

        print("\n" + "="*120)
        print("DETAILED COMPANY INFORMATION")
        print("="*120)

        for idx, (company, ird) in enumerate(companies_data, 1):
            print(f"\n{'─'*120}")
            print(f"COMPANY #{idx}: {company.name_english}")
            print(f"{'─'*120}")
            print(f"PAN: {company.pan}")
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
            print("IRD INFORMATION:")
            print(f"  IRD Status: {ird.account_status or 'N/A'}")
            print(f"  Taxpayer Name (EN): {ird.taxpayer_name_en or 'N/A'}")
            print(f"  Taxpayer Name (NP): {ird.taxpayer_name_np or 'N/A'}")
            print(f"  Account Type: {ird.account_type or 'N/A'}")
            print(f"  Tax Office: {ird.tax_office or 'N/A'}")
            print(f"  Registration Date (BS): {ird.registration_date_bs or 'N/A'}")
            print(f"  Latest Tax Clearance FY: {ird.latest_tax_clearance_fy or 'N/A'}")
            print(f"  Tax Clearance Verified: {ird.tax_clearance_verified or 'N/A'}")

            # Get directors for this company
            directors_stmt = (
                select(CompanyDirector)
                .where(CompanyDirector.company_id == company.id)
                .order_by(CompanyDirector.name_en)
            )
            directors_result = await db.execute(directors_stmt)
            directors = list(directors_result.scalars().all())

            if directors:
                print()
                print(f"DIRECTORS ({len(directors)}):")
                for d in directors:
                    print(f"  - {d.name_en}")
                    if d.role:
                        print(f"    Role: {d.role}")
                    if d.citizenship_no:
                        print(f"    Citizenship: {d.citizenship_no}")
                    if d.pan:
                        print(f"    PAN: {d.pan}")
                    if d.appointed_date:
                        print(f"    Appointed: {d.appointed_date.strftime('%Y-%m-%d')}")
            else:
                print()
                print("DIRECTORS: No director information available")

        # Analysis
        print("\n" + "="*120)
        print("CLUSTER ANALYSIS")
        print("="*120)

        # Check for patterns
        all_names = [c.name_english for c, _ in companies_data if c.name_english]

        # Golyan pattern
        golyan_count = sum(1 for name in all_names if 'golyan' in name.lower())
        agro_count = sum(1 for name in all_names if 'agro' in name.lower())

        print(f"\nName Patterns:")
        print(f"  Companies with 'Golyan' in name: {golyan_count}")
        print(f"  Companies with 'Agro' in name: {agro_count}")

        # District analysis
        districts = [c.district for c, _ in companies_data if c.district]
        if districts:
            from collections import Counter
            district_counts = Counter(districts)
            print(f"\nDistrict Distribution:")
            for district, count in district_counts.most_common():
                print(f"  {district}: {count} companies")

        # Registration date analysis
        reg_dates = [c.registration_date_ad for c, _ in companies_data if c.registration_date_ad]
        if reg_dates:
            date_range = (max(reg_dates) - min(reg_dates)).days
            print(f"\nRegistration Timeline:")
            print(f"  Earliest: {min(reg_dates).strftime('%Y-%m-%d')}")
            print(f"  Latest: {max(reg_dates).strftime('%Y-%m-%d')}")
            print(f"  Date range: {date_range} days (~{date_range/365:.1f} years)")

        # Company type analysis
        company_types = [c.company_type_category for c, _ in companies_data if c.company_type_category]
        if company_types:
            from collections import Counter
            type_counts = Counter(company_types)
            print(f"\nCompany Type Distribution:")
            for ctype, count in type_counts.most_common():
                print(f"  {ctype}: {count} companies")

        # IRD status analysis
        ird_statuses = [i.account_status for _, i in companies_data if i.account_status]
        if ird_statuses:
            from collections import Counter
            status_counts = Counter(ird_statuses)
            print(f"\nIRD Status Distribution:")
            for status, count in status_counts.most_common():
                print(f"  {status}: {count} companies")

        print("\n" + "="*120)
        print("RISK ASSESSMENT")
        print("="*120)
        print("\n🚩 Risk Indicators:")
        print(f"  ✓ All companies share same mobile number")
        print(f"  ✓ {golyan_count} companies share 'Golyan' branding")
        if date_range < 365:
            print(f"  ✓ All companies registered within {date_range} days")
        if len(set(districts)) == 1:
            print(f"  ✓ All companies in same district ({districts[0]})")
        if agro_count > 0:
            print(f"  ✓ {agro_count} companies in agriculture sector (tax benefit exploitation)")

        print("\n💡 Assessment:")
        print("  This appears to be a corporate network under common control.")
        print("  The mix of Golyan-branded companies and agro/forestry companies")
        print("  suggests a business group diversifying into tax-advantaged sectors.")
        print("="*120 + "\n")


if __name__ == "__main__":
    asyncio.run(get_cluster_10_details())
