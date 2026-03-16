#!/usr/bin/env python3
"""
Comprehensive Government Scraper Test Suite

Tests all scrapers and generates a report showing working vs non-working sources.
Target: At least 50% of sources should be working.
"""

import sys
import os
import time
import json
from datetime import datetime
from typing import Dict, List, Tuple, Any
from dataclasses import dataclass, asdict

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.ingestion.ministry_scraper_generic import GenericMinistryScraper, MINISTRY_CONFIGS
from app.ingestion.provincial_scraper import ProvincialScraper
from app.ingestion.constitutional_scraper import ConstitutionalScraper
from app.ingestion.municipality_scraper import MunicipalityScraper


@dataclass
class ScraperTestResult:
    """Result of testing a single scraper."""
    source_id: str
    source_name: str
    source_type: str  # ministry, province, constitutional, municipality
    endpoint: str
    status: str  # success, partial, failed
    posts_found: int
    error: str = ""
    response_time_ms: int = 0


def test_ministry_scrapers() -> List[ScraperTestResult]:
    """Test all ministry scrapers."""
    results = []

    print("\n" + "=" * 60)
    print("Testing Federal Ministry Scrapers")
    print("=" * 60)

    for ministry_id, config in MINISTRY_CONFIGS.items():
        # Create a scraper for this ministry
        scraper = GenericMinistryScraper(config, delay=0.3)

        for endpoint_key, endpoint_url in config.endpoints.items():
            print(f"  Testing {ministry_id} / {endpoint_key}...", end=" ", flush=True)

            start_time = time.time()
            try:
                posts = scraper.scrape_endpoint(endpoint_key, max_pages=1)

                post_count = len(posts)
                elapsed_ms = int((time.time() - start_time) * 1000)

                if post_count > 0:
                    status = "success"
                    print(f"OK ({post_count} posts, {elapsed_ms}ms)")
                else:
                    status = "partial"
                    print(f"EMPTY (0 posts, {elapsed_ms}ms)")

                results.append(ScraperTestResult(
                    source_id=ministry_id,
                    source_name=config.name,
                    source_type="ministry",
                    endpoint=endpoint_key,
                    status=status,
                    posts_found=post_count,
                    response_time_ms=elapsed_ms,
                ))

            except Exception as e:
                elapsed_ms = int((time.time() - start_time) * 1000)
                print(f"FAILED ({str(e)[:40]})")

                results.append(ScraperTestResult(
                    source_id=ministry_id,
                    source_name=config.name,
                    source_type="ministry",
                    endpoint=endpoint_key,
                    status="failed",
                    posts_found=0,
                    error=str(e)[:200],
                    response_time_ms=elapsed_ms,
                ))

    return results


def test_provincial_scrapers() -> List[ScraperTestResult]:
    """Test all provincial scrapers."""
    results = []
    scraper = ProvincialScraper(delay=0.3, verify_ssl=False)

    print("\n" + "=" * 60)
    print("Testing Provincial Scrapers")
    print("=" * 60)

    for province_key, province_info in scraper.PROVINCES.items():
        for page_key in ['press-release', 'news', 'notice']:
            if page_key not in scraper.PAGES:
                continue

            print(f"  Testing {province_key} / {page_key}...", end=" ", flush=True)

            start_time = time.time()
            try:
                posts = scraper.scrape_province(
                    province_key=province_key,
                    category=page_key,
                    max_pages=1
                )

                post_count = len(posts)
                elapsed_ms = int((time.time() - start_time) * 1000)

                if post_count > 0:
                    status = "success"
                    print(f"OK ({post_count} posts, {elapsed_ms}ms)")
                else:
                    status = "partial"
                    print(f"EMPTY (0 posts, {elapsed_ms}ms)")

                results.append(ScraperTestResult(
                    source_id=province_key,
                    source_name=province_info['name'],
                    source_type="province",
                    endpoint=page_key,
                    status=status,
                    posts_found=post_count,
                    response_time_ms=elapsed_ms,
                ))

            except Exception as e:
                elapsed_ms = int((time.time() - start_time) * 1000)
                print(f"FAILED ({str(e)[:40]})")

                results.append(ScraperTestResult(
                    source_id=province_key,
                    source_name=province_info['name'],
                    source_type="province",
                    endpoint=page_key,
                    status="failed",
                    posts_found=0,
                    error=str(e)[:200],
                    response_time_ms=elapsed_ms,
                ))

    return results


