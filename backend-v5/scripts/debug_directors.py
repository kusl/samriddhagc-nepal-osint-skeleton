#!/usr/bin/env python3
import asyncio
import sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, and_
from app.core.database import AsyncSessionLocal
from app.models.company import CompanyRegistration, CompanyDirector

DEITY_NAMES = ['akash', 'prithivi', 'guru', 'sukra', 'buddha', 'ravi', 'mangal', 'brihaspati', 'som', 'sani', 'parshurama', 'shiva', 'vishnu', 'brahma', 'rama', 'krishna', 'ganesh', 'indra', 'agni', 'varun', 'surya', 'chandra', 'rahu', 'ketu']

async def main():
    async with AsyncSessionLocal() as db:
        deity_stmt = select(CompanyRegistration).where(
            and_(
                CompanyRegistration.registration_number >= 281206,
                CompanyRegistration.registration_number <= 297307,
            )
        )
        result = await db.execute(deity_stmt)
        all_companies = result.scalars().all()
        deity_companies = {c.id: c for c in all_companies if c.name_english and (('agro' in c.name_english.lower() or 'forestry' in c.name_english.lower()) and any(deity in c.name_english.lower() for deity in DEITY_NAMES))}

        print(f'Found {len(deity_companies)} deity companies')

        company_ids = list(deity_companies.keys())
        directors_stmt = select(CompanyDirector).where(CompanyDirector.company_id.in_(company_ids))
        result = await db.execute(directors_stmt)
        directors = result.scalars().all()

        print(f'Found {len(directors)} director records for deity companies\n')

        director_to_companies = defaultdict(list)
        for director in directors:
            if director.name_en:
                director_to_companies[director.name_en].append(director.company_id)

        print("Top 10 directors by deity company count:")
        for director_name, company_ids_list in sorted(director_to_companies.items(), key=lambda x: len(x[1]), reverse=True)[:10]:
            deity_count = sum(1 for cid in company_ids_list if cid in deity_companies)
            print(f'  {director_name}: {deity_count} deity companies')

if __name__ == "__main__":
    asyncio.run(main())
