# Resource File Architecture: Separating Traits, State, Telemetry, and Derived Data

**Date:** 2026-01-07  
**Status:** Design Document (Implementation Pending)

---

## The Problem

`resource_user_physical_status.json` is currently trying to be:
1. A user profile (chronic conditions, preferences)
2. A day journal (daily state, mood)
3. A telemetry log (AFK events, timestamps)
4. An inference cache (computed scores)
5. Application state (greeting_sent flags)

**This mixing causes:**
- Stale data bugs (computed values not refreshed)
- Race conditions (concurrent writes to different sections)
- Accidental overwrites (long-term traits in daily files)
- Invalid JSON (comments, enum schemas mixed with data)
- Coupling (health model tied to UI behaviors)

---

## The Solution: Four-Layer Architecture

### Layer 1: Traits (Slow-Changing, Persistent)

**File:** `resources/resource_user_traits.json`

**Contains:**
- Chronic health conditions with metadata
- Stable preferences (sleep schedule, caffeine cutoff)
- Sensitivities and allergies
- Accommodation needs

**Update frequency:** Manually, or via explicit "update my profile" commands

**Example:**
```json
{
  "_metadata": {
    "resource_id": "resource_user_traits",
    "version": "1.0",
    "last_updated": "2026-01-07T10:00:00Z"
  },
  "health": {
    "chronic_conditions": [
      {
        "id": "back_pain",
        "display": "Back Pain",
        "typical_severity": "mild_to_moderate",
        "triggers": ["long_sitting", "poor_posture"],
        "helps": ["stretch", "walk", "standing_desk"],
        "suggested_interval_minutes": 50,
        "added": "2025-12-28"
      },
      {
        "id": "finger_pain",
        "display": "Finger Pain",
        "typical_severity": "moderate",
        "triggers": ["typing", "gaming"],
        "helps": ["finger_stretch", "breaks"],
        "suggested_interval_minutes": 25,
        "added": "2025-12-28"
      }
    ],
    "allergies": [],
    "sensitivities": []
  },
  "sleep": {
    "target_bedtime": "22:30",
    "target_wake_time": "07:00",
    "ideal_hours_min": 7,
    "ideal_hours_max": 8,
    "caffeine_cutoff": "14:00"
  },
  "exercise": {
    "preferences": ["nighttime_walks", "yoga_occasionally"]
  },
  "routine": {
    "typical_meal_times": {
      "breakfast": "08:00",
      "lunch": "12:30",
      "dinner": "18:00"
    }
  }
}
```

**Ownership:** User profile, manually edited or updated via explicit commands

---

### Layer 2: Daily State (Resets Daily, Volatile)

**File:** `resources/resource_user_day_state.json`

**Contains:**
- Today's physical, mental, emotional state
- Today's health status (which conditions are flaring)
- Today's acute conditions (headache, etc.)
- Today's wellness activity timestamps

**Update frequency:** Every 2-5 minutes (physical_status_inference refresh)

**Resets:** At day boundary (midnight or configured day_start)

**Example:**
```json
{
  "_metadata": {
    "resource_id": "resource_user_day_state",
    "version": "1.0",
    "last_updated": "2026-01-07T14:30:00Z",
    "day_date": "2026-01-07"
  },
  "physical": {
    "energy_level": "normal",
    "pain_level": "none",
    "observed_at": "2026-01-07T14:30:00Z"
  },
  "mental": {
    "mental_energy": "high",
    "mood_valence": "positive",
    "stress_load": "baseline",
    "mental_clarity": "clear",
    "observed_at": "2026-01-07T14:30:00Z"
  },
  "health": {
    "conditions_flaring_today": [],
    "acute_conditions": [],
    "sick_today": false,
    "illness": null,
    "observed_at": "2026-01-07T14:30:00Z"
  },
  "wellness_activities": {
    "last_hydration": "2026-01-07T13:27:00Z",
    "last_coffee": "2026-01-07T07:00:00Z",
    "last_finger_stretch": "2026-01-07T14:21:00Z",
    "last_back_stretch": "2026-01-07T14:21:00Z",
    "last_standing_break": "2026-01-07T14:21:00Z",
    "last_meal": "2026-01-07T13:27:00Z",
    "last_snack": "2026-01-07T08:57:00Z",
    "last_walk": "2026-01-07T14:30:00Z",
    "last_exercise": null,
    "coffees_today": 3
  },
  "schedule": {
    "meeting_density": "open",
    "next_free_block_minutes": 120,
    "imminent_deadline": false,
    "observed_at": "2026-01-07T14:30:00Z"
  }
}
```

**Ownership:** Computed by `physical_status_inference` agent and `activity_tracker` agent

**Note:** Each state section has an `observed_at` timestamp to prevent stale reads.

---

### Layer 3: Telemetry (High-Frequency Events, Append-Only)

**Already implemented:** Database tables
- `afk_events` (timestamp, event_type, idle_seconds, duration_minutes)
- `sleep_segments` (start, end, duration_minutes, source)
- `wake_segments` (start_time, end_time, duration_minutes, source, notes)

