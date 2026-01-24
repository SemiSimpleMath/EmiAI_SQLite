# Sleep Data Reconciliation Strategy

**Date:** 2026-01-08  
**Issue:** We have 3 sources of sleep data that must be reconciled for accuracy

---

## The Three Sources

### 1. `sleep_segments` table
- **What**: Recorded sleep periods (continuous blocks)
- **Source**: AFK detection, user chat, cold start
- **Example**: `11:00 PM - 7:00 AM` (8 hours)
- **Strength**: Marks confirmed sleep periods
- **Weakness**: Doesn't capture wake-ups during sleep

### 2. `wake_segments` table
- **What**: Periods when user was awake during sleep hours
- **Source**: User chat ("I woke up at 3 AM for bathroom")
- **Example**: `3:00 AM - 3:30 AM` (30 min awake)
- **Strength**: Captures interruptions user remembers
- **Weakness**: Relies on user reporting

### 3. `afk_events` table
- **What**: Raw AFK state changes (went_afk, returned)
- **Source**: System idle detection
- **Example**: `went_afk at 11:05 PM`, `returned at 7:05 AM`
- **Strength**: Objective, automatic, high resolution
- **Weakness**: Can't distinguish sleep from other long AFK

---

## The Problem

**Current implementation:** Only uses `sleep_segments` table for `calculate_last_night_sleep()`

**Missing:** Wake segments that interrupt sleep

**Example scenario:**
```
sleep_segments:
- 11:00 PM - 7:00 AM (8 hours)

wake_segments:
- 3:00 AM - 3:30 AM (bathroom, 30 min)

Current calculation: 8 hours sleep ❌
Actual sleep: 7.5 hours sleep ✅ (8 hours - 30 min wake)
```

---

## Reconciliation Strategy

### Principle: Build a Timeline

**Step 1: Collect all events in time order**
```python
events = [
    {"type": "sleep_start", "time": "11:00 PM", "source": "sleep_segments"},
    {"type": "wake_start", "time": "3:00 AM", "source": "wake_segments"},
    {"type": "wake_end", "time": "3:30 AM", "source": "wake_segments"},
    {"type": "sleep_end", "time": "7:00 AM", "source": "sleep_segments"},
]
```

**Step 2: Calculate actual sleep**
```python
sleep_segments = [
    ("11:00 PM", "3:00 AM"),   # 4 hours
    ("3:30 AM", "7:00 AM")     # 3.5 hours
]
total_sleep = 7.5 hours
wake_interruptions = 0.5 hours
```

### Algorithm: Subtract Wake Segments from Sleep Segments

```python
def reconcile_sleep_data(sleep_segments, wake_segments):
    """
    Reconcile sleep and wake segments to get accurate sleep duration.
    
    Args:
        sleep_segments: List of {start, end, duration_minutes, source}
        wake_segments: List of {start_time, end_time, duration_minutes, notes}
    
    Returns:
        {
            "total_sleep_minutes": float,
            "total_wake_minutes": float,
            "sleep_periods": [...],  # After subtracting wakes
            "wake_interruptions": [...],
            "fragmented": bool
        }
    """
    # 1. Build timeline of sleep/wake events
    events = []
    
    for seg in sleep_segments:
        events.append({
            "type": "sleep_start",
            "time": parse_time(seg["start"]),
            "segment_id": seg["id"]
        })
        events.append({
            "type": "sleep_end",
            "time": parse_time(seg["end"]),
            "segment_id": seg["id"]
        })
    
    for wake in wake_segments:
        events.append({
            "type": "wake_start",
            "time": parse_time(wake["start_time"]),
            "wake_id": wake["id"],
            "notes": wake["notes"]
        })
        events.append({
            "type": "wake_end",
            "time": parse_time(wake["end_time"]) if wake["end_time"] else None,
            "wake_id": wake["id"]
        })
    
    # 2. Sort by time
    events.sort(key=lambda e: e["time"])
    
    # 3. Walk through timeline, track state
    state = "awake"  # Start awake
    current_segment_start = None
    sleep_periods = []
    wake_interruptions = []
    
    for event in events:
        if event["type"] == "sleep_start":
            if state == "awake":
                state = "sleeping"
                current_segment_start = event["time"]
        
        elif event["type"] == "wake_start":
            if state == "sleeping" and current_segment_start:
                # End current sleep segment
                sleep_periods.append({
                    "start": current_segment_start,
                    "end": event["time"],
                    "duration_minutes": (event["time"] - current_segment_start).total_seconds() / 60
                })
                current_segment_start = None
            
            state = "awake_during_sleep"
            wake_interruptions.append({
                "start": event["time"],
                "notes": event.get("notes")
            })
        
        elif event["type"] == "wake_end":
            if state == "awake_during_sleep":
                state = "sleeping"
                current_segment_start = event["time"]
                # Complete wake interruption
                if wake_interruptions:
                    wake_interruptions[-1]["end"] = event["time"]
                    wake_interruptions[-1]["duration_minutes"] = (
                        event["time"] - wake_interruptions[-1]["start"]
                    ).total_seconds() / 60
        
        elif event["type"] == "sleep_end":
            if state == "sleeping" and current_segment_start:
                # End current sleep segment
                sleep_periods.append({
                    "start": current_segment_start,
                    "end": event["time"],
                    "duration_minutes": (event["time"] - current_segment_start).total_seconds() / 60
                })
                current_segment_start = None
            
            state = "awake"
    
    # 4. Calculate totals
    total_sleep_minutes = sum(p["duration_minutes"] for p in sleep_periods)
    total_wake_minutes = sum(w.get("duration_minutes", 0) for w in wake_interruptions)
    
    return {
        "total_sleep_minutes": total_sleep_minutes,
        "total_wake_minutes": total_wake_minutes,
        "sleep_periods": sleep_periods,
        "wake_interruptions": wake_interruptions,
        "fragmented": len(sleep_periods) > 1
    }
```

