#!/usr/bin/env python3
"""
Clean PWTT visualization script - produces the clean 3-panel format:
Pre Destruction | Post Destruction | PWTT heatmap
"""

import ee
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patheffects as path_effects
from matplotlib.patches import Rectangle
from matplotlib.colors import LinearSegmentedColormap
import requests
from PIL import Image
from io import BytesIO
import json
import os
import sys

# Add parent directory to path for pwtt_lib
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pwtt_lib.code.pwtt import filter_s1

# Initialize Earth Engine
ee.Initialize()

def get_ee_image_as_array(image, bbox, scale=10):
    """Download EE image as numpy array"""
    region = ee.Geometry.Rectangle(bbox)
    url = image.getThumbURL({
        'region': region,
        'dimensions': 512,
        'format': 'png'
    })
    response = requests.get(url)
    img = Image.open(BytesIO(response.content))
    return np.array(img)

def get_rgb_image(bbox, start_date, end_date):
    """Get Sentinel-2 RGB composite"""
    region = ee.Geometry.Rectangle(bbox)

    s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED') \
        .filterBounds(region) \
        .filterDate(start_date, end_date) \
        .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20)) \
        .median()

    rgb = s2.select(['B4', 'B3', 'B2']).divide(3000).clamp(0, 1)
    return rgb

def get_building_footprints(bbox):
    """Get building footprints from Google Open Buildings"""
    region = ee.Geometry.Rectangle(bbox)

    # Try Google Open Buildings
    try:
        buildings = ee.FeatureCollection('GOOGLE/Research/open-buildings/v3/polygons') \
            .filterBounds(region)

        count = buildings.size().getInfo()
        if count > 0:
            return buildings
    except:
        pass

    # Try OSM buildings
    try:
        osm = ee.FeatureCollection('projects/sat-io/open-datasets/OSM/OSM_buildings') \
            .filterBounds(region)
        return osm
    except:
        pass

    return None

