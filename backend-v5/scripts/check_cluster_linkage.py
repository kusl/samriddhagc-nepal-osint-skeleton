#!/usr/bin/env python3
"""Check why specific companies are clustered together."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.models.company import CompanyRegistration, IRDEnrichment

# PANs from the user's cluster
PANS = [
    '601630413',  # B.B. Agriculture
    '601630503',  # Aasha Agriculture
    '601843141',  # Rudra Academy
    '601794223',  # Trimurti Nepal Metal Workshop
    '601842489',  # Kritis Handicrafts
    '601844948',  # B.&B.Washing
    '601853128',  # Hive Cafe
    '601868335',  # Shris Pashupalan
    '601870228',  # Taal Barahi Tours
    '601883262',  # Jaljala English Boarding
    '601888627',  # Dhorpatan Jaljala
    '601890970',  # Premier International
    '602391685',  # Banke RosinTurpentine
    '602420356',  # Chikyujin Nepal
    '602445122',  # Himali Juni
    '602450773',  # Surya Futsal
    '602457967',  # Panchakoshi English
    '602459767',  # Doors Entertainment
    '602462965',  # Little Buddy Pre School
    '602467571',  # karki International
    '602471235',  # Four Red Doors Apartments
    '602475118',  # Rising Star Academy
    '602478908',  # Swargadwari Education
    '602480460',  # Anjel International Trade
]

async def main():
    async with AsyncSessionLocal() as db:
        print("=" * 80)
        print("CLUSTER LINKAGE ANALYSIS")
        print("=" * 80)

        # Get IRD data for these PANs
        ird_stmt = select(IRDEnrichment).where(IRDEnrichment.pan.in_(PANS))
        result = await db.execute(ird_stmt)
        ird_records = {ird.pan: ird for ird in result.scalars().all()}

        print(f"\nFound {len(ird_records)} IRD records out of {len(PANS)} PANs\n")

        # Check what's linking them
        phone_hashes = {}
        mobile_hashes = {}

        for pan in PANS:
            ird = ird_records.get(pan)
            if ird:
                print(f"PAN: {pan}")
                print(f"  Name: {ird.taxpayer_name_en}")
                print(f"  Phone Hash:  {ird.phone_hash or 'NONE'}")
                print(f"  Mobile Hash: {ird.mobile_hash or 'NONE'}")
                print(f"  Status: {ird.account_status}")
                print(f"  Tax Office: {ird.tax_office}")
                print(f"  Ward: {ird.ward_no}")
                print(f"  VDC: {ird.vdc_municipality}")
                print()

                if ird.phone_hash:
                    phone_hashes.setdefault(ird.phone_hash, []).append(pan)
                if ird.mobile_hash:
                    mobile_hashes.setdefault(ird.mobile_hash, []).append(pan)
            else:
                print(f"PAN: {pan} - NO IRD DATA FOUND")
                print()

        print("\n" + "=" * 80)
        print("SHARED PHONE HASHES:")
        print("=" * 80)
        for h, pans_list in phone_hashes.items():
            if len(pans_list) > 1:
                print(f"\nHash: {h}")
                print(f"  Shared by {len(pans_list)} companies:")
                for p in pans_list:
                    ird = ird_records.get(p)
                    print(f"    - {ird.taxpayer_name_en} (PAN: {p})")

        if not any(len(v) > 1 for v in phone_hashes.values()):
            print("\n  No shared phone hashes found!")

        print("\n" + "=" * 80)
        print("SHARED MOBILE HASHES:")
        print("=" * 80)
        for h, pans_list in mobile_hashes.items():
            if len(pans_list) > 1:
                print(f"\nHash: {h}")
                print(f"  Shared by {len(pans_list)} companies:")
                for p in pans_list:
                    ird = ird_records.get(p)
                    print(f"    - {ird.taxpayer_name_en} (PAN: {p})")

        if not any(len(v) > 1 for v in mobile_hashes.values()):
            print("\n  No shared mobile hashes found!")

        # Summary
        print("\n" + "=" * 80)
        print("SUMMARY:")
        print("=" * 80)
        total_with_phone = sum(1 for ird in ird_records.values() if ird.phone_hash)
        total_with_mobile = sum(1 for ird in ird_records.values() if ird.mobile_hash)
        print(f"  Total PANs checked: {len(PANS)}")
        print(f"  Found in IRD: {len(ird_records)}")
        print(f"  With phone hash: {total_with_phone}")
        print(f"  With mobile hash: {total_with_mobile}")
        print(f"  Without any hash: {len(ird_records) - max(total_with_phone, total_with_mobile)}")

if __name__ == "__main__":
    asyncio.run(main())
