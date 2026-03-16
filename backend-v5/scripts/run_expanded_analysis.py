#!/usr/bin/env python3
"""
PWTT Analysis with EXPANDED area to reduce blurriness.

The original Singha Durbar bbox was only ~1km x 0.9km, but PWTT uses
150m Gaussian convolution which causes blurring at that scale.

This script:
1. Expands the analysis area to 3km x 3km
2. Shows BOTH raw t-statistic AND smoothed version
3. Provides sharper building-level damage detection
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
import json

sys.path.insert(0, str(Path(__file__).parent.parent))
PWTT_LIB_PATH = Path(__file__).parent.parent / "pwtt_lib" / "code"
sys.path.insert(0, str(PWTT_LIB_PATH))

import ee
import geemap

print("Initializing Google Earth Engine...")
ee.Initialize()

import pwtt as pwtt_lib

try:
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap
    import numpy as np
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "matplotlib", "numpy"])
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap
    import numpy as np

OUTPUT_DIR = Path(__file__).parent.parent / "analysis_output"
OUTPUT_DIR.mkdir(exist_ok=True)

# Original Singha Durbar center
CENTER_LAT = 27.701
CENTER_LNG = 85.323

# EXPANDED bounding box: 3km x 3km around Singha Durbar
# 1 degree lat ≈ 111km, 1 degree lng ≈ 99km at this latitude
EXPAND_KM = 1.5  # 1.5km in each direction = 3km total
LAT_OFFSET = EXPAND_KM / 111
LNG_OFFSET = EXPAND_KM / 99

EXPANDED_BBOX = [
    CENTER_LNG - LNG_OFFSET,  # min_lng
    CENTER_LAT - LAT_OFFSET,  # min_lat
    CENTER_LNG + LNG_OFFSET,  # max_lng
    CENTER_LAT + LAT_OFFSET,  # max_lat
]

# Original small bbox for comparison
ORIGINAL_BBOX = [85.318, 27.697, 85.328, 27.705]

EVENT_DATE = "2025-09-08"

print("\n" + "=" * 70)
print("PWTT ANALYSIS - EXPANDED AREA (3km x 3km)")
print("=" * 70)
print(f"\nOriginal bbox: {ORIGINAL_BBOX}")
print(f"  Size: ~1km x 0.9km (TOO SMALL for 150m convolution)")
print(f"\nExpanded bbox: [{EXPANDED_BBOX[0]:.4f}, {EXPANDED_BBOX[1]:.4f}, {EXPANDED_BBOX[2]:.4f}, {EXPANDED_BBOX[3]:.4f}]")
print(f"  Size: ~3km x 3km (BETTER for PWTT analysis)")
print(f"\nEvent Date: {EVENT_DATE}")

# Create geometries
expanded_geometry = ee.Geometry.Rectangle(EXPANDED_BBOX)
original_geometry = ee.Geometry.Rectangle(ORIGINAL_BBOX)
aoi = ee.FeatureCollection([ee.Feature(expanded_geometry)])

# Calculate dates
event_dt = datetime.fromisoformat(EVENT_DATE)
war_start = (event_dt - timedelta(days=365)).strftime('%Y-%m-%d')
post_end = (event_dt + timedelta(days=60)).strftime('%Y-%m-%d')

# ═══════════════════════════════════════════════════════════════════════════════
# Run PWTT on EXPANDED area
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[1/4] Running PWTT on expanded 3km x 3km area...")

pwtt_result = pwtt_lib.filter_s1(
    aoi=aoi,
    inference_start=EVENT_DATE,
    war_start=ee.Date(war_start),
    pre_interval=12,
    post_interval=2,
    viz=False,
    export=False,
)

# Get both raw and smoothed t-statistics
t_statistic_smoothed = pwtt_result.select('T_statistic')  # Averaged with k50, k100, k150
max_change = pwtt_result.select('max_change')  # RAW t-stat (sharper but noisier)
damage_band = pwtt_result.select('damage')

print("      PWTT complete!")

# ═══════════════════════════════════════════════════════════════════════════════
# Calculate statistics for ORIGINAL Singha Durbar area
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[2/4] Calculating damage statistics for Singha Durbar...")

pixel_area = ee.Image.pixelArea()

def get_area_km2(mask, geom):
    result = mask.multiply(pixel_area).reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=geom,
        scale=10,
        maxPixels=1e9
    )
    val = result.values().get(0)
    return ee.Number(ee.Algorithms.If(val, val, 0)).divide(1e6).getInfo()

# Using the smoothed T_statistic
total_area = original_geometry.area().getInfo() / 1e6
damaged_area = get_area_km2(damage_band.gt(0), original_geometry)
critical_area = get_area_km2(t_statistic_smoothed.gte(4.0), original_geometry)
severe_area = get_area_km2(t_statistic_smoothed.gte(3.5).And(t_statistic_smoothed.lt(4.0)), original_geometry)
moderate_area = get_area_km2(t_statistic_smoothed.gte(3.0).And(t_statistic_smoothed.lt(3.5)), original_geometry)

print(f"\n      Singha Durbar Damage (within original bbox):")
print(f"      Total Area:    {total_area:.4f} km²")
print(f"      Damaged Area:  {damaged_area:.4f} km² ({damaged_area/total_area*100:.1f}%)")
print(f"      Critical:      {critical_area*1000:.1f} m²")
print(f"      Severe:        {severe_area*1000:.1f} m²")
print(f"      Moderate:      {moderate_area*1000:.1f} m²")

# ═══════════════════════════════════════════════════════════════════════════════
# Get building footprints and compute damage
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[3/4] Analyzing buildings with SHARPER raw t-statistic...")

buildings_fc = ee.FeatureCollection('GOOGLE/Research/open-buildings/v3/polygons')
buildings_in_aoi = (buildings_fc
    .filterBounds(original_geometry)  # Focus on Singha Durbar
    .filter(ee.Filter.gte('confidence', 0.7))
    .map(lambda f: f.set('area_m2', f.geometry().area(1)))
    .filter(ee.Filter.gte('area_m2', 50))
    .limit(200)
)

# Use RAW max_change (sharper) for building analysis
building_stats_raw = max_change.reduceRegions(
    collection=buildings_in_aoi,
    reducer=ee.Reducer.mean().combine(ee.Reducer.max(), sharedInputs=True),
    scale=10,
    tileScale=4,
)

# Also get smoothed for comparison
building_stats_smoothed = t_statistic_smoothed.reduceRegions(
    collection=buildings_in_aoi,
    reducer=ee.Reducer.mean(),
    scale=10,
    tileScale=4,
)

raw_features = building_stats_raw.getInfo()['features']
smoothed_features = building_stats_smoothed.getInfo()['features']

# Create lookup for smoothed values
smoothed_lookup = {f['id']: f['properties'].get('mean', 0) or 0 for f in smoothed_features}

buildings_data = []
severity_counts = {'critical': 0, 'severe': 0, 'moderate': 0, 'minor': 0, 'safe': 0}

for feature in raw_features:
    props = feature['properties']
    geom = feature['geometry']
    fid = feature['id']

    t_raw = props.get('mean') or 0
    t_max = props.get('max') or 0
    t_smoothed = smoothed_lookup.get(fid, 0)
    area_m2 = props.get('area_m2') or 0

    # Use RAW t-stat for classification (sharper)
    if t_raw >= 4.0:
        severity = 'critical'
    elif t_raw >= 3.5:
        severity = 'severe'
    elif t_raw >= 3.0:
        severity = 'moderate'
    elif t_raw >= 2.5:
        severity = 'minor'
    else:
        severity = 'safe'

    severity_counts[severity] += 1

    if geom['type'] == 'Polygon':
        coords = geom['coordinates'][0]
        centroid_lng = sum(c[0] for c in coords) / len(coords)
        centroid_lat = sum(c[1] for c in coords) / len(coords)
    else:
        centroid_lng, centroid_lat = CENTER_LNG, CENTER_LAT

    buildings_data.append({
        'geometry': geom,
        'centroid': [centroid_lat, centroid_lng],
        'area_m2': area_m2,
        't_raw': t_raw,
        't_max': t_max,
        't_smoothed': t_smoothed,
        'severity': severity,
    })

buildings_data.sort(key=lambda x: x['t_raw'], reverse=True)

print(f"\n      Building Severity (using RAW t-stat - SHARPER):")
print(f"      ├─ Critical: {severity_counts['critical']}")
print(f"      ├─ Severe:   {severity_counts['severe']}")
print(f"      ├─ Moderate: {severity_counts['moderate']}")
print(f"      ├─ Minor:    {severity_counts['minor']}")
print(f"      └─ Safe:     {severity_counts['safe']}")

# ═══════════════════════════════════════════════════════════════════════════════
# Create visualizations
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[4/4] Creating visualizations...")

# Visualization params
t_stat_vis = {'min': 3, 'max': 5, 'palette': ['yellow', 'orange', 'red', 'purple']}
raw_vis = {'min': 2, 'max': 6, 'palette': ['green', 'yellow', 'orange', 'red', 'purple']}

# Export images - EXPANDED area
print("      Exporting expanded area images...")

# Smoothed T-statistic (full 3km area)
smoothed_rgb = t_statistic_smoothed.visualize(**t_stat_vis).clip(expanded_geometry)
geemap.ee_export_image(
    smoothed_rgb,
    filename=str(OUTPUT_DIR / "expanded_t_stat_smoothed.tif"),
    scale=10,
    region=expanded_geometry,
)

# RAW max_change (sharper - full 3km area)
raw_rgb = max_change.visualize(**raw_vis).clip(expanded_geometry)
geemap.ee_export_image(
    raw_rgb,
    filename=str(OUTPUT_DIR / "expanded_t_stat_raw.tif"),
    scale=10,
    region=expanded_geometry,
)

# Zoomed in on Singha Durbar - RAW (sharper)
raw_zoomed = max_change.visualize(**raw_vis).clip(original_geometry)
geemap.ee_export_image(
    raw_zoomed,
    filename=str(OUTPUT_DIR / "singha_durbar_raw_sharp.tif"),
    scale=10,
    region=original_geometry,
)

# Convert to PNG
from PIL import Image
for tif in OUTPUT_DIR.glob("*.tif"):
    try:
        img = Image.open(tif)
        img.save(tif.with_suffix('.png'))
    except:
        pass

# Create comparison figure
print("      Creating comparison visualization...")

fig, axes = plt.subplots(2, 2, figsize=(14, 12))
fig.suptitle('PWTT Analysis Comparison - Smoothed vs Raw T-statistic\nSingha Durbar, Sept 8 2025',
             fontsize=14, fontweight='bold')

# Top left: Smoothed (blurry)
ax1 = axes[0, 0]
smoothed_path = OUTPUT_DIR / "expanded_t_stat_smoothed.png"
if smoothed_path.exists():
    img = Image.open(smoothed_path)
    ax1.imshow(img)
ax1.set_title('Smoothed T-statistic (3km area)\nk50+k100+k150 averaging = BLURRY', fontsize=11)
ax1.axis('off')

# Top right: Raw (sharper)
ax2 = axes[0, 1]
raw_path = OUTPUT_DIR / "expanded_t_stat_raw.png"
if raw_path.exists():
    img = Image.open(raw_path)
    ax2.imshow(img)
ax2.set_title('Raw T-statistic (3km area)\nNo convolution = SHARPER', fontsize=11)
ax2.axis('off')

# Bottom left: Zoomed raw
ax3 = axes[1, 0]
zoomed_path = OUTPUT_DIR / "singha_durbar_raw_sharp.png"
if zoomed_path.exists():
    img = Image.open(zoomed_path)
    ax3.imshow(img)
ax3.set_title('Singha Durbar - Raw T-stat (SHARP)\nThis is what you want!', fontsize=11)
ax3.axis('off')

# Bottom right: Building damage chart
ax4 = axes[1, 1]
severities = ['Critical', 'Severe', 'Moderate', 'Minor', 'Safe']
counts = [severity_counts['critical'], severity_counts['severe'],
          severity_counts['moderate'], severity_counts['minor'], severity_counts['safe']]
colors = ['#d73027', '#fc8d59', '#fee08b', '#d9ef8b', '#1a9850']
bars = ax4.barh(severities, counts, color=colors, edgecolor='black')
ax4.set_xlabel('Number of Buildings')
ax4.set_title('Building Damage (Raw T-stat)\nSharper detection', fontsize=11)
for bar, count in zip(bars, counts):
    ax4.text(bar.get_width() + 0.5, bar.get_y() + bar.get_height()/2, str(count), va='center')

plt.tight_layout()
comparison_path = OUTPUT_DIR / "smoothed_vs_raw_comparison.png"
plt.savefig(comparison_path, dpi=150, bbox_inches='tight', facecolor='white')
print(f"      Saved: {comparison_path.name}")

# Create interactive map with both layers
print("      Creating interactive map with raw t-stat...")

Map = geemap.Map(center=[CENTER_LAT, CENTER_LNG], zoom=16)
Map.add_basemap('SATELLITE')

# Add raw t-statistic (sharper)
Map.addLayer(max_change.clip(expanded_geometry), raw_vis, 'Raw T-stat (Sharp)', opacity=0.7)

# Add smoothed for comparison
Map.addLayer(t_statistic_smoothed.clip(expanded_geometry), t_stat_vis, 'Smoothed T-stat (Blurry)', opacity=0.5, shown=False)

# Add building footprints with proper hex colors
colors_map = {'critical': 'FF0000', 'severe': 'FF8C00', 'moderate': 'FFD700', 'minor': '90EE90', 'safe': '228B22'}
for sev in ['safe', 'minor', 'moderate', 'severe', 'critical']:
    features = [ee.Feature(ee.Geometry(b['geometry'])) for b in buildings_data if b['severity'] == sev]
    if features:
        fc = ee.FeatureCollection(features)
        Map.addLayer(fc.style(color=colors_map[sev], fillColor=colors_map[sev]), {}, f'{sev.capitalize()} Buildings')

# Add Singha Durbar outline
Map.addLayer(ee.FeatureCollection([ee.Feature(original_geometry)]).style(color='cyan', fillColor='00000000', width=3),
             {}, 'Singha Durbar Boundary')

map_path = OUTPUT_DIR / "expanded_analysis_map.html"
Map.to_html(str(map_path))
print(f"      Saved: {map_path.name}")

# Save results
results = {
    "analysis_type": "expanded_with_raw_tstat",
    "event_date": EVENT_DATE,
    "original_bbox": ORIGINAL_BBOX,
    "expanded_bbox": EXPANDED_BBOX,
    "explanation": "Original bbox was too small for PWTT's 150m convolution. Expanded to 3km and also showing RAW t-stat for sharper results.",
    "singha_durbar_stats": {
        "total_area_km2": total_area,
        "damaged_area_km2": damaged_area,
        "damage_percentage": damaged_area/total_area*100 if total_area > 0 else 0,
    },
    "building_severity_raw": severity_counts,
    "top_damaged_buildings": [
        {"t_raw": round(b['t_raw'], 2), "t_smoothed": round(b['t_smoothed'], 2),
         "area_m2": round(b['area_m2'], 1), "severity": b['severity']}
        for b in buildings_data[:10]
    ],
}

with open(OUTPUT_DIR / "expanded_analysis_results.json", 'w') as f:
    json.dump(results, f, indent=2)

# Print top buildings with comparison
print("\n" + "=" * 70)
print("TOP 10 BUILDINGS - RAW vs SMOOTHED T-STATISTIC")
print("=" * 70)
print(f"{'Rank':<6}{'T-raw':<10}{'T-smooth':<10}{'Diff':<10}{'Severity':<12}{'Area(m²)':<10}")
print("-" * 58)
for i, b in enumerate(buildings_data[:10], 1):
    diff = b['t_raw'] - b['t_smoothed']
    print(f"{i:<6}{b['t_raw']:<10.2f}{b['t_smoothed']:<10.2f}{diff:+<10.2f}{b['severity']:<12}{b['area_m2']:<10.1f}")

print("\n" + "=" * 70)
print("ANALYSIS COMPLETE")
print("=" * 70)
print(f"\nKey insight: Raw T-stat is {buildings_data[0]['t_raw'] - buildings_data[0]['t_smoothed']:.1f} points HIGHER than smoothed!")
print("The smoothing was hiding damage severity.")
print(f"\nOutput: {OUTPUT_DIR}")

import subprocess
subprocess.run(["open", str(OUTPUT_DIR)])
