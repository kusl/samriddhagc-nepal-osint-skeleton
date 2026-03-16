#!/usr/bin/env python3
"""
PWTT Building-Level Damage Assessment for Singha Durbar.

Uses oballinger/PWTT algorithm with Google Open Buildings footprints
to compute per-building damage statistics.

Based on: https://github.com/oballinger/PWTT
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
import json

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

try:
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    from matplotlib.colors import LinearSegmentedColormap
    import numpy as np
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "matplotlib", "numpy"])
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    from matplotlib.colors import LinearSegmentedColormap
    import numpy as np

# Output directory
OUTPUT_DIR = Path(__file__).parent.parent / "analysis_output"
OUTPUT_DIR.mkdir(exist_ok=True)

# Singha Durbar coordinates
BBOX = [85.318, 27.697, 85.328, 27.705]
EVENT_DATE = "2025-09-08"
CENTER = [27.701, 85.323]

# PWTT Thresholds
T_CRITICAL = 4.0
T_SEVERE = 3.5
T_MODERATE = 3.0
T_MINOR = 2.5

print("\n" + "=" * 70)
print("PWTT BUILDING-LEVEL DAMAGE ASSESSMENT")
print("Location: Singha Durbar Government Complex")
print(f"Event Date: {EVENT_DATE}")
print(f"Algorithm: oballinger/PWTT (https://github.com/oballinger/PWTT)")
print("=" * 70 + "\n")

# Create geometry
geometry = ee.Geometry.Rectangle(BBOX)
aoi = ee.FeatureCollection([ee.Feature(geometry)])

# Calculate dates
event_dt = datetime.fromisoformat(EVENT_DATE)
baseline_start = event_dt - timedelta(days=365)
war_start = baseline_start.strftime('%Y-%m-%d')
post_end = (event_dt + timedelta(days=60)).strftime('%Y-%m-%d')

print(f"Baseline period: {war_start} to {EVENT_DATE} (12 months)")
print(f"Post-event period: {EVENT_DATE} to {post_end} (2 months)")

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 1: Run PWTT Analysis
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[1/5] Running PWTT analysis...")
pwtt_result = pwtt_lib.filter_s1(
    aoi=aoi,
    inference_start=EVENT_DATE,
    war_start=ee.Date(war_start),
    pre_interval=12,
    post_interval=2,
    viz=False,
    export=False,
)
t_statistic = pwtt_result.select('T_statistic')
damage_band = pwtt_result.select('damage')
print("      PWTT analysis complete!")

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 2: Get Building Footprints from Google Open Buildings
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[2/5] Fetching building footprints from Google Open Buildings...")

# Google Open Buildings dataset (excellent coverage for South Asia)
buildings_fc = ee.FeatureCollection('GOOGLE/Research/open-buildings/v3/polygons')

# Filter to our area of interest
buildings_in_aoi = (buildings_fc
    .filterBounds(geometry)
    .filter(ee.Filter.gte('confidence', 0.7))  # High confidence buildings only
)

# Add area calculation
buildings_with_area = buildings_in_aoi.map(
    lambda f: f.set('area_m2', f.geometry().area(1))
)

# Filter by minimum area (50 m²) and limit to manageable number
buildings_filtered = (buildings_with_area
    .filter(ee.Filter.gte('area_m2', 50))
    .sort('area_m2', False)  # Largest first
    .limit(200)  # Top 200 buildings
)

building_count = buildings_filtered.size().getInfo()
print(f"      Found {building_count} buildings in the area")

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 3: Compute Per-Building Damage Statistics (PWTT reduceRegions)
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[3/5] Computing per-building damage statistics...")

# Use PWTT's reduceRegions approach to get mean t-statistic per building
building_stats = t_statistic.reduceRegions(
    collection=buildings_filtered,
    reducer=ee.Reducer.mean().combine(
        ee.Reducer.max(), sharedInputs=True
    ).combine(
        ee.Reducer.min(), sharedInputs=True
    ),
    scale=10,
    tileScale=4,
)

# Also get damage binary stats
damage_stats = damage_band.reduceRegions(
    collection=buildings_filtered,
    reducer=ee.Reducer.mean(),
    scale=10,
    tileScale=4,
)

# Get the results
print("      Downloading building statistics...")
building_features = building_stats.getInfo()['features']
damage_features = damage_stats.getInfo()['features']

# Create damage lookup
damage_lookup = {}
for f in damage_features:
    fid = f['id']
    damage_lookup[fid] = f['properties'].get('mean', 0) or 0

print(f"      Processed {len(building_features)} buildings")

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 4: Classify Buildings by Damage Severity
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[4/5] Classifying buildings by damage severity...")

buildings_data = []
severity_counts = {'critical': 0, 'severe': 0, 'moderate': 0, 'minor': 0, 'safe': 0}

for feature in building_features:
    props = feature['properties']
    geom = feature['geometry']
    fid = feature['id']

    # Get t-statistic values
    t_mean = props.get('mean') or 0
    t_max = props.get('max') or 0
    t_min = props.get('min') or 0
    area_m2 = props.get('area_m2') or 0
    confidence = props.get('confidence') or 0

    # Get damage percentage from damage band
    damage_pct = damage_lookup.get(fid, 0) * 100

    # Classify severity based on mean t-statistic (PWTT methodology)
    if t_mean >= T_CRITICAL:
        severity = 'critical'
        color = '#d73027'  # Red
    elif t_mean >= T_SEVERE:
        severity = 'severe'
        color = '#fc8d59'  # Orange
    elif t_mean >= T_MODERATE:
        severity = 'moderate'
        color = '#fee08b'  # Yellow
    elif t_mean >= T_MINOR:
        severity = 'minor'
        color = '#d9ef8b'  # Light green
    else:
        severity = 'safe'
        color = '#1a9850'  # Green

    severity_counts[severity] += 1

    # Calculate centroid
    if geom['type'] == 'Polygon':
        coords = geom['coordinates'][0]
        centroid_lng = sum(c[0] for c in coords) / len(coords)
        centroid_lat = sum(c[1] for c in coords) / len(coords)
    else:
        centroid_lng, centroid_lat = CENTER[1], CENTER[0]

    buildings_data.append({
        'id': fid,
        'geometry': geom,
        'centroid_lat': centroid_lat,
        'centroid_lng': centroid_lng,
        'area_m2': area_m2,
        't_mean': t_mean,
        't_max': t_max,
        't_min': t_min,
        'damage_pct': damage_pct,
        'severity': severity,
        'color': color,
        'confidence': confidence,
    })

print("\n      Severity Distribution:")
print(f"      ├─ Critical (t≥{T_CRITICAL}): {severity_counts['critical']} buildings")
print(f"      ├─ Severe (t≥{T_SEVERE}):   {severity_counts['severe']} buildings")
print(f"      ├─ Moderate (t≥{T_MODERATE}): {severity_counts['moderate']} buildings")
print(f"      ├─ Minor (t≥{T_MINOR}):    {severity_counts['minor']} buildings")
print(f"      └─ Safe (t<{T_MINOR}):     {severity_counts['safe']} buildings")

# Sort by damage (most damaged first)
buildings_data.sort(key=lambda x: x['t_mean'], reverse=True)

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 5: Create Visualizations
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[5/5] Creating visualizations...")

# 5a. Create GeoJSON with building damage data
geojson_data = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "geometry": b['geometry'],
            "properties": {
                "id": b['id'],
                "t_mean": round(b['t_mean'], 3),
                "t_max": round(b['t_max'], 3),
                "damage_pct": round(b['damage_pct'], 1),
                "severity": b['severity'],
                "area_m2": round(b['area_m2'], 1),
            }
        }
        for b in buildings_data
    ]
}

geojson_path = OUTPUT_DIR / "building_damage.geojson"
with open(geojson_path, 'w') as f:
    json.dump(geojson_data, f, indent=2)
print(f"      Saved: {geojson_path.name}")

# 5b. Create detailed JSON results
results = {
    "event_name": "GenZ Protest - Singha Durbar",
    "event_date": EVENT_DATE,
    "bbox": BBOX,
    "algorithm": "oballinger/PWTT",
    "baseline_months": 12,
    "post_event_months": 2,
    "total_buildings": len(buildings_data),
    "severity_counts": severity_counts,
    "thresholds": {
        "critical": T_CRITICAL,
        "severe": T_SEVERE,
        "moderate": T_MODERATE,
        "minor": T_MINOR,
    },
    "buildings": [
        {
            "id": b['id'],
            "centroid": [b['centroid_lat'], b['centroid_lng']],
            "area_m2": round(b['area_m2'], 1),
            "t_mean": round(b['t_mean'], 3),
            "t_max": round(b['t_max'], 3),
            "damage_pct": round(b['damage_pct'], 1),
            "severity": b['severity'],
        }
        for b in buildings_data[:50]  # Top 50 most damaged
    ],
    "analysis_timestamp": datetime.now().isoformat(),
}

results_path = OUTPUT_DIR / "building_damage_results.json"
with open(results_path, 'w') as f:
    json.dump(results, f, indent=2)
print(f"      Saved: {results_path.name}")

# 5c. Create matplotlib visualization
fig, axes = plt.subplots(1, 2, figsize=(16, 8))
fig.suptitle(f'PWTT Building Damage Assessment - Singha Durbar\nEvent: {EVENT_DATE} | Algorithm: oballinger/PWTT',
             fontsize=14, fontweight='bold')

# Left: Building damage map (scatter plot of centroids)
ax1 = axes[0]
colors = {'critical': '#d73027', 'severe': '#fc8d59', 'moderate': '#fee08b', 'minor': '#d9ef8b', 'safe': '#1a9850'}

for severity in ['safe', 'minor', 'moderate', 'severe', 'critical']:  # Draw safe first, critical last
    buildings_sev = [b for b in buildings_data if b['severity'] == severity]
    if buildings_sev:
        lngs = [b['centroid_lng'] for b in buildings_sev]
        lats = [b['centroid_lat'] for b in buildings_sev]
        sizes = [max(20, min(200, b['area_m2'] / 5)) for b in buildings_sev]
        ax1.scatter(lngs, lats, c=colors[severity], s=sizes, alpha=0.7,
                   label=f"{severity.capitalize()} ({len(buildings_sev)})", edgecolors='black', linewidths=0.5)

ax1.set_xlim(BBOX[0], BBOX[2])
ax1.set_ylim(BBOX[1], BBOX[3])
ax1.set_xlabel('Longitude')
ax1.set_ylabel('Latitude')
ax1.set_title('Building Damage by Location\n(size = building area)')
ax1.legend(loc='upper left', fontsize=9)
ax1.set_aspect('equal')
ax1.grid(True, alpha=0.3)

# Right: Bar chart of severity distribution
ax2 = axes[1]
severities = ['Critical', 'Severe', 'Moderate', 'Minor', 'Safe']
counts = [severity_counts['critical'], severity_counts['severe'], severity_counts['moderate'],
          severity_counts['minor'], severity_counts['safe']]
bar_colors = ['#d73027', '#fc8d59', '#fee08b', '#d9ef8b', '#1a9850']

bars = ax2.barh(severities, counts, color=bar_colors, edgecolor='black')
ax2.set_xlabel('Number of Buildings')
ax2.set_title('Building Damage Distribution')

# Add count labels
for bar, count in zip(bars, counts):
    ax2.text(bar.get_width() + 1, bar.get_y() + bar.get_height()/2,
             str(count), va='center', fontsize=11)

# Add threshold annotations
ax2.text(max(counts) * 0.7, 4, f't ≥ {T_CRITICAL}', fontsize=9, color='gray')
ax2.text(max(counts) * 0.7, 3, f't ≥ {T_SEVERE}', fontsize=9, color='gray')
ax2.text(max(counts) * 0.7, 2, f't ≥ {T_MODERATE}', fontsize=9, color='gray')
ax2.text(max(counts) * 0.7, 1, f't ≥ {T_MINOR}', fontsize=9, color='gray')
ax2.text(max(counts) * 0.7, 0, f't < {T_MINOR}', fontsize=9, color='gray')

plt.tight_layout()

viz_path = OUTPUT_DIR / "building_damage_summary.png"
plt.savefig(viz_path, dpi=150, bbox_inches='tight', facecolor='white')
print(f"      Saved: {viz_path.name}")

# 5d. Create interactive HTML map with building polygons
print("      Creating interactive map...")

Map = geemap.Map(center=CENTER, zoom=17)
Map.add_basemap('SATELLITE')

# Add T-statistic layer
t_stat_vis = {'min': 3, 'max': 5, 'palette': ['yellow', 'orange', 'red', 'purple']}
Map.addLayer(t_statistic.clip(geometry), t_stat_vis, 'T-Statistic', opacity=0.6)

# Add building footprints colored by severity
# Create separate feature collections for each severity
for severity, color in colors.items():
    severity_features = [
        ee.Feature(ee.Geometry(b['geometry'])).set('severity', severity).set('t_mean', b['t_mean'])
        for b in buildings_data if b['severity'] == severity
    ]
    if severity_features:
        fc = ee.FeatureCollection(severity_features)
        Map.addLayer(fc, {'color': color}, f'Buildings - {severity.capitalize()}')

# Add legend
legend_dict = {
    'Critical (t≥4.0)': '#d73027',
    'Severe (t≥3.5)': '#fc8d59',
    'Moderate (t≥3.0)': '#fee08b',
    'Minor (t≥2.5)': '#d9ef8b',
    'Safe (t<2.5)': '#1a9850',
}
Map.add_legend(title='Building Damage', legend_dict=legend_dict, position='bottomright')

map_path = OUTPUT_DIR / "building_damage_map.html"
Map.to_html(str(map_path))
print(f"      Saved: {map_path.name}")

# 5e. Print top 10 most damaged buildings
print("\n" + "=" * 70)
print("TOP 10 MOST DAMAGED BUILDINGS")
print("=" * 70)
print(f"{'Rank':<6}{'T-stat':<10}{'Severity':<12}{'Area (m²)':<12}{'Damage %':<10}")
print("-" * 50)
for i, b in enumerate(buildings_data[:10], 1):
    print(f"{i:<6}{b['t_mean']:<10.2f}{b['severity']:<12}{b['area_m2']:<12.1f}{b['damage_pct']:<10.1f}")

# ═══════════════════════════════════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("ANALYSIS COMPLETE")
print("=" * 70)
print(f"\nTotal Buildings Analyzed: {len(buildings_data)}")
print(f"Damaged Buildings (t≥{T_MODERATE}): {severity_counts['critical'] + severity_counts['severe'] + severity_counts['moderate']}")
print(f"\nOutput files saved to: {OUTPUT_DIR}")
print("  - building_damage.geojson      (GeoJSON with all buildings)")
print("  - building_damage_results.json (Detailed analysis results)")
print("  - building_damage_summary.png  (Visualization chart)")
print("  - building_damage_map.html     (Interactive map)")

# Open output folder
import subprocess
subprocess.run(["open", str(OUTPUT_DIR)])
