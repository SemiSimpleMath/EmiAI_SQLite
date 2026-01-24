# Architecture Decision: Separating Traits, State, Telemetry, and Derived Data

**Date:** 2026-01-07  
**Decision:** Restructure resource files to separate concerns  
**Status:** Design approved, implementation pending

---

## Executive Summary

The current `resource_user_physical_status.json` mixes four distinct types of data:
1. User profile traits (chronic conditions)
2. Daily volatile state (mood, energy)
3. High-frequency telemetry (AFK events, timestamps)
4. Application session flags (greeting_sent)

**This mixing causes bugs:**
- Stale data (computed values not refreshed)
- Race conditions (concurrent writes)
- Accidental overwrites (long-term facts in daily files)
- Invalid JSON (comments, enum schemas mixed with data)
- Coupling (health model tied to UI behaviors)

**The solution:** Four-layer architecture with clear ownership and update patterns.

---

## Current State (Before)

```
resources/
├── resource_user_health.json              # Chronic conditions only
├── resource_user_physical_status.json     # EVERYTHING MIXED
├── resource_user_sleep_current.json       # Sleep summary (GOOD - derived from DB)
└── resource_tracked_activities.json       # Wellness activity config

Database:
├── afk_events                             # High-frequency telemetry (GOOD)
├── sleep_segments                         # Sleep history (GOOD)
└── wake_segments                          # Wake periods (GOOD)
```

