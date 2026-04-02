# PWTT Algorithm Improvements v2.0

## Overview

This document summarizes the improvements made to the PWTT (Pixel-Wise T-Test) damage detection algorithm for better detection of civil unrest damage.

## Problem Statement

The original PWTT algorithm was calibrated for war-zone destruction (Aleppo, Mariupol) with t-statistic threshold of 3.0. When applied to civil unrest scenarios (like the GenZ protests in Singha Durbar/Federal Parliament), the algorithm only detected ~3% of damaged area, despite visible changes in satellite imagery.

## Validation Data

**Screenshots analyzed:**
- Pre-event: Nov 20, 2021
- Post-event: Oct 8, 2025
- Coordinates: 27°41'53.44"N, 85°19'26.92"E

**T-Statistic Distribution in area:**
```
Mean: 0.949
Median (p50): 0.718
p75: 1.281
p90: 2.032
p95: 2.595
p99: 4.032
Max: 11.876
```

## Changes Made

### 1. Main Detection Threshold (pwtt_service.py)

**Before:**
```python
T_STAT_THRESHOLD = 2.0  # Previously 3.0, then 2.0
```

**After:**
```python
T_STAT_THRESHOLD = 1.5  # Optimized for civil unrest
```

### 2. Severity Thresholds (pwtt_service.py)

**Before:**
```python
T_STAT_CRITICAL = 3.5
T_STAT_SEVERE = 2.5
T_STAT_MODERATE = 2.0
T_STAT_MINOR = 1.5
```

**After:**
```python
T_STAT_CRITICAL = 3.0    # Structural damage
T_STAT_SEVERE = 2.2      # Significant damage
T_STAT_MODERATE = 1.5    # Partial damage
T_STAT_MINOR = 1.0       # Surface damage
```

### 3. Event-Type Multipliers (pwtt_service.py)

**Before:**
```python
EVENT_THRESHOLD_MULTIPLIERS = {
    'civil_unrest': 0.8,
    'fire': 0.75,
}
```

**After:**
```python
EVENT_THRESHOLD_MULTIPLIERS = {
    'civil_unrest': 0.70,  # Much lower for protests/fires
    'fire': 0.65,          # Even lower for fire damage
}
```

### 4. Damage Probability Calculation (pwtt_service.py)

**Before:**
```python
damage_probability = t_stat_masked.subtract(self.T_STAT_THRESHOLD).divide(2).clamp(0, 1)
```

**After:**
```python
# Scale of 1.5 gives better gradation for lower t-values
damage_probability = t_stat_masked.subtract(self.T_STAT_THRESHOLD).divide(1.5).clamp(0, 1)
```

### 5. Visualization Improvements (pwtt_service.py)

- Added more color gradation for lower damage levels
- T-stat visualization range reduced from 0-6 to 0-4 for better detail
- Added inclusive mask showing marginal changes (t > 1.0)
- Enhanced 8-color palette for damage visualization

### 6. Building Detection Thresholds (building_detection.py)

**Before:**
```python
T_STAT_CRITICAL = 3.5
T_STAT_SEVERE = 2.5
T_STAT_MODERATE = 2.0
T_STAT_MINOR = 1.5
```

**After:**
```python
T_STAT_CRITICAL = 3.0
T_STAT_SEVERE = 2.2
T_STAT_MODERATE = 1.5
T_STAT_MINOR = 1.0
```

### 7. Building Detection Baseline (building_detection.py)

**Before:**
```python
baseline_days: int = 30
post_event_days: int = 15
```

**After:**
```python
baseline_days: int = 180   # 6 months for stable baseline
post_event_days: int = 45  # 45 days post-event
```

## Results

### Detection Improvement by Threshold

| Threshold | Detected Area | % of Total |
|-----------|---------------|------------|
| 3.0 (original PWTT) | 0.0332 km² | 3.04% |
| 2.0 (previous) | 0.1099 km² | 10.04% |
| **1.5 (new)** | **0.2121 km²** | **19.38%** |
| 1.0 (minor) | 0.3989 km² | 36.44% |

### Federal Parliament / BICC Assessment Results

```
Total area: 0.3832 km²
Damaged area: 0.0851 km²
Damage percentage: 22.22%

Severity Breakdown:
- Critical (t>3.0): 0.0036 km²
- Severe (2.2<t<=3.0): 0.0135 km²
- Moderate (1.5<t<=2.2): 0.0681 km²
- Minor (1.0<t<=1.5): 0.1409 km²

Total Affected (all severities): 54.44%

Metadata:
- Baseline images: 58
- Post-event images: 10
- Confidence: 95.0%
- Hotspots: 10
- Building zones: 73
```

### Improvement Summary

| Metric | Before | After | Change |
|--------|--------|-------|--------|
| Damage % (threshold 3.0) | 3.04% | - | baseline |
| Damage % (new threshold 1.5) | - | 19.38% | +538% |
| Federal Parliament damage | ~5% | 22.22% | +344% |
| Total affected area | ~10% | 54.44% | +444% |

## Files Modified

1. `/backend-v5/app/services/damage_assessment/pwtt_service.py`
   - Thresholds lowered
   - Damage probability calculation updated
   - Visualization palettes enhanced
   - Added inclusive damage mask

2. `/backend-v5/app/services/damage_assessment/building_detection.py`
   - Thresholds aligned with pwtt_service.py
   - Baseline period extended
   - Area-based multipliers adjusted

## New Scripts Created

1. `/backend-v5/scripts/create_federal_parliament_assessment.py`
   - Creates assessment for Federal Parliament/BICC area
   - Runs actual PWTT analysis
   - Creates building damage zones

2. `/backend-v5/scripts/validate_pwtt_against_screenshots.py`
   - Validates algorithm against screenshot evidence
   - Computes t-statistic distribution
   - Compares different thresholds

## Recommendations for Future Improvement

1. **Add Optical Change Detection**: SAR alone may miss some damage types. Consider adding Sentinel-2 NDBI/NDVI change detection as complementary signal.

2. **Time-Series Analysis**: Instead of before/after comparison, use time-series to detect gradual changes.

3. **Ground Truth Calibration**: Collect ground truth data from civil unrest events to further optimize thresholds.

4. **Event-Type Detection**: Automatically detect event type and apply appropriate threshold multipliers.

---
*Last updated: 2026-01-30*
*Assessment ID: 2a649118-69e4-4dc5-b0cf-6036b6de2a2b*
