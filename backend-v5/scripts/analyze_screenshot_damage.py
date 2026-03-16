#!/usr/bin/env python3
"""
Analyze before/after satellite screenshots to detect damage.

Uses computer vision techniques:
1. Image differencing (absolute pixel difference)
2. Vegetation index changes (green channel analysis)
3. Texture analysis (edge detection changes)
4. Change hotspot detection
"""

import sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

# Paths to screenshots (CORRECTED: green/vegetation image is AFTER the protest)
BEFORE_IMAGE = Path("/Users/samriddhagc/Desktop/Projects/nepal_osint_v5/Screenshot 2026-01-31 at 00.37.20.png")  # Less green = BEFORE
AFTER_IMAGE = Path("/Users/samriddhagc/Desktop/Projects/nepal_osint_v5/Screenshot 2026-01-31 at 00.37.37.png")   # More green = AFTER (with black arson spot)
OUTPUT_DIR = Path("/Users/samriddhagc/Desktop/Projects/nepal_osint_v5/backend-v5/analysis_output")


def load_images():
    """Load and align before/after images."""
    before = Image.open(BEFORE_IMAGE).convert('RGB')
    after = Image.open(AFTER_IMAGE).convert('RGB')

    # Resize to match if needed
    if before.size != after.size:
        # Resize after to match before
        after = after.resize(before.size, Image.Resampling.LANCZOS)

    print(f"Image size: {before.size}")
    return before, after


def compute_difference_map(before: Image.Image, after: Image.Image) -> np.ndarray:
    """Compute absolute difference between images."""
    before_arr = np.array(before, dtype=np.float32)
    after_arr = np.array(after, dtype=np.float32)

    # Absolute difference across all channels
    diff = np.abs(after_arr - before_arr)

    # Mean across color channels
    diff_gray = np.mean(diff, axis=2)

    return diff_gray


def compute_vegetation_change(before: Image.Image, after: Image.Image) -> np.ndarray:
    """Detect vegetation loss (decrease in green relative to red/blue)."""
    before_arr = np.array(before, dtype=np.float32)
    after_arr = np.array(after, dtype=np.float32)

    # Simple vegetation index: (G - R) / (G + R + 1)
    def veg_index(arr):
        r, g, b = arr[:,:,0], arr[:,:,1], arr[:,:,2]
        return (g - r) / (g + r + 1)

    before_veg = veg_index(before_arr)
    after_veg = veg_index(after_arr)

    # Negative values = vegetation loss
    veg_change = before_veg - after_veg

    return veg_change


def compute_texture_change(before: Image.Image, after: Image.Image) -> np.ndarray:
    """Detect texture changes using edge detection."""
    # Convert to grayscale
    before_gray = before.convert('L')
    after_gray = after.convert('L')

    # Apply edge detection
    before_edges = before_gray.filter(ImageFilter.FIND_EDGES)
    after_edges = after_gray.filter(ImageFilter.FIND_EDGES)

    before_arr = np.array(before_edges, dtype=np.float32)
    after_arr = np.array(after_edges, dtype=np.float32)

    # Difference in edge intensity
    edge_diff = np.abs(after_arr - before_arr)

    return edge_diff