def run_clean_pwtt_analysis(
    location_name,
    bbox,
    event_date,
    before_days=365,
    after_days=30,
    output_dir='analysis_output'
):
    """
    Run PWTT analysis and create clean 3-panel visualization

    Args:
        location_name: Name of the location
        bbox: [west, south, east, north]
        event_date: Date of the event (YYYY-MM-DD)
        before_days: Days before event for baseline
        after_days: Days after event for comparison
        output_dir: Output directory
    """

    from datetime import datetime, timedelta

    event_dt = datetime.strptime(event_date, '%Y-%m-%d')
    before_start = (event_dt - timedelta(days=before_days)).strftime('%Y-%m-%d')
    before_end = (event_dt - timedelta(days=1)).strftime('%Y-%m-%d')
    after_start = event_date
    after_end = (event_dt + timedelta(days=after_days)).strftime('%Y-%m-%d')

    print(f"Analyzing: {location_name}")
    print(f"Before period: {before_start} to {before_end}")
    print(f"After period: {after_start} to {after_end}")

    region = ee.Geometry.Rectangle(bbox)

    # Run PWTT
    print("Running PWTT analysis...")
    # filter_s1 params: aoi, inference_start, war_start, pre_interval (months), post_interval (months)
    pre_months = before_days // 30
    post_months = max(1, after_days // 30)

    pwtt_result = filter_s1(
        aoi=region,
        inference_start=event_date,
        war_start=event_date,
        pre_interval=pre_months,
        post_interval=post_months
    )

    t_stat = pwtt_result.select('T_statistic')

    # Get RGB images
    print("Fetching RGB imagery...")
    rgb_before = get_rgb_image(bbox, before_start, before_end)
    rgb_after = get_rgb_image(bbox, after_start, after_end)

    # Download as arrays
    print("Downloading images...")
    rgb_before_arr = get_ee_image_as_array(rgb_before.visualize(min=0, max=1), bbox)
    rgb_after_arr = get_ee_image_as_array(rgb_after.visualize(min=0, max=1), bbox)

    # Get T-statistic with custom colormap
    t_stat_vis = t_stat.visualize(
        min=0,
        max=15,
        palette=['#440154', '#482878', '#3e4a89', '#31688e', '#26828e',
                 '#1f9e89', '#35b779', '#6ece58', '#b5de2b', '#fde725']
    )
    t_stat_arr = get_ee_image_as_array(t_stat_vis, bbox)

    # Get building footprints
    print("Fetching building footprints...")
    buildings = get_building_footprints(bbox)
    building_coords = []

    if buildings:
        try:
            # Get building polygons
            building_list = buildings.limit(500).getInfo()
            for feature in building_list.get('features', []):
                coords = feature['geometry']['coordinates']
                if feature['geometry']['type'] == 'Polygon':
                    building_coords.append(coords[0])
                elif feature['geometry']['type'] == 'MultiPolygon':
                    for poly in coords:
                        building_coords.append(poly[0])
        except Exception as e:
            print(f"Could not fetch buildings: {e}")

    # Create output directory
    safe_name = location_name.lower().replace(' ', '_').replace("'", "").replace(',', '')
    out_dir = os.path.join(output_dir, safe_name)
    os.makedirs(out_dir, exist_ok=True)

    # Create clean 3-panel figure
    print("Creating visualization...")
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))

    # Calculate scale bar
    lat_center = (bbox[1] + bbox[3]) / 2
    lon_diff = bbox[2] - bbox[0]
    meters_per_deg = 111320 * np.cos(np.radians(lat_center))
    total_meters = lon_diff * meters_per_deg

    # Determine appropriate scale bar length
    if total_meters > 1000:
        scale_meters = 100
    elif total_meters > 500:
        scale_meters = 50
    else:
        scale_meters = 25

    scale_pixels = (scale_meters / total_meters) * rgb_before_arr.shape[1]

    # Panel 1: Pre Destruction
    axes[0].imshow(rgb_before_arr)
    axes[0].set_title('Pre Destruction', fontsize=14, fontweight='bold')
    axes[0].axis('off')

    # Add scale bar
    bar_x = rgb_before_arr.shape[1] - scale_pixels - 20
    bar_y = rgb_before_arr.shape[0] - 30
    axes[0].add_patch(Rectangle((bar_x, bar_y), scale_pixels, 5,
                                 facecolor='white', edgecolor='black', linewidth=1))
    axes[0].text(bar_x + scale_pixels/2, bar_y - 8, f'{scale_meters} m',
                 ha='center', va='bottom', fontsize=9, color='white',
                 fontweight='bold',
                 path_effects=[path_effects.withStroke(linewidth=2, foreground='black')])

    # Panel 2: Post Destruction
    axes[1].imshow(rgb_after_arr)
    axes[1].set_title('Post Destruction', fontsize=14, fontweight='bold')
    axes[1].axis('off')

    # Add scale bar
    axes[1].add_patch(Rectangle((bar_x, bar_y), scale_pixels, 5,
                                 facecolor='white', edgecolor='black', linewidth=1))
    axes[1].text(bar_x + scale_pixels/2, bar_y - 8, f'{scale_meters} m',
                 ha='center', va='bottom', fontsize=9, color='white',
                 fontweight='bold',
                 path_effects=[path_effects.withStroke(linewidth=2, foreground='black')])

    # Panel 3: PWTT
    axes[2].imshow(t_stat_arr)
    axes[2].set_title('PWTT', fontsize=14, fontweight='bold')
    axes[2].axis('off')

    # Add scale bar
    axes[2].add_patch(Rectangle((bar_x, bar_y), scale_pixels, 5,
                                 facecolor='white', edgecolor='black', linewidth=1))
    axes[2].text(bar_x + scale_pixels/2, bar_y - 8, f'{scale_meters} m',
                 ha='center', va='bottom', fontsize=9, color='white',
                 fontweight='bold',
                 path_effects=[path_effects.withStroke(linewidth=2, foreground='black')])

    # Draw building footprints on PWTT panel
    if building_coords:
        img_height, img_width = t_stat_arr.shape[:2]
        for coords in building_coords:
            # Convert geo coords to pixel coords
            pixels = []
            for lon, lat in coords:
                px = (lon - bbox[0]) / (bbox[2] - bbox[0]) * img_width
                py = (bbox[3] - lat) / (bbox[3] - bbox[1]) * img_height
                pixels.append([px, py])

            if len(pixels) > 2:
                pixels = np.array(pixels)
                # Close the polygon
                pixels = np.vstack([pixels, pixels[0]])
                axes[2].plot(pixels[:, 0], pixels[:, 1], 'w-', linewidth=0.5, alpha=0.7)

    plt.tight_layout()

    # Save figure
    output_path = os.path.join(out_dir, 'pwtt_pre_post.png')
    plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()

    print(f"Saved: {output_path}")

    # Also save individual images
    Image.fromarray(rgb_before_arr).save(os.path.join(out_dir, 'pre_destruction.png'))
    Image.fromarray(rgb_after_arr).save(os.path.join(out_dir, 'post_destruction.png'))
    Image.fromarray(t_stat_arr).save(os.path.join(out_dir, 'pwtt_heatmap.png'))

    # Save analysis metadata
    metadata = {
        'location': location_name,
        'bbox': bbox,
        'event_date': event_date,
        'before_period': f'{before_start} to {before_end}',
        'after_period': f'{after_start} to {after_end}',
        'buildings_detected': len(building_coords)
    }

    with open(os.path.join(out_dir, 'analysis_metadata.json'), 'w') as f:
        json.dump(metadata, f, indent=2)

    print(f"Analysis complete! Output saved to: {out_dir}")
    return output_path


