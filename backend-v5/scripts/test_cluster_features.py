#!/usr/bin/env python3
"""Test the new cluster filter features."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import AsyncSessionLocal
from app.services.corporate_intel_service import CorporateIntelService


async def test_cluster_filter():
    """Test the has_cluster filter."""
    print("="*80)
    print("Testing Cluster Filter Feature")
    print("="*80)
    print()

    async with AsyncSessionLocal() as db:
        service = CorporateIntelService(db)

        # Test 1: Get companies in clusters
        print("Test 1: Companies IN clusters (has_cluster=True)")
        result = await service.search_companies(
            has_cluster=True,
            page=1,
            limit=5,
        )
        print(f"  Found: {result['total']} companies")
        print(f"  Showing first 5:")
        for company in result['companies'][:5]:
            print(f"    - {company['company_name']} (PAN: {company['pan']})")
        print()

        # Test 2: Get companies NOT in clusters
        print("Test 2: Companies NOT in clusters (has_cluster=False)")
        result = await service.search_companies(
            has_cluster=False,
            page=1,
            limit=5,
        )
        print(f"  Found: {result['total']} companies")
        print(f"  Showing first 5:")
        for company in result['companies'][:5]:
            print(f"    - {company['company_name']} (PAN: {company['pan'] or 'No PAN'})")
        print()


async def test_simplified_clusters():
    """Test the simplified cluster display."""
    print("="*80)
    print("Testing Simplified Cluster Display")
    print("="*80)
    print()

    async with AsyncSessionLocal() as db:
        service = CorporateIntelService(db)

        result = await service.get_phone_clusters()

        print(f"Total clusters: {result['total_clusters']}")
        print(f"Total linked companies: {result['total_linked_companies']}")
        print()

        print("Top 5 largest clusters (showing first registered company only):")
        print()

        for idx, cluster in enumerate(result['clusters'][:5], 1):
            first = cluster['first_registered']
            print(f"{idx}. {first['company_name']}")
            print(f"   Registration: #{first['registration_number']}")
            print(f"   PAN: {first['pan']}")
            print(f"   District: {first['district']}")
            print(f"   Hash Type: {cluster['hash_type']}")
            print(f"   Total Companies in Cluster: {cluster['company_count']}")
            print()


async def main():
    try:
        await test_cluster_filter()
        await test_simplified_clusters()
        print("="*80)
        print("✅ All tests completed successfully!")
        print("="*80)
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
