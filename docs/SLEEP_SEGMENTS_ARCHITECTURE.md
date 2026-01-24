# Sleep Segments Architecture - Current State

## The Problem You've Identified

You're seeing a **mixed bag** of data in the `sleep_segments` table:

```json
[
  {
    "id": 6,
    "start": "2026-01-07 07:32:16 PM PST",
    "end": "2026-01-07 10:17:57 PM PST",
    "source": "afk_detection",  // ❌ WRONG - this was during awake hours
    "duration_minutes": 165.68
  },
  {
    "id": 5,
    "start": "2026-01-04 11:07:00 PM PST",
    "end": "2026-01-07 03:00:00 AM PST",
    "source": "user_chat",  // ✅ User said this
    "duration_minutes": 3113
  }
]
```

**Issues:**
1. **System-detected sleep segments** are being stored permanently in the database
2. These are **mixed with user-reported segments**, making it hard to distinguish
3. The system is **computing bad segments** (7:32 PM - 10:17 PM is NOT sleep!)
4. The database becomes a "junk drawer" of both good and bad data

---

## Current Architecture (How It Works Now)

### 1. Three Data Sources

| Source | Description | Storage |
|--------|-------------|---------|
| **AFK Events** | Raw computer idle/active state changes | `afk_events` table |
| **Sleep Segments (System)** | Sleep inferred from long AFK periods | `sleep_segments` table (source='afk_detection') |
| **Sleep Segments (User)** | User says "I slept from X to Y" | `sleep_segments` table (source='user_chat') |
| **Wake Segments (User)** | User says "I woke up at 3 AM for a bit" | `wake_segments` table |

### 2. Where System Sleep Segments Are Created

**File:** `app/assistant/physical_status_manager/day_start_manager.py`, line 229

```python
def handle_afk_return(self, afk_info: Dict[str, Any], now: datetime, now_local: datetime):
    # ...
    
    # Classify: is this AFK period sleep-like?
    if self._classify_sleep_candidate(afk_start_local, afk_end_local):
        # It's sleep! Record it to database ⚠️
        self.sleep_tracker.record_sleep_segment(afk_start_dt, afk_end_dt, source="afk_detection")
        # ...
```

**When this runs:**
- Every time user returns from AFK
- If AFK period >= 120 min AND 60% overlap with sleep window (10:30 PM - 9:00 AM)
- **Immediately writes to database** ← This is the issue

### 3. Where User Sleep Segments Are Created

**File:** `app/assistant/physical_status_manager/sleep_segment_tracker.py`, line 363

```python
def process_sleep_events(self, sleep_events: List[Dict[str, Any]]):
    for event in sleep_events:
        if start_time_str and end_time_str:
            # User said "I slept from X to Y"
            self.record_sleep_segment(start_dt, end_dt, source="user_chat")
```

**When this runs:**
- When `activity_tracker` agent detects sleep mentions in chat
- User says things like "I slept from 10 PM to 6 AM"

### 4. Reconciliation (When Computing Last Night's Sleep)

**File:** `app/assistant/physical_status_manager/sleep_reconciliation.py`

```python
def reconcile_sleep_data(sleep_segments, wake_segments):
    # 1. Filter out system segments that overlap with user segments
    # 2. Build timeline of sleep/wake events
    # 3. Walk timeline and compute net sleep
```

**Hierarchy:**
1. User sleep segments (replace overlapping system segments)
2. User wake segments (subtract from sleep segments)
3. System sleep segments (only if no user data for that period)

---

## The Problem

### Current Flow (Broken)

```
AFK Period Detected
       ↓
  Classify as sleep?
       ↓ YES
  Write to database ← ❌ Too early! Bad data gets stored
       ↓
  (Later) Reconcile when computing sleep
       ↓
  Use reconciliation to override bad data
```

**Why this is bad:**
1. Database becomes polluted with false positives (7:32 PM - 10:17 PM)
2. User segments and system segments are mixed in same table
3. Reconciliation happens at read time, not write time
4. Debugging is confusing (is this junk data or real data?)

---

## What You Want (Better Architecture)

### Option A: Don't Store System Sleep Segments (Clean Separation)

```
AFK Events Table (raw telemetry)
     ↓
Compute sleep on-the-fly when needed
     ↓
Reconcile with user segments
     ↓
Use reconciled data for calculations
```

**Changes:**
- Remove `self.sleep_tracker.record_sleep_segment(..., source="afk_detection")` from `day_start_manager.py`
- Keep AFK events only
- Compute sleep from AFK events at read time
- Store only user-reported segments in `sleep_segments` table

