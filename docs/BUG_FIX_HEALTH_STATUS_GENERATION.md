# Bug Fix: AttributeError in Health Status Resource Generation

**Date:** 2026-01-07  
**Status:** ✅ Fixed

---

## Error

```
AttributeError: 'DayStartManager' object has no attribute 'get_day_start_datetime'
```

**Location:** `app/assistant/physical_status_manager/physical_status_manager.py` line 364

**Context:** Called from `_generate_and_save_health_status_resource()` when trying to get the day start time for AFK statistics calculation.

---

## Root Cause

The method `get_day_start_datetime()` doesn't exist on `DayStartManager`. The day_start_time is actually stored directly in `self.status_data["day_start_time"]` as an ISO string.

---

## Fix

**Changed from:**
```python
day_start_dt = self.day_start_manager.get_day_start_datetime()
afk_stats = get_afk_statistics(day_start_dt=day_start_dt)
```

**Changed to:**
```python
# Get day_start_time from status_data
day_start_time_str = self.status_data.get("day_start_time")
if day_start_time_str:
    day_start_dt = datetime.fromisoformat(day_start_time_str.replace("Z", "+00:00"))
    if day_start_dt.tzinfo is None:
        day_start_dt = day_start_dt.replace(tzinfo=timezone.utc)
else:
    # Default to midnight if no day_start_time set
    day_start_dt = now.replace(hour=0, minute=0, second=0, microsecond=0)

# Get AFK statistics (pythonic)
afk_stats = get_afk_statistics(day_start_time=day_start_dt)
```

---

## Additional Fixes

Also fixed the parameter name passed to `get_afk_statistics()`:
- Changed `day_start_dt` → `day_start_time` (to match function signature)

---

## Verification

The fix:
1. ✅ Reads `day_start_time` from `self.status_data`
2. ✅ Parses ISO string to datetime
3. ✅ Ensures timezone awareness
4. ✅ Provides sensible default (midnight) if not set
5. ✅ Passes correct parameter name to `get_afk_statistics()`

---

## Testing

The health status resource should now generate successfully when `PhysicalStatusManager.refresh()` runs.

**Expected behavior:**
- `resource_user_health_status.json` created in `resources/` folder
- No AttributeError
- AFK statistics correctly computed from day_start_time