def test_constitutional_scrapers() -> List[ScraperTestResult]:
    """Test all constitutional body scrapers."""
    results = []
    scraper = ConstitutionalScraper(delay=0.3, verify_ssl=False)

    print("\n" + "=" * 60)
    print("Testing Constitutional Body Scrapers")
    print("=" * 60)

    for body_id, config in scraper.BODIES.items():
        for endpoint_key in config.endpoints.keys():
            print(f"  Testing {body_id} / {endpoint_key}...", end=" ", flush=True)

            start_time = time.time()
            try:
                body_results = scraper.scrape_body(
                    body_id=body_id,
                    endpoints=[endpoint_key],
                    max_pages=1
                )

                post_count = len(body_results.get(endpoint_key, []))
                elapsed_ms = int((time.time() - start_time) * 1000)

                if post_count > 0:
                    status = "success"
                    print(f"OK ({post_count} posts, {elapsed_ms}ms)")
                else:
                    status = "partial"
                    print(f"EMPTY (0 posts, {elapsed_ms}ms)")

                results.append(ScraperTestResult(
                    source_id=body_id,
                    source_name=config.name,
                    source_type="constitutional",
                    endpoint=endpoint_key,
                    status=status,
                    posts_found=post_count,
                    response_time_ms=elapsed_ms,
                ))

            except Exception as e:
                elapsed_ms = int((time.time() - start_time) * 1000)
                print(f"FAILED ({str(e)[:40]})")

                results.append(ScraperTestResult(
                    source_id=body_id,
                    source_name=config.name,
                    source_type="constitutional",
                    endpoint=endpoint_key,
                    status="failed",
                    posts_found=0,
                    error=str(e)[:200],
                    response_time_ms=elapsed_ms,
                ))

    return results


def test_municipality_scrapers() -> List[ScraperTestResult]:
    """Test all municipality scrapers."""
    results = []
    scraper = MunicipalityScraper(delay=0.3, verify_ssl=False)

    print("\n" + "=" * 60)
    print("Testing Municipality Scrapers")
    print("=" * 60)

    for mun_id, config in scraper.MUNICIPALITIES.items():
        for endpoint_key in config.endpoints.keys():
            print(f"  Testing {mun_id} / {endpoint_key}...", end=" ", flush=True)

            start_time = time.time()
            try:
                mun_results = scraper.scrape_municipality(
                    mun_id=mun_id,
                    endpoints=[endpoint_key],
                    max_pages=1
                )

                post_count = len(mun_results.get(endpoint_key, []))
                elapsed_ms = int((time.time() - start_time) * 1000)

                if post_count > 0:
                    status = "success"
                    print(f"OK ({post_count} posts, {elapsed_ms}ms)")
                else:
                    status = "partial"
                    print(f"EMPTY (0 posts, {elapsed_ms}ms)")

                results.append(ScraperTestResult(
                    source_id=mun_id,
                    source_name=config.name,
                    source_type="municipality",
                    endpoint=endpoint_key,
                    status=status,
                    posts_found=post_count,
                    response_time_ms=elapsed_ms,
                ))

            except Exception as e:
                elapsed_ms = int((time.time() - start_time) * 1000)
                print(f"FAILED ({str(e)[:40]})")

                results.append(ScraperTestResult(
                    source_id=mun_id,
                    source_name=config.name,
                    source_type="municipality",
                    endpoint=endpoint_key,
                    status="failed",
                    posts_found=0,
                    error=str(e)[:200],
                    response_time_ms=elapsed_ms,
                ))

    return results