**Pros:**
- Clean separation: `sleep_segments` = ground truth (user said), `afk_events` = raw telemetry
- No junk data in database
- Easy to understand what's in the database

**Cons:**
- Slightly slower (compute from AFK events each time)
- But you already query AFK events anyway for reconciliation

### Option B: Tag System Segments as "Provisional" (Keep Current)

```
Sleep Segments Table
├── source='user_chat' (permanent, ground truth)
├── source='afk_detection' (provisional, can be wrong)
└── source='cold_start_assumed' (fallback)
```

**Changes:**
- Keep current behavior
- Rely on reconciliation to filter bad segments
- Add cleanup job to delete old system segments (> 7 days)

**Pros:**
- No code changes needed (reconciliation already handles this)
- Can debug system sleep detection by looking at DB

**Cons:**
- Database contains junk data
- Confusing when you look at raw segments

---

## My Recommendation: Option A (Don't Store System Segments)

### Why?

1. **You already have the raw data**: `afk_events` table contains everything needed to compute sleep
2. **Cleaner mental model**: 
   - `afk_events` = raw telemetry (system observed)
   - `sleep_segments` = ground truth (user confirmed)
   - `wake_segments` = corrections (user confirmed)
3. **No junk data**: Database only contains trustworthy information
4. **Easier debugging**: If you see a sleep segment, you know it's from user

### Implementation

**Step 1: Remove the bad write**

```python
# File: day_start_manager.py, line 229
# OLD:
self.sleep_tracker.record_sleep_segment(afk_start_dt, afk_end_dt, source="afk_detection")

# NEW:
# Don't write to database - we'll compute from AFK events at read time
logger.info(f"💤 Sleep detected from AFK: {afk_duration_minutes:.1f} min (not stored, will compute from afk_events)")
```

**Step 2: Update reconciliation to query AFK events**

```python
# File: sleep_segment_tracker.py
def calculate_last_night_sleep(self, wake_time: datetime, last_day_start: Optional[str]):
    # Get user-reported segments
    user_sleep_segments = get_sleep_segments_last_24_hours()  # Only user_chat + cold_start
    wake_segments = get_wake_segments_last_24_hours()
    
    # Compute system sleep from AFK events
    afk_events = get_recent_afk_events(hours=24)
    system_sleep_segments = self._compute_sleep_from_afk_events(afk_events)
    
    # Merge
    all_sleep_segments = user_sleep_segments + system_sleep_segments
    
    # Reconcile
    result = reconcile_sleep_data(all_sleep_segments, wake_segments)
    return result
```

**Step 3: Add helper to compute sleep from AFK**

```python
def _compute_sleep_from_afk_events(self, afk_events: List[Dict]) -> List[Dict]:
    """Compute sleep segments from AFK events without storing them.
    
    Returns:
        List of dicts with 'start', 'end', 'duration_minutes', 'source'='afk_computed'
    """
    sleep_segments = []
    
    # Build intervals from went_afk → returned pairs
    # Filter for sleep-like intervals (>= 120 min, 60% overlap with sleep window)
    # Return as list of dicts
    
    return sleep_segments
```

---

## About "potentially_afk" Events

### Your Question: "Is it necessary to log?"

**What they are:**
- Grace period events (1-3 minutes of idle)
- Logged so you can see when inactivity started
- Used to backdate `went_afk` timestamp when user crosses 3 min threshold

**Are they necessary?**

**If you keep them:**
- More accurate AFK start times (backdated to 1 min, not 3 min)
- Better for wellness reminders (you can see "almost AFK" state)
- More telemetry for debugging

**If you remove them:**
- Simpler database (only `went_afk` and `returned`)
- Less noise in logs
- Still functional (just lose 2 minutes of precision)

**My take:** Keep them, but add a cleanup job to delete old ones (> 7 days). They're useful for:
1. Backdating AFK start times (if user goes from 1 min → 5 min idle, you know they were AFK since minute 1, not minute 3)
2. Wellness cycle pausing (you don't want to trigger reminders during grace period)

But definitely **clean up old events** to prevent table bloat.

---

## Summary

### Current State (Broken)
- System writes bad sleep segments to database (7:32 PM - 10:17 PM)
- Database mixes user truth and system guesses
- Reconciliation fixes it at read time, but database is still polluted

### Recommended Fix (Option A)
1. **Don't store system sleep segments**
2. Compute sleep from `afk_events` at read time
3. Keep `sleep_segments` table for user-reported segments only
4. Use reconciliation to merge computed + user segments

### Minimal Change (Option B)
- Keep current behavior
- Accept that database has junk data
- Rely on reconciliation to filter it out
- Add cleanup job to delete old system segments

**What do you want to do?** I recommend Option A for a clean architecture.
