#!/usr/bin/env python3
"""
Run PWTT damage assessment on Singha Durbar for September 8, 2025.

Uses the oballinger/PWTT library for accurate SAR-based damage detection.
Saves output images to analysis_output/ directory.
"""

import asyncio
import os
import sys
from pathlib import Path
from datetime import datetime
import requests
from io import BytesIO

# Add the app to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Add PWTT library to path
PWTT_LIB_PATH = Path(__file__).parent.parent / "pwtt_lib" / "code"
sys.path.insert(0, str(PWTT_LIB_PATH))

import ee
import geemap

# Initialize Earth Engine
print("Initializing Google Earth Engine...")
try:
    ee.Initialize()
    print("GEE initialized successfully!")
except Exception as e:
    print(f"GEE initialization failed: {e}")
    print("Attempting to authenticate...")
    ee.Authenticate()
    ee.Initialize()

# Import PWTT library
import pwtt as pwtt_lib

# Output directory
OUTPUT_DIR = Path(__file__).parent.parent / "analysis_output"
OUTPUT_DIR.mkdir(exist_ok=True)

# Singha Durbar coordinates
SINGHA_DURBAR_BBOX = [85.318, 27.697, 85.328, 27.705]  # [min_lng, min_lat, max_lng, max_lat]
EVENT_DATE = "2025-09-08"


def download_tile_image(tile_url: str, output_path: Path, bbox: list, zoom: int = 16):
    """Download a GEE tile as an image."""
    try:
        # Calculate tile coordinates for the center of the bbox
        center_lat = (bbox[1] + bbox[3]) / 2
        center_lng = (bbox[0] + bbox[2]) / 2

        # Convert lat/lng to tile coordinates
        import math
        n = 2 ** zoom
        x = int((center_lng + 180) / 360 * n)
        y = int((1 - math.asinh(math.tan(math.radians(center_lat))) / math.pi) / 2 * n)

        # Replace placeholders in tile URL
        url = tile_url.replace('{z}', str(zoom)).replace('{x}', str(x)).replace('{y}', str(y))

        print(f"  Downloading tile from: {url[:80]}...")
        response = requests.get(url, timeout=30)

        if response.status_code == 200:
            with open(output_path, 'wb') as f:
                f.write(response.content)
            print(f"  Saved: {output_path.name}")
            return True
        else:
            print(f"  Failed to download (status {response.status_code})")
            return False
    except Exception as e:
        print(f"  Error downloading tile: {e}")
        return False


