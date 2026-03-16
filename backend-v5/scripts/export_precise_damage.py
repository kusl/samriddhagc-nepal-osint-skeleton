#!/usr/bin/env python3
"""
ULTRA-PRECISE damage detection - finds exact damage peaks with small markers.
- Finds local maxima (peaks) in damage raster
- Creates small, precise markers around each peak
- No large bounding boxes - just precise point locations
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

from PIL import Image, ImageDraw, ImageFont
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np
from scipy import ndimage
from scipy.ndimage import maximum_filter, minimum_filter
import rasterio

OUTPUT_DIR = Path(__file__).parent.parent / "analysis_output"
OUTPUT_DIR.mkdir(exist_ok=True)

# Singha Durbar
BBOX = [85.315, 27.694, 85.331, 27.708]
CENTER = [27.701, 85.323]
EVENT_DATE = "2025-09-08"

print("\n" + "=" * 70)
print("ULTRA-PRECISE DAMAGE DETECTION - SINGHA DURBAR")
print(f"Event Date: {EVENT_DATE}")
print("=" * 70)

geometry = ee.Geometry.Rectangle(BBOX)
event_dt = datetime.fromisoformat(EVENT_DATE)

before_start = (event_dt - timedelta(days=365)).strftime('%Y-%m-%d')
before_end = (event_dt - timedelta(days=1)).strftime('%Y-%m-%d')
after_start = EVENT_DATE
after_end = (event_dt + timedelta(days=90)).strftime('%Y-%m-%d')

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 1: Run PWTT and export raw t-statistic raster
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[1/5] Running PWTT analysis...")

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

print("      Exporting raw t-statistic raster (10m resolution)...")
geemap.ee_export_image(
    max_change,
    filename=str(OUTPUT_DIR / "t_stat_raw.tif"),
    scale=10,
    region=geometry,
)

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 2: Export satellite imagery
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[2/5] Exporting satellite imagery...")

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

rgb_vis = {'bands': ['B4', 'B3', 'B2'], 'min': 0, 'max': 3000}

print("      Exporting RGB...")
geemap.ee_export_image(
    s2_before.visualize(**rgb_vis),
    filename=str(OUTPUT_DIR / "rgb_before_highres.tif"),
    scale=5,
    region=geometry,
)

geemap.ee_export_image(
    s2_after.visualize(**rgb_vis),
    filename=str(OUTPUT_DIR / "rgb_after_highres.tif"),
    scale=5,
    region=geometry,
)

# SAR imagery
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

print("      Exporting SAR...")
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

# Convert to PNG
for tif in OUTPUT_DIR.glob("*_highres.tif"):
    try:
        img = Image.open(tif)
        img.save(tif.with_suffix('.png'))
    except:
        pass

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 3: Find LOCAL MAXIMA (peaks) for precise damage locations
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[3/5] Finding precise damage peaks (local maxima)...")

# Load the raw t-statistic raster
t_stat_path = OUTPUT_DIR / "t_stat_raw.tif"
with rasterio.open(str(t_stat_path)) as src:
    t_stat_array = src.read(1)
    transform = src.transform

# Convert transform to geotransform
gt = (transform.c, transform.a, transform.b, transform.f, transform.d, transform.e)

print(f"      Raster shape: {t_stat_array.shape}")

# Handle NaN and infinite values
t_stat_array = np.nan_to_num(t_stat_array, nan=0, posinf=0, neginf=0)
print(f"      T-stat range: {np.min(t_stat_array):.2f} to {np.max(t_stat_array):.2f}")

# Find LOCAL MAXIMA using morphological approach
# A pixel is a local maximum if it equals the maximum in its neighborhood
NEIGHBORHOOD_SIZE = 5  # 5x5 window = 50m x 50m at 10m resolution

# Apply local maximum filter
local_max = maximum_filter(t_stat_array, size=NEIGHBORHOOD_SIZE)

# Find peaks: pixels where value equals local maximum AND exceeds threshold
PEAK_THRESHOLD = 4.0  # Only peaks with t >= 4.0

peaks_mask = (t_stat_array == local_max) & (t_stat_array >= PEAK_THRESHOLD)
peak_locations = np.where(peaks_mask)

print(f"      Found {len(peak_locations[0])} raw peaks (t >= {PEAK_THRESHOLD})")

def pixel_to_geo(row, col, gt):
    """Convert pixel coordinates to geographic coordinates."""
    lng = gt[0] + col * gt[1] + row * gt[2]
    lat = gt[3] + col * gt[4] + row * gt[5]
    return lng, lat

# Extract peak information
peaks = []
for row, col in zip(peak_locations[0], peak_locations[1]):
    t_val = float(t_stat_array[row, col])
    lng, lat = pixel_to_geo(row, col, gt)

    # Classify severity
    if t_val >= 6.0:
        severity = 'critical'
    elif t_val >= 5.0:
        severity = 'severe'
    else:
        severity = 'moderate'

    peaks.append({
        'lng': lng,
        'lat': lat,
        't_stat': t_val,
        'severity': severity,
        'row': int(row),
        'col': int(col),
    })

# Sort by t-stat (highest first)
peaks.sort(key=lambda x: x['t_stat'], reverse=True)

# Remove peaks that are too close together (within 30m)
MIN_DISTANCE_DEG = 0.0003  # ~30m

unique_peaks = []
for p in peaks:
    is_duplicate = False
    for existing in unique_peaks:
        dist = np.sqrt((p['lng'] - existing['lng'])**2 + (p['lat'] - existing['lat'])**2)
        if dist < MIN_DISTANCE_DEG:
            is_duplicate = True
            break
    if not is_duplicate:
        unique_peaks.append(p)

# Limit to top peaks for cleaner visualization
MAX_PEAKS = 60
unique_peaks = unique_peaks[:MAX_PEAKS]

print(f"      Unique peaks after filtering: {len(unique_peaks)}")

# Count by severity
critical_count = sum(1 for p in unique_peaks if p['severity'] == 'critical')
severe_count = sum(1 for p in unique_peaks if p['severity'] == 'severe')
moderate_count = sum(1 for p in unique_peaks if p['severity'] == 'moderate')

print(f"        - Critical (t≥6.0): {critical_count}")
print(f"        - Severe (t≥5.0): {severe_count}")
print(f"        - Moderate (t≥4.0): {moderate_count}")

print("\n      Top 15 damage peaks:")
for i, p in enumerate(unique_peaks[:15]):
    print(f"        {i+1}. [{p['lng']:.5f}, {p['lat']:.5f}] t={p['t_stat']:.2f} ({p['severity']})")

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 4: Create visualization with SMALL PRECISE MARKERS
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[4/5] Creating precise damage visualization...")

def add_peak_markers(img_path, output_path, peaks, bbox, title):
    """Add small circular markers at damage peak locations."""
    img = Image.open(img_path).convert('RGBA')
    draw = ImageDraw.Draw(img)

    img_width, img_height = img.size

    def geo_to_pixel(lng, lat):
        x = (lng - bbox[0]) / (bbox[2] - bbox[0]) * img_width
        y = (1 - (lat - bbox[1]) / (bbox[3] - bbox[1])) * img_height
        return int(x), int(y)

    colors = {
        'critical': (255, 0, 0),
        'severe': (255, 140, 0),
        'moderate': (255, 255, 0),
    }

    # Draw markers - small circles/crosshairs for precision
    for p in peaks:
        x, y = geo_to_pixel(p['lng'], p['lat'])
        severity = p['severity']
        color = colors.get(severity, (255, 255, 0))
        t_val = p['t_stat']

        # Size based on t-stat magnitude (larger = more damage)
        base_radius = 4
        if t_val >= 10:
            radius = base_radius + 4
        elif t_val >= 7:
            radius = base_radius + 2
        else:
            radius = base_radius

        # Draw circle outline
        for r in range(radius - 1, radius + 2):
            draw.ellipse([x - r, y - r, x + r, y + r], outline=color)

        # Draw crosshair for critical peaks
        if severity == 'critical':
            line_len = radius + 3
            draw.line([x - line_len, y, x + line_len, y], fill=color, width=1)
            draw.line([x, y - line_len, x, y + line_len], fill=color, width=1)

    # Add title
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 13)
        font_small = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 10)
    except:
        font = ImageFont.load_default()
        font_small = font

    draw.rectangle([0, 0, img_width, 18], fill=(0, 0, 0, 230))
    draw.text((6, 2), title, fill=(255, 255, 255), font=font)

    # Add compact legend
    legend_y = img_height - 50
    draw.rectangle([4, legend_y, 95, img_height - 4], fill=(0, 0, 0, 210))

    y_offset = legend_y + 4
    for sev, col in [('Critical', (255, 0, 0)), ('Severe', (255, 140, 0)), ('Moderate', (255, 255, 0))]:
        count = sum(1 for p in peaks if p['severity'] == sev.lower())
        if count > 0:
            # Draw small circle as legend marker
            draw.ellipse([8, y_offset + 1, 16, y_offset + 9], outline=col)
            draw.text((20, y_offset - 1), f"{sev}: {count}", fill=col, font=font_small)
            y_offset += 12

    img.save(output_path)
    print(f"      Saved: {output_path.name}")

# Add markers to RGB and SAR images
rgb_after_path = OUTPUT_DIR / "rgb_after_highres.png"
sar_after_path = OUTPUT_DIR / "sar_after_highres.png"

if rgb_after_path.exists():
    add_peak_markers(
        rgb_after_path,
        OUTPUT_DIR / "rgb_precise_damage.png",
        unique_peaks,
        BBOX,
        f"Precise Damage Peaks - {EVENT_DATE} - {len(unique_peaks)} hotspots"
    )

if sar_after_path.exists():
    add_peak_markers(
        sar_after_path,
        OUTPUT_DIR / "sar_precise_damage.png",
        unique_peaks,
        BBOX,
        f"SAR Damage Peaks - {EVENT_DATE} - {len(unique_peaks)} hotspots"
    )

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 5: Create paper-style comparison figure
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[5/5] Creating paper-style figure with heatmap overlay...")

fig, axes = plt.subplots(2, 3, figsize=(18, 12))
fig.suptitle(f'PWTT Damage Detection - Singha Durbar, {EVENT_DATE}\n'
             f'{len(unique_peaks)} Precise Damage Hotspots (Local Maxima)',
             fontsize=14, fontweight='bold')

color_map = {'critical': 'red', 'severe': 'orange', 'moderate': 'yellow'}
marker_map = {'critical': 'X', 'severe': 'o', 'moderate': 's'}

def add_markers_to_ax(ax, peaks, bbox, img_shape):
    """Add markers to matplotlib axis."""
    for p in peaks:
        x = (p['lng'] - bbox[0]) / (bbox[2] - bbox[0]) * img_shape[1]
        y = (1 - (p['lat'] - bbox[1]) / (bbox[3] - bbox[1])) * img_shape[0]

        severity = p['severity']
        color = color_map.get(severity, 'yellow')
        marker = marker_map.get(severity, 'o')

        # Size based on t-stat
        size = 30 + (p['t_stat'] - 4) * 8

        ax.scatter(x, y, c=color, s=size, marker=marker, edgecolors='white',
                   linewidths=0.5, alpha=0.9)

# Row 1: RGB imagery
rgb_before = OUTPUT_DIR / "rgb_before_highres.png"
rgb_after = OUTPUT_DIR / "rgb_after_highres.png"

ax1 = axes[0, 0]
if rgb_before.exists():
    img = np.array(Image.open(rgb_before))
    ax1.imshow(img)
ax1.set_title('Sentinel-2 RGB - BEFORE', fontsize=11)
ax1.axis('off')

ax2 = axes[0, 1]
if rgb_after.exists():
    img = np.array(Image.open(rgb_after))
    ax2.imshow(img)
ax2.set_title('Sentinel-2 RGB - AFTER', fontsize=11)
ax2.axis('off')

ax3 = axes[0, 2]
if rgb_after.exists():
    img = np.array(Image.open(rgb_after))
    ax3.imshow(img)
    add_markers_to_ax(ax3, unique_peaks, BBOX, img.shape)
ax3.set_title(f'RGB + Damage Peaks\n({len(unique_peaks)} hotspots)', fontsize=11)
ax3.axis('off')

# Row 2: SAR + Heatmap
sar_before = OUTPUT_DIR / "sar_before_highres.png"
sar_after = OUTPUT_DIR / "sar_after_highres.png"

ax4 = axes[1, 0]
if sar_before.exists():
    img = np.array(Image.open(sar_before))
    ax4.imshow(img, cmap='gray')
ax4.set_title('Sentinel-1 SAR - BEFORE', fontsize=11)
ax4.axis('off')

ax5 = axes[1, 1]
if sar_after.exists():
    img = np.array(Image.open(sar_after))
    ax5.imshow(img, cmap='gray')
ax5.set_title('Sentinel-1 SAR - AFTER', fontsize=11)
ax5.axis('off')

# Damage heatmap with markers
ax6 = axes[1, 2]
from matplotlib.colors import LinearSegmentedColormap
damage_cmap = LinearSegmentedColormap.from_list('damage',
    ['#1a1a2e', '#16213e', '#0f3460', '#e94560', '#ff0000'], N=256)

t_stat_display = np.ma.masked_where(t_stat_array < 2.5, t_stat_array)
im = ax6.imshow(t_stat_display, cmap=damage_cmap, vmin=2.5, vmax=12)

# Add peak markers on heatmap
for p in unique_peaks:
    color = color_map.get(p['severity'], 'white')
    ax6.plot(p['col'], p['row'], 'o', markersize=4, markerfacecolor='none',
             markeredgecolor='white', markeredgewidth=1)

ax6.set_title('T-Statistic Heatmap + Peaks', fontsize=11)
ax6.axis('off')

cbar = fig.colorbar(im, ax=ax6, fraction=0.046, pad=0.04)
cbar.set_label('T-statistic', fontsize=10)

# Legend
legend_elements = [
    plt.scatter([], [], c='red', s=60, marker='X', label=f'Critical (t≥6): {critical_count}'),
    plt.scatter([], [], c='orange', s=50, marker='o', label=f'Severe (t≥5): {severe_count}'),
    plt.scatter([], [], c='yellow', s=40, marker='s', label=f'Moderate (t≥4): {moderate_count}'),
]
fig.legend(handles=legend_elements, loc='lower center', ncol=3, fontsize=11,
           bbox_to_anchor=(0.5, 0.02))

plt.tight_layout(rect=[0, 0.06, 1, 0.95])

paper_fig_path = OUTPUT_DIR / "paper_style_damage_detection.png"
plt.savefig(paper_fig_path, dpi=200, bbox_inches='tight', facecolor='white')
print(f"      Saved: {paper_fig_path.name}")

# Save hotspot data
with open(OUTPUT_DIR / "precise_damage_hotspots.json", 'w') as f:
    json.dump({
        'event_date': EVENT_DATE,
        'bbox': BBOX,
        'peak_threshold': PEAK_THRESHOLD,
        'total_peaks': len(unique_peaks),
        'by_severity': {
            'critical': critical_count,
            'severe': severe_count,
            'moderate': moderate_count,
        },
        'peaks': [
            {
                'lng': p['lng'],
                'lat': p['lat'],
                't_stat': p['t_stat'],
                'severity': p['severity'],
            }
            for p in unique_peaks
        ],
    }, f, indent=2)

# ═══════════════════════════════════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("PRECISE DAMAGE DETECTION COMPLETE")
print("=" * 70)

print(f"\nDetected {len(unique_peaks)} precise damage peaks:")
print(f"  - Critical (t≥6.0): {critical_count}")
print(f"  - Severe (t≥5.0): {severe_count}")
print(f"  - Moderate (t≥4.0): {moderate_count}")

print(f"\nTop 10 most severe damage locations:")
for i, p in enumerate(unique_peaks[:10]):
    print(f"  {i+1}. [{p['lng']:.5f}, {p['lat']:.5f}] T-stat: {p['t_stat']:.2f}")

# Check if main Singha Durbar building area has peaks
SINGHA_DURBAR_CENTER = (85.3215, 27.7005)
nearby_peaks = [p for p in unique_peaks
                if abs(p['lng'] - SINGHA_DURBAR_CENTER[0]) < 0.003
                and abs(p['lat'] - SINGHA_DURBAR_CENTER[1]) < 0.003]

if nearby_peaks:
    print(f"\nDamage peaks near main Singha Durbar building ({len(nearby_peaks)}):")
    for p in nearby_peaks[:5]:
        print(f"  - [{p['lng']:.5f}, {p['lat']:.5f}] T-stat: {p['t_stat']:.2f}")

print(f"\nOutput files:")
print("  - paper_style_damage_detection.png")
print("  - rgb_precise_damage.png")
print("  - sar_precise_damage.png")
print("  - precise_damage_hotspots.json")

import subprocess
subprocess.run(["open", str(OUTPUT_DIR)])
subprocess.run(["open", str(paper_fig_path)])
subprocess.run(["open", str(OUTPUT_DIR / "rgb_precise_damage.png")])