**Why separate:**
- High write frequency (every idle check, every AFK transition)
- Aggregation needed (compute totals, not store them)
- Append-only (no overwrites, no race conditions)

**Query interface:** Database functions in `afk_sleep_db.py`
- `get_afk_statistics(day_start_dt)` → computes totals from events
- `get_sleep_segments_last_24_hours()` → reads recent sleep
- `calculate_last_night_sleep(wake_time)` → computes sleep summary

**Cleanup:** Periodic (AFK events keep 30 days, sleep/wake segments keep forever)

---

### Layer 4: Derived/Computed (Cache with Provenance)

**File:** `resources/resource_user_derived_state.json` (OPTIONAL)

**Contains:**
- Wellness scores (with confidence and inputs)
- Sleep deficit buckets (derived from sleep_segments)
- Energy level buckets (derived from sleep + time-of-day)
- Cognitive load estimates (derived from calendar + AFK)

**Update frequency:** On-demand or cached for 5 minutes

**Example:**
```json
{
  "_metadata": {
    "resource_id": "resource_user_derived_state",
    "version": "1.0",
    "computed_at": "2026-01-07T14:30:00Z"
  },
  "wellness_score": {
    "value": 0.75,
    "confidence": "high",
    "inputs": ["sleep_quality", "activity_timers", "pain_level"],
    "reason_codes": ["good_sleep", "hydrated", "no_pain"],
    "computed_at": "2026-01-07T14:30:00Z"
  },
  "sleep_deficit": {
    "hours": -0.5,
    "bucket": "normal",
    "computed_from": "last_night_sleep",
    "computed_at": "2026-01-07T14:30:00Z"
  },
  "cognitive_load": {
    "value": "medium",
    "factors": ["2_meetings_today", "1_deadline_this_week"],
    "computed_at": "2026-01-07T14:30:00Z"
  }
}
```

**Ownership:** Computed functions with caching, NOT directly edited

**When to use:** For expensive computations that don't change frequently

**Alternative:** Skip this file entirely and compute on-read (simpler, less stale data risk)

---

## Application State (Not Health Data!)

**File:** `app_state/assistant_session.json` (NEW)

**Contains:**
- `day_started` (boolean)
- `morning_greeting_sent` (boolean)
- `last_activity_tracker_run_time` (ISO8601)
- Session-specific flags

**Why separate:** Health model should not know about UI behaviors

---

## Migration Plan

### Current File Mapping

| Current Field in `resource_user_physical_status.json` | New Location |
|------------------------------------------------------|--------------|
| `health_status.chronic_conditions` | → `resource_user_traits.json` (health.chronic_conditions) |
| `health_status.acute_conditions` | → `resource_user_day_state.json` (health.acute_conditions) |
| `physiology.energy_level` | → `resource_user_day_state.json` (physical.energy_level) |
| `emotional_state.mood` | → `resource_user_day_state.json` (mental.mood_valence) |
| `wellness_activities.*` | → `resource_user_day_state.json` (wellness_activities.*) |
| `computer_activity.is_afk` | → Read from `afk_events` DB (telemetry) |
| `computer_activity.total_afk_time_today` | → Computed from `afk_events` DB |
| `sleep_segments` | → Read from `sleep_segments` DB (telemetry) |
| `last_night_sleep` | → Computed from `sleep_segments` DB |
| `day_started` | → `app_state/assistant_session.json` |
| `morning_greeting_sent` | → `app_state/assistant_session.json` |

### Step-by-Step Migration

1. **Create `resource_user_traits.json`**
   - Copy chronic conditions from `resource_user_health.json`
   - Add structure for triggers, helps, typical_severity
   - No code changes yet (just create the file)

2. **Create `resource_user_day_state.json`**
   - Define schema with physical, mental, health, wellness_activities
   - Write initial generator function
   - Update `physical_status_inference` agent to write to this file

3. **Create `app_state/assistant_session.json`**
   - Move `day_started`, `morning_greeting_sent` from physical_status
   - Update `DayStartManager` to read/write this file

4. **Update all readers**
   - `proactive_orchestrator` → read from `day_state.json`
   - `context_generator` → read from `day_state.json`
   - `activity_tracker` → write to `day_state.json`

5. **Remove `resource_user_physical_status.json`**
   - After all code is migrated
   - Archive for reference

---

## Benefits of This Architecture

### 1. No More Stale Data
- Each state section has `observed_at` timestamp
- Volatile fields are computed on-read from telemetry
- Cached values include `computed_at` + `confidence`

### 2. No More Accidental Overwrites
- Traits file is rarely touched (explicit updates only)
- Day state resets daily (no accumulation)
- Telemetry is append-only (no overwrites)

### 3. No More Race Conditions
- High-frequency writes (AFK, sleep) go to database
- Daily state updates are atomic (single agent writes)
- Session state is separate (no contention)

### 4. Clean Separation of Concerns
- Traits → User profile (medical facts)
- Day state → Today's status (resets daily)
- Telemetry → Raw events (permanent record)
- Derived → Computed summaries (optional cache)

