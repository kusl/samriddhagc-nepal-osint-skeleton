#!/usr/bin/env python3
"""Find the Golyan cluster."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, func, and_, or_
from app.core.database import AsyncSessionLocal
from app.models.company import CompanyRegistration, IRDEnrichment

async def main():
    async with AsyncSessionLocal() as db:
        # First, find any Golyan companies
        stmt = select(CompanyRegistration).where(
            or_(
                CompanyRegistration.name_english.ilike('%golyan%'),
                CompanyRegistration.name_nepali.ilike('%golyan%'),
            )
        )
        result = await db.execute(stmt)
        golyan_companies = result.scalars().all()

        print(f"Found {len(golyan_companies)} companies with 'Golyan' in name:")
        print("="*80)

        for company in golyan_companies:
            print(f"\n📍 {company.name_english}")
            print(f"   Registration #: {company.registration_number}")
            print(f"   PAN: {company.pan}")
            print(f"   District: {company.district}")
            print(f"   Registration Date (BS): {company.registration_date_bs}")

            if company.pan:
                # Find IRD enrichment
                ird_stmt = select(IRDEnrichment).where(IRDEnrichment.pan == company.pan)
                ird_result = await db.execute(ird_stmt)
                ird = ird_result.scalar_one_or_none()

                if ird and ird.phone_hash:
                    # Find how many companies share this phone
                    count_stmt = select(func.count(IRDEnrichment.id)).where(
                        IRDEnrichment.phone_hash == ird.phone_hash
                    )
                    count_result = await db.execute(count_stmt)
                    count = count_result.scalar()

                    print(f"   📞 Phone cluster size: {count} companies")

                    if count > 1:
                        # Get all companies in this cluster
                        cluster_stmt = (
                            select(CompanyRegistration, IRDEnrichment)
                            .join(IRDEnrichment, CompanyRegistration.pan == IRDEnrichment.pan)
                            .where(IRDEnrichment.phone_hash == ird.phone_hash)
                            .order_by(CompanyRegistration.registration_number)
                        )
                        cluster_result = await db.execute(cluster_stmt)
                        cluster_members = cluster_result.all()

                        print(f"\n   Cluster members (first 10 by registration date):")
                        print(f"   " + "-"*76)
                        for i, (c, ir) in enumerate(cluster_members[:10], 1):
                            marker = "🎯" if c.id == company.id else "  "
                            print(f"   {marker} {i}. {c.name_english[:50]}")
                            print(f"      Reg #{c.registration_number} | {c.registration_date_bs or 'N/A'}")

                        print(f"\n   ✅ FIRST REGISTERED in this cluster:")
                        first = cluster_members[0][0]
                        print(f"      {first.name_english}")
                        print(f"      Registration #: {first.registration_number}")
                        print(f"      Registration Date: {first.registration_date_bs}")

        # Also check for large clusters (45-55 companies)
        print("\n" + "="*80)
        print("\nTop 10 largest phone clusters:")
        print("="*80)

        large_clusters_stmt = (
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
            .having(func.count(IRDEnrichment.id) > 1)
            .order_by(func.count(IRDEnrichment.id).desc())
            .limit(10)
        )

        result = await db.execute(large_clusters_stmt)
        large_clusters = result.all()

        for i, (phone_hash, count) in enumerate(large_clusters, 1):
            # Get first company in this cluster
            first_stmt = (
                select(CompanyRegistration)
                .join(IRDEnrichment, CompanyRegistration.pan == IRDEnrichment.pan)
                .where(IRDEnrichment.phone_hash == phone_hash)
                .order_by(CompanyRegistration.registration_number)
                .limit(1)
            )
            first_result = await db.execute(first_stmt)
            first_company = first_result.scalar_one_or_none()

            if first_company:
                print(f"\n{i}. {count} companies - First: {first_company.name_english}")
                print(f"   Reg #{first_company.registration_number} | {first_company.district}")

if __name__ == "__main__":
    asyncio.run(main())
