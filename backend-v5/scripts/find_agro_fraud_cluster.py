#!/usr/bin/env python3
"""Find the agricultural tax evasion cluster (51 companies, sequential registrations)."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, and_, or_
from app.core.database import AsyncSessionLocal
from app.models.company import CompanyRegistration, IRDEnrichment

async def main():
    async with AsyncSessionLocal() as db:
        # Find companies in the sequential registration range
        stmt = (
            select(CompanyRegistration, IRDEnrichment)
            .outerjoin(IRDEnrichment, CompanyRegistration.pan == IRDEnrichment.pan)
            .where(
                and_(
                    CompanyRegistration.registration_number >= 281206,
                    CompanyRegistration.registration_number <= 297307,
                    or_(
                        CompanyRegistration.name_english.ilike('%golyan%'),
                        CompanyRegistration.name_english.ilike('%agro%'),
                        CompanyRegistration.name_english.ilike('%forestry%'),
                    )
                )
            )
            .order_by(CompanyRegistration.registration_number)
        )

        result = await db.execute(stmt)
        companies = result.all()

        print(f"Found {len(companies)} companies in range 281206-297307 with Golyan/Agro/Forestry")
        print("="*80)

        # Group by phone hash if available
        phone_clusters = {}
        no_ird = []

        for company, ird in companies:
            if ird and ird.phone_hash:
                phone_clusters.setdefault(ird.phone_hash, []).append((company, ird))
            else:
                no_ird.append(company)

        # Find the largest cluster
        if phone_clusters:
            largest_hash = max(phone_clusters.keys(), key=lambda h: len(phone_clusters[h]))
            largest_cluster = phone_clusters[largest_hash]

            print(f"\n🚨 LARGEST CLUSTER: {len(largest_cluster)} companies sharing same phone")
            print("="*80)
            print("\nFirst 15 companies (by registration number):")
            print("-"*80)

            for i, (company, ird) in enumerate(largest_cluster[:15], 1):
                print(f"\n{i}. {company.name_english}")
                print(f"   Registration #: {company.registration_number}")
                print(f"   Registration Date: {company.registration_date_bs}")
                print(f"   PAN: {company.pan}")
                print(f"   Type: {company.company_type}")
                print(f"   IRD Status: {ird.account_status if ird else 'N/A'}")

            print("\n" + "="*80)
            print(f"✅ FIRST REGISTERED COMPANY:")
            first_company, first_ird = largest_cluster[0]
            print(f"   Name: {first_company.name_english}")
            print(f"   Registration #: {first_company.registration_number}")
            print(f"   Registration Date: {first_company.registration_date_bs}")
            print(f"   District: {first_company.district}")
            print(f"   PAN: {first_company.pan}")

            # Check if it's Golyan Group
            if 'golyan group' in first_company.name_english.lower():
                print(f"\n   ⚠️  This is the parent company (Golyan Group)")

            print(f"\n📊 Total cluster size: {len(largest_cluster)} companies")

            # Show last few
            print("\nLast 5 companies:")
            print("-"*80)
            for i, (company, ird) in enumerate(largest_cluster[-5:], len(largest_cluster) - 4):
                print(f"{i}. {company.name_english} (Reg #{company.registration_number})")

        # Check for Golyan Group specifically
        print("\n" + "="*80)
        print("Golyan Group Details:")
        print("="*80)
        golyan_stmt = select(CompanyRegistration).where(
            CompanyRegistration.name_english.ilike('%golyan group%')
        )
        golyan_result = await db.execute(golyan_stmt)
        golyan = golyan_result.scalar_one_or_none()

        if golyan:
            print(f"\n📍 {golyan.name_english}")
            print(f"   Registration #: {golyan.registration_number}")
            print(f"   Registration Date: {golyan.registration_date_bs}")
            print(f"   PAN: {golyan.pan}")
            print(f"   District: {golyan.district}")

            # Check if it's in the cluster
            if golyan.pan:
                ird_stmt = select(IRDEnrichment).where(IRDEnrichment.pan == golyan.pan)
                ird_result = await db.execute(ird_stmt)
                golyan_ird = ird_result.scalar_one_or_none()

                if golyan_ird and golyan_ird.phone_hash in phone_clusters:
                    cluster_position = next((i+1 for i, (c, _) in enumerate(phone_clusters[golyan_ird.phone_hash]) if c.id == golyan.id), None)
                    print(f"   Position in cluster: #{cluster_position} out of {len(phone_clusters[golyan_ird.phone_hash])}")

if __name__ == "__main__":
    asyncio.run(main())
