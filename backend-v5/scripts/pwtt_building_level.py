#!/usr/bin/env python3
"""
PWTT Building-Level Damage Detection

Implements the correct PWTT algorithm as per the flowchart:
1. Calculate T-statistic per pixel
2. Get building footprints
3. Calculate MEAN T-stat within each building
4. Apply threshold per building
5. Classify as damaged/undamaged per building

This reduces false positives by aggregating at building level.
"""

import ee
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patheffects as path_effects
from matplotlib.patches import Rectangle, Polygon
from matplotlib.collections import PatchCollection
import requests
from PIL import Image
from io import BytesIO
import json
import os
import sys

# Add parent directory to path for pwtt_lib
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pwtt_lib.code.pwtt import lee_filter, ttest

# Initialize Earth Engine
ee.Initialize()

# Damage threshold (T-statistic value)
DAMAGE_THRESHOLD = 3.0  # Buildings with mean T-stat > 3 are flagged as damaged


def get_raw_tstat(aoi, event_date, pre_months=12, post_months=2):
    """
    Calculate raw T-statistic without convolution smoothing.
    This gives sharper, more accurate per-pixel values.
    """
    inference_start = ee.Date(event_date)
    war_start = ee.Date(event_date)

    # Get orbits available in the post-event period
    orbits = ee.ImageCollection("COPERNICUS/S1_GRD_FLOAT") \
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VH")) \
        .filter(ee.Filter.eq("instrumentMode", "IW")) \
        .filterBounds(aoi) \
        .filterDate(inference_start, inference_start.advance(post_months, 'months')) \
        .aggregate_array('relativeOrbitNumber_start') \
        .distinct()

    def map_orbit(orbit):
        s1 = ee.ImageCollection("COPERNICUS/S1_GRD_FLOAT") \
            .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VH")) \
            .filter(ee.Filter.eq("instrumentMode", "IW")) \
            .filter(ee.Filter.eq("relativeOrbitNumber_start", orbit)) \
            .map(lee_filter) \
            .select(['VV', 'VH']) \
            .map(lambda image: image.log()) \
            .filterBounds(aoi)

        return ttest(s1, inference_start, war_start, pre_months, post_months)

    # Get max T-stat across all orbits
    image = ee.ImageCollection(orbits.map(map_orbit)).max()

    # Take max of VV and VH (as per flowchart: Max[T])
    t_stat = image.select('VV').max(image.select('VH')).rename('T_statistic')

    return t_stat.clip(aoi)


def get_building_footprints(bbox):
    """Get building footprints from available sources"""
    region = ee.Geometry.Rectangle(bbox)

    # Try Google Open Buildings first
    try:
        buildings = ee.FeatureCollection('GOOGLE/Research/open-buildings/v3/polygons') \
            .filterBounds(region)

        count = buildings.size().getInfo()
        if count > 0:
            print(f"Found {count} buildings from Google Open Buildings")
            return buildings
    except Exception as e:
        print(f"Google Open Buildings not available: {e}")

    # Try Microsoft Buildings
    try:
        # For Nepal, try the global MS buildings
        ms_buildings = ee.FeatureCollection('projects/sat-io/open-datasets/MSBuildings/Nepal') \
            .filterBounds(region)
        count = ms_buildings.size().getInfo()
        if count > 0:
            print(f"Found {count} buildings from Microsoft Buildings")
            return ms_buildings
    except Exception as e:
        print(f"Microsoft Buildings not available: {e}")

    # Try OSM buildings
    try:
        osm = ee.FeatureCollection('projects/sat-io/open-datasets/OSM_Polygons/OSM_Polygons_Building') \
            .filterBounds(region)
        count = osm.size().getInfo()
        if count > 0:
            print(f"Found {count} buildings from OSM")
            return osm
    except:
        pass

    print("No building footprints available")
    return None


