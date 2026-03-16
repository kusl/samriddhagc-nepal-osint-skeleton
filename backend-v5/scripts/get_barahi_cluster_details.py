"""Get detailed information for Barahi Holdings cluster."""
import asyncio
import sys
from pathlib import Path
from collections import Counter

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, func, and_
from app.core.database import AsyncSessionLocal
from app.models.company import CompanyRegistration, IRDEnrichment, CompanyDirector


async def get_barahi_cluster_details():
    """Get full details of the Barahi Holdings mobile cluster (12 companies)."""
    async with AsyncSessionLocal() as db:
        # Find the mobile hash for cluster with 12 companies containing "Holdings"

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
            .having(func.count(IRDEnrichment.id) >= 12)
            .order_by(func.count(IRDEnrichment.id).desc())
        )

        result = await db.execute(mobile_counts)
        mobile_clusters = result.all()

        # Find the cluster with 12 companies (Holdings cluster)
        target_cluster = None
        for mobile_hash, count in mobile_clusters:
            if count == 12:
                # Check if it contains "Holdings" companies
                companies_stmt = (
                    select(CompanyRegistration)
                    .join(IRDEnrichment, CompanyRegistration.pan == IRDEnrichment.pan)
                    .where(IRDEnrichment.mobile_hash == mobile_hash)
                    .limit(1)
                )
                test_result = await db.execute(companies_stmt)
                test_company = test_result.scalar_one_or_none()

                if test_company and 'holding' in (test_company.name_english or '').lower():
                    target_cluster = (mobile_hash, count)
                    break

        if not target_cluster:
            print("Looking for Holdings clusters with 12 companies...")
            for mobile_hash, count in mobile_clusters:
                companies_stmt = (
                    select(CompanyRegistration)
                    .join(IRDEnrichment, CompanyRegistration.pan == IRDEnrichment.pan)
                    .where(IRDEnrichment.mobile_hash == mobile_hash)
                    .limit(3)
                )
                test_result = await db.execute(companies_stmt)
                test_companies = list(test_result.scalars().all())
                sample_names = [c.name_english for c in test_companies if c.name_english]
                print(f"Cluster with {count} companies: {', '.join(sample_names[:3])}")

            # If not found, try to find by searching for "Holdings" pattern
            holdings_stmt = (
                select(IRDEnrichment.mobile_hash, func.count(IRDEnrichment.id).label("cnt"))
                .join(CompanyRegistration, CompanyRegistration.pan == IRDEnrichment.pan)
                .where(
                    and_(
                        IRDEnrichment.mobile_hash.isnot(None),
                        IRDEnrichment.mobile_hash != "",
                        CompanyRegistration.name_english.ilike('%holdings%')
                    )
                )
                .group_by(IRDEnrichment.mobile_hash)
                .having(func.count(IRDEnrichment.id) >= 5)
                .order_by(func.count(IRDEnrichment.id).desc())
            )
            holdings_result = await db.execute(holdings_stmt)
            holdings_clusters = holdings_result.all()

            if holdings_clusters:
                target_cluster = holdings_clusters[0]
                print(f"\nFound Holdings cluster with {target_cluster[1]} companies")
            else:
                print("\nCould not find Barahi/Holdings cluster")
                return

        mobile_hash, count = target_cluster

        print("="*120)
        print(f"BARAHI HOLDINGS CLUSTER: {count} COMPANIES")
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
            company_type = company.company_type_category or "N/A"

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
                        print(f"    Director PAN: {d.pan}")
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

        # Holdings pattern
        holdings_count = sum(1 for name in all_names if 'holding' in name.lower())

        # Extract base names (before "Holdings")
        base_names = []
        for name in all_names:
            if 'holding' in name.lower():
                base = name.split('Holdings')[0].strip()
                base_names.append(base)

        print(f"\nName Patterns:")
        print(f"  Companies with 'Holdings' in name: {holdings_count}")
        if base_names:
            print(f"  Base names: {', '.join(base_names)}")

        # District analysis
        districts = [c.district for c, _ in companies_data if c.district]
        if districts:
            district_counts = Counter(districts)
            print(f"\nDistrict Distribution:")
            for district, cnt in district_counts.most_common():
                print(f"  {district}: {cnt} companies")

        # Address analysis
        addresses = [c.company_address for c, _ in companies_data if c.company_address]
        if addresses:
            address_counts = Counter(addresses)
            print(f"\nAddress Distribution:")
            for address, cnt in address_counts.most_common(5):
                print(f"  {address[:80]}: {cnt} companies")

        # Registration date analysis
        reg_dates = [c.registration_date_ad for c, _ in companies_data if c.registration_date_ad]
        if reg_dates and len(reg_dates) > 1:
            date_range = (max(reg_dates) - min(reg_dates)).days
            print(f"\nRegistration Timeline:")
            print(f"  Earliest: {min(reg_dates).strftime('%Y-%m-%d')}")
            print(f"  Latest: {max(reg_dates).strftime('%Y-%m-%d')}")
            print(f"  Date range: {date_range} days (~{date_range/365:.1f} years)")

        # Company type analysis
        company_types = [c.company_type_category for c, _ in companies_data if c.company_type_category]
        if company_types:
            type_counts = Counter(company_types)
            print(f"\nCompany Type Distribution:")
            for ctype, cnt in type_counts.most_common():
                print(f"  {ctype}: {cnt} companies")

        # IRD status analysis
        ird_statuses = [i.account_status for _, i in companies_data if i.account_status]
        if ird_statuses:
            status_counts = Counter(ird_statuses)
            print(f"\nIRD Status Distribution:")
            for status, cnt in status_counts.most_common():
                print(f"  {status}: {cnt} companies")

        # Collect all directors across all companies
        all_directors = []
        for company, _ in companies_data:
            directors_stmt = (
                select(CompanyDirector)
                .where(CompanyDirector.company_id == company.id)
            )
            directors_result = await db.execute(directors_stmt)
            directors = list(directors_result.scalars().all())
            all_directors.extend(directors)

        if all_directors:
            director_names = [d.name_en for d in all_directors if d.name_en]
            director_counts = Counter(director_names)
            print(f"\nShared Directors (appearing in multiple companies):")
            shared = [(name, cnt) for name, cnt in director_counts.most_common() if cnt > 1]
            if shared:
                for name, cnt in shared:
                    print(f"  {name}: {cnt} companies")
            else:
                print("  No shared directors found")

        print("\n" + "="*120)
        print("RISK ASSESSMENT")
        print("="*120)
        print("\n🚩 Risk Indicators:")
        print(f"  ✓ All {count} companies share same mobile number")
        print(f"  ✓ {holdings_count} companies are 'Holdings' companies")

        if len(set(districts)) == 1:
            print(f"  ✓ All companies in same district ({districts[0]})")

        if len(set(addresses)) == 1:
            print(f"  ✓ All companies at same address")
        elif len(set(addresses)) <= 3:
            print(f"  ✓ Companies concentrated in {len(set(addresses))} addresses")

        if reg_dates and len(reg_dates) > 1 and date_range < 365:
            print(f"  ✓ All companies registered within {date_range} days")

        print("\n💡 Assessment:")
        print("  This appears to be a holding company structure for:")
        print("  - Wealth management and asset protection")
        print("  - Tax planning and profit distribution")
        print("  - Corporate group restructuring")
        print("  - Investment portfolio segmentation")
        print("\n  'Holdings' companies are typically used to:")
        print("  - Own shares in operating companies")
        print("  - Manage intellectual property")
        print("  - Isolate liabilities")
        print("  - Optimize tax treatment of dividends and capital gains")
        print("="*120 + "\n")


if __name__ == "__main__":
    asyncio.run(get_barahi_cluster_details())
