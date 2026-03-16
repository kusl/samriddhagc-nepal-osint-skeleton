#!/usr/bin/env python3
"""
Export Sentinel imagery with ROBUST damage detection.
- Pixel-based hotspot detection (not just building footprints)
- Uses MAX reducer instead of MEAN to catch localized damage
- Manual key building polygons for important structures
- Clusters damaged pixels into damage zones
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
print("GEE initialized!")

import pwtt as pwtt_lib

try:
    from PIL import Image, ImageDraw, ImageFont
    import matplotlib.pyplot as plt
    import matplotlib.patches as patches
    import numpy as np
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pillow", "matplotlib", "numpy"])
    from PIL import Image, ImageDraw, ImageFont
    import matplotlib.pyplot as plt
    import matplotlib.patches as patches
    import numpy as np

OUTPUT_DIR = Path(__file__).parent.parent / "analysis_output"
OUTPUT_DIR.mkdir(exist_ok=True)

# Singha Durbar
BBOX = [85.315, 27.694, 85.331, 27.708]
CENTER = [27.701, 85.323]
EVENT_DATE = "2025-09-08"

# Key buildings in Singha Durbar complex (manually defined for important structures)
KEY_BUILDINGS = [
    {
        'name': 'Main Singha Durbar Building',
        'bbox': [85.3200, 27.6995, 85.3235, 27.7015],
        'importance': 'high'
    },
    {
        'name': 'West Wing',
        'bbox': [85.3180, 27.6990, 85.3200, 27.7010],
        'importance': 'high'
    },
    {
        'name': 'East Administrative Block',
        'bbox': [85.3235, 27.6990, 85.3260, 27.7020],
        'importance': 'medium'
    },
    {
        'name': 'North Complex',
        'bbox': [85.3200, 27.7015, 85.3240, 27.7040],
        'importance': 'medium'
    },
]

print("\n" + "=" * 70)
print("ROBUST DAMAGE DETECTION - SINGHA DURBAR")
print(f"Event Date: {EVENT_DATE}")
print("=" * 70)

geometry = ee.Geometry.Rectangle(BBOX)
event_dt = datetime.fromisoformat(EVENT_DATE)

before_start = (event_dt - timedelta(days=365)).strftime('%Y-%m-%d')
before_end = (event_dt - timedelta(days=1)).strftime('%Y-%m-%d')
after_start = EVENT_DATE
after_end = (event_dt + timedelta(days=90)).strftime('%Y-%m-%d')

print(f"\nBefore period: {before_start} to {before_end} (1 year)")
print(f"After period:  {after_start} to {after_end} (3 months)")

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 1: Run PWTT Analysis
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[1/6] Running PWTT analysis...")

aoi = ee.FeatureCollection([ee.Feature(geometry)])
war_start = (event_dt - timedelta(days=365)).strftime('%Y-%m-%d')

pwtt_result = pwtt_lib.filter_s1(
    aoi=aoi,
    inference_start=EVENT_DATE,
    war_start=ee.Date(war_start),
    pre_interval=12,
    post_interval=2,
    viz=False,
    export=False,
)

max_change = pwtt_result.select('max_change')
t_stat_smoothed = pwtt_result.select('T_statistic')

# Get overall statistics
overall_stats = max_change.reduceRegion(
    reducer=ee.Reducer.mean().combine(
        reducer2=ee.Reducer.max(),
        sharedInputs=True
    ).combine(
        reducer2=ee.Reducer.percentile([90, 95, 99]),
        sharedInputs=True
    ),
    geometry=geometry,
    scale=10,
).getInfo()

print(f"      Overall t-statistics in area:")
print(f"        Mean: {overall_stats.get('max_change_mean', 0):.2f}")
print(f"        Max:  {overall_stats.get('max_change_max', 0):.2f}")
print(f"        P90:  {overall_stats.get('max_change_p90', 0):.2f}")
print(f"        P95:  {overall_stats.get('max_change_p95', 0):.2f}")
print(f"        P99:  {overall_stats.get('max_change_p99', 0):.2f}")

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 2: Detect damage in KEY BUILDINGS using MAX reducer
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[2/6] Analyzing key government buildings...")

key_building_results = []
for kb in KEY_BUILDINGS:
    kb_geom = ee.Geometry.Rectangle(kb['bbox'])

    # Use multiple reducers to get comprehensive stats
    stats = max_change.reduceRegion(
        reducer=ee.Reducer.mean().combine(
            reducer2=ee.Reducer.max(),
            sharedInputs=True
        ).combine(
            reducer2=ee.Reducer.percentile([75, 90]),
            sharedInputs=True
        ),
        geometry=kb_geom,
        scale=10,
    ).getInfo()

    t_mean = stats.get('max_change_mean', 0) or 0
    t_max = stats.get('max_change_max', 0) or 0
    t_p75 = stats.get('max_change_p75', 0) or 0
    t_p90 = stats.get('max_change_p90', 0) or 0

    # Use P75 for damage classification (more robust than mean, less extreme than max)
    # This captures if 25% of the building shows damage
    t_score = t_p75

    if t_max >= 3.0:  # If ANY significant damage detected
        if t_p90 >= 4.0:
            severity = 'critical'
            color = 'red'
        elif t_p90 >= 3.5:
            severity = 'severe'
            color = 'orange'
        elif t_p75 >= 3.0:
            severity = 'moderate'
            color = 'yellow'
        else:
            severity = 'minor'
            color = 'lime'

        key_building_results.append({
            'name': kb['name'],
            'bbox': kb['bbox'],
            'centroid': [(kb['bbox'][1] + kb['bbox'][3])/2, (kb['bbox'][0] + kb['bbox'][2])/2],
            't_mean': t_mean,
            't_max': t_max,
            't_p75': t_p75,
            't_p90': t_p90,
            'severity': severity,
            'color': color,
            'is_key_building': True,
        })
        print(f"      {kb['name']}: max={t_max:.2f}, p90={t_p90:.2f}, p75={t_p75:.2f} -> {severity.upper()}")
    else:
        print(f"      {kb['name']}: max={t_max:.2f} (no significant damage)")

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 3: Pixel-based hotspot detection (find damage clusters)
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[3/6] Running pixel-based hotspot detection...")

# Create damage mask at different thresholds
damage_critical = max_change.gte(4.0)
damage_severe = max_change.gte(3.5).And(max_change.lt(4.0))
damage_moderate = max_change.gte(3.0).And(max_change.lt(3.5))

# Count damaged pixels
critical_pixels = damage_critical.reduceRegion(
    reducer=ee.Reducer.sum(),
    geometry=geometry,
    scale=10,
).getInfo().get('max_change', 0) or 0

severe_pixels = damage_severe.reduceRegion(
    reducer=ee.Reducer.sum(),
    geometry=geometry,
    scale=10,
).getInfo().get('max_change', 0) or 0

moderate_pixels = damage_moderate.reduceRegion(
    reducer=ee.Reducer.sum(),
    geometry=geometry,
    scale=10,
).getInfo().get('max_change', 0) or 0

print(f"      Critical pixels (t≥4.0): {int(critical_pixels)}")
print(f"      Severe pixels (t≥3.5):   {int(severe_pixels)}")
print(f"      Moderate pixels (t≥3.0): {int(moderate_pixels)}")

# Cluster damaged pixels into connected components
# Use morphological operations to group nearby damaged pixels
damage_any = max_change.gte(3.0)
damage_clustered = damage_any.focalMax(radius=15, units='meters').focalMin(radius=10, units='meters')

# Convert to vectors (damage zones)
damage_vectors = damage_clustered.selfMask().reduceToVectors(
    geometry=geometry,
    scale=10,
    geometryType='polygon',
    eightConnected=True,
    maxPixels=1e8,
    tileScale=4,
)

# Get stats for each damage zone
damage_zones_with_stats = max_change.reduceRegions(
    collection=damage_vectors,
    reducer=ee.Reducer.mean().combine(
        reducer2=ee.Reducer.max(),
        sharedInputs=True
    ),
    scale=10,
    tileScale=4,
)

damage_zones_info = damage_zones_with_stats.getInfo()
print(f"      Detected {len(damage_zones_info['features'])} damage zones")

# Process damage zones
damage_zones = []
for f in damage_zones_info['features']:
    props = f['properties']
    t_mean = props.get('mean', 0) or 0
    t_max = props.get('max', 0) or 0

    if t_max >= 3.0:
        geom = f['geometry']
        if geom['type'] == 'Polygon':
            coords = geom['coordinates'][0]
            lngs = [c[0] for c in coords]
            lats = [c[1] for c in coords]

            # Calculate area
            area = (max(lngs) - min(lngs)) * (max(lats) - min(lats)) * 111000 * 111000  # rough m²

            if area >= 100:  # At least 100 m² damage zone
                if t_max >= 4.0:
                    severity = 'critical'
                    color = 'red'
                elif t_max >= 3.5:
                    severity = 'severe'
                    color = 'orange'
                else:
                    severity = 'moderate'
                    color = 'yellow'

                damage_zones.append({
                    'bbox': [min(lngs), min(lats), max(lngs), max(lats)],
                    'centroid': [sum(lats)/len(lats), sum(lngs)/len(lngs)],
                    't_mean': t_mean,
                    't_max': t_max,
                    'severity': severity,
                    'color': color,
                    'area_m2': area,
                    'is_key_building': False,
                })

damage_zones.sort(key=lambda x: x['t_max'], reverse=True)
print(f"      Significant damage zones (≥100m²): {len(damage_zones)}")

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 4: Also check Google Open Buildings with MAX reducer
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[4/6] Checking building footprints with MAX reducer...")

buildings_fc = ee.FeatureCollection('GOOGLE/Research/open-buildings/v3/polygons')
buildings_in_aoi = (buildings_fc
    .filterBounds(geometry)
    .filter(ee.Filter.gte('confidence', 0.65))  # Lowered threshold
    .map(lambda f: f.set('area_m2', f.geometry().area(1)))
    .filter(ee.Filter.gte('area_m2', 30))  # Lowered to 30m²
)

# Use MAX reducer to catch localized damage
building_stats = max_change.reduceRegions(
    collection=buildings_in_aoi,
    reducer=ee.Reducer.mean().combine(
        reducer2=ee.Reducer.max(),
        sharedInputs=True
    ).combine(
        reducer2=ee.Reducer.percentile([75]),
        sharedInputs=True
    ),
    scale=10,
    tileScale=4,
)

features = building_stats.limit(500).getInfo()['features']

damaged_buildings = []
for f in features:
    props = f['properties']
    t_mean = props.get('mean', 0) or 0
    t_max = props.get('max', 0) or 0
    t_p75 = props.get('p75', 0) or 0

    # Use MAX for detection (catches localized damage)
    if t_max >= 3.5:  # Higher threshold since using max
        geom = f['geometry']
        if geom['type'] == 'Polygon':
            coords = geom['coordinates'][0]
            lngs = [c[0] for c in coords]
            lats = [c[1] for c in coords]

            if t_max >= 5.0:
                severity = 'critical'
                color = 'red'
            elif t_max >= 4.0:
                severity = 'severe'
                color = 'orange'
            else:
                severity = 'moderate'
                color = 'yellow'

            damaged_buildings.append({
                'bbox': [min(lngs), min(lats), max(lngs), max(lats)],
                'centroid': [sum(lats)/len(lats), sum(lngs)/len(lngs)],
                't_mean': t_mean,
                't_max': t_max,
                't_p75': t_p75,
                'severity': severity,
                'color': color,
                'area_m2': props.get('area_m2', 0),
                'is_key_building': False,
            })

damaged_buildings.sort(key=lambda x: x['t_max'], reverse=True)
print(f"      Damaged buildings (t_max≥3.5): {len(damaged_buildings)}")

# ═══════════════════════════════════════════════════════════════════════════════
# Combine all detections
# ═══════════════════════════════════════════════════════════════════════════════
all_detections = key_building_results + damage_zones[:50] + damaged_buildings[:100]

# Remove duplicates (overlapping boxes)
def boxes_overlap(b1, b2, threshold=0.5):
    """Check if two boxes overlap significantly."""
    x1 = max(b1[0], b2[0])
    y1 = max(b1[1], b2[1])
    x2 = min(b1[2], b2[2])
    y2 = min(b1[3], b2[3])

    if x1 >= x2 or y1 >= y2:
        return False

    intersection = (x2 - x1) * (y2 - y1)
    area1 = (b1[2] - b1[0]) * (b1[3] - b1[1])
    area2 = (b2[2] - b2[0]) * (b2[3] - b2[1])

    return intersection / min(area1, area2) > threshold

# Deduplicate, keeping higher severity ones
unique_detections = []
for d in all_detections:
    is_duplicate = False
    for existing in unique_detections:
        if boxes_overlap(d['bbox'], existing['bbox']):
            is_duplicate = True
            break
    if not is_duplicate:
        unique_detections.append(d)

# Sort by severity then t_max
severity_order = {'critical': 0, 'severe': 1, 'moderate': 2, 'minor': 3}
unique_detections.sort(key=lambda x: (severity_order.get(x['severity'], 99), -x.get('t_max', 0)))

print(f"\n      Total unique detections: {len(unique_detections)}")
print(f"        - Key buildings: {sum(1 for d in unique_detections if d.get('is_key_building'))}")
print(f"        - Critical: {sum(1 for d in unique_detections if d['severity']=='critical')}")
print(f"        - Severe: {sum(1 for d in unique_detections if d['severity']=='severe')}")
print(f"        - Moderate: {sum(1 for d in unique_detections if d['severity']=='moderate')}")

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 5: Export imagery
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[5/6] Exporting high-resolution imagery...")

# Sentinel-2 RGB
def mask_clouds(image):
    qa = image.select('QA60')
    cloud_bit_mask = 1 << 10
    cirrus_bit_mask = 1 << 11
    mask = qa.bitwiseAnd(cloud_bit_mask).eq(0).And(qa.bitwiseAnd(cirrus_bit_mask).eq(0))
    return image.updateMask(mask)

s2_before = (
    ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
    .filterBounds(geometry)
    .filterDate(before_start, before_end)
    .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 50))
    .map(mask_clouds)
    .median()
    .clip(geometry)
)

s2_after = (
    ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
    .filterBounds(geometry)
    .filterDate(after_start, after_end)
    .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 50))
    .map(mask_clouds)
    .median()
    .clip(geometry)
)

s2_before_count = (
    ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
    .filterBounds(geometry)
    .filterDate(before_start, before_end)
    .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 50))
    .size().getInfo()
)

s2_after_count = (
    ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
    .filterBounds(geometry)
    .filterDate(after_start, after_end)
    .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 50))
    .size().getInfo()
)

print(f"      RGB Before: {s2_before_count} images")
print(f"      RGB After: {s2_after_count} images")

rgb_vis = {'bands': ['B4', 'B3', 'B2'], 'min': 0, 'max': 3000}

print("      Exporting RGB before...")
geemap.ee_export_image(
    s2_before.visualize(**rgb_vis),
    filename=str(OUTPUT_DIR / "rgb_before_highres.tif"),
    scale=5,
    region=geometry,
)

print("      Exporting RGB after...")
geemap.ee_export_image(
    s2_after.visualize(**rgb_vis),
    filename=str(OUTPUT_DIR / "rgb_after_highres.tif"),
    scale=5,
    region=geometry,
)

# Sentinel-1 SAR
print("      Exporting SAR...")
s1 = (
    ee.ImageCollection("COPERNICUS/S1_GRD")
    .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
    .filter(ee.Filter.eq("instrumentMode", "IW"))
    .filterBounds(geometry)
    .select('VV')
)

sar_before = s1.filterDate(before_start, before_end).median().clip(geometry)
sar_after = s1.filterDate(after_start, after_end).median().clip(geometry)
sar_vis = {'min': -25, 'max': 0, 'palette': ['000000', 'ffffff']}

geemap.ee_export_image(
    sar_before.visualize(**sar_vis),
    filename=str(OUTPUT_DIR / "sar_before_highres.tif"),
    scale=5,
    region=geometry,
)

geemap.ee_export_image(
    sar_after.visualize(**sar_vis),
    filename=str(OUTPUT_DIR / "sar_after_highres.tif"),
    scale=5,
    region=geometry,
)

# Export damage probability heatmap
print("      Exporting damage heatmap...")
damage_vis = {'min': 2, 'max': 6, 'palette': ['green', 'yellow', 'orange', 'red', 'purple']}
geemap.ee_export_image(
    max_change.visualize(**damage_vis),
    filename=str(OUTPUT_DIR / "damage_heatmap.tif"),
    scale=5,
    region=geometry,
)

# Convert TIFFs to PNG
for tif in OUTPUT_DIR.glob("*_highres.tif"):
    try:
        img = Image.open(tif)
        img.save(tif.with_suffix('.png'))
    except:
        pass

try:
    img = Image.open(OUTPUT_DIR / "damage_heatmap.tif")
    img.save(OUTPUT_DIR / "damage_heatmap.png")
except:
    pass

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 6: Create visualization with damage boxes
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[6/6] Creating damage detection visualizations...")

def add_damage_boxes(img_path, output_path, detections, bbox, title):
    """Add bounding boxes around damage detections."""
    img = Image.open(img_path).convert('RGBA')
    draw = ImageDraw.Draw(img)

    img_width, img_height = img.size

    def geo_to_pixel(lng, lat):
        x = (lng - bbox[0]) / (bbox[2] - bbox[0]) * img_width
        y = (1 - (lat - bbox[1]) / (bbox[3] - bbox[1])) * img_height
        return int(x), int(y)

    colors = {
        'critical': (255, 0, 0, 255),
        'severe': (255, 165, 0, 255),
        'moderate': (255, 255, 0, 255),
        'minor': (144, 238, 144, 255)
    }

    # Draw boxes
    for d in detections:
        d_bbox = d['bbox']
        severity = d['severity']
        color = colors.get(severity, (255, 255, 0, 255))
        is_key = d.get('is_key_building', False)

        x1, y1 = geo_to_pixel(d_bbox[0], d_bbox[3])
        x2, y2 = geo_to_pixel(d_bbox[2], d_bbox[1])

        # Add padding
        padding = 3
        x1 -= padding
        y1 -= padding
        x2 += padding
        y2 += padding

        # Draw thicker box for key buildings
        line_width = 4 if is_key else 2
        for i in range(line_width):
            draw.rectangle([x1-i, y1-i, x2+i, y2+i], outline=color[:3])

    # Add title
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 14)
        font_small = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 11)
    except:
        font = ImageFont.load_default()
        font_small = font

    draw.rectangle([0, 0, img_width, 22], fill=(0, 0, 0, 200))
    draw.text((10, 4), title, fill=(255, 255, 255), font=font)

    # Add legend
    legend_y = img_height - 85
    draw.rectangle([5, legend_y, 130, img_height - 5], fill=(0, 0, 0, 180))
    draw.text((10, legend_y + 5), "Damage Level:", fill=(255, 255, 255), font=font_small)

    y_offset = legend_y + 20
    for sev, col in [('Critical', (255, 0, 0)), ('Severe', (255, 165, 0)), ('Moderate', (255, 255, 0))]:
        draw.rectangle([10, y_offset, 22, y_offset + 10], outline=col, width=2)
        draw.text((27, y_offset - 2), sev, fill=col, font=font_small)
        y_offset += 15

    img.save(output_path)
    print(f"      Saved: {output_path.name}")

# Add boxes to images
rgb_after_path = OUTPUT_DIR / "rgb_after_highres.png"
sar_after_path = OUTPUT_DIR / "sar_after_highres.png"

if rgb_after_path.exists():
    add_damage_boxes(
        rgb_after_path,
        OUTPUT_DIR / "rgb_after_with_damage_boxes.png",
        unique_detections,
        BBOX,
        f"Sentinel-2 RGB - {EVENT_DATE} - {len(unique_detections)} Damage Detections"
    )

if sar_after_path.exists():
    add_damage_boxes(
        sar_after_path,
        OUTPUT_DIR / "sar_after_with_damage_boxes.png",
        unique_detections,
        BBOX,
        f"Sentinel-1 SAR - {EVENT_DATE} - {len(unique_detections)} Damage Detections"
    )

# Create paper-style figure
fig, axes = plt.subplots(2, 3, figsize=(18, 12))
fig.suptitle(f'PWTT Damage Detection - Singha Durbar, {EVENT_DATE}\n'
             f'{len(unique_detections)} Damage Detections '
             f'(Critical: {sum(1 for d in unique_detections if d["severity"]=="critical")}, '
             f'Severe: {sum(1 for d in unique_detections if d["severity"]=="severe")}, '
             f'Moderate: {sum(1 for d in unique_detections if d["severity"]=="moderate")})',
             fontsize=13, fontweight='bold')

color_map = {'critical': 'red', 'severe': 'orange', 'moderate': 'yellow', 'minor': 'lime'}

def add_boxes_to_ax(ax, detections, bbox, img_shape):
    for d in detections:
        d_bbox = d['bbox']
        severity = d['severity']
        color = color_map.get(severity, 'yellow')
        is_key = d.get('is_key_building', False)

        x1 = (d_bbox[0] - bbox[0]) / (bbox[2] - bbox[0]) * img_shape[1]
        y1 = (1 - (d_bbox[3] - bbox[1]) / (bbox[3] - bbox[1])) * img_shape[0]
        width = (d_bbox[2] - d_bbox[0]) / (bbox[2] - bbox[0]) * img_shape[1]
        height = (d_bbox[3] - d_bbox[1]) / (bbox[3] - bbox[1]) * img_shape[0]

        lw = 3 if is_key else 1.5
        rect = patches.Rectangle((x1, y1), width, height,
                                  linewidth=lw, edgecolor=color, facecolor='none')
        ax.add_patch(rect)

# RGB Before
ax1 = axes[0, 0]
rgb_before = OUTPUT_DIR / "rgb_before_highres.png"
if rgb_before.exists():
    img = np.array(Image.open(rgb_before))
    ax1.imshow(img)
ax1.set_title(f'Sentinel-2 RGB - BEFORE\n{before_start} to {before_end}\n({s2_before_count} images)', fontsize=10)
ax1.axis('off')

# RGB After
ax2 = axes[0, 1]
if rgb_after_path.exists():
    img = np.array(Image.open(rgb_after_path))
    ax2.imshow(img)
ax2.set_title(f'Sentinel-2 RGB - AFTER\n{after_start} to {after_end}\n({s2_after_count} images)', fontsize=10)
ax2.axis('off')

# RGB with boxes
ax3 = axes[0, 2]
if rgb_after_path.exists():
    img = np.array(Image.open(rgb_after_path))
    ax3.imshow(img)
    add_boxes_to_ax(ax3, unique_detections, BBOX, img.shape)
ax3.set_title(f'RGB + Damage Detection\n{len(unique_detections)} detections', fontsize=10)
ax3.axis('off')

# SAR Before
ax4 = axes[1, 0]
sar_before_path = OUTPUT_DIR / "sar_before_highres.png"
if sar_before_path.exists():
    img = np.array(Image.open(sar_before_path))
    ax4.imshow(img, cmap='gray')
ax4.set_title('Sentinel-1 SAR - BEFORE', fontsize=10)
ax4.axis('off')

# SAR After
ax5 = axes[1, 1]
sar_after_path_orig = OUTPUT_DIR / "sar_after_highres.png"
if sar_after_path_orig.exists():
    img = np.array(Image.open(sar_after_path_orig))
    ax5.imshow(img, cmap='gray')
ax5.set_title('Sentinel-1 SAR - AFTER', fontsize=10)
ax5.axis('off')

# SAR with boxes
ax6 = axes[1, 2]
if sar_after_path_orig.exists():
    img = np.array(Image.open(sar_after_path_orig))
    ax6.imshow(img, cmap='gray')
    add_boxes_to_ax(ax6, unique_detections, BBOX, img.shape)
ax6.set_title('SAR + Damage Detection', fontsize=10)
ax6.axis('off')

# Legend
legend_elements = [
    patches.Patch(facecolor='none', edgecolor='red', linewidth=2,
                  label=f'Critical: {sum(1 for d in unique_detections if d["severity"]=="critical")}'),
    patches.Patch(facecolor='none', edgecolor='orange', linewidth=2,
                  label=f'Severe: {sum(1 for d in unique_detections if d["severity"]=="severe")}'),
    patches.Patch(facecolor='none', edgecolor='yellow', linewidth=2,
                  label=f'Moderate: {sum(1 for d in unique_detections if d["severity"]=="moderate")}'),
]
fig.legend(handles=legend_elements, loc='lower center', ncol=3, fontsize=11,
           bbox_to_anchor=(0.5, 0.02))

plt.tight_layout(rect=[0, 0.06, 1, 0.95])

paper_fig_path = OUTPUT_DIR / "paper_style_damage_detection.png"
plt.savefig(paper_fig_path, dpi=200, bbox_inches='tight', facecolor='white')
print(f"      Saved: {paper_fig_path.name}")

# Save detection data
with open(OUTPUT_DIR / "damaged_buildings_list.json", 'w') as f:
    json.dump({
        'event_date': EVENT_DATE,
        'analysis_bbox': BBOX,
        'total_detections': len(unique_detections),
        'by_severity': {
            'critical': sum(1 for d in unique_detections if d['severity'] == 'critical'),
            'severe': sum(1 for d in unique_detections if d['severity'] == 'severe'),
            'moderate': sum(1 for d in unique_detections if d['severity'] == 'moderate'),
        },
        'key_buildings': [d for d in unique_detections if d.get('is_key_building')],
        'overall_stats': overall_stats,
        'all_detections': unique_detections[:50],
    }, f, indent=2)

# ═══════════════════════════════════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("DAMAGE DETECTION COMPLETE")
print("=" * 70)

print(f"\nKey Building Analysis:")
for kb in key_building_results:
    print(f"  - {kb['name']}: {kb['severity'].upper()} (max t={kb['t_max']:.2f})")

print(f"\nTotal Detections: {len(unique_detections)}")
print(f"  - Critical: {sum(1 for d in unique_detections if d['severity']=='critical')}")
print(f"  - Severe:   {sum(1 for d in unique_detections if d['severity']=='severe')}")
print(f"  - Moderate: {sum(1 for d in unique_detections if d['severity']=='moderate')}")

print(f"\nOverall area statistics:")
print(f"  - Max t-statistic: {overall_stats.get('max_change_max', 0):.2f}")
print(f"  - P95 t-statistic: {overall_stats.get('max_change_p95', 0):.2f}")
print(f"  - P90 t-statistic: {overall_stats.get('max_change_p90', 0):.2f}")

print(f"\nOutput files in: {OUTPUT_DIR}")
print("  - paper_style_damage_detection.png")
print("  - rgb_after_with_damage_boxes.png")
print("  - sar_after_with_damage_boxes.png")
print("  - damage_heatmap.png")
print("  - damaged_buildings_list.json")

import subprocess
subprocess.run(["open", str(OUTPUT_DIR)])
subprocess.run(["open", str(paper_fig_path)])
