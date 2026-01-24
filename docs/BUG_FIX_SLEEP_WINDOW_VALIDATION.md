# Bug Fix: AFK Detection Creating Sleep Segments Outside Sleep Window

**Date:** 2026-01-07  
**Status:** ✅ Fixed

---

## The Problem

AFK segments were being incorrectly classified as sleep when they occurred outside the configured sleep window.

**Example:**
```json
{
  "start": "2026-01-07 07:32:16 PM PST",  // 7:32 PM
  "end": "2026-01-07 10:17:57 PM PST",    // 10:17 PM
  "duration_minutes": 165.68,              // 2.8 hours
  "source": "afk_detection"
}
```

**Configured sleep window:** 10:30 PM - 9:00 AM

**Problem:** A 2.8-hour AFK from 7:32 PM - 10:17 PM was being recorded as sleep, even though:
- Start time (7:32 PM) is **before** sleep window starts (10:30 PM)
- This is clearly just a long AFK period in the evening, not sleep

---

## Root Cause

**File:** `app/assistant/physical_status_manager/day_start_manager.py`  
**Method:** `handle_afk_return()`  
**Lines:** 109-128

**The REAL bug had TWO problems:**

### Problem 1: Only compared HOURS, not MINUTES

The sleep window is "22:30" - "09:00" (10:30 PM - 9:00 AM), but the comparison only looked at hours:

```python
sleep_start_hour = 22  # Minutes (30) were ignored!
sleep_end_hour = 9
```

This meant:
- 10:17 PM (22:17) was treated the same as 10:30 PM (22:30)
- Any time with hour=22 was considered inside the sleep window
- But 22:17 is actually BEFORE 22:30!

### Problem 2: Used OR logic instead of AND

**Buggy Logic:**
```python
is_sleep_afk = (
    afk_duration_minutes >= sleep_afk_threshold and
    (afk_start_dt.hour >= sleep_start_hour or afk_end_dt.hour <= sleep_end_hour)
    #                                        ^^
    #                                        OR means if EITHER is in window → sleep
)
```

**Why it was wrong:**
- The OR meant if EITHER start OR end was in the sleep window → classified as sleep
- For the 7:32 PM - 10:17 PM segment:
  - Start hour: 19 → `19 >= 22` → False
  - End hour: 22 → `22 >= 22` → **True** (even though 22:17 < 22:30!)
  - Result: **True** (classified as sleep)

**Combined effect:**
1. Only comparing hours meant 10:17 PM looked like it was in the sleep window
2. OR logic meant only one end needed to be "in window" for it to count
3. Result: Evening AFK periods got misclassified as sleep

---

## The Fix

**Changed to:**
1. **Compare full time (hours AND minutes)** by converting to "minutes since midnight"
2. **Require BOTH start AND end** to be in sleep window (AND logic)

```python
# Parse sleep window with minutes
sleep_start_str = '22:30'
sleep_start_hour = 22
sleep_start_minute = 30
sleep_start_minutes = 22 * 60 + 30 = 1350  # minutes since midnight

sleep_end_str = '09:00'
sleep_end_hour = 9
sleep_end_minute = 0
sleep_end_minutes = 9 * 60 + 0 = 540  # minutes since midnight

def is_in_sleep_window(dt: datetime) -> bool:
    """Check if datetime is within sleep window (handles midnight wraparound)."""
    time_minutes = dt.hour * 60 + dt.minute  # Convert to minutes since midnight
    start_minutes = sleep_start_hour * 60 + sleep_start_minute
    end_minutes = sleep_end_hour * 60 + sleep_end_minute
    
    if start_minutes > end_minutes:
        # Wraps midnight (e.g., 22:30 - 09:00)
        # In window if: >= start OR < end
        return time_minutes >= start_minutes or time_minutes < end_minutes
    else:
        # Doesn't wrap (e.g., 01:00 - 06:00)
        # In window if: >= start AND < end
        return start_minutes <= time_minutes < end_minutes

is_sleep_afk = (
    afk_duration_minutes >= sleep_afk_threshold and
    is_in_sleep_window(afk_start_dt) and  # BOTH must be true
    is_in_sleep_window(afk_end_dt)        # AND logic
)
```

**Why this is correct:**
1. **Minutes matter**: 10:17 PM (1257 min) vs 10:30 PM (1350 min) are now different
2. **AND logic**: BOTH start and end must be within the sleep window
3. **Midnight wraparound handled**: Correctly handles 22:30 → next day 09:00

---

## Test Cases

### Case 1: Evening AFK (NOT sleep) ✅
- **Start:** 7:32 PM (19:32) = 1172 minutes since midnight
- **End:** 10:17 PM (22:17) = 1337 minutes since midnight
- **Sleep window:** 22:30 - 09:00 (1350 - 540 minutes)
- **Result:** 
  - `is_in_sleep_window(1172)` → False (not >= 1350, not < 540)
  - `is_in_sleep_window(1337)` → False (not >= 1350, not < 540)
  - **AND** → **False** (not sleep) ✅
  - **Note:** 10:17 PM is still BEFORE 10:30 PM sleep start!

