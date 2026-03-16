#!/usr/bin/env python3
"""Check IRD enrichment status."""
import asyncio
import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, func
from app.core.database import AsyncSessionLocal
from app.models.company import CompanyRegistration, IRDEnrichment

async def check_ird_status():
    async with AsyncSessionLocal() as db:
        # Count total companies
        total_companies_stmt = select(func.count(CompanyRegistration.id))
        result = await db.execute(total_companies_stmt)
        total_companies = result.scalar()

        # Count companies with IRD enrichment flag
        ird_flagged_stmt = select(func.count(CompanyRegistration.id)).where(
            CompanyRegistration.ird_enriched == True
        )
        result = await db.execute(ird_flagged_stmt)
        ird_flagged_count = result.scalar()

        # Count actual IRD enrichment records
        ird_records_stmt = select(func.count(IRDEnrichment.id))
        result = await db.execute(ird_records_stmt)
        ird_records_count = result.scalar()

        # Count records with phone/mobile hash
        phone_hash_stmt = select(func.count(IRDEnrichment.id)).where(
            IRDEnrichment.phone_hash.isnot(None)
        )
        result = await db.execute(phone_hash_stmt)
        phone_hash_count = result.scalar()

        mobile_hash_stmt = select(func.count(IRDEnrichment.id)).where(
            IRDEnrichment.mobile_hash.isnot(None)
        )
        result = await db.execute(mobile_hash_stmt)
        mobile_hash_count = result.scalar()

        # Get recent enrichments (last 7 days)
        seven_days_ago = datetime.utcnow() - timedelta(days=7)
        recent_stmt = select(func.count(IRDEnrichment.id)).where(
            IRDEnrichment.created_at >= seven_days_ago
        )
        result = await db.execute(recent_stmt)
        recent_count = result.scalar()

        # Get sample IRD records
        sample_stmt = select(IRDEnrichment).limit(5)
        result = await db.execute(sample_stmt)
        sample_records = result.scalars().all()

        print("=" * 70)
        print("IRD ENRICHMENT STATUS REPORT")
        print("=" * 70)
        print(f"\n📊 OVERALL STATISTICS:")
        print(f"  Total Companies in DB:        {total_companies:,}")
        print(f"  Companies Flagged as Enriched: {ird_flagged_count:,} ({ird_flagged_count/total_companies*100:.1f}%)")
        print(f"  IRD Enrichment Records:        {ird_records_count:,}")

        print(f"\n📞 CONTACT DATA:")
        print(f"  Records with Phone Hash:      {phone_hash_count:,} ({phone_hash_count/ird_records_count*100:.1f}%)")
        print(f"  Records with Mobile Hash:     {mobile_hash_count:,} ({mobile_hash_count/ird_records_count*100:.1f}%)")

        print(f"\n⏰ RECENT ACTIVITY:")
        print(f"  Enrichments (last 7 days):    {recent_count:,}")

        if recent_count > 0:
            print(f"  Status: ✅ ACTIVE - New enrichments in last 7 days")
        elif ird_records_count > 0:
            print(f"  Status: ⚠️  INACTIVE - No new enrichments recently")
        else:
            print(f"  Status: ❌ NOT CONFIGURED - No IRD data found")

        if sample_records:
            print(f"\n📝 SAMPLE IRD RECORDS:")
            for i, record in enumerate(sample_records, 1):
                print(f"\n  {i}. PAN: {record.pan}")
                print(f"     Name: {record.taxpayer_name_en}")
                print(f"     Phone Hash: {'✓' if record.phone_hash else '✗'}")
                print(f"     Mobile Hash: {'✓' if record.mobile_hash else '✗'}")
                print(f"     Status: {record.account_status}")
                print(f"     Created: {record.created_at}")

        # Check for Golyan cluster specifically
        print(f"\n🔍 GOLYAN GROUP CHECK:")
        golyan_stmt = select(CompanyRegistration).where(
            CompanyRegistration.name_english.ilike('%golyan%')
        )
        result = await db.execute(golyan_stmt)
        golyan_companies = result.scalars().all()

        print(f"  Found {len(golyan_companies)} Golyan companies")

        enriched_golyan = 0
        for company in golyan_companies:
            if company.pan:
                ird_check = select(IRDEnrichment).where(IRDEnrichment.pan == company.pan)
                result = await db.execute(ird_check)
                ird_record = result.scalar_one_or_none()
                if ird_record:
                    enriched_golyan += 1
                    print(f"  ✓ {company.name_english} - IRD enriched")
                    if ird_record.phone_hash:
                        print(f"    Phone hash: {ird_record.phone_hash[:16]}...")
                    if ird_record.mobile_hash:
                        print(f"    Mobile hash: {ird_record.mobile_hash[:16]}...")
                else:
                    print(f"  ✗ {company.name_english} - No IRD data")

        print(f"\n  Golyan companies with IRD data: {enriched_golyan}/{len(golyan_companies)}")

        print("\n" + "=" * 70)

if __name__ == "__main__":
    asyncio.run(check_ird_status())