---

## Integration Points

### 1. Update `calculate_last_night_sleep()`

**File:** `app/assistant/physical_status_manager/sleep_segment_tracker.py`

```python
def calculate_last_night_sleep(self, wake_time, last_day_start):
    # 1. Get sleep segments from database
    sleep_segments = get_sleep_segments_last_24_hours()
    
    # 2. Get wake segments from database
    wake_segments = get_wake_segments_last_24_hours()
    
    # 3. Reconcile
    reconciled = reconcile_sleep_data(sleep_segments, wake_segments)
    
    # 4. Return enriched data
    return {
        "total_minutes": reconciled["total_sleep_minutes"],
        "total_hours": reconciled["total_sleep_minutes"] / 60,
        "sleep_periods": reconciled["sleep_periods"],
        "wake_interruptions": reconciled["wake_interruptions"],
        "fragmented": reconciled["fragmented"],
        "quality": determine_quality(reconciled),
        # ...
    }
```

### 2. Use AFK Events for Validation

**Optional enhancement:** Cross-check sleep segments against raw AFK events

```python
def validate_sleep_segment_with_afk_events(sleep_segment, afk_events):
    """
    Validate a sleep segment against raw AFK events.
    
    Useful for detecting:
    - Unreported wake-ups (brief returned events during sleep)
    - Sleep segment accuracy
    """
    sleep_start = parse_time(sleep_segment["start"])
    sleep_end = parse_time(sleep_segment["end"])
    
    # Find AFK events during this sleep period
    events_during_sleep = [
        e for e in afk_events
        if sleep_start <= parse_time(e["timestamp"]) <= sleep_end
    ]
    
    # Look for "returned" events (potential wake-ups)
    returns = [e for e in events_during_sleep if e["event_type"] == "returned"]
    
    if returns:
        logger.info(f"Found {len(returns)} brief returns during sleep - possible unreported wake-ups")
        # Could auto-create wake segments, or flag for user review
    
    return {
        "validated": True,
        "potential_wake_ups": returns
    }
```

---

## Priority

### P0 (Critical - Do Now):
✅ Create `reconcile_sleep_data()` function  
✅ Update `calculate_last_night_sleep()` to use reconciliation  
✅ Test with real data (sleep + wake segments)

### P1 (Important):
- Add reconciliation to `sleep_data_generator.py` for resource file
- Display wake interruptions in debug UI
- Show fragmented sleep in LLM prompts

### P2 (Nice to Have):
- Use AFK events for validation
- Auto-detect unreported wake-ups from brief "returned" events
- Flag suspicious sleep segments for review

---

## Testing

### Test Case 1: Simple Sleep (no interruptions)
```
sleep_segments: 11 PM - 7 AM
wake_segments: (none)
Expected: 8 hours sleep, not fragmented
```

### Test Case 2: Bathroom Break
```
sleep_segments: 11 PM - 7 AM
wake_segments: 3 AM - 3:30 AM (bathroom)
Expected: 7.5 hours sleep, fragmented, 1 wake interruption
```

### Test Case 3: Insomnia
```
sleep_segments: 11 PM - 7 AM
wake_segments: 
  - 2 AM - 3 AM (couldn't sleep)
  - 4 AM - 4:15 AM (bathroom)
Expected: 6.75 hours sleep, fragmented, 2 wake interruptions
```

### Test Case 4: Multiple Sleep Segments
```
sleep_segments:
  - 11 PM - 3 AM (4h)
  - 4 AM - 7 AM (3h)
wake_segments: 3 AM - 4 AM (awake)
Expected: 7 hours sleep, fragmented, 1 wake interruption
```

---

## Data Quality

### Conflict Resolution Rules

**Conflict 1: Wake segment outside sleep segment**
```
sleep_segments: 11 PM - 7 AM
wake_segments: 8 AM - 8:30 AM
Resolution: Ignore wake segment (outside sleep window)
```

**Conflict 2: Wake segment longer than sleep segment**
```
sleep_segments: 11 PM - 7 AM (8h)
wake_segments: 2 AM - 9 AM (7h)
Resolution: Log warning, cap wake to sleep bounds (2 AM - 7 AM = 5h wake)
```

**Conflict 3: Overlapping wake segments**
```
wake_segments:
  - 3 AM - 4 AM
  - 3:30 AM - 4:30 AM
Resolution: Merge to single wake (3 AM - 4:30 AM)
```

---

## Implementation File

**New file needed:** `app/assistant/physical_status_manager/sleep_reconciliation.py`

This will contain:
- `reconcile_sleep_data()` - main reconciliation function
- `merge_overlapping_wakes()` - handle overlaps
- `validate_segment_bounds()` - check for conflicts
- `build_sleep_timeline()` - create ordered event timeline

---

## Next Steps

1. Create `sleep_reconciliation.py` with reconciliation logic
2. Update `calculate_last_night_sleep()` to use reconciliation
3. Update `generate_sleep_resource_file()` to include wake interruptions
4. Add wake interruptions display to debug UI
5. Test with all 4 test cases

This is a critical piece for accurate sleep tracking! Should I implement this now?
