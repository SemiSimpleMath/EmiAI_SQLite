# Cold Start vs Restart Sleep Logic - Fixed

## Problem
When Flask restarts, the system was:
1. Creating synthetic "cold_start_assumed" sleep segments even when database had real data
2. Setting `day_start_time` to the restart time (e.g., 10:45 PM) instead of actual wake time (e.g., 9:39 AM)
3. On true cold start (no data), using restart time instead of typical wake time from config

## Root Cause
The "cold start" logic didn't distinguish between:
- **TRUE cold start**: First time ever, no database data → needs synthetic sleep at typical wake time
- **Restart**: Flask restarted, but database has real sleep data → should use existing data

## Solution

### 1. Check for Database Data First
```python
existing_segments = get_sleep_segments_last_24_hours()
has_database_data = len(existing_segments) > 0
```

### 2. Branch Logic Based on Data Availability

**If database has data (RESTART):**
- Use existing sleep segments from database
- Find the most recent sleep segment end time = actual wake time
- Set `day_start_time` to actual wake time (NOT restart time)
- No synthetic segments created

**If no database data (TRUE COLD START):**
- Get typical wake time from config (e.g., 07:00 from `normal_sleep.end`)
- Create synthetic "cold_start_assumed" segment ending at typical wake time
- Set `day_start_time` to typical wake time (NOT restart time)
- This synthetic data will naturally "age out" as real data accumulates

### 3. Use Meaningful Timestamps

**Restart scenario:**
```python
# Determine actual wake time from most recent sleep segment
latest_segment = max(existing_segments, key=lambda s: s['end'])
wake_time_dt = datetime.fromisoformat(latest_segment['end'].replace('Z', '+00:00'))
actual_wake_time = wake_time_dt

# Use this as day_start_time
self.status_data["day_start_time"] = actual_wake_time.isoformat()
```

**True cold start scenario:**
```python
# Get typical wake time from config (e.g., 07:00)
typical_wake_time_str = self.config_loader.get_typical_wake_time()
wake_hour, wake_minute = typical_wake_time_str.split(':')

# Create datetime for typical wake time today
typical_wake_local = now_local.replace(hour=int(wake_hour), minute=int(wake_minute))
typical_wake_utc = local_to_utc(typical_wake_local)

# Use this as day_start_time (NOT restart time!)
self.status_data["day_start_time"] = typical_wake_utc.isoformat()
```

## Result

### Before Fix:
- Restart at 10:45 PM → creates 8.5h synthetic sleep ending at 10:45 PM
- `day_start_time`: 2026-01-06 10:45 PM (wrong! restart time)
- Multiple overlapping sleep segments in resource file
- True cold start at 2 AM → `day_start_time`: 2:00 AM (wrong! restart time)

### After Fix:
- **Restart at 10:45 PM** → uses existing database data
  - `day_start_time`: 2026-01-06 09:39 AM (correct! actual wake time from DB)
- **True cold start at 2 AM** → creates synthetic sleep ending at 07:00 AM
  - `day_start_time`: 2026-01-07 07:00 AM (correct! typical wake time from config)
- Clean, accurate sleep data from database or meaningful defaults

## Configuration
The typical wake time comes from `resources/config_sleep_tracking.yaml`:
```yaml
normal_sleep:
  start: "22:30"  # Typical bedtime
  end: "07:00"    # Typical wake time ← Used for cold start day_start_time
  duration_hours: 8.5
```

## Files Modified
- `app/assistant/physical_status_manager/day_start_manager.py`
  - `_trigger_cold_start_day()`: Added database check, actual wake time logic, and typical wake time for true cold starts
- `app/assistant/physical_status_manager/sleep_config_loader.py`
  - `get_typical_wake_time()`: New method to retrieve typical wake time from config

## Testing
```bash
# Check what scenario applies
python test_cold_start_logic.py

# Verify actual wake time would be used (restart)
python test_day_start_time.py

# Verify typical wake time would be used (true cold start)
python test_typical_wake_time.py

# Restart Flask and verify day_start_time uses wake time, not restart time
```

## Key Insight
**"Cold start" for sleep tracking means NO DATABASE DATA, not just Flask restart!**
- Database persists across restarts
- Only create synthetic sleep on first-ever run
- Use typical wake time (7 AM) from config, not random restart time
- Always prefer real data from database over assumptions
- **Restart time is meaningless - only event times matter!**