def calculate_building_damage(t_stat_image, buildings, threshold=DAMAGE_THRESHOLD):
    """
    Calculate mean T-statistic within each building and classify damage.

    This is the key step that reduces false positives - we aggregate
    at building level instead of flagging individual noisy pixels.
    """

    # Reduce T-statistic to mean value per building
    buildings_with_stats = t_stat_image.reduceRegions(
        collection=buildings,
        reducer=ee.Reducer.mean().combine(
            reducer2=ee.Reducer.max(),
            sharedInputs=True
        ).combine(
            reducer2=ee.Reducer.percentile([90]),
            sharedInputs=True
        ),
        scale=10,
        tileScale=4
    )

    # Add damage classification based on mean T-stat
    def classify_damage(feature):
        mean_t = ee.Number(feature.get('mean')).max(0)
        max_t = ee.Number(feature.get('max')).max(0)
        p90_t = ee.Number(feature.get('p90')).max(0)

        # Use mean for classification (reduces noise)
        is_damaged = mean_t.gt(threshold)

        # Severity levels based on mean T-stat
        severity = ee.Algorithms.If(
            mean_t.gt(6), 'critical',
            ee.Algorithms.If(
                mean_t.gt(4.5), 'severe',
                ee.Algorithms.If(
                    mean_t.gt(threshold), 'moderate',
                    'undamaged'
                )
            )
        )

        return feature.set({
            'mean_t_stat': mean_t,
            'max_t_stat': max_t,
            'p90_t_stat': p90_t,
            'is_damaged': is_damaged,
            'severity': severity
        })

    return buildings_with_stats.map(classify_damage)