**Problems with `resource_user_physical_status.json`:**
- Contains both traits (chronic conditions) and state (today's mood)
- Contains both telemetry (AFK totals) and session flags (greeting_sent)
- Contains enum schemas ("normal | low | high") mixed with data
- Contains duplicate fields (sleep_deficit as enum AND number)
- No timestamps on volatile fields (when was mood observed?)

---

## Future State (After)

```
resources/
├── resource_user_traits.json              # Slow-changing (chronic conditions, preferences)
├── resource_user_day_state.json           # Daily state (resets at day boundary)
├── resource_user_sleep_current.json       # Sleep summary (already correct)
└── resource_tracked_activities.json       # Wellness activity config

app_state/
└── assistant_session.json                 # Session flags (greeting_sent, day_started)

Database: (unchanged)
├── afk_events                             # High-frequency telemetry
├── sleep_segments                         # Sleep history
└── wake_segments                          # Wake periods

Schemas: (NEW)
└── app/assistant/schemas/
    └── physical_status_schema.json        # Enum definitions (separate from data)
```

---

## Layer 1: Traits (Slow-Changing, Manual Updates)

**File:** `resource_user_traits.json`

**What it contains:**
- Chronic health conditions with metadata (severity, triggers, helps)
- Sleep preferences (target bedtime, wake time, caffeine cutoff)
- Exercise preferences
- Routine preferences (typical meal times)

**Update frequency:** Manually or via explicit "update my profile" commands

**Resets:** Never (permanent until explicitly changed)

**Owner:** User

**Example:**
```json
{
  "health": {
    "chronic_conditions": [
      {
        "id": "back_pain",
        "typical_severity": "mild_to_moderate",
        "triggers": ["long_sitting"],
        "helps": ["stretch", "walk"],
        "suggested_interval_minutes": 50
      }
    ]
  },
  "sleep": {
    "target_bedtime": "22:30",
    "target_wake_time": "07:00",
    "caffeine_cutoff": "14:00"
  }
}
```

---

## Layer 2: Day State (Resets Daily, Volatile)

**File:** `resource_user_day_state.json`

**What it contains:**
- Today's physical state (energy, pain level)
- Today's mental state (mood, stress, mental energy)
- Today's health status (which conditions are flaring, acute conditions)
- Today's wellness activity timestamps (last hydration, last stretch, etc.)
- Today's schedule pressure (meeting density, deadlines)

**Update frequency:** Every 2-5 minutes (physical_status_inference refresh)

**Resets:** At day boundary (midnight or configured day_start)

**Owner:** `physical_status_inference` agent (writes state), `activity_tracker` agent (writes timestamps)

**Key feature:** Each section has `observed_at` timestamp to prevent stale reads

**Example:**
```json
{
  "physical": {
    "energy_level": "normal",
    "pain_level": "none",
    "observed_at": "2026-01-07T14:30:00Z"
  },
  "mental": {
    "mental_energy": "high",
    "mood_valence": "positive",
    "stress_load": "baseline",
    "observed_at": "2026-01-07T14:30:00Z"
  },
  "health": {
    "conditions_flaring_today": [],
    "acute_conditions": [],
    "observed_at": "2026-01-07T14:30:00Z"
  },
  "wellness_activities": {
    "last_hydration": "2026-01-07T13:27:00Z",
    "last_finger_stretch": "2026-01-07T14:21:00Z"
  }
}
```

---

## Layer 3: Telemetry (High-Frequency, Append-Only)

**Storage:** Database tables (already implemented)

**What it contains:**
- `afk_events` (timestamp, event_type, idle_seconds, duration_minutes)
- `sleep_segments` (start, end, duration_minutes, source)
- `wake_segments` (start_time, end_time, duration_minutes, notes)

**Update frequency:** High (every idle check, every AFK transition)

**Resets:** Periodic cleanup (AFK: 30 days, sleep/wake: never)

**Owner:** Low-level monitors (`afk_monitor`, `sleep_segment_tracker`)

**Query interface:** Database functions
- `get_afk_statistics(day_start_dt)` → computes totals from events
- `get_sleep_segments_last_24_hours()` → reads recent sleep
- `calculate_last_night_sleep(wake_time)` → computes sleep summary

**Key principle:** Don't store aggregates (total_afk_time_today), compute them on-read from events

---

## Layer 4: Derived/Cache (Optional, Computed with Provenance)

**File:** `resource_user_sleep_current.json` (already exists and correct!)

**What it contains:**
- 24-hour rolling sleep summary
- Computed from `sleep_segments` database
- Includes `source`, `last_updated`, and `computed_at`

**Update frequency:** On-demand when sleep segment is recorded

**Owner:** `sleep_data_generator.py`

**Why it's correct:**
- Clear provenance (`source: "database"`)
- Clear timestamp (`last_updated`)
- Computed from canonical source (database)
- Not trying to be source of truth (database is)

**Other derived data?**
- **Do NOT create more derived files for now**
- Compute on-read (energy buckets, cognitive load, etc.)
- Add caching only if performance issue

---

## Application State (Not Health Data!)

**File:** `app_state/assistant_session.json` (NEW)

**What it contains:**
- `day_started` (boolean)
- `morning_greeting_sent` (boolean)
- `last_activity_tracker_run_time` (ISO8601)
- Session-specific flags

**Why separate:** Health model should not know about UI behaviors

**Update frequency:** On state change (day start, greeting sent)

**Resets:** Daily (at day boundary)

**Owner:** `day_start_manager`, greeting system

---

## Enum Schemas (Separate from Data)

**File:** `app/assistant/schemas/physical_status_schema.json` (NEW)

**What it contains:**
- Valid enum values (`energy_level: ["depleted", "low", "normal", "high"]`)
- Field descriptions
- Validation rules

**Why separate:** Data files should be pure JSON, not JSON5 with comments

**Usage:**
- Loaded by `physical_status_inference` agent for output validation
- Used by Pydantic models for type checking
- NOT stored in data files

---

## Key Principles

### 1. Pure JSON (No Comments, No Schema in Data)

**Bad:**
```json
{
  "energy_level": "normal | low | high",  // This is schema, not data!
  "mood": "positive"  // This is a comment, makes it JSON5
}
```

**Good (data):**
```json
{
  "energy_level": "normal",
  "mood": "positive",
  "observed_at": "2026-01-07T14:30:00Z"
}
```

**Good (schema):**
```json
{
  "energy_level": {
    "type": "enum",
    "values": ["depleted", "low", "normal", "high"]
  }
}
```

### 2. Timestamps on Volatile Fields

**Bad:**
```json
{
  "mood": "positive"  // When was this observed? Might be stale!
}
```

**Good:**
```json
{
  "mood": "positive",
  "observed_at": "2026-01-07T14:30:00Z"
}
```

### 3. Canonical Source (No Duplication)

**Bad:**
```json
{
  "sleep_deficit": "moderate",           // Enum
  "sleep_deficit_hours": 2.5,            // Number
  "total_sleep_minutes": 390             // Third representation!
}
```

**Good:**
```json
{
  "last_night_sleep": {
    "total_minutes": 390,
    "target_minutes": 450,
    "observed_at": "2026-01-07T09:30:00Z"
  }
  // Deficit computed on-read: (390 - 450) / 60 = -1 hour
  // Bucket derived: deficit < -1.5 → "high", < -0.5 → "moderate", else "low"
}
```

### 4. Compute Aggregates, Don't Store Them

**Bad:**
```json
{
  "total_afk_time_today": 120,  // Stored, can become stale
  "afk_count_today": 5           // Risk of incorrect accumulation
}
```

**Good:**
```python
# Query database for today's AFK events
stats = get_afk_statistics(day_start_dt=day_start)
# Returns: {"total_afk_minutes": 120, "afk_count_today": 5}
# Computed fresh every time, never stale
```

### 5. Session State Separate from Health Data

**Bad:**
```json
{
  "energy_level": "normal",
  "morning_greeting_sent": true  // UI state mixed with health data!
}
```

**Good:**
```
resource_user_day_state.json:     {"energy_level": "normal"}
app_state/assistant_session.json: {"morning_greeting_sent": true}
```

---

## Migration Plan

### Phase 1: Create New Files (No Code Changes Yet)

1. **Create `resource_user_traits.json`**
   - Copy structure from `resource_user_health.json`
   - Enhance with triggers, helps, typical_severity
   - Add sleep preferences, routine preferences

2. **Create `resource_user_day_state.json`**
   - Define schema (physical, mental, health, wellness_activities, schedule)
   - Add `observed_at` to each section
   - Leave empty for now

3. **Create `app_state/assistant_session.json`**
   - Define schema (day_started, morning_greeting_sent, etc.)
   - Leave empty for now

4. **Create `app/assistant/schemas/physical_status_schema.json`**
   - Extract enum definitions
   - Add field descriptions

### Phase 2: Update Writers

5. **Update `physical_status_inference` agent**
   - Read from `resource_user_traits.json` (traits)
   - Write to `resource_user_day_state.json` (state)
   - Include `observed_at` in each section

6. **Update `activity_tracker` agent**
   - Write wellness timestamps to `resource_user_day_state.json`

7. **Update `day_start_manager`**
   - Write session flags to `app_state/assistant_session.json`
   - Read day_started from session file

### Phase 3: Update Readers

8. **Update `proactive_orchestrator`**
   - Read from `resource_user_day_state.json` (not physical_status)
   - Read from `resource_user_traits.json` (for chronic conditions)

9. **Update `context_generator`**
   - Read from `resource_user_day_state.json`
   - Compute AFK stats from database (not from stored aggregates)

10. **Update all other readers**
    - Search codebase for `resource_user_physical_status.json`
    - Update to read from new files

### Phase 4: Cleanup

11. **Remove `resource_user_physical_status.json`**
    - After all readers migrated
    - Archive for reference

12. **Remove stored AFK aggregates**
    - Always compute from database
    - Cache in-memory if needed (but re-compute every refresh)

---

## Testing Strategy

### Unit Tests

1. **Test trait file loading**
   - Load `resource_user_traits.json`
   - Verify chronic conditions structure
   - Test missing/malformed data

2. **Test day state reset**
   - Create day_state with yesterday's data
   - Trigger day boundary
   - Verify state resets but traits don't

3. **Test AFK statistics computation**
   - Insert AFK events in database
   - Compute totals via `get_afk_statistics()`
   - Verify correctness vs. stored aggregates

### Integration Tests

4. **Test full refresh cycle**
   - Trigger `physical_status_manager.refresh()`
   - Verify reads from traits file
   - Verify writes to day_state file with `observed_at`
   - Verify session flags in session file

5. **Test proactive orchestrator**
   - Mock day_state file
   - Mock traits file
   - Verify correct context building
   - Verify suggestions use correct data

### Edge Cases

6. **Test stale data detection**
   - Set `observed_at` to 1 hour ago
   - Trigger refresh
   - Verify warning logged

7. **Test concurrent writes**
   - Simulate activity_tracker and physical_status_inference running simultaneously
   - Verify no race conditions (should be none - they write different files now!)

---

## Expected Benefits

### Bug Fixes

1. **No more stale wellness_score** - Computed on-read with confidence
2. **No more incorrect AFK totals** - Always computed from events
3. **No more lost chronic conditions** - In separate traits file
4. **No more greeting_sent affecting health model** - Separate session file

### Code Quality

5. **Clearer ownership** - Each file has single writer
6. **Easier testing** - Mock traits for different profiles
7. **Better debugging** - Clear provenance for derived values
8. **Simpler logic** - No "is this stale?" checks needed

### Future Flexibility

9. **Multiple users** - Each has own traits file
10. **Historical analysis** - Query telemetry database for trends
11. **A/B testing** - Swap traits files to test different profiles
12. **Performance** - Add caching layer without changing core logic

---

## Questions to Resolve Before Implementation

1. **Do we need `resource_user_derived_state.json`?**
   - **Decision:** No, skip it for now. Compute on-read.
   - Can add later if performance issue.

2. **Should AFK aggregates be cached in-memory?**
   - **Decision:** Yes, cache during refresh cycle.
   - Re-compute from DB every refresh (2-5 min), not on every read.

3. **Where do calendar and tasks live?**
   - **Decision:** Keep in `resource_daily_context.json` (separate).
   - Not health data, different update frequency.

4. **What about location data?**
   - **Decision:** Keep in `resource_user_location.json` (separate).
   - Not health data, updated by location monitor.

---

## Timeline

**Phase 1 (File creation):** 1 hour
- Create new file structures
- No code changes, just files

**Phase 2 (Update writers):** 2-3 hours
- Update physical_status_inference agent
- Update activity_tracker agent
- Update day_start_manager

**Phase 3 (Update readers):** 2-3 hours
- Update proactive_orchestrator
- Update context_generator
- Update all other readers

**Phase 4 (Cleanup):** 1 hour
- Remove old file
- Remove old code paths
- Add deprecation warnings

**Total estimated time:** 6-8 hours of development + testing

---

## Risks and Mitigations

### Risk 1: Breaking existing functionality
**Mitigation:** Keep old file until all readers migrated, add deprecation warnings

### Risk 2: Missing a reader during migration
**Mitigation:** Search codebase for `resource_user_physical_status`, test thoroughly

### Risk 3: Race conditions during transition
**Mitigation:** Update writers first, then readers, test concurrent execution

### Risk 4: Stale data during migration
**Mitigation:** Add `observed_at` checks, log warnings for stale reads

---

## Success Criteria

1. **All tests pass** - Unit, integration, edge cases
2. **No old file references** - Search returns zero results
3. **Proactive suggestions work** - End-to-end test
4. **Day boundary works** - State resets, traits persist
5. **AFK statistics correct** - Computed from DB matches expected

---

## Conclusion

This architectural separation is essential for system robustness. The current mixing of traits, state, telemetry, and session flags creates maintenance burden and subtle bugs.

By separating concerns into distinct files with clear ownership and update patterns, we:
- Eliminate stale data bugs
- Prevent race conditions
- Simplify testing and debugging
- Enable future enhancements

**Next step:** Begin Phase 1 (file creation) after user approval.