### 5. Easier Testing and Debugging
- Mock traits file for different user profiles
- Reset day state file to test edge cases
- Query telemetry database for historical analysis
- Clear provenance for derived values

---

## Enum Schemas (Separate from Data)

**File:** `app/assistant/schemas/physical_status_schema.json`

**Contains:**
- Valid values for `energy_level`, `mood_valence`, `stress_load`, etc.
- Field descriptions and constraints
- Validation rules

**Usage:**
- Loaded by `physical_status_inference` agent for output validation
- Used by Pydantic models for type checking
- NOT stored in data files (schema is separate)

**Example:**
```json
{
  "physical": {
    "energy_level": {
      "type": "enum",
      "values": ["depleted", "low", "normal", "high"],
      "description": "Physical energy capacity (not mental)"
    },
    "pain_level": {
      "type": "enum",
      "values": ["none", "mild", "moderate", "severe"],
      "description": "Overall pain sensation"
    }
  },
  "mental": {
    "mood_valence": {
      "type": "enum",
      "values": ["positive", "neutral", "negative"],
      "description": "Overall emotional tone"
    },
    "stress_load": {
      "type": "enum",
      "values": ["baseline", "elevated", "high"],
      "description": "Stress level (not cognitive load)"
    }
  }
}
```

---

## What About `resource_user_sleep_current.json`?

**Keep it!** But clarify its role:

**Purpose:** 24-hour rolling sleep summary (for LLM context)

**Source:** Computed from `sleep_segments` database (last 24 hours)

**Update frequency:** On-demand when sleep segment is recorded

**Status:** CORRECT ARCHITECTURE (it's a derived/cache file with provenance)

**Current implementation:** Already correct! `sleep_data_generator.py` computes from DB.

---

## What About `resource_user_health.json`?

**Keep it!** But clarify its role:

**Purpose:** Permanent health traits (chronic conditions, preferences)

**Rename to:** `resource_user_traits.json` (better name for expanded scope)

**Expand to include:** Sleep preferences, routine preferences, exercise preferences

**Status:** Already mostly correct, just needs minor enhancements

---

## Summary: Where Does Each Piece of Data Live?

| Data Type | File | Update Frequency | Resets? | Owner |
|-----------|------|-----------------|---------|-------|
| Chronic conditions | `resource_user_traits.json` | Manually | No | User |
| Sleep preferences | `resource_user_traits.json` | Manually | No | User |
| Today's physical state | `resource_user_day_state.json` | 2-5 min | Daily | physical_status_inference |
| Today's mental state | `resource_user_day_state.json` | 2-5 min | Daily | physical_status_inference |
| Today's health status | `resource_user_day_state.json` | 2-5 min | Daily | physical_status_inference |
| Wellness timestamps | `resource_user_day_state.json` | On event | Daily | activity_tracker |
| AFK events | `afk_events` DB | Every idle check | No (30d) | afk_monitor |
| Sleep segments | `sleep_segments` DB | On sleep end | No | sleep_segment_tracker |
| Wake segments | `wake_segments` DB | On chat detection | No | activity_tracker |
| Sleep summary (24h) | `resource_user_sleep_current.json` | On segment record | No | sleep_data_generator |
| Day started flag | `app_state/assistant_session.json` | On day start | Daily | day_start_manager |
| Greeting sent flag | `app_state/assistant_session.json` | On greeting | Daily | morning_greeting |

---

## Next Steps

1. **Create `resource_user_traits.json`** (expand from `resource_user_health.json`)
2. **Create `resource_user_day_state.json`** (extract from `resource_user_physical_status.json`)
3. **Create `app_state/assistant_session.json`** (move session flags)
4. **Update `physical_status_inference` agent** (write to new structure)
5. **Update all readers** (proactive_orchestrator, context_generator, etc.)
6. **Remove `resource_user_physical_status.json`** (after migration complete)

---

## Questions to Resolve

1. **Do we need `resource_user_derived_state.json`?**
   - Pro: Caches expensive computations (wellness_score)
   - Con: Another file to manage, risk of stale data
   - **Recommendation:** Skip it. Compute on-read for now. Add caching later if performance issue.

2. **Where do calendar and tasks live?**
   - Current: `resource_daily_context.json`
   - **Recommendation:** Keep separate. Not health data, different update frequency.

3. **Should we store AFK aggregates or always compute from DB?**
   - Current: Stored in `computer_activity` dict
   - **Recommendation:** Always compute from DB. More reliable, no staleness.
   - Cache in-memory if performance issue (but re-compute every refresh cycle).

4. **Do we need "last_updated" on every section?**
   - **Recommendation:** Yes, use `observed_at` for each state section.
   - Prevents reading stale values across refresh cycles.

---

## Conclusion

**The key principle:** Separate traits (slow), state (daily), telemetry (high-freq), and derived (cache).

**The key benefit:** Bugs disappear when data ownership is clear and update patterns are explicit.

**The migration path:** Incremental, test each step, deprecate old file last.

This architecture will make the system more robust, testable, and maintainable! 🎯
