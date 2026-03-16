"""Find phone clusters with 40+ companies and export company names."""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, func, and_
from app.core.database import AsyncSessionLocal
from app.models.company import CompanyRegistration, IRDEnrichment


async def find_large_phone_clusters():
    """Find and display phone/mobile clusters with 40+ companies."""
    async with AsyncSessionLocal() as db:
        print("Searching for phone clusters with 40+ companies...\n")

        # 1. Find phone hash clusters with count > 40
        print("=== PHONE HASH CLUSTERS ===")
        phone_subq = (
            select(
                IRDEnrichment.phone_hash,
                func.count(IRDEnrichment.id).label("cnt"),
            )
            .where(
                and_(
                    IRDEnrichment.phone_hash.isnot(None),
                    IRDEnrichment.phone_hash != "",
                )
            )
            .group_by(IRDEnrichment.phone_hash)
            .having(func.count(IRDEnrichment.id) >= 40)
            .subquery()
        )

        phone_hash_counts = await db.execute(
            select(phone_subq.c.phone_hash, phone_subq.c.cnt)
            .order_by(phone_subq.c.cnt.desc())
        )
        phone_hash_results = phone_hash_counts.all()

        if phone_hash_results:
            print(f"Found {len(phone_hash_results)} phone hash cluster(s) with 40+ companies\n")

            for idx, (phone_hash, count) in enumerate(phone_hash_results, 1):
                print(f"\n{'='*80}")
                print(f"PHONE CLUSTER #{idx}: {count} companies")
                print(f"Phone Hash: {phone_hash}")
                print(f"{'='*80}\n")

                # Get all companies in this cluster
                companies_stmt = (
                    select(CompanyRegistration, IRDEnrichment)
                    .join(IRDEnrichment, CompanyRegistration.pan == IRDEnrichment.pan)
                    .where(IRDEnrichment.phone_hash == phone_hash)
                    .order_by(CompanyRegistration.name_english)
                )
                companies_result = await db.execute(companies_stmt)
                companies = companies_result.all()

                print(f"{'#':<5} {'Company Name':<60} {'PAN':<15} {'District':<20} {'IRD Status':<20}")
                print("-" * 120)

                for i, (company, ird) in enumerate(companies, 1):
                    company_name = company.name_english or "(unnamed)"
                    pan = company.pan or "N/A"
                    district = company.district or "N/A"
                    ird_status = ird.account_status or "N/A"

                    print(f"{i:<5} {company_name[:60]:<60} {pan:<15} {district:<20} {ird_status:<20}")
        else:
            print("No phone hash clusters with 40+ companies found.\n")

        # 2. Find mobile hash clusters with count > 40
        print("\n" + "="*80)
        print("=== MOBILE HASH CLUSTERS ===")
        mobile_subq = (
            select(
                IRDEnrichment.mobile_hash,
                func.count(IRDEnrichment.id).label("cnt"),
            )
            .where(
                and_(
                    IRDEnrichment.mobile_hash.isnot(None),
                    IRDEnrichment.mobile_hash != "",
                )
            )
            .group_by(IRDEnrichment.mobile_hash)
            .having(func.count(IRDEnrichment.id) >= 40)
            .subquery()
        )

        mobile_hash_counts = await db.execute(
            select(mobile_subq.c.mobile_hash, mobile_subq.c.cnt)
            .order_by(mobile_subq.c.cnt.desc())
        )
        mobile_hash_results = mobile_hash_counts.all()

        if mobile_hash_results:
            print(f"Found {len(mobile_hash_results)} mobile hash cluster(s) with 40+ companies\n")

            for idx, (mobile_hash, count) in enumerate(mobile_hash_results, 1):
                print(f"\n{'='*80}")
                print(f"MOBILE CLUSTER #{idx}: {count} companies")
                print(f"Mobile Hash: {mobile_hash}")
                print(f"{'='*80}\n")

                # Get all companies in this cluster
                companies_stmt = (
                    select(CompanyRegistration, IRDEnrichment)
                    .join(IRDEnrichment, CompanyRegistration.pan == IRDEnrichment.pan)
                    .where(IRDEnrichment.mobile_hash == mobile_hash)
                    .order_by(CompanyRegistration.name_english)
                )
                companies_result = await db.execute(companies_stmt)
                companies = companies_result.all()

                print(f"{'#':<5} {'Company Name':<60} {'PAN':<15} {'District':<20} {'IRD Status':<20}")
                print("-" * 120)

                for i, (company, ird) in enumerate(companies, 1):
                    company_name = company.name_english or "(unnamed)"
                    pan = company.pan or "N/A"
                    district = company.district or "N/A"
                    ird_status = ird.account_status or "N/A"

                    print(f"{i:<5} {company_name[:60]:<60} {pan:<15} {district:<20} {ird_status:<20}")
        else:
            print("No mobile hash clusters with 40+ companies found.\n")

        # 3. Summary
        print("\n" + "="*80)
        print("SUMMARY")
        print("="*80)
        total_large_clusters = len(phone_hash_results) + len(mobile_hash_results)
        total_companies = sum(count for _, count in phone_hash_results) + sum(count for _, count in mobile_hash_results)
        print(f"Total large clusters (40+ companies): {total_large_clusters}")
        print(f"Total companies in large clusters: {total_companies}")
        print("="*80 + "\n")


if __name__ == "__main__":
    asyncio.run(find_large_phone_clusters())