def detect_burn_scars(before: Image.Image, after: Image.Image, dark_threshold: int = 60) -> tuple:
    """Detect burn scars / arson damage (dark spots that appear in after image).

    Arson damage typically shows as very dark areas (charred/collapsed roofs).
    We look for pixels that became significantly darker in the after image.
    """
    before_arr = np.array(before.convert('L'), dtype=np.float32)
    after_arr = np.array(after.convert('L'), dtype=np.float32)

    # Find areas that became darker (negative change = darkening)
    darkening = before_arr - after_arr

    # Find areas in AFTER that are very dark (potential burn scars)
    dark_in_after = after_arr < dark_threshold

    # Significant darkening (at least 30 brightness units darker)
    significant_darkening = darkening > 30

    # Burn scar mask: dark in after AND significantly darker than before
    burn_mask = dark_in_after & significant_darkening

    # Also detect isolated dark spots in after (may be new black areas)
    # These are dark in after but weren't dark in before
    new_dark_spots = dark_in_after & (before_arr > dark_threshold + 20)

    # Combined burn detection
    combined_burn = burn_mask | new_dark_spots

    # Find burn scar locations
    burn_locations = []
    h, w = combined_burn.shape
    cell_size = 15

    for y in range(0, h - cell_size, cell_size // 2):
        for x in range(0, w - cell_size, cell_size // 2):
            cell = combined_burn[y:y+cell_size, x:x+cell_size]
            if np.mean(cell) > 0.15:  # 15% of pixels show burn evidence
                after_brightness = np.mean(after_arr[y:y+cell_size, x:x+cell_size])
                before_brightness = np.mean(before_arr[y:y+cell_size, x:x+cell_size])
                darkening_amount = before_brightness - after_brightness

                burn_locations.append({
                    'x': x + cell_size // 2,
                    'y': y + cell_size // 2,
                    'coverage': float(np.mean(cell)),
                    'after_brightness': float(after_brightness),
                    'darkening': float(darkening_amount),
                    'severity': 'ARSON/COLLAPSE' if after_brightness < 40 else 'FIRE_DAMAGE'
                })

    # Sort by darkening amount (most severe first)
    burn_locations.sort(key=lambda x: -x['darkening'])

    return combined_burn, burn_locations[:15]


def detect_damage_hotspots(diff_map: np.ndarray, threshold_percentile: float = 90) -> list:
    """Detect clusters of high-change pixels."""
    threshold = np.percentile(diff_map, threshold_percentile)
    high_change = diff_map > threshold

    # Find connected regions (simple approach - grid cells)
    h, w = diff_map.shape
    cell_size = 20  # pixels

    hotspots = []
    for y in range(0, h - cell_size, cell_size // 2):
        for x in range(0, w - cell_size, cell_size // 2):
            cell = high_change[y:y+cell_size, x:x+cell_size]
            cell_diff = diff_map[y:y+cell_size, x:x+cell_size]

            if np.mean(cell) > 0.3:  # 30% of pixels show high change
                hotspots.append({
                    'x': x + cell_size // 2,
                    'y': y + cell_size // 2,
                    'intensity': float(np.mean(cell_diff)),
                    'coverage': float(np.mean(cell)),
                })

    # Sort by intensity
    hotspots.sort(key=lambda h: h['intensity'], reverse=True)

    return hotspots[:20]  # Top 20 hotspots


def create_visualization(before: Image.Image, after: Image.Image,
                         diff_map: np.ndarray, veg_change: np.ndarray,
                         hotspots: list, burn_locations: list = None,
                         burn_mask: np.ndarray = None) -> Image.Image:
    """Create a visualization showing detected damage including arson/burn scars."""
    w, h = before.size

    # Create output image (2x2 grid + legend)
    output = Image.new('RGB', (w * 2 + 20, h * 2 + 120), color=(30, 30, 30))
    draw = ImageDraw.Draw(output)

    # Top left: Before
    output.paste(before, (0, 0))
    draw.text((10, 10), "BEFORE (Pre-Protest)", fill=(255, 255, 0))

    # Top right: After with BURN SCARS marked
    after_marked = after.copy()
    mark_draw = ImageDraw.Draw(after_marked)

    # Mark burn scars / arson with RED X
    if burn_locations:
        for i, bl in enumerate(burn_locations[:5]):
            x, y = bl['x'], bl['y']
            r = 12
            # Draw red X for arson/fire damage
            mark_draw.line([x-r, y-r, x+r, y+r], fill=(255, 0, 0), width=3)
            mark_draw.line([x-r, y+r, x+r, y-r], fill=(255, 0, 0), width=3)
            mark_draw.ellipse([x-r-2, y-r-2, x+r+2, y+r+2], outline=(255, 0, 0), width=2)
            mark_draw.text((x+r+4, y-8), f"ARSON #{i+1}", fill=(255, 0, 0))

    output.paste(after_marked, (w + 20, 0))
    draw.text((w + 30, 10), "AFTER (Post-Protest) - RED X = ARSON", fill=(255, 255, 0))

    # Bottom left: Burn scar detection map
    if burn_mask is not None:
        burn_viz = np.zeros((h, w, 3), dtype=np.uint8)
        burn_viz[:,:,0] = (burn_mask * 255).astype(np.uint8)  # Red for burns
        # Also show general change in blue
        diff_normalized = (diff_map / diff_map.max() * 128).astype(np.uint8)
        burn_viz[:,:,2] = diff_normalized
        burn_img = Image.fromarray(burn_viz)
    else:
        diff_normalized = (diff_map / diff_map.max() * 255).astype(np.uint8)
        burn_viz = np.zeros((h, w, 3), dtype=np.uint8)
        burn_viz[:,:,0] = diff_normalized
        burn_viz[:,:,1] = (255 - diff_normalized) // 2
        burn_img = Image.fromarray(burn_viz)

    output.paste(burn_img, (0, h + 20))
    draw.text((10, h + 30), "BURN SCARS (Red) + CHANGE (Blue)", fill=(255, 255, 0))

    # Bottom right: After with ALL damage marked
    after_all = after.copy()
    all_draw = ImageDraw.Draw(after_all)

    # Mark general hotspots with orange circles
    for i, hs in enumerate(hotspots[:8]):
        x, y = hs['x'], hs['y']
        r = int(8 + hs['intensity'] / 5)
        color = (255, 165, 0)  # Orange
        all_draw.ellipse([x-r, y-r, x+r, y+r], outline=color, width=2)

    # Mark burn scars with red X (overlay)
    if burn_locations:
        for i, bl in enumerate(burn_locations[:5]):
            x, y = bl['x'], bl['y']
            r = 10
            all_draw.line([x-r, y-r, x+r, y+r], fill=(255, 0, 0), width=3)
            all_draw.line([x-r, y+r, x+r, y-r], fill=(255, 0, 0), width=3)

    output.paste(after_all, (w + 20, h + 20))
    draw.text((w + 30, h + 30), "ALL DAMAGE (Red X=Arson, Orange=Other)", fill=(255, 255, 0))

    # Legend at bottom
    y_legend = h * 2 + 45
    draw.text((10, y_legend), "DAMAGE ANALYSIS RESULTS", fill=(255, 255, 255))

    if burn_locations:
        draw.text((10, y_legend + 18), f"🔥 ARSON/FIRE DAMAGE DETECTED: {len(burn_locations)} sites", fill=(255, 100, 100))
        for i, bl in enumerate(burn_locations[:3]):
            draw.text((10, y_legend + 36 + i*14),
                      f"   #{i+1}: ({bl['x']}, {bl['y']}) - {bl['severity']}",
                      fill=(255, 150, 150))

    draw.text((w + 30, y_legend), f"General hotspots: {len(hotspots)}", fill=(255, 200, 100))
    if hotspots:
        for i, hs in enumerate(hotspots[:3]):
            draw.text((w + 30, y_legend + 18 + i*14),
                      f"   #{i+1}: ({hs['x']}, {hs['y']})",
                      fill=(255, 220, 180))

    return output


def analyze_damage():
    """Main analysis function."""
    print("=" * 60)
    print("SATELLITE SCREENSHOT DAMAGE ANALYSIS")
    print("=" * 60)
    print("(CORRECTED: Green image = AFTER, detecting arson/roof collapse)")

    # Create output directory
    OUTPUT_DIR.mkdir(exist_ok=True)

    # Load images
    print("\n1. Loading images...")
    before, after = load_images()

    # Compute difference maps
    print("2. Computing change detection...")
    diff_map = compute_difference_map(before, after)
    veg_change = compute_vegetation_change(before, after)
    texture_change = compute_texture_change(before, after)

    # BURN SCAR / ARSON DETECTION
    print("3. Detecting burn scars / arson damage...")
    burn_mask, burn_locations = detect_burn_scars(before, after)

    # Combined analysis
    combined = (diff_map / diff_map.max() * 0.5 +
                np.maximum(veg_change, 0) * 0.3 +
                texture_change / texture_change.max() * 0.2)

    # Detect general hotspots
    print("4. Detecting general damage hotspots...")
    hotspots = detect_damage_hotspots(combined, threshold_percentile=85)

    # Print results
    print("\n" + "=" * 60)
    print("ANALYSIS RESULTS")
    print("=" * 60)

    print(f"\nOverall change statistics:")
    print(f"  - Mean pixel difference: {np.mean(diff_map):.2f}")
    print(f"  - Max pixel difference: {np.max(diff_map):.2f}")
    print(f"  - Vegetation change: {np.mean(veg_change) * 100:.2f}%")
    print(f"  - High-change pixels: {np.sum(diff_map > np.percentile(diff_map, 90)) / diff_map.size * 100:.1f}%")

    # BURN SCAR / ARSON RESULTS
    print("\n" + "-" * 60)
    print("🔥 BURN SCAR / ARSON DETECTION")
    print("-" * 60)
    if burn_locations:
        print(f"\n⚠️  DETECTED {len(burn_locations)} POTENTIAL ARSON/FIRE DAMAGE SITES:")
        for i, bl in enumerate(burn_locations[:10]):
            print(f"  #{i+1}: Position ({bl['x']}, {bl['y']}) - {bl['severity']}")
            print(f"       Brightness after: {bl['after_brightness']:.0f} (darker = more damage)")
            print(f"       Darkening amount: {bl['darkening']:.1f}")
    else:
        print("\n  No significant burn scars detected")

    print("\n" + "-" * 60)
    print("GENERAL DAMAGE HOTSPOTS")
    print("-" * 60)
    print(f"\nDetected {len(hotspots)} general damage hotspots:")
    for i, hs in enumerate(hotspots[:10]):
        severity = "CRITICAL" if hs['intensity'] > 40 else "SEVERE" if hs['intensity'] > 25 else "MODERATE"
        print(f"  #{i+1}: Position ({hs['x']}, {hs['y']}) - Intensity: {hs['intensity']:.1f} - {severity}")

    # Create visualization
    print("\n5. Creating visualization...")
    viz = create_visualization(before, after, diff_map, veg_change, hotspots,
                               burn_locations=burn_locations, burn_mask=burn_mask)

    output_path = OUTPUT_DIR / "damage_analysis_result.png"
    viz.save(output_path)
    print(f"\nVisualization saved to: {output_path}")

    # Save individual maps
    diff_img_path = OUTPUT_DIR / "difference_map.png"
    diff_normalized = (diff_map / diff_map.max() * 255).astype(np.uint8)
    Image.fromarray(diff_normalized).save(diff_img_path)

    veg_img_path = OUTPUT_DIR / "vegetation_change.png"
    veg_normalized = ((veg_change + 0.5) * 255).clip(0, 255).astype(np.uint8)
    Image.fromarray(veg_normalized).save(veg_img_path)

    print(f"Difference map saved to: {diff_img_path}")
    print(f"Vegetation change saved to: {veg_img_path}")

    # Summary
    print("\n" + "=" * 60)
    print("DAMAGE SUMMARY")
    print("=" * 60)

    # Arson summary
    arson_count = len([b for b in burn_locations if b['severity'] == 'ARSON/COLLAPSE'])
    fire_count = len([b for b in burn_locations if b['severity'] == 'FIRE_DAMAGE'])

    if arson_count > 0 or fire_count > 0:
        print(f"\n  🔥 ARSON/ROOF COLLAPSE: {arson_count} sites")
        print(f"  🔥 FIRE DAMAGE:         {fire_count} sites")

    critical_count = sum(1 for h in hotspots if h['intensity'] > 40)
    severe_count = sum(1 for h in hotspots if 25 < h['intensity'] <= 40)
    moderate_count = sum(1 for h in hotspots if h['intensity'] <= 25)

    print(f"\n  CRITICAL damage zones: {critical_count}")
    print(f"  SEVERE damage zones:   {severe_count}")
    print(f"  MODERATE damage zones: {moderate_count}")

    total_change = np.mean(diff_map > np.percentile(diff_map, 75)) * 100
    print(f"\n  Total area with significant change: {total_change:.1f}%")

    # Return both
    return {'hotspots': hotspots, 'burn_locations': burn_locations}


if __name__ == "__main__":
    analyze_damage()