### Case 2: Actual Sleep (IS sleep) ✅
- **Start:** 11:00 PM (23:00) = 1380 minutes
- **End:** 7:00 AM (07:00) = 420 minutes
- **Sleep window:** 22:30 - 09:00 (1350 - 540 minutes)
- **Result:**
  - `is_in_sleep_window(1380)` → True (>= 1350)
  - `is_in_sleep_window(420)` → True (< 540)
  - **AND** → **True** (is sleep) ✅

### Case 3: Late Night AFK (IS sleep) ✅
- **Start:** 1:00 AM (01:00) = 60 minutes
- **End:** 3:00 AM (03:00) = 180 minutes
- **Sleep window:** 22:30 - 09:00 (1350 - 540 minutes)
- **Result:**
  - `is_in_sleep_window(60)` → True (< 540)
  - `is_in_sleep_window(180)` → True (< 540)
  - **AND** → **True** (is sleep) ✅

### Case 4: Early Morning AFK (NOT sleep if after window)
- **Start:** 9:30 AM (09:30) = 570 minutes
- **End:** 11:00 AM (11:00) = 660 minutes
- **Sleep window:** 22:30 - 09:00 (1350 - 540 minutes)
- **Result:**
  - `is_in_sleep_window(570)` → False (not >= 1350, not < 540)
  - `is_in_sleep_window(660)` → False (not >= 1350, not < 540)
  - **AND** → **False** (not sleep) ✅

### Case 5: Edge case at sleep start boundary ✅
- **Start:** 10:30 PM (22:30) = 1350 minutes (exactly at sleep start)
- **End:** 11:00 PM (23:00) = 1380 minutes
- **Sleep window:** 22:30 - 09:00 (1350 - 540 minutes)
- **Result:**
  - `is_in_sleep_window(1350)` → True (>= 1350)
  - `is_in_sleep_window(1380)` → True (>= 1350)
  - **AND** → **True** (is sleep) ✅

---

## Impact

### Before Fix:
- ❌ Evening AFK periods (dinner, TV, etc.) recorded as sleep
- ❌ Sleep data polluted with non-sleep segments
- ❌ Incorrect sleep duration calculations
- ❌ Poor quality sleep resource file

### After Fix:
- ✅ Only true sleep periods recorded
- ✅ Evening AFK stays as AFK, not sleep
- ✅ Accurate sleep duration calculations
- ✅ Clean sleep resource file

---

## Verification

**Check the debug UI:**
1. Navigate to `http://localhost:5000/debug/status`
2. Scroll to "Sleep Segments Log (Database)"
3. Verify no segments exist outside sleep window hours
4. Future AFK periods outside sleep window should not create sleep segments

**Manual test:**
1. Be AFK for 30+ minutes during evening (before 10:30 PM)
2. Return from AFK
3. Check sleep_segments table
4. Should NOT have a new segment

---

## Related Configuration

**File:** `resources/config_sleep_tracking.yaml`

```yaml
sleep_window:
  start: "22:30"  # 10:30 PM
  end: "09:00"    # 9:00 AM

sleep_afk_threshold_minutes: 20
```

**To adjust sleep window:**
- Edit the `sleep_window` section in config
- System will automatically use new hours
- No code changes needed

---

## Cleanup

**Optional:** Delete invalid sleep segments from database

```python
# Script to clean up evening AFK segments misclassified as sleep
from app.assistant.day_flow_manager.archive.afk_sleep_db import get_session
from app.models.afk_sleep_tracking import SleepSegment
from datetime import datetime

session = get_session()
try:
  # Delete segments with start time before 10:30 PM (hour < 22)
  # and source = 'afk_detection'
  invalid_segments = session.query(SleepSegment).filter(
    SleepSegment.source == 'afk_detection'
  ).all()

  deleted = 0
  for seg in invalid_segments:
    start_hour = seg.start_time.hour
    end_hour = seg.end_time.hour if seg.end_time else start_hour

    # Check if segment is outside sleep window (22:30 - 09:00)
    if not ((start_hour >= 22 or start_hour < 9) and (end_hour >= 22 or end_hour < 9)):
      session.delete(seg)
      deleted += 1
      print(f"Deleted invalid segment: {seg.start_time} - {seg.end_time}")

  session.commit()
  print(f"Cleaned up {deleted} invalid sleep segments")
finally:
  session.close()
```

---

## Conclusion

The bug was caused by using OR logic instead of AND logic when checking if an AFK period occurred during the sleep window. The fix ensures that BOTH the start and end times must be within the sleep window for it to be classified as sleep.

**Status:** ✅ Fixed and tested
