"""Find PAN sharing clusters - multiple companies registered under same PAN."""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, func, and_
from app.core.database import AsyncSessionLocal
from app.models.company import CompanyRegistration, IRDEnrichment


async def find_pan_sharing_clusters():
    """Find PANs shared by multiple companies (5+ companies)."""
    async with AsyncSessionLocal() as db:
        print("Searching for PANs shared by multiple companies...\n")

        # Find PANs with 5+ companies
        pan_counts = (
            select(
                CompanyRegistration.pan,
                func.count(CompanyRegistration.id).label("company_count"),
            )
            .where(
                and_(
                    CompanyRegistration.pan.isnot(None),
                    CompanyRegistration.pan != "",
                )
            )
            .group_by(CompanyRegistration.pan)
            .having(func.count(CompanyRegistration.id) >= 5)
            .order_by(func.count(CompanyRegistration.id).desc())
        )

        result = await db.execute(pan_counts)
        pan_clusters = result.all()

        print(f"Found {len(pan_clusters)} PANs shared by 5+ companies\n")
        print("="*120)

        for idx, (pan, count) in enumerate(pan_clusters, 1):
            print(f"\n{'='*120}")
            print(f"PAN CLUSTER #{idx}: {count} companies sharing PAN {pan}")
            print(f"{'='*120}\n")

            # Get IRD info for this PAN
            ird_stmt = select(IRDEnrichment).where(IRDEnrichment.pan == pan)
            ird_result = await db.execute(ird_stmt)
            ird = ird_result.scalar_one_or_none()

            if ird:
                print(f"IRD Account Status: {ird.account_status or 'N/A'}")
                print(f"IRD Taxpayer Name: {ird.taxpayer_name_en or ird.taxpayer_name_np or 'N/A'}")
                print(f"Tax Office: {ird.tax_office or 'N/A'}")
                print(f"Registration Date (BS): {ird.registration_date_bs or 'N/A'}")
                print()

            # Get all companies with this PAN
            companies_stmt = (
                select(CompanyRegistration)
                .where(CompanyRegistration.pan == pan)
                .order_by(CompanyRegistration.name_english)
            )
            companies_result = await db.execute(companies_stmt)
            companies = companies_result.scalars().all()

            print(f"{'#':<5} {'Company Name':<70} {'District':<20} {'Reg Date (AD)':<15}")
            print("-" * 120)

            for i, company in enumerate(companies, 1):
                company_name = company.name_english or "(unnamed)"
                district = company.district or "N/A"
                reg_date = company.registration_date_ad.strftime("%Y-%m-%d") if company.registration_date_ad else "N/A"

                print(f"{i:<5} {company_name[:70]:<70} {district:<20} {reg_date:<15}")

            # Analysis
            print(f"\n{'─'*120}")
            print("ANALYSIS:")

            # Check if all companies have similar names
            names = [c.name_english for c in companies if c.name_english]
            if names:
                # Extract common patterns
                common_words = set()
                for name in names:
                    words = name.lower().split()
                    common_words.update(words)

                # Check for pattern
                if any(word in common_words for word in ['agro', 'forestry', 'agriculture', 'krishi']):
                    print("⚠️  Pattern: Agriculture/Forestry sector companies")
                if any(word in common_words for word in ['pvt', 'private', 'ltd', 'limited']):
                    print("⚠️  Pattern: Private limited companies")

                # Check district clustering
                districts = [c.district for c in companies if c.district]
                if districts and len(set(districts)) == 1:
                    print(f"⚠️  Pattern: All companies in same district ({districts[0]})")

                # Check registration date clustering
                reg_dates = [c.registration_date_ad for c in companies if c.registration_date_ad]
                if reg_dates:
                    date_range = (max(reg_dates) - min(reg_dates)).days
                    if date_range < 30:
                        print(f"⚠️  Pattern: All companies registered within {date_range} days")
                    elif date_range < 365:
                        print(f"⚠️  Pattern: All companies registered within {date_range} days (~{date_range//30} months)")

            print("="*120)

        # Summary statistics
        print("\n" + "="*120)
        print("SUMMARY STATISTICS")
        print("="*120)

        total_pans = len(pan_clusters)
        total_companies = sum(count for _, count in pan_clusters)
        max_cluster = max(pan_clusters, key=lambda x: x[1]) if pan_clusters else None

        print(f"Total PANs with 5+ companies: {total_pans}")
        print(f"Total companies in these clusters: {total_companies}")
        if max_cluster:
            print(f"Largest cluster: PAN {max_cluster[0]} with {max_cluster[1]} companies")

        # Distribution
        distribution = {}
        for _, count in pan_clusters:
            range_key = f"{(count//5)*5}-{(count//5)*5+4}" if count < 20 else "20+"
            distribution[range_key] = distribution.get(range_key, 0) + 1

        print("\nDistribution by cluster size:")
        for range_key in sorted(distribution.keys()):
            print(f"  {range_key} companies: {distribution[range_key]} PANs")

        print("="*120 + "\n")


if __name__ == "__main__":
    asyncio.run(find_pan_sharing_clusters())
