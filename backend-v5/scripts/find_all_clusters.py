"""Find all types of suspicious clusters - PAN, address, phone/mobile."""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, func, and_
from app.core.database import AsyncSessionLocal
from app.models.company import CompanyRegistration, IRDEnrichment


async def find_all_suspicious_clusters():
    """Find multiple types of suspicious company clusters."""
    async with AsyncSessionLocal() as db:
        print("="*120)
        print("CORPORATE INTELLIGENCE: SUSPICIOUS CLUSTER ANALYSIS")
        print("="*120)

        # 1. PAN SHARING (2+ companies)
        print("\n\n### 1. PAN SHARING CLUSTERS (Multiple companies under same PAN) ###\n")

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
            .having(func.count(CompanyRegistration.id) >= 2)
            .order_by(func.count(CompanyRegistration.id).desc())
            .limit(20)  # Top 20 clusters
        )

        result = await db.execute(pan_counts)
        pan_clusters = result.all()

        print(f"Found {len(pan_clusters)} PANs shared by 2+ companies (showing top 20)\n")

        for idx, (pan, count) in enumerate(pan_clusters[:10], 1):  # Show top 10 in detail
            # Get IRD info
            ird_stmt = select(IRDEnrichment).where(IRDEnrichment.pan == pan)
            ird_result = await db.execute(ird_stmt)
            ird = ird_result.scalar_one_or_none()

            # Get companies
            companies_stmt = (
                select(CompanyRegistration)
                .where(CompanyRegistration.pan == pan)
                .order_by(CompanyRegistration.name_english)
            )
            companies_result = await db.execute(companies_stmt)
            companies = list(companies_result.scalars().all())

            print(f"{idx}. PAN {pan} - {count} companies")
            print(f"   IRD Status: {ird.account_status if ird else 'N/A'}")
            print(f"   Companies: {', '.join([c.name_english[:40] for c in companies[:3]])}{'...' if len(companies) > 3 else ''}")
            print()

        # 2. ADDRESS CLUSTERING (10+ companies)
        print("\n\n### 2. ADDRESS CLUSTERING (Shell company indicators) ###\n")

        address_counts = (
            select(
                CompanyRegistration.company_address,
                CompanyRegistration.district,
                func.count(CompanyRegistration.id).label("company_count"),
            )
            .where(
                and_(
                    CompanyRegistration.company_address.isnot(None),
                    CompanyRegistration.company_address != "",
                )
            )
            .group_by(CompanyRegistration.company_address, CompanyRegistration.district)
            .having(func.count(CompanyRegistration.id) >= 10)
            .order_by(func.count(CompanyRegistration.id).desc())
            .limit(20)
        )

        result = await db.execute(address_counts)
        address_clusters = result.all()

        print(f"Found {len(address_clusters)} addresses with 10+ companies (showing top 20)\n")

        for idx, (address, district, count) in enumerate(address_clusters[:10], 1):
            print(f"{idx}. {count} companies at: {address[:80]}")
            print(f"   District: {district or 'N/A'}")

            # Get sample companies
            companies_stmt = (
                select(CompanyRegistration)
                .where(CompanyRegistration.company_address == address)
                .order_by(CompanyRegistration.name_english)
                .limit(3)
            )
            companies_result = await db.execute(companies_stmt)
            companies = list(companies_result.scalars().all())

            print(f"   Sample companies: {', '.join([c.name_english[:40] for c in companies])}")
            print()

        # 3. PHONE/MOBILE CLUSTERING (10+ companies)
        print("\n\n### 3. PHONE/MOBILE CLUSTERING (Shared contact numbers) ###\n")

        # Phone clusters
        phone_counts = (
            select(
                IRDEnrichment.phone_hash,
                func.count(IRDEnrichment.id).label("company_count"),
            )
            .where(
                and_(
                    IRDEnrichment.phone_hash.isnot(None),
                    IRDEnrichment.phone_hash != "",
                )
            )
            .group_by(IRDEnrichment.phone_hash)
            .having(func.count(IRDEnrichment.id) >= 10)
            .order_by(func.count(IRDEnrichment.id).desc())
            .limit(10)
        )

        result = await db.execute(phone_counts)
        phone_clusters = result.all()

        print(f"PHONE HASH - Found {len(phone_clusters)} phone numbers shared by 10+ companies\n")

        for idx, (phone_hash, count) in enumerate(phone_clusters, 1):
            # Get sample companies
            companies_stmt = (
                select(CompanyRegistration, IRDEnrichment)
                .join(IRDEnrichment, CompanyRegistration.pan == IRDEnrichment.pan)
                .where(IRDEnrichment.phone_hash == phone_hash)
                .order_by(CompanyRegistration.name_english)
                .limit(3)
            )
            companies_result = await db.execute(companies_stmt)
            companies = [(c, i) for c, i in companies_result.all()]

            print(f"{idx}. Phone Hash {phone_hash[:32]}... - {count} companies")
            if companies:
                print(f"   Sample: {', '.join([c.name_english[:40] for c, _ in companies])}")
            print()

        # Mobile clusters
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
            .limit(10)
        )

        result = await db.execute(mobile_counts)
        mobile_clusters = result.all()

        print(f"\nMOBILE HASH - Found {len(mobile_clusters)} mobile numbers shared by 10+ companies\n")

        for idx, (mobile_hash, count) in enumerate(mobile_clusters, 1):
            # Get sample companies
            companies_stmt = (
                select(CompanyRegistration, IRDEnrichment)
                .join(IRDEnrichment, CompanyRegistration.pan == IRDEnrichment.pan)
                .where(IRDEnrichment.mobile_hash == mobile_hash)
                .order_by(CompanyRegistration.name_english)
                .limit(5)
            )
            companies_result = await db.execute(companies_stmt)
            companies = [(c, i) for c, i in companies_result.all()]

            print(f"{idx}. Mobile Hash {mobile_hash[:32]}... - {count} companies")
            if companies:
                district = companies[0][0].district if companies else "N/A"
                print(f"   District: {district}")
                print(f"   Sample: {', '.join([c.name_english[:50] for c, _ in companies[:3]])}{'...' if len(companies) > 3 else ''}")
            print()

        # SUMMARY
        print("\n" + "="*120)
        print("SUMMARY")
        print("="*120)
        print(f"PAN sharing clusters (2+ companies): {len(pan_clusters)}")
        print(f"Address clusters (10+ companies): {len(address_clusters)}")
        print(f"Phone clusters (10+ companies): {len(phone_clusters)}")
        print(f"Mobile clusters (10+ companies): {len(mobile_clusters)}")
        print("="*120 + "\n")


if __name__ == "__main__":
    asyncio.run(find_all_suspicious_clusters())
