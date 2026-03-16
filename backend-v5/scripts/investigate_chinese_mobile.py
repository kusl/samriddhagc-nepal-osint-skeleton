#!/usr/bin/env python3
"""
SPECIAL INVESTIGATION SCRIPT - Chinese Company Mobile Number Verification

Queries IRD API directly WITHOUT hashing to get actual mobile number.
This bypasses the privacy_hasher to enable fraud investigation.

Usage:
    python scripts/investigate_chinese_mobile.py
"""
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.ingestion.ird_client import IRDClient


async def investigate_chinese_cluster():
    """Query IRD for Chinese companies and save RAW response with mobile numbers."""

    # Chinese companies sharing mobile hash 56dca8f16523b3858ba00be7d3650c69
    chinese_companies = [
        {"name": "Chinese Enterprises Incubation Center", "pan": "606546490"},
        {"name": "Changsha Yuanjian Construction", "pan": "610314735"},
        {"name": "Ganzhou Xiongsheng Construction", "pan": "610390322"},
        {"name": "Nepal Blue Star Traders", "pan": "610208458"},
        {"name": "Nepal Garmin Trading Company", "pan": "610208519"},
    ]

    print("=" * 100)
    print("🔍 CHINESE CLUSTER MOBILE NUMBER INVESTIGATION")
    print("=" * 100)
    print()
    print(f"Investigating {len(chinese_companies)} companies from the cluster")
    print("Querying IRD API directly to get ACTUAL mobile numbers (not hashed)")
    print()
    print("⚠️  WARNING: This script does NOT sanitize or hash PII")
    print("   Only use for authorized fraud investigation")
    print()
    print("=" * 100)
    print()

    # Create output directory
    output_dir = Path(__file__).parent.parent / "investigation_output"
    output_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"chinese_cluster_raw_data_{timestamp}.json"

    results = []

    # Initialize IRD client with browser
    print("🌐 Launching browser for IRD queries...")
    async with IRDClient(max_concurrency=1, headless=False) as client:
        print("✅ Browser ready")
        print()

        for idx, company in enumerate(chinese_companies, 1):
            print(f"[{idx}/{len(chinese_companies)}] Querying: {company['name']}")
            print(f"    PAN: {company['pan']}")

            try:
                # Query IRD API
                ird_data = await client.search_pan(company['pan'])

                if not ird_data:
                    print(f"    ❌ No data returned from IRD")
                    results.append({
                        "company_name": company['name'],
                        "pan": company['pan'],
                        "status": "no_data",
                        "data": None
                    })
                    continue

                # Extract mobile from response (NOT HASHED!)
                pan_details = ird_data.get("panDetails", [])
                if pan_details and len(pan_details) > 0:
                    detail = pan_details[0]
                    mobile = detail.get("mobile", "NOT FOUND")
                    telephone = detail.get("telephone", "NOT FOUND")

                    print(f"    ✅ Data received")
                    print(f"    📱 Mobile: {mobile}")
                    print(f"    ☎️  Telephone: {telephone}")

                    results.append({
                        "company_name": company['name'],
                        "pan": company['pan'],
                        "status": "success",
                        "mobile": mobile,
                        "telephone": telephone,
                        "taxpayer_name": detail.get("trade_Name_Eng"),
                        "tax_office": detail.get("office_Name"),
                        "vdc_municipality": detail.get("vdc_Town"),
                        "ward_no": detail.get("ward_No"),
                        "account_status": detail.get("account_Status"),
                        "full_response": ird_data
                    })
                else:
                    print(f"    ⚠️  No panDetails in response")
                    results.append({
                        "company_name": company['name'],
                        "pan": company['pan'],
                        "status": "no_details",
                        "full_response": ird_data
                    })

            except Exception as e:
                print(f"    ❌ Error: {e}")
                results.append({
                    "company_name": company['name'],
                    "pan": company['pan'],
                    "status": "error",
                    "error": str(e)
                })

            print()

            # Brief pause between requests
            await asyncio.sleep(3)

    # Save results to JSON
    print("=" * 100)
    print("💾 SAVING RESULTS")
    print("=" * 100)
    print()

    output_data = {
        "investigation_date": timestamp,
        "investigation_purpose": "Chinese cluster mobile number verification for fraud investigation",
        "total_companies": len(chinese_companies),
        "results": results
    }

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    print(f"✅ Results saved to: {output_file}")
    print()

    # Summary
    print("=" * 100)
    print("📊 SUMMARY")
    print("=" * 100)
    print()

    mobiles_found = [r for r in results if r.get("status") == "success" and r.get("mobile") and r["mobile"] != "NOT FOUND" and r["mobile"] != "-"]

    if mobiles_found:
        print(f"✅ Found {len(mobiles_found)} companies with mobile numbers")
        print()

        # Check if all share same number
        unique_mobiles = set(r["mobile"] for r in mobiles_found)

        if len(unique_mobiles) == 1:
            print("🚨 CONFIRMED: All companies share SAME mobile number!")
            print(f"   Shared Mobile: {list(unique_mobiles)[0]}")
            print()
            print("   You can now use this number with Truecaller to identify the owner")
        elif len(unique_mobiles) > 1:
            print(f"⚠️  Found {len(unique_mobiles)} different mobile numbers:")
            for mobile in unique_mobiles:
                count = sum(1 for r in mobiles_found if r["mobile"] == mobile)
                print(f"   - {mobile} ({count} companies)")

        print()
        print("Companies with mobiles:")
        for r in mobiles_found:
            print(f"  • {r['company_name']}")
            print(f"    Mobile: {r['mobile']}")
    else:
        print("❌ No mobile numbers found in current IRD data")
        print()
        print("This could mean:")
        print("  • Chinese companies removed mobiles from IRD")
        print("  • IRD API now returns '-' for foreign companies")
        print("  • Numbers were temporary/fake during registration")

    print()
    print("=" * 100)
    print(f"Full investigation data saved to: {output_file}")
    print("=" * 100)


if __name__ == "__main__":
    print()
    print("🔍 CHINESE CLUSTER INVESTIGATION")
    print("=" * 100)
    print()
    print("This script will query IRD API directly and show ACTUAL mobile numbers")
    print("WITHOUT hashing or sanitization.")
    print()
    input("Press ENTER to continue (or Ctrl+C to cancel)...")
    print()

    asyncio.run(investigate_chinese_cluster())