def run_pwtt_analysis():
    """Run PWTT analysis on Singha Durbar."""
    print("\n" + "=" * 60)
    print("PWTT DAMAGE ASSESSMENT - SINGHA DURBAR")
    print(f"Event Date: {EVENT_DATE}")
    print(f"Bounding Box: {SINGHA_DURBAR_BBOX}")
    print("=" * 60 + "\n")

    # Create geometry
    geometry = ee.Geometry.Rectangle(SINGHA_DURBAR_BBOX)
    aoi = ee.FeatureCollection([ee.Feature(geometry)])

    # Parse event date
    event_dt = datetime.fromisoformat(EVENT_DATE)
    inference_start = EVENT_DATE

    # Calculate war_start (baseline start - 12 months before)
    from datetime import timedelta
    baseline_start = event_dt - timedelta(days=365)
    war_start = baseline_start.strftime('%Y-%m-%d')

    print(f"Baseline period: {war_start} to {EVENT_DATE}")
    print(f"Post-event period: {EVENT_DATE} to {(event_dt + timedelta(days=60)).strftime('%Y-%m-%d')}")
    print("\nRunning PWTT analysis (this may take a few minutes)...")

    # Run PWTT analysis using oballinger/PWTT library
    try:
        pwtt_result = pwtt_lib.filter_s1(
            aoi=aoi,
            inference_start=inference_start,
            war_start=ee.Date(war_start),
            pre_interval=12,  # 12 months baseline
            post_interval=2,   # 2 months post-event
            viz=False,
            export=False,
        )
        print("PWTT analysis completed!")
    except Exception as e:
        print(f"PWTT analysis failed: {e}")
        return

    # Extract bands
    t_statistic = pwtt_result.select('T_statistic')
    damage_binary = pwtt_result.select('damage')

    # Calculate statistics
    print("\nCalculating damage statistics...")
    pixel_area = ee.Image.pixelArea()

    # Total area
    total_area_m2 = geometry.area().getInfo()
    total_area_km2 = total_area_m2 / 1e6

    # Damaged area (t > 3)
    damaged_mask = damage_binary.gt(0)
    damaged_area_result = damaged_mask.multiply(pixel_area).reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=geometry,
        scale=10,
        maxPixels=1e9
    )
    damaged_area_m2 = damaged_area_result.get('damage').getInfo() or 0
    damaged_area_km2 = damaged_area_m2 / 1e6

    # Severity breakdown
    critical_mask = t_statistic.gte(4.0)
    severe_mask = t_statistic.gte(3.5).And(t_statistic.lt(4.0))
    moderate_mask = t_statistic.gte(3.0).And(t_statistic.lt(3.5))
    minor_mask = t_statistic.gte(2.5).And(t_statistic.lt(3.0))

    def get_area(mask):
        result = mask.multiply(pixel_area).reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=geometry,
            scale=10,
            maxPixels=1e9
        )
        vals = result.values().getInfo()
        return (vals[0] if vals else 0) / 1e6

    critical_km2 = get_area(critical_mask)
    severe_km2 = get_area(severe_mask)
    moderate_km2 = get_area(moderate_mask)
    minor_km2 = get_area(minor_mask)

    # Print results
    print("\n" + "=" * 60)
    print("DAMAGE ASSESSMENT RESULTS")
    print("=" * 60)
    print(f"Total Area:      {total_area_km2:.4f} km²")
    print(f"Damaged Area:    {damaged_area_km2:.4f} km² ({damaged_area_km2/total_area_km2*100:.2f}%)")
    print("-" * 40)
    print("Severity Breakdown:")
    print(f"  Critical (t≥4.0): {critical_km2:.6f} km²")
    print(f"  Severe (t≥3.5):   {severe_km2:.6f} km²")
    print(f"  Moderate (t≥3.0): {moderate_km2:.6f} km²")
    print(f"  Minor (t≥2.5):    {minor_km2:.6f} km²")
    print("=" * 60)

    # Generate visualization tiles
    print("\nGenerating visualization tiles...")

    # T-statistic visualization (PWTT style)
    t_stat_vis = {
        'min': 3,
        'max': 5,
        'palette': ['yellow', 'red', 'purple']
    }

    # Damage probability visualization
    damage_prob = t_statistic.subtract(3).divide(2).clamp(0, 1)
    damage_vis = {
        'min': 0,
        'max': 1,
        'palette': ['1a9850', '66bd63', 'a6d96a', 'fee08b', 'fdae61', 'f46d43', 'd73027', 'a50026']
    }

    # SAR visualization
    sar_vis = {'min': -25, 'max': 0, 'palette': ['000000', 'ffffff']}

    # Get map IDs
    t_stat_clipped = t_statistic.clip(geometry)
    damage_clipped = damage_prob.updateMask(t_statistic.gte(2.5)).clip(geometry)

    print("  Getting T-statistic tile URL...")
    t_stat_map = t_stat_clipped.getMapId(t_stat_vis)
    t_stat_url = t_stat_map['tile_fetcher'].url_format

    print("  Getting damage probability tile URL...")
    damage_map = damage_clipped.getMapId(damage_vis)
    damage_url = damage_map['tile_fetcher'].url_format

    # Get SAR imagery
    print("  Getting SAR imagery...")
    s1_collection = (
        ee.ImageCollection("COPERNICUS/S1_GRD")
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
        .filter(ee.Filter.eq("instrumentMode", "IW"))
        .filterBounds(geometry)
        .select('VV')
    )

    before_sar = s1_collection.filterDate(war_start, EVENT_DATE).mean().clip(geometry)
    after_sar = s1_collection.filterDate(EVENT_DATE, (event_dt + timedelta(days=60)).strftime('%Y-%m-%d')).mean().clip(geometry)

    before_sar_map = before_sar.getMapId(sar_vis)
    after_sar_map = after_sar.getMapId(sar_vis)

    before_sar_url = before_sar_map['tile_fetcher'].url_format
    after_sar_url = after_sar_map['tile_fetcher'].url_format

    # Download tiles
    print("\nDownloading tiles...")

    download_tile_image(t_stat_url, OUTPUT_DIR / "t_statistic.png", SINGHA_DURBAR_BBOX, zoom=17)
    download_tile_image(damage_url, OUTPUT_DIR / "damage_probability.png", SINGHA_DURBAR_BBOX, zoom=17)
    download_tile_image(before_sar_url, OUTPUT_DIR / "sar_before.png", SINGHA_DURBAR_BBOX, zoom=17)
    download_tile_image(after_sar_url, OUTPUT_DIR / "sar_after.png", SINGHA_DURBAR_BBOX, zoom=17)

    # Save results to JSON
    import json
    results = {
        "event_name": "GenZ Protest - Singha Durbar",
        "event_date": EVENT_DATE,
        "bbox": SINGHA_DURBAR_BBOX,
        "total_area_km2": total_area_km2,
        "damaged_area_km2": damaged_area_km2,
        "damage_percentage": damaged_area_km2 / total_area_km2 * 100 if total_area_km2 > 0 else 0,
        "severity_breakdown": {
            "critical_km2": critical_km2,
            "severe_km2": severe_km2,
            "moderate_km2": moderate_km2,
            "minor_km2": minor_km2,
        },
        "tile_urls": {
            "t_statistic": t_stat_url,
            "damage_probability": damage_url,
            "sar_before": before_sar_url,
            "sar_after": after_sar_url,
        },
        "analysis_timestamp": datetime.now().isoformat(),
    }

    with open(OUTPUT_DIR / "analysis_results.json", 'w') as f:
        json.dump(results, f, indent=2)

    print(f"\nResults saved to: {OUTPUT_DIR}")
    print("  - t_statistic.png")
    print("  - damage_probability.png")
    print("  - sar_before.png")
    print("  - sar_after.png")
    print("  - analysis_results.json")

    # Create a simple map visualization using geemap
    print("\nGenerating interactive map...")
    try:
        Map = geemap.Map(center=[27.701, 85.323], zoom=16)
        Map.add_basemap('SATELLITE')
        Map.addLayer(t_stat_clipped, t_stat_vis, 'T-Statistic')
        Map.addLayer(damage_clipped, damage_vis, 'Damage Probability')

        map_path = OUTPUT_DIR / "damage_map.html"
        Map.to_html(str(map_path))
        print(f"  Saved interactive map: {map_path}")
    except Exception as e:
        print(f"  Could not generate interactive map: {e}")

    print("\n" + "=" * 60)
    print("ANALYSIS COMPLETE")
    print("=" * 60)

    return results


if __name__ == "__main__":
    run_pwtt_analysis()
