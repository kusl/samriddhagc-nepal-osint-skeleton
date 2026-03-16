#!/usr/bin/env python3
"""Check the 51-company cluster to find first registered."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, func, and_
from app.core.database import AsyncSessionLocal
from app.models.company import CompanyRegistration, IRDEnrichment

async def main():
    async with AsyncSessionLocal() as db:
        # Find phone hashes with 51 companies
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
            .having(func.count(IRDEnrichment.id) == 51)
            .subquery()
        )

        # Get all companies in these clusters
        stmt = (
            select(CompanyRegistration, IRDEnrichment)
            .join(IRDEnrichment, CompanyRegistration.pan == IRDEnrichment.pan)
            .where(IRDEnrichment.phone_hash.in_(select(phone_subq.c.phone_hash)))
            .order_by(CompanyRegistration.registration_number)
        )

        result = await db.execute(stmt)
        companies = result.all()

        print(f"\nFound {len(companies)} companies in clusters with exactly 51 members")
        print("="*80)

        if companies:
            # Group by phone hash
            from collections import defaultdict
            clusters = defaultdict(list)
            for company, ird in companies:
                clusters[ird.phone_hash].append((company, ird))

            for phone_hash, members in clusters.items():
                print(f"\nCluster with {len(members)} companies:")
                print(f"Phone hash: {phone_hash[:20]}...")
                print("\nFirst 10 companies (by registration number):")
                print("-"*80)

                for i, (company, ird) in enumerate(members[:10], 1):
                    print(f"\n{i}. {company.name_english}")
                    print(f"   Registration #: {company.registration_number}")
                    print(f"   PAN: {company.pan}")
                    print(f"   District: {company.district}")
                    print(f"   Registration Date (BS): {company.registration_date_bs}")
                    print(f"   IRD Status: {ird.account_status}")

                # Check for Golyan
                golyan_found = [(c, i) for c, i in members if 'golyan' in (c.name_english or '').lower()]
                if golyan_found:
                    print(f"\n🔍 Found Golyan company in this cluster:")
                    for company, ird in golyan_found:
                        print(f"   - {company.name_english}")
                        print(f"     Reg #{company.registration_number}")
                        print(f"     Reg Date: {company.registration_date_bs}")
                        print(f"     Position in cluster: #{members.index((company, ird)) + 1} out of {len(members)}")

                print(f"\n" + "="*80)
                print(f"📊 Total companies in this cluster: {len(members)}")
                print(f"✅ FIRST REGISTERED: {members[0][0].name_english}")
                print(f"   Registration #: {members[0][0].registration_number}")
                print(f"   Registration Date: {members[0][0].registration_date_bs}")

if __name__ == "__main__":
    asyncio.run(main())
