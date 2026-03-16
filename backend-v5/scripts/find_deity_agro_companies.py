#!/usr/bin/env python3
"""Find Hindu deity-themed agro companies in sequential range."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, and_
from app.core.database import AsyncSessionLocal
from app.models.company import CompanyRegistration, IRDEnrichment

# Hindu deity names mentioned
DEITY_NAMES = [
    'akash', 'prithivi', 'guru', 'sukra', 'buddha', 'ravi', 'mangal',
    'brihaspati', 'som', 'sani', 'parshurama', 'shiva', 'vishnu',
    'brahma', 'rama', 'krishna', 'ganesh', 'indra', 'agni', 'varun',
    'surya', 'chandra'
]

async def main():
    async with AsyncSessionLocal() as db:
        # Find companies in the range 281206-297307
        stmt = (
            select(CompanyRegistration)
            .where(
                and_(
                    CompanyRegistration.registration_number >= 281206,
                    CompanyRegistration.registration_number <= 297307,
                )
            )
            .order_by(CompanyRegistration.registration_number)
        )

        result = await db.execute(stmt)
        all_companies = result.scalars().all()

        print(f"Total companies in range 281206-297307: {len(all_companies)}")
        print("="*80)

        # Filter for agro/forestry companies
        agro_companies = [
            c for c in all_companies
            if c.name_english and (
                'agro' in c.name_english.lower() or
                'forestry' in c.name_english.lower()
            )
        ]

        print(f"\nFound {len(agro_companies)} Agro/Forestry companies")
        print("="*80)

        # Filter for deity-themed ones
        deity_companies = [
            c for c in agro_companies
            if any(deity in c.name_english.lower() for deity in DEITY_NAMES)
        ]

        print(f"\nFound {len(deity_companies)} Deity-themed Agro companies:")
        print("="*80)

        # Show all deity companies
        for i, company in enumerate(deity_companies[:60], 1):
            deity_found = [d for d in DEITY_NAMES if d in company.name_english.lower()]
            print(f"\n{i}. {company.name_english}")
            print(f"   Registration #: {company.registration_number}")
            print(f"   Registration Date: {company.registration_date_bs}")
            print(f"   PAN: {company.pan or 'NO PAN'}")
            print(f"   Deity: {', '.join(deity_found)}")

        # Check if Golyan Group is in this range
        golyan_in_range = [c for c in all_companies if 'golyan' in c.name_english.lower()]
        if golyan_in_range:
            print("\n" + "="*80)
            print(f"\n🎯 Golyan companies in this range:")
            for company in golyan_in_range:
                print(f"\n   {company.name_english}")
                print(f"   Registration #: {company.registration_number}")
                print(f"   Registration Date: {company.registration_date_bs}")
                print(f"   PAN: {company.pan}")

        # Find the very first company in the entire range
        print("\n" + "="*80)
        print("\n✅ VERY FIRST COMPANY in range 281206-297307:")
        if all_companies:
            first = all_companies[0]
            print(f"   {first.name_english}")
            print(f"   Registration #: {first.registration_number}")
            print(f"   Registration Date: {first.registration_date_bs}")
            print(f"   Type: {first.company_type}")
            print(f"   District: {first.district}")
            print(f"   PAN: {first.pan}")

        # If deity companies found, show first one
        if deity_companies:
            print("\n" + "="*80)
            print("\n✅ FIRST DEITY-THEMED AGRO COMPANY:")
            first_deity = deity_companies[0]
            deity_found = [d for d in DEITY_NAMES if d in first_deity.name_english.lower()]
            print(f"   {first_deity.name_english}")
            print(f"   Registration #: {first_deity.registration_number}")
            print(f"   Registration Date: {first_deity.registration_date_bs}")
            print(f"   Deity: {', '.join(deity_found)}")
            print(f"   PAN: {first_deity.pan}")

        # Check IRD enrichment status
        enriched_count = sum(1 for c in deity_companies if c.pan and c.ird_enriched)
        print(f"\n📊 Statistics:")
        print(f"   Total in range: {len(all_companies)}")
        print(f"   Agro/Forestry: {len(agro_companies)}")
        print(f"   Deity-themed: {len(deity_companies)}")
        print(f"   With PAN: {sum(1 for c in deity_companies if c.pan)}")
        print(f"   IRD enriched: {enriched_count}")

if __name__ == "__main__":
    asyncio.run(main())
