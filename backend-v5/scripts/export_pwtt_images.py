#!/usr/bin/env python3
"""
Export PWTT damage assessment images for Singha Durbar.
Uses geemap to export high-resolution images.
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add paths
sys.path.insert(0, str(Path(__file__).parent.parent))
PWTT_LIB_PATH = Path(__file__).parent.parent / "pwtt_lib" / "code"
sys.path.insert(0, str(PWTT_LIB_PATH))

import ee
import geemap

# Initialize GEE
print("Initializing Google Earth Engine...")
ee.Initialize()
print("GEE initialized!")

import pwtt as pwtt_lib

# Output directory
OUTPUT_DIR = Path(__file__).parent.parent / "analysis_output"
OUTPUT_DIR.mkdir(exist_ok=True)

# Singha Durbar coordinates
BBOX = [85.318, 27.697, 85.328, 27.705]
EVENT_DATE = "2025-09-08"

print("\n" + "=" * 60)
print("EXPORTING PWTT ANALYSIS IMAGES")
print(f"Location: Singha Durbar")
print(f"Event Date: {EVENT_DATE}")
print("=" * 60 + "\n")

# Create geometry
geometry = ee.Geometry.Rectangle(BBOX)
aoi = ee.FeatureCollection([ee.Feature(geometry)])

# Calculate dates
event_dt = datetime.fromisoformat(EVENT_DATE)
baseline_start = event_dt - timedelta(days=365)
war_start = baseline_start.strftime('%Y-%m-%d')
post_end = (event_dt + timedelta(days=60)).strftime('%Y-%m-%d')

print("Running PWTT analysis...")
pwtt_result = pwtt_lib.filter_s1(
    aoi=aoi,
    inference_start=EVENT_DATE,
    war_start=ee.Date(war_start),
    pre_interval=12,
    post_interval=2,
    viz=False,
    export=False,
)
print("PWTT analysis complete!")

# Extract bands
t_statistic = pwtt_result.select('T_statistic').clip(geometry)
damage = pwtt_result.select('damage').clip(geometry)

# Create damage probability
damage_prob = t_statistic.subtract(3).divide(2).clamp(0, 1).updateMask(t_statistic.gte(2.5))

# Visualization parameters
t_stat_vis = {'min': 3, 'max': 5, 'palette': ['yellow', 'orange', 'red', 'purple']}
damage_vis = {'min': 0, 'max': 1, 'palette': ['green', 'yellow', 'orange', 'red', 'darkred']}
sar_vis = {'min': -25, 'max': 0, 'palette': ['black', 'white']}

# Get SAR imagery
print("\nGetting SAR imagery...")
s1 = (
    ee.ImageCollection("COPERNICUS/S1_GRD")
    .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
    .filter(ee.Filter.eq("instrumentMode", "IW"))
    .filterBounds(geometry)
    .select('VV')
)

before_sar = s1.filterDate(war_start, EVENT_DATE).mean().clip(geometry)
after_sar = s1.filterDate(EVENT_DATE, post_end).mean().clip(geometry)

# Export using geemap
print("\nExporting images (this may take a minute)...")

# T-statistic image
print("  Exporting T-statistic...")
t_stat_rgb = t_statistic.visualize(**t_stat_vis)
geemap.ee_export_image(
    t_stat_rgb,
    filename=str(OUTPUT_DIR / "t_statistic_highres.tif"),
    scale=10,
    region=geometry,
    file_per_band=False,
)

# Damage probability
print("  Exporting damage probability...")
damage_rgb = damage_prob.visualize(**damage_vis)
geemap.ee_export_image(
    damage_rgb,
    filename=str(OUTPUT_DIR / "damage_probability_highres.tif"),
    scale=10,
    region=geometry,
    file_per_band=False,
)

# Before SAR
print("  Exporting SAR before...")
before_sar_rgb = before_sar.visualize(**sar_vis)
geemap.ee_export_image(
    before_sar_rgb,
    filename=str(OUTPUT_DIR / "sar_before_highres.tif"),
    scale=10,
    region=geometry,
    file_per_band=False,
)

# After SAR
print("  Exporting SAR after...")
after_sar_rgb = after_sar.visualize(**sar_vis)
geemap.ee_export_image(
    after_sar_rgb,
    filename=str(OUTPUT_DIR / "sar_after_highres.tif"),
    scale=10,
    region=geometry,
    file_per_band=False,
)

print("\n" + "=" * 60)
print("EXPORT COMPLETE")
print(f"Images saved to: {OUTPUT_DIR}")
print("=" * 60)

# List output files
print("\nOutput files:")
for f in OUTPUT_DIR.iterdir():
    size = f.stat().st_size / 1024
    print(f"  {f.name}: {size:.1f} KB")
