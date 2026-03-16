"""Search for NCCS company with various patterns."""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, or_
from app.core.database import AsyncSessionLocal
from app.models.company import CompanyRegistration


async def search_nccs_variations():
    """Search for NCCS with different patterns."""
    async with AsyncSessionLocal() as db:
        print("Searching for NCCS company variations...\n")

        # Try different patterns
        patterns = [
            '%nccs%',
            '%n.c.c.s%',
            '%n c c s%',
            '%ncc%',
            '%nepal%communication%',
            '%nepal%computer%',
            '%nepal%consultancy%',
            '%communication%service%',
            '%computer%service%',
        ]

        all_results = {}

        for pattern in patterns:
            search_stmt = (
                select(CompanyRegistration)
                .where(
                    or_(
                        CompanyRegistration.name_english.ilike(pattern),
                        CompanyRegistration.name_nepali.ilike(pattern),
                    )
                )
                .order_by(CompanyRegistration.name_english)
                .limit(50)
            )

            result = await db.execute(search_stmt)
            companies = list(result.scalars().all())

            if companies:
                print(f"Pattern '{pattern}' - Found {len(companies)} matches:")
                for c in companies[:10]:  # Show first 10
                    if c.id not in all_results:
                        all_results[c.id] = c
                        print(f"  - {c.name_english}")
                        print(f"    PAN: {c.pan or 'N/A'}, District: {c.district or 'N/A'}")
                print()

        if not all_results:
            print("No matches found. Please provide more details about the company:")
            print("  - Full company name")
            print("  - PAN number")
            print("  - District")
            print("  - Any other identifying information")


if __name__ == "__main__":
    asyncio.run(search_nccs_variations())
