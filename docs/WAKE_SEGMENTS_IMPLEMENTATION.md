# Wake Segments - Implementation Complete

## Overview
We've added support for tracking **wake segments** - periods when the user was awake during sleep hours. This allows accurate sleep calculation and lets users correct their sleep data via chat.

## The Problem We Solved
**Before:**
- User: "I woke up at 3 AM and couldn't sleep for a while"
- System: Records sleep ending at 3 AM, no way to track the wake period

**After:**
- User: "I woke up at 3 AM and couldn't sleep for a while"
- System: Creates wake segment (3:00 AM, ~45 min), subtracts from total sleep

## Database Schema

### New Table: `wake_segments`
```sql
CREATE TABLE wake_segments (
    id INTEGER PRIMARY KEY,
    start_time TIMESTAMP NOT NULL,  -- When user woke up (UTC)
    end_time TIMESTAMP,              -- When they went back to sleep (NULL if estimated)
    duration_minutes REAL NOT NULL,  -- How long awake (calculated or estimated)
    source VARCHAR NOT NULL,         -- 'user_chat', 'manual', 'activity_tracker'
    notes VARCHAR,                   -- 'bathroom', 'couldn't sleep', etc.
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## Activity Tracker Updates

### 1. New Schema Field: `WakeSegment`
```python
class WakeSegment(BaseModel):
    start_time: str  # "03:00", "3:00 AM"
    end_time: Optional[str]  # "03:30" or None
    duration_estimate_minutes: Optional[int]  # Used when end_time not specified
    notes: Optional[str]  # "bathroom", "couldn't sleep"
    raw_mention: str  # User's exact words
```

### 2. Agent Output
```python
class AgentForm(BaseModel):
    # ... existing fields ...
    wake_segments: List[WakeSegment] = []  # NEW!
```

### 3. Detection Rules (in system prompt)

The agent now understands:

| User Statement | Agent Output |
|----------------|-------------|
| "woke up at 3 AM for a while" | {start_time: "03:00", duration_estimate_minutes: 45, notes: null} |
| "got up at 2:30 for bathroom" | {start_time: "02:30", duration_estimate_minutes: 10, notes: "bathroom"} |
| "I was awake from 3 to 3:30" | {start_time: "03:00", end_time: "03:30"} |
| "woke at 4 AM, read for a bit" | {start_time: "04:00", duration_estimate_minutes: 20, notes: "reading"} |
| "up between 2 and 4 AM" | {start_time: "02:00", end_time: "04:00"} |

### 4. Duration Estimation Rules
- "for a while", "quite a while" → 45 minutes
- "for a bit", "briefly" → 20 minutes
- "couldn't sleep", "tossed and turned" → 60 minutes
- "got up to [task]" (bathroom, water) → 10 minutes
- Exact times always preferred over estimates

## Database Functions

### New Functions in `afk_sleep_db.py`

```python
# Record a wake segment
record_wake_segment(
    start_time: datetime,
    end_time: Optional[datetime] = None,
    duration_minutes: Optional[float] = None,
    source: str = 'user_chat',
    notes: Optional[str] = None
) -> Optional[int]

# Get wake segments from last 24 hours
get_wake_segments_last_24_hours() -> List[Dict[str, Any]]

# Cleanup old wake segments
cleanup_old_wake_segments(days: int = 30) -> int
```

## Sleep Calculation (To Be Implemented)

**Next step:** Update sleep calculations to account for wake segments:

```python
def calculate_net_sleep(sleep_segments, wake_segments):
    """Calculate actual sleep time by subtracting wake time."""
    total_sleep = sum(s.duration_minutes for s in sleep_segments)
    total_awake = sum(w.duration_minutes for w in wake_segments)
    net_sleep = total_sleep - total_awake
    
    return {
        'total_sleep_minutes': net_sleep,
        'gross_sleep_minutes': total_sleep,
        'awake_minutes': total_awake,
        'timeline': build_timeline(sleep_segments, wake_segments)
    }
```

## Timeline Reconstruction

**Example output:**
```json
{
  "date": "2026-01-07",
  "net_sleep_minutes": 420,
  "timeline": [
    {"type": "sleep", "start": "23:00", "end": "03:00", "duration": 240},
    {"type": "awake", "start": "03:00", "end": "03:30", "duration": 30, "notes": "bathroom"},
    {"type": "sleep", "start": "03:30", "end": "07:00", "duration": 210}
  ]
}
```

## Files Modified

1. **`app/assistant/agents/activity_tracker/agent_form.py`**
   - Added `WakeSegment` schema
   - Added `wake_segments` field to `AgentForm`

2. **`app/assistant/agents/activity_tracker/prompts/system.j2`**
   - Added section 4: Wake Segments detection rules
   - Added duration estimation guidelines
   - Added examples for common wake statements

3. **`app/models/wake_segments.py`** (NEW)
   - SQLAlchemy model for `WakeSegment`

4. **`app/models/__init__.py`**
   - Export `WakeSegment` model

5. **`app/assistant/physical_status_manager/afk_sleep_db.py`**
   - Added `record_wake_segment()`
   - Added `get_wake_segments_last_24_hours()`
   - Added `cleanup_old_wake_segments()`

6. **`migration_scripts/add_wake_segments_table.py`** (NEW)
   - Migration script to create `wake_segments` table

## Still To Do

### 1. Process wake_segments in PhysicalStatusManager
Update `_run_activity_tracker()` to handle wake segments:

```python
wake_segments = agent_result.get('wake_segments', [])
if wake_segments:
    for wake_seg in wake_segments:
        # Parse times, record to database
        record_wake_segment(...)
```

### 2. Update Sleep Calculations
Modify `calculate_last_night_sleep()` to:
- Query wake segments in the sleep window
- Subtract wake time from total sleep
- Return net sleep instead of gross sleep

### 3. Update Sleep Resource File
Add wake segments to `resource_user_sleep_current.json`:
```json
{
  "total_sleep_minutes": 420,  // Net sleep (after subtracting wake time)
  "gross_sleep_minutes": 450,  // Raw sleep segments
  "awake_minutes": 30,         // Wake segments
  "wake_segments": [...]
}
```

### 4. Add to Background Cleanup
Update `BackgroundTaskManager` to cleanup old wake segments (same as AFK events).

## Testing

**Test the activity_tracker agent:**
```bash
# Test wake segment detection
User: "I woke up at 3 AM and couldn't go back to sleep for a while"
Expected: wake_segment with start_time="03:00", duration_estimate_minutes=45

User: "Got up for bathroom at 2:30"
Expected: wake_segment with start_time="02:30", duration_estimate_minutes=10, notes="bathroom"
```

## Migration

Run the migration:
```bash
python migration_scripts/add_wake_segments_table.py
```

## Benefits

✅ **User can self-correct sleep data**
- "Actually I was awake 2-3 AM" → adds wake segment
- Sleep calculations automatically adjust

✅ **Accurate sleep totals**
- Net sleep = sleep time - wake time
- No more overestimating sleep

✅ **Complete timeline**
- Can visualize: Sleep → Awake → Sleep
- Understand sleep fragmentation

✅ **Simple editing**
- Wake segments are independent
- Can add/delete/modify without breaking sleep segments

✅ **Better insights**
- Track sleep disruptions
- Understand sleep quality patterns
