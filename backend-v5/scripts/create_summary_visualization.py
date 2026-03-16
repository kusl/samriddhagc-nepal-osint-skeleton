#!/usr/bin/env python3
"""
Create summary visualization of PWTT damage assessment results.
Converts TIFF files to PNG and creates a combined visualization.
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
import numpy as np

# Initialize GEE
ee.Initialize()

import pwtt as pwtt_lib

try:
    from PIL import Image
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
except ImportError:
    print("Installing required packages...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pillow", "matplotlib"])
    from PIL import Image
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches

# Output directory
OUTPUT_DIR = Path(__file__).parent.parent / "analysis_output"

# Singha Durbar
BBOX = [85.318, 27.697, 85.328, 27.705]
EVENT_DATE = "2025-09-08"

print("=" * 60)
print("PWTT DAMAGE ASSESSMENT SUMMARY")
print("Singha Durbar - September 8, 2025")
print("=" * 60)

# Load analysis results
results_path = OUTPUT_DIR / "analysis_results.json"
if results_path.exists():
    with open(results_path) as f:
        results = json.load(f)
    print(f"\nDamage Summary:")
    print(f"  Total Area: {results['total_area_km2']:.4f} km²")
    print(f"  Damaged Area: {results['damaged_area_km2']:.4f} km² ({results['damage_percentage']:.2f}%)")
    print(f"\nSeverity Breakdown:")
    sev = results['severity_breakdown']
    print(f"  Critical (t≥4.0): {sev['critical_km2']*1000:.2f} m²")
    print(f"  Severe (t≥3.5):   {sev['severe_km2']*1000:.2f} m²")
    print(f"  Moderate (t≥3.0): {sev['moderate_km2']*1000:.2f} m²")
    print(f"  Minor (t≥2.5):    {sev['minor_km2']*1000:.2f} m²")

# Convert TIFFs to PNGs
print("\nConverting images...")

def tiff_to_png(tiff_path, png_path):
    """Convert TIFF to PNG."""
    try:
        img = Image.open(tiff_path)
        img.save(png_path)
        print(f"  Converted: {png_path.name}")
        return True
    except Exception as e:
        print(f"  Failed to convert {tiff_path.name}: {e}")
        return False

tiff_files = list(OUTPUT_DIR.glob("*.tif"))
for tiff_file in tiff_files:
    png_file = tiff_file.with_suffix('.png')
    tiff_to_png(tiff_file, png_file)

# Create combined visualization
print("\nCreating summary visualization...")

fig, axes = plt.subplots(2, 2, figsize=(14, 12))
fig.suptitle(f'PWTT Damage Assessment - Singha Durbar\nEvent Date: {EVENT_DATE}', fontsize=16, fontweight='bold')

# T-statistic
ax1 = axes[0, 0]
t_stat_path = OUTPUT_DIR / "t_statistic_highres.png"
if t_stat_path.exists():
    img = Image.open(t_stat_path)
    ax1.imshow(img)
ax1.set_title('T-Statistic (PWTT)\nt > 3 = Significant Damage', fontsize=12)
ax1.axis('off')

# Add colorbar legend for t-stat
from matplotlib.colors import LinearSegmentedColormap
cmap_t = LinearSegmentedColormap.from_list('pwtt', ['yellow', 'orange', 'red', 'purple'])
sm = plt.cm.ScalarMappable(cmap=cmap_t, norm=plt.Normalize(vmin=3, vmax=5))
plt.colorbar(sm, ax=ax1, label='T-statistic', fraction=0.046, pad=0.04)

# Damage probability
ax2 = axes[0, 1]
damage_path = OUTPUT_DIR / "damage_probability_highres.png"
if damage_path.exists():
    img = Image.open(damage_path)
    ax2.imshow(img)
ax2.set_title('Damage Probability\n0 = No Damage, 1 = Critical', fontsize=12)
ax2.axis('off')

# Add colorbar for damage
cmap_d = LinearSegmentedColormap.from_list('damage', ['green', 'yellow', 'orange', 'red', 'darkred'])
sm2 = plt.cm.ScalarMappable(cmap=cmap_d, norm=plt.Normalize(vmin=0, vmax=1))
plt.colorbar(sm2, ax=ax2, label='Damage Probability', fraction=0.046, pad=0.04)

# SAR Before
ax3 = axes[1, 0]
before_path = OUTPUT_DIR / "sar_before_highres.png"
if before_path.exists():
    img = Image.open(before_path)
    ax3.imshow(img, cmap='gray')
ax3.set_title(f'SAR Before Event\n(Baseline: 12 months)', fontsize=12)
ax3.axis('off')

# SAR After
ax4 = axes[1, 1]
after_path = OUTPUT_DIR / "sar_after_highres.png"
if after_path.exists():
    img = Image.open(after_path)
    ax4.imshow(img, cmap='gray')
ax4.set_title(f'SAR After Event\n(Post-event: 2 months)', fontsize=12)
ax4.axis('off')

# Add results text box
if results_path.exists():
    textstr = f"""Analysis Results:
• Total Area: {results['total_area_km2']:.4f} km²
• Damaged: {results['damaged_area_km2']:.4f} km² ({results['damage_percentage']:.1f}%)
• Critical: {sev['critical_km2']*1000:.0f} m²
• Severe: {sev['severe_km2']*1000:.0f} m²
• Moderate: {sev['moderate_km2']*1000:.0f} m²
• Algorithm: oballinger/PWTT"""

    props = dict(boxstyle='round', facecolor='wheat', alpha=0.8)
    fig.text(0.02, 0.02, textstr, fontsize=10, verticalalignment='bottom',
             fontfamily='monospace', bbox=props)

plt.tight_layout(rect=[0, 0.08, 1, 0.96])

# Save
summary_path = OUTPUT_DIR / "pwtt_summary_singha_durbar.png"
plt.savefig(summary_path, dpi=150, bbox_inches='tight', facecolor='white')
print(f"\nSaved summary: {summary_path}")

# Open the folder
print(f"\nAll outputs saved to: {OUTPUT_DIR}")
print("\nFiles created:")
for f in sorted(OUTPUT_DIR.iterdir()):
    if f.is_file():
        size = f.stat().st_size / 1024
        print(f"  {f.name}: {size:.1f} KB")

print("\n" + "=" * 60)
print("DONE - Opening output folder...")
print("=" * 60)

import subprocess
subprocess.run(["open", str(OUTPUT_DIR)])
