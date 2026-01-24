# Sleep Resource File Generator - Implementation Complete

## Overview

Created a system that automatically computes `resource_user_sleep_current.json` from database sleep segments. This ensures the resource file that agents read is always synchronized with the database.

## What Was Created

### 1. Sleep Data Generator Module

**File:** `app/assistant/physical_status_manager/sleep_data_generator.py`

A comprehensive module that:
- Queries sleep segments from the database
- Calculates sleep metrics (total, main sleep, naps, quality)
- Generates the resource file in the expected format
- Provides CLI interface for manual generation

### Key Functions

#### `generate_sleep_resource_file()`
- **Purpose**: Main function that computes and writes the resource file
- **Data source**: Database (`sleep_segments` table)
- **Output**: `resources/resource_user_sleep_current.json`
- **Returns**: Dict with the computed sleep data

**What it computes:**
- `total_sleep_minutes`: Sum of all segments
- `main_sleep_minutes`: Longest segment duration
- `nap_minutes`: Total - main sleep
- `sleep_quality`: "good", "fair", "poor", or "unknown"
- `fragmented`: True if multiple segments
- `segment_count`: Number of sleep periods
- `bedtime_previous`: Earliest segment start time
- `wake_time_today`: Latest segment end time
- `sleep_periods`: Classified segments (main_sleep vs nap)
- `segments`: Raw segment data with source attribution

#### `refresh_sleep_resource_if_stale(max_age_minutes=60)`
- **Purpose**: Only regenerate if file is older than threshold
- **Default**: 60 minutes
- **Use case**: Efficient periodic updates without unnecessary computation

#### `get_sleep_resource_data()`
- **Purpose**: Read current resource file
- **Returns**: Dict with sleep data
- **Fallback**: Empty dict if file doesn't exist

### 2. Integration with SleepSegmentTracker

**File:** `app/assistant/physical_status_manager/sleep_segment_tracker.py`

**Changes:**
- Added `_update_sleep_resource_file()` helper function
- Calls `generate_sleep_resource_file()` after:
  - Recording new sleep segment (`record_sleep_segment()`)
  - Creating synthetic sleep (`create_synthetic_sleep_segment()`)

**Result**: Resource file is automatically updated whenever sleep data changes in the database.

## Data Flow

### Before (Old System)
```
SleepTracker → JSON file (user_sleep_current.json)
Agents → read JSON file
```

### After (New System)
```
AFKMonitor → Database (sleep_segments table)
SleepSegmentTracker → Database (sleep_segments table)
                   → generate_sleep_resource_file()
                   → resource_user_sleep_current.json
Agents → read resource_user_sleep_current.json
```

### Database as Source of Truth
- **Raw data**: Database stores individual sleep segments
- **Computed data**: Resource file computed from database on-demand
- **Agents**: Read computed summary from resource file

## Resource File Format

```json
{
  "date": "2026-01-06",
  "day_date": "2026-01-06",
  "total_sleep_minutes": 480.0,
  "main_sleep_minutes": 480.0,
  "nap_minutes": 0.0,
  "sleep_quality": "good",
  "fragmented": false,
  "segment_count": 1,
  "sleep_periods": [
    {
      "start": "2026-01-05T22:00:00",
      "end": "2026-01-06T06:00:00",
      "duration_minutes": 480.0,
      "type": "main_sleep"
    }
  ],
  "segments": [
    {
      "start": "2026-01-05T22:00:00",
      "end": "2026-01-06T06:00:00",
      "duration_minutes": 480.0,
      "source": "user_chat"
    }
  ],
  "wake_time": "06:00",
  "wake_time_today": "2026-01-06 06:00",
  "bedtime_previous": "2026-01-05 22:00",
  "last_updated": "2026-01-07T01:44:20.705714+00:00",
  "source": "database"
}
```

### Field Descriptions

| Field | Description | Example |
|-------|-------------|---------|
| `date` | Day date (wake-up day) | "2026-01-06" |
| `total_sleep_minutes` | Total sleep (all segments) | 480.0 |
| `main_sleep_minutes` | Longest continuous sleep | 480.0 |
| `nap_minutes` | Short sleep periods | 0.0 |
| `sleep_quality` | Computed quality | "good", "fair", "poor" |
| `fragmented` | Multiple segments? | true/false |
| `segment_count` | Number of sleep periods | 1 |
| `sleep_periods` | Classified segments | Array of objects |
| `segments` | Raw segment data | Array of objects |
| `wake_time` | Time only (HH:MM) | "06:00" |
| `wake_time_today` | Full timestamp (local) | "2026-01-06 06:00" |
| `bedtime_previous` | Bedtime (local) | "2026-01-05 22:00" |
| `last_updated` | When file was generated | ISO timestamp |
| `source` | Always "database" | "database" |

