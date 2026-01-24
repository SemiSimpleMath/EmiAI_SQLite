# Database Logs Added to Orchestrator Pipeline Debug UI

**Date:** 2026-01-07  
**Status:** ✅ Complete

---

## What Was Added

### New Database Log Sections

The debug UI now displays raw telemetry data from the database:

#### 1. Sleep Segments Log
**Source:** `sleep_segments` table  
**Display:** Last 50 segments  
**Fields:**
- `id` - Segment ID
- `start` - Start time (local)
- `end` - End time (local)
- `duration_minutes` - Duration in minutes
- `duration_hours` - Duration in hours (rounded)
- `source` - Source of segment (afk_detection, user_chat, cold_start_assumed)

#### 2. AFK Events Log
**Source:** `afk_events` table  
**Display:** Last 100 events  
**Fields:**
- `id` - Event ID
- `timestamp` - When event occurred (local)
- `event_type` - Type (went_afk, returned, potentially_afk)
- `idle_seconds` - Idle duration
- `duration_minutes` - AFK duration (for 'returned' events)
- `is_afk` - Boolean flag
- `is_potentially_afk` - Boolean flag

#### 3. Wake Segments Log
**Source:** `wake_segments` table  
**Display:** Last 20 segments  
**Fields:**
- `id` - Segment ID
- `start_time` - When woke up (local)
- `end_time` - When went back to sleep (local)
- `duration_minutes` - How long awake
- `source` - Source (user_chat, manual)
- `notes` - Why awake (bathroom, couldn't sleep, etc.)

---

## Implementation Details

### Backend Functions Added

**File:** `app/routes/debug_status.py`

```python
def _get_sleep_segments_log(limit=50):
    """Get recent sleep segments from database."""
    # Queries sleep_segments table
    # Orders by start DESC
    # Converts timestamps to local time
    # Returns list of dicts

def _get_afk_events_log(limit=100):
    """Get recent AFK events from database."""
    # Queries afk_events table
    # Orders by timestamp DESC
    # Converts timestamps to local time
    # Returns list of dicts

def _get_wake_segments_log(limit=20):
    """Get recent wake segments from database."""
    # Queries wake_segments table
    # Orders by start_time DESC
    # Converts timestamps to local time
    # Returns list of dicts
```

### Frontend Display

**File:** `app/templates/debug_status.html`

Three new cards added to the grid:
- **💤 Sleep Segments Log** (blue label: raw telemetry)
- **⏸️ AFK Events Log** (blue label: raw telemetry)
- **👁️ Wake Segments Log** (blue label: raw telemetry)

Each card shows:
- Emoji icon + title
- Table name + record count
- Blue label: "Raw telemetry from database"
- Syntax-highlighted JSON array

---

## Display Order (Updated)

The debug UI now shows (in order):

### Orchestrator Inputs (Green labels)
1. Health Status (generated)
2. User Health (traits)
3. Sleep Data (24h summary)
4. Tracked Activities (config)
5. Location
6. Daily Context
7. User Routine

### Database Telemetry (Blue labels)
8. Sleep Segments Log (last 50)
9. AFK Events Log (last 100)
10. Wake Segments Log (last 20)

### Legacy (Warning label)
11. Physical Status (old format)

---

## Usage

### View Database Logs

1. Navigate to: `http://localhost:5000/debug/status`
2. Scroll down to see database log sections
3. All timestamps are in local time
4. Auto-refreshes every 60 seconds

### What You Can See

**Sleep Segments:**
- Recent sleep periods detected by AFK monitor
- User-entered sleep times from chat
- Cold start synthetic segments

**AFK Events:**
- Every time user goes AFK
- Every time user returns from AFK
- Potentially AFK state transitions
- Complete audit trail of activity

**Wake Segments:**
- Night wake-ups mentioned in chat
- Duration of each wake period
- Notes about why awake

---

## Benefits

### 1. Complete Visibility
- See raw data that feeds into health status
- Understand how sleep summary is computed
- Debug AFK detection issues

### 2. Troubleshooting
- Verify AFK events are being recorded
- Check if sleep segments look correct
- Identify gaps in data collection

### 3. Data Quality
- Spot anomalies (e.g., 20-hour sleep segments)
- Check source attribution
- Validate timestamps

### 4. Understanding Pipeline
- See progression: raw events → summary → inference → suggestions
- Trace how telemetry flows through system
- Understand agent inputs

---

## Example Output

**Sleep Segments Log:**
```json
[
  {
    "id": 123,
    "start": "2026-01-07 01:30:00 AM PST",
    "end": "2026-01-07 08:15:00 AM PST",
    "duration_minutes": 405,
    "duration_hours": 6.8,
    "source": "afk_detection"
  },
  ...
]
```

**AFK Events Log:**
```json
[
  {
    "id": 456,
    "timestamp": "2026-01-07 07:00:00 PM PST",
    "event_type": "returned",
    "idle_seconds": 0,
    "duration_minutes": 120.5,
    "is_afk": false,
    "is_potentially_afk": false
  },
  ...
]
```

**Wake Segments Log:**
```json
[
  {
    "id": 789,
    "start_time": "2026-01-07 03:00:00 AM PST",
    "end_time": "2026-01-07 03:15:00 AM PST",
    "duration_minutes": 15,
    "source": "user_chat",
    "notes": "bathroom"
  },
  ...
]
```

---

## Next Steps

The orchestrator pipeline debug UI is now complete with:
- ✅ All orchestrator input files
- ✅ Database telemetry logs
- ✅ Legacy files for comparison
- ✅ Auto-refresh capability
- ✅ Manual trigger buttons

**Ready for use!** 🎯
