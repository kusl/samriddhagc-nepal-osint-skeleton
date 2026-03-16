#!/usr/bin/env python3
"""
Seed DFIMS (Development Finance) organizations into political_entities.

Fetches all organizations from dfims-api.naxa.com.np and creates
political_entity records with extra_data containing DFIMS metadata.
Optionally fuzzy-matches DFIMS orgs to registered companies.

Usage:
    cd backend-v5
    python scripts/seed_dfims_organizations.py                # Ingest orgs only
    python scripts/seed_dfims_organizations.py --link-companies  # + fuzzy match
"""
import argparse
import asyncio
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import AsyncSessionLocal
from app.services.dfims_ingestion_service import ingest_organizations, link_to_companies


async def main(link_companies: bool = False) -> None:
    print("=" * 70)
    print("DFIMS Organization Ingestion")
    print("=" * 70)

    async with AsyncSessionLocal() as session:
        # Step 1: Ingest organizations
        print("\n[1/2] Fetching and ingesting DFIMS organizations...")
        stats = await ingest_organizations(session)
        print(f"  Fetched:  {stats['total_fetched']}")
        print(f"  Created:  {stats['created']}")
        print(f"  Updated:  {stats['updated']}")
        print(f"  Skipped:  {stats['skipped']}")

        # Step 2: Optional company linking
        if link_companies:
            print("\n[2/2] Fuzzy-matching DFIMS orgs to companies...")
            link_stats = await link_to_companies(session)
            print(f"  DFIMS entities:     {link_stats['dfims_count']}")
            print(f"  Company candidates: {link_stats['company_candidates']}")
            print(f"  Matches found:      {len(link_stats['matches'])}")

            if link_stats["matches"]:
                print("\n  Matches:")
                print(f"  {'DFIMS Name':<45} {'Company Name':<45} {'Score':>6}")
                print("  " + "-" * 98)
                for m in link_stats["matches"]:
                    print(f"  {m['dfims_name']:<45} {m['company_name']:<45} {m['score']:>6.3f}")
        else:
            print("\n[2/2] Skipping company linking (use --link-companies to enable)")

    print("\n" + "=" * 70)
    print("Done. Run graph ingestion to populate unified graph:")
    print("  curl -X POST http://localhost:8001/api/v1/unified-graph/ingest")
    print("=" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed DFIMS organizations")
    parser.add_argument(
        "--link-companies",
        action="store_true",
        help="Also fuzzy-match DFIMS orgs to registered companies",
    )
    args = parser.parse_args()
    asyncio.run(main(link_companies=args.link_companies))