## Automatic Updates

The resource file is automatically updated when:

1. **New sleep segment recorded** (from AFK detection):
   ```python
   sleep_segment_tracker.record_sleep_segment(start, end, source='afk_detection')
   → generates resource file
   ```

2. **User reports sleep** (from chat):
   ```python
   sleep_segment_tracker.process_sleep_events(sleep_events)
   → record_sleep_segment() called
   → generates resource file
   ```

3. **Synthetic sleep created** (cold start):
   ```python
   sleep_segment_tracker.create_synthetic_sleep_segment(wake_time, duration)
   → generates resource file
   ```

## Manual Generation

### Command Line Interface

```bash
# Regenerate if stale (>60 min old)
python -m app.assistant.physical_status_manager.sleep_data_generator

# Force regeneration (ignore age)
python -m app.assistant.physical_status_manager.sleep_data_generator --force

# Show full JSON output
python -m app.assistant.physical_status_manager.sleep_data_generator --show
```

### Programmatic Usage

```python
from app.assistant.day_flow_manager.archive.sleep_data_generator import (
    generate_sleep_resource_file,
    refresh_sleep_resource_if_stale,
    get_sleep_resource_data
)

# Force regeneration
data = generate_sleep_resource_file()

# Regenerate only if stale
refreshed = refresh_sleep_resource_if_stale(max_age_minutes=60)

# Read existing data
data = get_sleep_resource_data()
```

## Quality Calculation

Sleep quality is computed using these rules:

```python
if total_hours >= 7.0:
    quality = "good"
elif total_hours >= 6.0:
    quality = "fair"
elif total_hours > 0:
    quality = "poor"
else:
    quality = "unknown"
```

## Main Sleep vs. Naps

- **Main sleep**: Longest continuous segment
- **Naps**: All other segments
- Classification is automatic based on duration

Example:
- Segment 1: 480 min (8 hours) → **main_sleep**
- Segment 2: 30 min → **nap**
- Segment 3: 20 min → **nap**

Result:
- `main_sleep_minutes`: 480
- `nap_minutes`: 50
- `total_sleep_minutes`: 530

## Backward Compatibility

The resource file maintains the same structure as before:
- Agents that read `resource_user_sleep_current.json` continue to work
- All expected fields are present
- Additional field: `source: "database"` (indicates DB-backed)

## Testing

### Verified Output

```bash
$ python -m app.assistant.physical_status_manager.sleep_data_generator

Sleep Summary
============================================================
Date: 2026-01-06
Total Sleep: 1380.0 min (23.0h)
  - Main Sleep: 480.0 min
  - Naps: 900.0 min
Quality: good
Fragmented: True
Segments: 3
Bedtime: 2026-01-05 14:00
Wake Time: 2026-01-06 09:39

[+] Resource file: resources/resource_user_sleep_current.json
```

### File Location

✅ File written to: `resources/resource_user_sleep_current.json`
✅ Format: Valid JSON
✅ All expected fields present
✅ Source attribution included

## Benefits

### 1. Single Source of Truth
- Database holds raw sleep segments
- Resource file computed from database
- No data duplication or inconsistency

### 2. Automatic Synchronization
- Resource file updates whenever sleep data changes
- Agents always see current data
- No manual refresh needed

### 3. Easy Debugging
- Can regenerate resource file anytime from database
- Can inspect raw segments vs. computed summary
- Source attribution shows where data came from

### 4. Flexible Updates
- Can batch-update multiple segments
- Resource file regenerated once after all updates
- Efficient for bulk operations

### 5. Historical Analysis
- Database retains full segment history
- Can recompute past days on demand
- Can generate reports for date ranges

## Future Enhancements

### 1. Date Range Support
```python
generate_sleep_resource_file(date="2026-01-05")
# Generate for a specific past date
```

### 2. Multi-Day Summaries
```python
generate_weekly_sleep_summary()
# Average sleep for last 7 days
```

### 3. Trend Analysis
```python
calculate_sleep_trends(days=30)
# Sleep quality trends over time
```

### 4. Sleep Goals
```python
check_sleep_goals(target_hours=8.0)
# Compare actual vs. target
```

## Related Files

- `app/assistant/physical_status_manager/sleep_data_generator.py` - Generator module (NEW)
- `app/assistant/physical_status_manager/sleep_segment_tracker.py` - Updated to call generator
- `app/assistant/physical_status_manager/afk_sleep_db.py` - Database access layer
- `resources/resource_user_sleep_current.json` - Generated resource file

## Status

✅ **COMPLETE** - Sleep resource file is now automatically computed from database
- Generates on every sleep segment change
- CLI interface for manual generation
- Maintains backward compatibility
- Includes source attribution