def run_clean_development_analysis(
    location_name,
    bbox,
    before_year,
    after_year,
    output_dir='analysis_output'
):
    """
    Run development detection with clean 3-panel visualization
    Labels: Pre-Development | Post-Development | PWTT
    """

    before_start = f'{before_year}-01-01'
    before_end = f'{before_year}-12-31'
    after_start = f'{after_year}-01-01'
    after_end = f'{after_year}-12-31'

    print(f"Analyzing development: {location_name}")
    print(f"Before period: {before_start} to {before_end}")
    print(f"After period: {after_start} to {after_end}")

    region = ee.Geometry.Rectangle(bbox)

    # Run PWTT for development detection
    print("Running PWTT analysis...")
    # Use middle of after period as "event"
    event_date = f'{after_year}-06-01'
    pre_months = (after_year - before_year) * 6 + 6  # Compare years
    post_months = 6

    pwtt_result = filter_s1(
        aoi=region,
        inference_start=event_date,
        war_start=event_date,
        pre_interval=pre_months,
        post_interval=post_months
    )

    t_stat = pwtt_result.select('T_statistic')

    # Get RGB images
    print("Fetching RGB imagery...")
    rgb_before = get_rgb_image(bbox, before_start, before_end)
    rgb_after = get_rgb_image(bbox, after_start, after_end)

    # Download as arrays
    print("Downloading images...")
    rgb_before_arr = get_ee_image_as_array(rgb_before.visualize(min=0, max=1), bbox)
    rgb_after_arr = get_ee_image_as_array(rgb_after.visualize(min=0, max=1), bbox)

    # Get T-statistic
    t_stat_vis = t_stat.visualize(
        min=0,
        max=15,
        palette=['#440154', '#482878', '#3e4a89', '#31688e', '#26828e',
                 '#1f9e89', '#35b779', '#6ece58', '#b5de2b', '#fde725']
    )
    t_stat_arr = get_ee_image_as_array(t_stat_vis, bbox)

    # Create output directory
    safe_name = location_name.lower().replace(' ', '_').replace("'", "").replace(',', '')
    out_dir = os.path.join(output_dir, safe_name)
    os.makedirs(out_dir, exist_ok=True)

    # Create clean 3-panel figure
    print("Creating visualization...")
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))

    # Calculate scale bar
    lat_center = (bbox[1] + bbox[3]) / 2
    lon_diff = bbox[2] - bbox[0]
    meters_per_deg = 111320 * np.cos(np.radians(lat_center))
    total_meters = lon_diff * meters_per_deg

    if total_meters > 2000:
        scale_meters = 500
    elif total_meters > 1000:
        scale_meters = 200
    elif total_meters > 500:
        scale_meters = 100
    else:
        scale_meters = 50

    scale_pixels = (scale_meters / total_meters) * rgb_before_arr.shape[1]

    # Panel 1: Pre-Development
    axes[0].imshow(rgb_before_arr)
    axes[0].set_title(f'Pre-Development ({before_year})', fontsize=14, fontweight='bold')
    axes[0].axis('off')

    bar_x = rgb_before_arr.shape[1] - scale_pixels - 20
    bar_y = rgb_before_arr.shape[0] - 30
    axes[0].add_patch(Rectangle((bar_x, bar_y), scale_pixels, 5,
                                 facecolor='white', edgecolor='black', linewidth=1))
    axes[0].text(bar_x + scale_pixels/2, bar_y - 8, f'{scale_meters} m',
                 ha='center', va='bottom', fontsize=9, color='white',
                 fontweight='bold',
                 path_effects=[path_effects.withStroke(linewidth=2, foreground='black')])

    # Panel 2: Post-Development
    axes[1].imshow(rgb_after_arr)
    axes[1].set_title(f'Post-Development ({after_year})', fontsize=14, fontweight='bold')
    axes[1].axis('off')

    axes[1].add_patch(Rectangle((bar_x, bar_y), scale_pixels, 5,
                                 facecolor='white', edgecolor='black', linewidth=1))
    axes[1].text(bar_x + scale_pixels/2, bar_y - 8, f'{scale_meters} m',
                 ha='center', va='bottom', fontsize=9, color='white',
                 fontweight='bold',
                 path_effects=[path_effects.withStroke(linewidth=2, foreground='black')])

    # Panel 3: PWTT
    axes[2].imshow(t_stat_arr)
    axes[2].set_title('PWTT', fontsize=14, fontweight='bold')
    axes[2].axis('off')

    axes[2].add_patch(Rectangle((bar_x, bar_y), scale_pixels, 5,
                                 facecolor='white', edgecolor='black', linewidth=1))
    axes[2].text(bar_x + scale_pixels/2, bar_y - 8, f'{scale_meters} m',
                 ha='center', va='bottom', fontsize=9, color='white',
                 fontweight='bold',
                 path_effects=[path_effects.withStroke(linewidth=2, foreground='black')])

    plt.tight_layout()

    # Save figure
    output_path = os.path.join(out_dir, 'pwtt_pre_post.png')
    plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()

    print(f"Saved: {output_path}")

    # Save individual images
    Image.fromarray(rgb_before_arr).save(os.path.join(out_dir, 'pre_development.png'))
    Image.fromarray(rgb_after_arr).save(os.path.join(out_dir, 'post_development.png'))
    Image.fromarray(t_stat_arr).save(os.path.join(out_dir, 'pwtt_heatmap.png'))

    print(f"Analysis complete! Output saved to: {out_dir}")
    return output_path


if __name__ == '__main__':
    # Example: Run damage detection for Singha Durbar
    run_clean_pwtt_analysis(
        location_name="Singha Durbar",
        bbox=[85.3175, 27.6925, 85.3275, 27.7025],
        event_date="2025-09-08",
        output_dir='analysis_output'
    )