def generate_report(all_results: List[ScraperTestResult]) -> Dict[str, Any]:
    """Generate a comprehensive report from test results."""

    # Count by status
    success_count = sum(1 for r in all_results if r.status == "success")
    partial_count = sum(1 for r in all_results if r.status == "partial")
    failed_count = sum(1 for r in all_results if r.status == "failed")
    total_count = len(all_results)

    # Calculate percentages
    success_rate = (success_count / total_count * 100) if total_count > 0 else 0
    working_rate = ((success_count + partial_count) / total_count * 100) if total_count > 0 else 0

    # Count unique sources
    unique_sources = set((r.source_id, r.source_type) for r in all_results)
    working_sources = set(
        (r.source_id, r.source_type)
        for r in all_results
        if r.status in ("success", "partial")
    )

    # Group by source type
    by_type = {}
    for r in all_results:
        if r.source_type not in by_type:
            by_type[r.source_type] = {"success": 0, "partial": 0, "failed": 0, "total": 0}
        by_type[r.source_type][r.status] += 1
        by_type[r.source_type]["total"] += 1

    # Total posts found
    total_posts = sum(r.posts_found for r in all_results)

    report = {
        "generated_at": datetime.utcnow().isoformat(),
        "summary": {
            "total_endpoints_tested": total_count,
            "success_count": success_count,
            "partial_count": partial_count,
            "failed_count": failed_count,
            "success_rate_percent": round(success_rate, 1),
            "working_rate_percent": round(working_rate, 1),
            "unique_sources": len(unique_sources),
            "working_sources": len(working_sources),
            "total_posts_found": total_posts,
            "target_met": working_rate >= 50,
        },
        "by_source_type": by_type,
        "failed_endpoints": [
            asdict(r) for r in all_results if r.status == "failed"
        ],
        "all_results": [asdict(r) for r in all_results],
    }

    return report


def print_summary(report: Dict[str, Any]):
    """Print a human-readable summary."""
    summary = report["summary"]
    by_type = report["by_source_type"]

    print("\n" + "=" * 60)
    print("SCRAPER TEST REPORT")
    print("=" * 60)

    print(f"\nGenerated: {report['generated_at']}")

    print("\n--- OVERALL SUMMARY ---")
    print(f"Total Endpoints Tested: {summary['total_endpoints_tested']}")
    print(f"  - Success (posts found): {summary['success_count']}")
    print(f"  - Partial (no posts but responded): {summary['partial_count']}")
    print(f"  - Failed (error): {summary['failed_count']}")
    print(f"\nSuccess Rate: {summary['success_rate_percent']}%")
    print(f"Working Rate (success + partial): {summary['working_rate_percent']}%")
    print(f"\nUnique Sources: {summary['unique_sources']}")
    print(f"Working Sources: {summary['working_sources']}")
    print(f"Total Posts Found: {summary['total_posts_found']}")

    print("\n--- BY SOURCE TYPE ---")
    for source_type, counts in by_type.items():
        total = counts['total']
        working = counts['success'] + counts['partial']
        rate = (working / total * 100) if total > 0 else 0
        print(f"\n{source_type.upper()}:")
        print(f"  Total: {total}")
        print(f"  Success: {counts['success']}, Partial: {counts['partial']}, Failed: {counts['failed']}")
        print(f"  Working Rate: {rate:.1f}%")

    print("\n--- TARGET ---")
    if summary['target_met']:
        print("TARGET MET: At least 50% of sources are working!")
    else:
        print(f"TARGET NOT MET: Only {summary['working_rate_percent']}% working (need 50%)")

    # Print failed sources
    if report['failed_endpoints']:
        print("\n--- FAILED ENDPOINTS ---")
        for failed in report['failed_endpoints'][:10]:
            print(f"  - {failed['source_id']}/{failed['endpoint']}: {failed['error'][:50]}")
        if len(report['failed_endpoints']) > 10:
            print(f"  ... and {len(report['failed_endpoints']) - 10} more")


def main():
    """Run all scraper tests."""
    print("=" * 60)
    print("NARADA Government Scraper Test Suite")
    print("=" * 60)
    print(f"\nStarted: {datetime.now().isoformat()}")

    all_results = []

    # Test each category
    all_results.extend(test_ministry_scrapers())
    all_results.extend(test_provincial_scrapers())
    all_results.extend(test_constitutional_scrapers())
    all_results.extend(test_municipality_scrapers())

    # Generate report
    report = generate_report(all_results)

    # Print summary
    print_summary(report)

    # Save detailed report
    report_path = "/tmp/scraper_test_report.json"
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\nDetailed report saved to: {report_path}")

    # Return exit code based on target
    return 0 if report["summary"]["target_met"] else 1


if __name__ == "__main__":
    sys.exit(main())
