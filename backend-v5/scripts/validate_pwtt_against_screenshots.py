#!/usr/bin/env python3
"""
Validate PWTT Algorithm Against Screenshot Evidence.

This script validates the damage detection algorithm by comparing
the PWTT analysis results against the visual evidence shown in the
user-provided screenshots.

Screenshots analyzed:
1. Pre-event: Nov 20, 2021 - Baseline imagery
2. Post-event: Oct 8, 2025 - After GenZ protests

Coordinates from screenshots: 27°41'53.44"N, 85°19'26.92"E
(27.698178°N, 85.324144°E)

The script tests:
1. T-statistic distribution over the area
2. Damage percentage detection
3. Building-level damage classification
4. Comparison against visual damage indicators

Usage:
    cd backend-v5
    python scripts/validate_pwtt_against_screenshots.py
"""
import asyncio
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import ee
from app.services.earth_engine.gee_client import GEEClient, GEE_COLLECTIONS
from app.services.damage_assessment.pwtt_service import PWTTService


async def run_diagnostic_analysis(bbox: list[float], event_date: str):
    """Run diagnostic analysis to understand t-statistic distribution."""

    print("\n" + "=" * 70)
    print("DIAGNOSTIC: T-Statistic Distribution Analysis")
    print("=" * 70)

    gee_client = await GEEClient.get_instance()

    # Parse dates
    event_dt = datetime.fromisoformat(event_date)
    baseline_start = event_dt - timedelta(days=365)
    baseline_end = event_dt - timedelta(days=1)
    post_start = event_dt
    post_end = event_dt + timedelta(days=60)

    geometry = ee.Geometry.Rectangle(bbox)

    # Get SAR collections
    baseline_collection = (
        ee.ImageCollection(GEE_COLLECTIONS['sentinel1'])
        .filterBounds(geometry)
        .filterDate(baseline_start.strftime('%Y-%m-%d'), baseline_end.strftime('%Y-%m-%d'))
        .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VV'))
        .filter(ee.Filter.eq('instrumentMode', 'IW'))
        .select('VV')
    )

    post_collection = (
        ee.ImageCollection(GEE_COLLECTIONS['sentinel1'])
        .filterBounds(geometry)
        .filterDate(post_start.strftime('%Y-%m-%d'), post_end.strftime('%Y-%m-%d'))
        .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VV'))
        .filter(ee.Filter.eq('instrumentMode', 'IW'))
        .select('VV')
    )

    baseline_count = baseline_collection.size().getInfo()
    post_count = post_collection.size().getInfo()

    print(f"\nImagery count:")
    print(f"  Baseline images: {baseline_count}")
    print(f"  Post-event images: {post_count}")

    if baseline_count < 3 or post_count < 1:
        print("ERROR: Insufficient imagery for analysis")
        return None

    # Compute statistics
    baseline_mean = baseline_collection.mean()
    baseline_std = baseline_collection.reduce(ee.Reducer.stdDev())
    post_mean = post_collection.mean()
    post_std = post_collection.reduce(ee.Reducer.stdDev())

    # Two-sample pooled t-test
    import math
    n1, n2 = baseline_count, post_count
    df = n1 + n2 - 2
    pre_var = baseline_std.pow(2).multiply(n1 - 1)
    post_var = post_std.pow(2).multiply(n2 - 1)
    pooled_variance = pre_var.add(post_var).divide(df)
    pooled_sd = pooled_variance.sqrt()
    se_factor = math.sqrt(1.0/n1 + 1.0/n2)
    epsilon = ee.Image.constant(0.01)
    standard_error = pooled_sd.multiply(se_factor).max(epsilon)
    t_statistic = post_mean.subtract(baseline_mean).abs().divide(standard_error)

    # Compute statistics across the area
    stats = t_statistic.reduceRegion(
        reducer=ee.Reducer.mean()
            .combine(ee.Reducer.min(), sharedInputs=True)
            .combine(ee.Reducer.max(), sharedInputs=True)
            .combine(ee.Reducer.stdDev(), sharedInputs=True)
            .combine(ee.Reducer.percentile([50, 75, 90, 95, 99]), sharedInputs=True),
        geometry=geometry,
        scale=10,
        maxPixels=1e9
    ).getInfo()

    print(f"\nT-Statistic Distribution:")
    print(f"  Mean: {stats.get('VV_mean', 0):.3f}")
    print(f"  Min: {stats.get('VV_min', 0):.3f}")
    print(f"  Max: {stats.get('VV_max', 0):.3f}")
    print(f"  StdDev: {stats.get('VV_stdDev', 0):.3f}")
    print(f"  Median (p50): {stats.get('VV_p50', 0):.3f}")
    print(f"  p75: {stats.get('VV_p75', 0):.3f}")
    print(f"  p90: {stats.get('VV_p90', 0):.3f}")
    print(f"  p95: {stats.get('VV_p95', 0):.3f}")
    print(f"  p99: {stats.get('VV_p99', 0):.3f}")

    # Compute area above different thresholds
    pixel_area = ee.Image.pixelArea()
    total_area = geometry.area().divide(1e6).getInfo()

    thresholds = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0]
    print(f"\nDamage Area by Threshold (total area: {total_area:.4f} km²):")

    for threshold in thresholds:
        mask = t_statistic.gte(threshold)
        # Multiply mask by pixel area - result will have band name from t_statistic
        area_result = mask.multiply(pixel_area).reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=geometry,
            scale=10,
            maxPixels=1e9
        ).getInfo()

        # Get the first value from the result dict
        area_m2 = list(area_result.values())[0] if area_result else 0
        area_km2 = area_m2 / 1e6 if area_m2 else 0
        pct = (area_km2 / total_area) * 100 if total_area > 0 else 0

        status = ""
        if threshold == 1.5:
            status = " <-- NEW THRESHOLD (civil unrest)"
        elif threshold == 2.0:
            status = " (previous threshold)"
        elif threshold == 3.0:
            status = " (original PWTT threshold)"

        print(f"  t > {threshold}: {area_km2:.4f} km² ({pct:.2f}%){status}")

    return stats


