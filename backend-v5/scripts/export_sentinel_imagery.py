#!/usr/bin/env python3
"""
Export clean Sentinel-1 SAR and Sentinel-2 RGB imagery for Singha Durbar.
Before and after the September 8, 2025 event.

No heatmaps - just the raw satellite imagery for visual comparison.
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

import ee
import geemap

print("Initializing Google Earth Engine...")
ee.Initialize()
print("GEE initialized!")

try:
    from PIL import Image
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pillow", "matplotlib"])
    from PIL import Image
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches

OUTPUT_DIR = Path(__file__).parent.parent / "analysis_output"
OUTPUT_DIR.mkdir(exist_ok=True)

# Singha Durbar - slightly larger area for better context
BBOX = [85.315, 27.694, 85.331, 27.708]  # Expanded slightly
CENTER = [27.701, 85.323]
EVENT_DATE = "2025-09-08"

print("\n" + "=" * 60)
print("SENTINEL IMAGERY EXPORT - SINGHA DURBAR")
print(f"Event Date: {EVENT_DATE}")
print("=" * 60)

# Create geometry
geometry = ee.Geometry.Rectangle(BBOX)

# Parse dates
event_dt = datetime.fromisoformat(EVENT_DATE)
before_start = (event_dt - timedelta(days=90)).strftime('%Y-%m-%d')
before_end = (event_dt - timedelta(days=1)).strftime('%Y-%m-%d')
after_start = EVENT_DATE
after_end = (event_dt + timedelta(days=60)).strftime('%Y-%m-%d')

print(f"\nBefore period: {before_start} to {before_end}")
print(f"After period:  {after_start} to {after_end}")

# ═══════════════════════════════════════════════════════════════════════════════
# SENTINEL-1 SAR IMAGERY
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[1/4] Fetching Sentinel-1 SAR imagery...")

s1 = (
    ee.ImageCollection("COPERNICUS/S1_GRD")
    .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
    .filter(ee.Filter.eq("instrumentMode", "IW"))
    .filterBounds(geometry)
)

# Before event - median composite
s1_before = s1.filterDate(before_start, before_end).select('VV').median().clip(geometry)
before_count = s1.filterDate(before_start, before_end).size().getInfo()
print(f"      Before: {before_count} images")

# After event - median composite
s1_after = s1.filterDate(after_start, after_end).select('VV').median().clip(geometry)
after_count = s1.filterDate(after_start, after_end).size().getInfo()
print(f"      After:  {after_count} images")

# SAR visualization - grayscale
sar_vis = {'min': -25, 'max': 0, 'palette': ['000000', 'ffffff']}

print("\n[2/4] Exporting SAR images...")

# Export before SAR
print("      Exporting SAR before...")
s1_before_rgb = s1_before.visualize(**sar_vis)
geemap.ee_export_image(
    s1_before_rgb,
    filename=str(OUTPUT_DIR / "sentinel1_sar_before.tif"),
    scale=10,
    region=geometry,
)

# Export after SAR
print("      Exporting SAR after...")
s1_after_rgb = s1_after.visualize(**sar_vis)
geemap.ee_export_image(
    s1_after_rgb,
    filename=str(OUTPUT_DIR / "sentinel1_sar_after.tif"),
    scale=10,
    region=geometry,
)

# ═══════════════════════════════════════════════════════════════════════════════
# SENTINEL-2 RGB IMAGERY
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[3/4] Fetching Sentinel-2 RGB imagery...")

def mask_clouds(image):
    qa = image.select('QA60')
    cloud_bit_mask = 1 << 10
    cirrus_bit_mask = 1 << 11
    mask = qa.bitwiseAnd(cloud_bit_mask).eq(0).And(qa.bitwiseAnd(cirrus_bit_mask).eq(0))
    return image.updateMask(mask)

s2 = (
    ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
    .filterBounds(geometry)
    .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 30))
    .map(mask_clouds)
)

# Before RGB
s2_before = s2.filterDate(before_start, before_end).median().clip(geometry)
s2_before_count = s2.filterDate(before_start, before_end).size().getInfo()
print(f"      Before: {s2_before_count} images")

# After RGB
s2_after = s2.filterDate(after_start, after_end).median().clip(geometry)
s2_after_count = s2.filterDate(after_start, after_end).size().getInfo()
print(f"      After:  {s2_after_count} images")

# RGB visualization (true color)
rgb_vis = {'bands': ['B4', 'B3', 'B2'], 'min': 0, 'max': 3000}

print("\n      Exporting RGB images...")

# Export before RGB
print("      Exporting RGB before...")
s2_before_rgb = s2_before.visualize(**rgb_vis)
geemap.ee_export_image(
    s2_before_rgb,
    filename=str(OUTPUT_DIR / "sentinel2_rgb_before.tif"),
    scale=10,
    region=geometry,
)

# Export after RGB
print("      Exporting RGB after...")
s2_after_rgb = s2_after.visualize(**rgb_vis)
geemap.ee_export_image(
    s2_after_rgb,
    filename=str(OUTPUT_DIR / "sentinel2_rgb_after.tif"),
    scale=10,
    region=geometry,
)

# ═══════════════════════════════════════════════════════════════════════════════
# CREATE COMPARISON VISUALIZATIONS
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[4/4] Creating comparison visualizations...")

# Convert TIFFs to PNGs
for tif in OUTPUT_DIR.glob("sentinel*.tif"):
    try:
        img = Image.open(tif)
        img.save(tif.with_suffix('.png'))
        print(f"      Converted: {tif.stem}.png")
    except Exception as e:
        print(f"      Failed: {tif.name} - {e}")

# Create side-by-side comparison figure
fig, axes = plt.subplots(2, 2, figsize=(16, 14))
fig.suptitle(f'Sentinel Imagery - Singha Durbar\nBefore vs After September 8, 2025',
             fontsize=16, fontweight='bold')

# SAR Before
ax1 = axes[0, 0]
sar_before_path = OUTPUT_DIR / "sentinel1_sar_before.png"
if sar_before_path.exists():
    img = Image.open(sar_before_path)
    ax1.imshow(img, cmap='gray')
ax1.set_title(f'Sentinel-1 SAR - BEFORE\n({before_start} to {before_end})\n{before_count} images', fontsize=12)
ax1.axis('off')

# SAR After
ax2 = axes[0, 1]
sar_after_path = OUTPUT_DIR / "sentinel1_sar_after.png"
if sar_after_path.exists():
    img = Image.open(sar_after_path)
    ax2.imshow(img, cmap='gray')
ax2.set_title(f'Sentinel-1 SAR - AFTER\n({after_start} to {after_end})\n{after_count} images', fontsize=12)
ax2.axis('off')

# RGB Before
ax3 = axes[1, 0]
rgb_before_path = OUTPUT_DIR / "sentinel2_rgb_before.png"
if rgb_before_path.exists():
    img = Image.open(rgb_before_path)
    ax3.imshow(img)
ax3.set_title(f'Sentinel-2 RGB - BEFORE\n({before_start} to {before_end})\n{s2_before_count} images', fontsize=12)
ax3.axis('off')

# RGB After
ax4 = axes[1, 1]
rgb_after_path = OUTPUT_DIR / "sentinel2_rgb_after.png"
if rgb_after_path.exists():
    img = Image.open(rgb_after_path)
    ax4.imshow(img)
ax4.set_title(f'Sentinel-2 RGB - AFTER\n({after_start} to {after_end})\n{s2_after_count} images', fontsize=12)
ax4.axis('off')

# Add annotations
fig.text(0.5, 0.02,
         'SAR (top): Radar backscatter - changes indicate structural changes\n'
         'RGB (bottom): True color optical imagery',
         ha='center', fontsize=10, style='italic')

plt.tight_layout(rect=[0, 0.05, 1, 0.96])

comparison_path = OUTPUT_DIR / "sentinel_before_after_comparison.png"
plt.savefig(comparison_path, dpi=150, bbox_inches='tight', facecolor='white')
print(f"\n      Saved: {comparison_path.name}")

# Create a simple HTML viewer (no Jupyter widgets)
html_content = f'''<!DOCTYPE html>
<html>
<head>
    <title>Sentinel Imagery - Singha Durbar</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; background: #1a1a2e; color: white; }}
        h1 {{ text-align: center; }}
        .container {{ display: flex; flex-wrap: wrap; justify-content: center; gap: 20px; }}
        .image-box {{ background: #16213e; padding: 15px; border-radius: 10px; text-align: center; }}
        .image-box img {{ max-width: 400px; border-radius: 5px; }}
        .image-box h3 {{ margin: 10px 0 5px 0; }}
        .image-box p {{ margin: 5px 0; color: #aaa; font-size: 12px; }}
        #map {{ height: 500px; width: 100%; margin: 20px 0; border-radius: 10px; }}
        .legend {{ background: white; padding: 10px; border-radius: 5px; color: black; }}
    </style>
</head>
<body>
    <h1>Sentinel Imagery - Singha Durbar</h1>
    <h2 style="text-align:center; color:#888;">Event Date: {EVENT_DATE}</h2>

    <div class="container">
        <div class="image-box">
            <h3>SAR Before</h3>
            <img src="sentinel1_sar_before.png" alt="SAR Before">
            <p>{before_start} to {before_end} ({before_count} images)</p>
        </div>
        <div class="image-box">
            <h3>SAR After</h3>
            <img src="sentinel1_sar_after.png" alt="SAR After">
            <p>{after_start} to {after_end} ({after_count} images)</p>
        </div>
    </div>

    <div class="container">
        <div class="image-box">
            <h3>RGB Before</h3>
            <img src="sentinel2_rgb_before.png" alt="RGB Before">
            <p>{before_start} to {before_end} ({s2_before_count} images)</p>
        </div>
        <div class="image-box">
            <h3>RGB After</h3>
            <img src="sentinel2_rgb_after.png" alt="RGB After">
            <p>{after_start} to {after_end} ({s2_after_count} images)</p>
        </div>
    </div>

    <h2 style="text-align:center; margin-top:30px;">Interactive Map</h2>
    <div id="map"></div>

    <script>
        var map = L.map('map').setView([{CENTER[0]}, {CENTER[1]}], 16);

        // Base layers
        var satellite = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
            attribution: 'Esri World Imagery'
        }}).addTo(map);

        var osm = L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
            attribution: 'OpenStreetMap'
        }});

        // Singha Durbar boundary
        var bounds = L.rectangle([[{BBOX[1]}, {BBOX[0]}], [{BBOX[3]}, {BBOX[2]}]], {{
            color: 'cyan',
            weight: 3,
            fill: false
        }}).addTo(map);

        // Layer control
        var baseMaps = {{
            "Satellite": satellite,
            "OpenStreetMap": osm
        }};
        L.control.layers(baseMaps).addTo(map);

        // Info box
        var info = L.control({{position: 'bottomleft'}});
        info.onAdd = function(map) {{
            var div = L.DomUtil.create('div', 'legend');
            div.innerHTML = '<b>Singha Durbar</b><br>Lat: {CENTER[0]:.4f}<br>Lng: {CENTER[1]:.4f}';
            return div;
        }};
        info.addTo(map);
    </script>
</body>
</html>
'''

html_path = OUTPUT_DIR / "sentinel_imagery_viewer.html"
with open(html_path, 'w') as f:
    f.write(html_content)
print(f"      Saved: {html_path.name}")

# ═══════════════════════════════════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("EXPORT COMPLETE")
print("=" * 60)
print(f"\nOutput files in: {OUTPUT_DIR}")
print("\nSentinel-1 SAR (Radar):")
print("  - sentinel1_sar_before.png")
print("  - sentinel1_sar_after.png")
print("\nSentinel-2 RGB (Optical):")
print("  - sentinel2_rgb_before.png")
print("  - sentinel2_rgb_after.png")
print("\nComparison:")
print("  - sentinel_before_after_comparison.png")
print("  - sentinel_imagery_viewer.html (simple HTML viewer)")

# Open folder
import subprocess
subprocess.run(["open", str(OUTPUT_DIR)])
subprocess.run(["open", str(html_path)])