def get_ee_image_as_array(image, bbox, dimensions=512):
    """Download EE image as numpy array"""
    region = ee.Geometry.Rectangle(bbox)
    url = image.getThumbURL({
        'region': region,
        'dimensions': dimensions,
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


def run_building_level_detection(
    location_name,
    bbox,
    event_date,
    before_days=365,
    after_days=30,
    threshold=DAMAGE_THRESHOLD,
    output_dir='analysis_output'
):
    """
    Run building-level PWTT damage detection.

    This implements the correct algorithm from the flowchart:
    1. Calculate T-stat per pixel
    2. Get building footprints
    3. Calculate mean T-stat per building
    4. Threshold per building
    5. Visualize with building polygons colored by damage
    """

    from datetime import datetime, timedelta

    event_dt = datetime.strptime(event_date, '%Y-%m-%d')
    before_start = (event_dt - timedelta(days=before_days)).strftime('%Y-%m-%d')
    before_end = (event_dt - timedelta(days=1)).strftime('%Y-%m-%d')
    after_start = event_date
    after_end = (event_dt + timedelta(days=after_days)).strftime('%Y-%m-%d')

    print(f"Building-Level PWTT Analysis: {location_name}")
    print(f"Before period: {before_start} to {before_end}")
    print(f"After period: {after_start} to {after_end}")
    print(f"Damage threshold: T-stat > {threshold}")

    region = ee.Geometry.Rectangle(bbox)

    # Step 1: Calculate raw T-statistic
    print("Step 1: Calculating T-statistic...")
    pre_months = before_days // 30
    post_months = max(1, after_days // 30)
    t_stat = get_raw_tstat(region, event_date, pre_months, post_months)

    # Step 2: Get building footprints
    print("Step 2: Getting building footprints...")
    buildings = get_building_footprints(bbox)

    damaged_buildings = []
    all_buildings = []

    if buildings:
        # Step 3: Calculate mean T-stat per building
        print("Step 3: Calculating mean T-stat per building...")
        buildings_with_damage = calculate_building_damage(t_stat, buildings, threshold)

        # Get results
        print("Fetching building damage results...")
        results = buildings_with_damage.limit(1000).getInfo()

        total_buildings = len(results['features'])
        damaged_count = 0

        for feature in results['features']:
            props = feature['properties']
            coords = feature['geometry']['coordinates']

            mean_t = props.get('mean_t_stat', 0) or 0
            severity = props.get('severity', 'undamaged')

            building_info = {
                'coordinates': coords,
                'geometry_type': feature['geometry']['type'],
                'mean_t_stat': mean_t,
                'max_t_stat': props.get('max_t_stat', 0) or 0,
                'severity': severity
            }

            all_buildings.append(building_info)

            if severity != 'undamaged':
                damaged_count += 1
                damaged_buildings.append(building_info)

        print(f"Total buildings analyzed: {total_buildings}")
        print(f"Damaged buildings (T > {threshold}): {damaged_count}")
        print(f"  - Critical (T > 6): {sum(1 for b in damaged_buildings if b['severity'] == 'critical')}")
        print(f"  - Severe (T > 4.5): {sum(1 for b in damaged_buildings if b['severity'] == 'severe')}")
        print(f"  - Moderate (T > 3): {sum(1 for b in damaged_buildings if b['severity'] == 'moderate')}")
    else:
        print("No building footprints available - using pixel-level detection")
        total_buildings = 0
        damaged_count = 0

    # Step 4: Get imagery for visualization
    print("Step 4: Fetching imagery...")
    rgb_before = get_rgb_image(bbox, before_start, before_end)
    rgb_after = get_rgb_image(bbox, after_start, after_end)

    rgb_before_arr = get_ee_image_as_array(rgb_before.visualize(min=0, max=1), bbox)
    rgb_after_arr = get_ee_image_as_array(rgb_after.visualize(min=0, max=1), bbox)

    t_stat_vis = t_stat.visualize(
        min=0,
        max=10,
        palette=['#440154', '#482878', '#3e4a89', '#31688e', '#26828e',
                 '#1f9e89', '#35b779', '#6ece58', '#b5de2b', '#fde725']
    )
    t_stat_arr = get_ee_image_as_array(t_stat_vis, bbox)

    # Step 5: Create visualization
    print("Step 5: Creating visualization...")

    # Create output directory
    safe_name = location_name.lower().replace(' ', '_').replace("'", "").replace(',', '')
    out_dir = os.path.join(output_dir, safe_name + '_building_level')
    os.makedirs(out_dir, exist_ok=True)

    fig, axes = plt.subplots(1, 3, figsize=(15, 5))

    # Calculate scale bar
    lat_center = (bbox[1] + bbox[3]) / 2
    lon_diff = bbox[2] - bbox[0]
    meters_per_deg = 111320 * np.cos(np.radians(lat_center))
    total_meters = lon_diff * meters_per_deg

    if total_meters > 1000:
        scale_meters = 100
    elif total_meters > 500:
        scale_meters = 50
    else:
        scale_meters = 25

    scale_pixels = (scale_meters / total_meters) * rgb_before_arr.shape[1]
    img_height, img_width = rgb_before_arr.shape[:2]

    bar_x = img_width - scale_pixels - 20
    bar_y = img_height - 30

    # Panel 1: Pre Destruction
    axes[0].imshow(rgb_before_arr)
    axes[0].set_title('Pre Destruction', fontsize=14, fontweight='bold')
    axes[0].axis('off')
    axes[0].add_patch(Rectangle((bar_x, bar_y), scale_pixels, 5,
                                 facecolor='white', edgecolor='black', linewidth=1))
    axes[0].text(bar_x + scale_pixels/2, bar_y - 8, f'{scale_meters} m',
                 ha='center', va='bottom', fontsize=9, color='white', fontweight='bold',
                 path_effects=[path_effects.withStroke(linewidth=2, foreground='black')])

    # Panel 2: Post Destruction
    axes[1].imshow(rgb_after_arr)
    axes[1].set_title('Post Destruction', fontsize=14, fontweight='bold')
    axes[1].axis('off')
    axes[1].add_patch(Rectangle((bar_x, bar_y), scale_pixels, 5,
                                 facecolor='white', edgecolor='black', linewidth=1))
    axes[1].text(bar_x + scale_pixels/2, bar_y - 8, f'{scale_meters} m',
                 ha='center', va='bottom', fontsize=9, color='white', fontweight='bold',
                 path_effects=[path_effects.withStroke(linewidth=2, foreground='black')])

    # Panel 3: PWTT with building footprints
    axes[2].imshow(t_stat_arr)
    axes[2].set_title('PWTT', fontsize=14, fontweight='bold')
    axes[2].axis('off')
    axes[2].add_patch(Rectangle((bar_x, bar_y), scale_pixels, 5,
                                 facecolor='white', edgecolor='black', linewidth=1))
    axes[2].text(bar_x + scale_pixels/2, bar_y - 8, f'{scale_meters} m',
                 ha='center', va='bottom', fontsize=9, color='white', fontweight='bold',
                 path_effects=[path_effects.withStroke(linewidth=2, foreground='black')])

    # Draw building footprints with damage coloring
    severity_colors = {
        'undamaged': 'white',
        'moderate': 'yellow',
        'severe': 'orange',
        'critical': 'red'
    }

    for building in all_buildings:
        coords = building['coordinates']
        severity = building['severity']
        color = severity_colors.get(severity, 'white')

        # Convert coordinates to pixels
        if building['geometry_type'] == 'Polygon':
            poly_coords = coords[0]
        elif building['geometry_type'] == 'MultiPolygon':
            poly_coords = coords[0][0]
        else:
            continue

        pixels = []
        for lon, lat in poly_coords:
            px = (lon - bbox[0]) / (bbox[2] - bbox[0]) * img_width
            py = (bbox[3] - lat) / (bbox[3] - bbox[1]) * img_height
            pixels.append([px, py])

        if len(pixels) > 2:
            pixels = np.array(pixels)

            if severity == 'undamaged':
                # Just outline for undamaged
                axes[2].plot(pixels[:, 0], pixels[:, 1], 'w-', linewidth=0.3, alpha=0.5)
            else:
                # Filled polygon for damaged
                poly = Polygon(pixels, facecolor=color, edgecolor='white',
                              alpha=0.6, linewidth=0.5)
                axes[2].add_patch(poly)

    plt.tight_layout()

    # Save outputs
    output_path = os.path.join(out_dir, 'pwtt_pre_post.png')
    plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()

    print(f"Saved: {output_path}")

    # Save individual images
    Image.fromarray(rgb_before_arr).save(os.path.join(out_dir, 'pre_destruction.png'))
    Image.fromarray(rgb_after_arr).save(os.path.join(out_dir, 'post_destruction.png'))
    Image.fromarray(t_stat_arr).save(os.path.join(out_dir, 'pwtt_heatmap.png'))

    # Save results
    results_data = {
        'location': location_name,
        'bbox': bbox,
        'event_date': event_date,
        'threshold': threshold,
        'total_buildings': total_buildings,
        'damaged_buildings': damaged_count,
        'by_severity': {
            'critical': sum(1 for b in damaged_buildings if b['severity'] == 'critical'),
            'severe': sum(1 for b in damaged_buildings if b['severity'] == 'severe'),
            'moderate': sum(1 for b in damaged_buildings if b['severity'] == 'moderate')
        },
        'damaged_building_details': [
            {
                'mean_t_stat': b['mean_t_stat'],
                'max_t_stat': b['max_t_stat'],
                'severity': b['severity']
            }
            for b in damaged_buildings
        ]
    }

    with open(os.path.join(out_dir, 'building_damage_results.json'), 'w') as f:
        json.dump(results_data, f, indent=2)

    print(f"Analysis complete! Output saved to: {out_dir}")
    return output_path, results_data


if __name__ == '__main__':
    # Test on Singha Durbar
    run_building_level_detection(
        location_name="Singha Durbar",
        bbox=[85.3175, 27.6925, 85.3275, 27.7025],
        event_date="2025-09-08",
        output_dir='analysis_output'
    )