async def validate_algorithm():
    """Main validation function."""

    print("=" * 70)
    print("PWTT Algorithm Validation Against Screenshot Evidence")
    print("=" * 70)

    # ═══════════════════════════════════════════════════════════════════════════
    # SCREENSHOT COORDINATES
    # ═══════════════════════════════════════════════════════════════════════════
    # From the user's screenshots:
    # - Post-event: Oct 8, 2025 (shown as "Imagery Date: 10/8/2025")
    # - Pre-event: Nov 20, 2021 (shown as "Imagery Date: 11/20/2021")
    # - Coordinates: 27°41'53.44"N, 85°19'26.92"E = 27.698178°N, 85.324144°E
    # - Federal Parliament House marker in upper right area

    # Exact screenshot coordinates (center)
    screenshot_center_lat = 27.698178
    screenshot_center_lng = 85.324144

    # Create bbox around the screenshot view (approximately 500m radius)
    delta = 0.005  # ~500m at this latitude
    screenshot_bbox = [
        screenshot_center_lng - delta,  # min_lng
        screenshot_center_lat - delta,  # min_lat
        screenshot_center_lng + delta,  # max_lng
        screenshot_center_lat + delta,  # max_lat
    ]

    # Event date (GenZ protests)
    event_date = "2025-09-08"

    print(f"\nScreenshot analysis:")
    print(f"  Center: {screenshot_center_lat}°N, {screenshot_center_lng}°E")
    print(f"  BBox: {screenshot_bbox}")
    print(f"  Event date: {event_date}")

    # ═══════════════════════════════════════════════════════════════════════════
    # TEST 1: Diagnostic Analysis (T-stat distribution)
    # ═══════════════════════════════════════════════════════════════════════════
    diag_stats = await run_diagnostic_analysis(screenshot_bbox, event_date)

    # ═══════════════════════════════════════════════════════════════════════════
    # TEST 2: Run PWTT Service with new thresholds
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("TEST: Running PWTT Service (New Thresholds)")
    print("=" * 70)

    pwtt_service = PWTTService()

    # Verify threshold settings
    print(f"\nCurrent PWTT Thresholds:")
    print(f"  T_STAT_THRESHOLD: {pwtt_service.T_STAT_THRESHOLD}")
    print(f"  T_STAT_CRITICAL: {pwtt_service.T_STAT_CRITICAL}")
    print(f"  T_STAT_SEVERE: {pwtt_service.T_STAT_SEVERE}")
    print(f"  T_STAT_MODERATE: {pwtt_service.T_STAT_MODERATE}")
    print(f"  T_STAT_MINOR: {pwtt_service.T_STAT_MINOR}")

    try:
        result = await pwtt_service.detect_damage(
            bbox=screenshot_bbox,
            event_date=event_date,
            baseline_days=365,
            post_event_days=60,
        )

        if result.error:
            print(f"\nPWTT Error: {result.error}")
        else:
            print(f"\nPWTT Results:")
            print(f"  Total area: {result.total_area_km2:.4f} km²")
            print(f"  Damaged area: {result.damaged_area_km2:.4f} km²")
            print(f"  Damage percentage: {result.damage_percentage:.2f}%")
            print(f"\n  Severity Breakdown:")
            print(f"    Critical (t>{pwtt_service.T_STAT_CRITICAL}): {result.critical_area_km2:.4f} km²")
            print(f"    Severe ({pwtt_service.T_STAT_SEVERE}<t<={pwtt_service.T_STAT_CRITICAL}): {result.severe_area_km2:.4f} km²")
            print(f"    Moderate ({pwtt_service.T_STAT_MODERATE}<t<={pwtt_service.T_STAT_SEVERE}): {result.moderate_area_km2:.4f} km²")
            print(f"    Minor ({pwtt_service.T_STAT_MINOR}<t<={pwtt_service.T_STAT_MODERATE}): {result.minor_area_km2:.4f} km²")
            print(f"\n  Metadata:")
            print(f"    Baseline images: {result.baseline_images_count}")
            print(f"    Post-event images: {result.post_images_count}")
            print(f"    Confidence: {result.confidence_score:.1%}")
            print(f"    Hotspots: {len(result.hotspots)}")

            # Calculate total affected area
            total_affected = (
                result.critical_area_km2 +
                result.severe_area_km2 +
                result.moderate_area_km2 +
                result.minor_area_km2
            )
            total_affected_pct = (total_affected / result.total_area_km2) * 100 if result.total_area_km2 > 0 else 0
            print(f"\n  Total Affected (all severities): {total_affected:.4f} km² ({total_affected_pct:.2f}%)")

    except Exception as e:
        print(f"\nPWTT Error: {e}")
        import traceback
        traceback.print_exc()

    # ═══════════════════════════════════════════════════════════════════════════
    # TEST 3: Federal Parliament specific area
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("TEST: Federal Parliament / BICC Area")
    print("=" * 70)

    # Federal Parliament area (tighter bbox around the marker location)
    fed_parliament_bbox = [85.3235, 27.6975, 85.3305, 27.7025]

    print(f"\nFederal Parliament BBox: {fed_parliament_bbox}")

    try:
        fed_result = await pwtt_service.detect_damage(
            bbox=fed_parliament_bbox,
            event_date=event_date,
            baseline_days=365,
            post_event_days=60,
        )

        if fed_result.error:
            print(f"Error: {fed_result.error}")
        else:
            print(f"\nResults:")
            print(f"  Damaged area: {fed_result.damaged_area_km2:.4f} km²")
            print(f"  Damage percentage: {fed_result.damage_percentage:.2f}%")
            print(f"  Critical: {fed_result.critical_area_km2:.4f} km²")
            print(f"  Severe: {fed_result.severe_area_km2:.4f} km²")
            print(f"  Moderate: {fed_result.moderate_area_km2:.4f} km²")
            print(f"  Minor: {fed_result.minor_area_km2:.4f} km²")

    except Exception as e:
        print(f"Error: {e}")

    # ═══════════════════════════════════════════════════════════════════════════
    # VALIDATION SUMMARY
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("VALIDATION SUMMARY")
    print("=" * 70)

    print("""
Algorithm Status:
-----------------
- T-statistic threshold lowered from 2.0 to 1.5 for civil unrest detection
- Severity thresholds adjusted:
  * Critical: 3.0 (was 3.5)
  * Severe: 2.2 (was 2.5)
  * Moderate: 1.5 (was 2.0)
  * Minor: 1.0 (was 1.5)

Expected Behavior:
------------------
With these lowered thresholds, the algorithm should now:
1. Detect more subtle changes from civil unrest damage
2. Show higher damage percentages in affected areas
3. Display damage visualization for areas with t > 1.0

Validation Against Screenshots:
-------------------------------
The screenshots show visible changes between:
- Pre-event (Nov 20, 2021)
- Post-event (Oct 8, 2025)

The algorithm should detect changes in:
- Federal Parliament / BICC area
- Singha Durbar complex
- Surrounding infrastructure

If the damage percentage is still low (<5%), the changes visible in the
screenshots may be:
1. Below satellite detection resolution
2. Surface/cosmetic changes not affecting SAR backscatter
3. Optical-only changes (color, vegetation) not visible in SAR

Consider adding optical change detection (Sentinel-2 NDBI/NDVI) for
complementary analysis of surface changes.
""")


if __name__ == "__main__":
    asyncio.run(validate_algorithm())
