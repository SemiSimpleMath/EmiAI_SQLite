# Physical Status Fields - Usage Audit

## Current Structure

```json
{
  "timestamp": "...",
  "last_updated": "...",
  "day_started": true,
  "day_start_time": "...",
  "morning_greeting_sent": false,
  "sleep_segments": [...],  // DEPRECATED - should be removed
  "last_night_sleep": {...},
  "computer_activity": {...},
  "wellness_activities": {...},
  "health_status": {...},
  "physiology": {...},
  "cognitive_state": {...},
  "emotional_state": {...},
  "schedule_pressure": {...},
  "status_timeline": [],  // UNUSED
  "last_activity_tracker_run_time": "..."
}
```

---

## SECTION 1: Core Tracking (ACTIVELY USED)

### ✅ `day_started`, `day_start_time`, `morning_greeting_sent`
**Status:** ACTIVELY USED  
**Where:** `day_start_manager.py`  
**Purpose:** Track if day has started, when it started, greeting sent  
**Decision:** **KEEP**

### ✅ `last_night_sleep`
**Status:** ACTIVELY USED  
**Where:** Displayed in prompts, used by agents  
**Purpose:** Summary of last night's sleep for current day context  
**Decision:** **KEEP**

### ✅ `computer_activity`
**Status:** ACTIVELY USED  
**Where:** `afk_monitor.py`, displayed in UI  
**Purpose:** Current AFK status, work session tracking  
**Decision:** **KEEP**

### ✅ `wellness_activities`
**Status:** ACTIVELY USED  
**Where:** `activity_recorder.py`, proactive orchestrator  
**Purpose:** Track last time each wellness activity occurred  
**Decision:** **KEEP**

### ✅ `last_activity_tracker_run_time`
**Status:** ACTIVELY USED  
**Where:** `physical_status_manager.py`  
**Purpose:** Prevent duplicate activity tracker runs  
**Decision:** **KEEP**

---

## SECTION 2: Status Inference (USED BUT GENERIC)

### ⚠️ `health_status`
**Status:** UPDATED by status_inference agent  
**Fields:**
- `overall_wellness`: "Good", "Fair", "Poor"
- `acute_conditions`: [] - list of current issues
- `chronic_conditions`: [] - from user_health.json
- `recent_mentions`: [] - health mentions in chat
- `wellness_score`: 0.7
- `acute_conditions_detected`: []
- `chronic_conditions_flaring`: []

**Where Used:**
- Written by `physical_status_inference` agent
- Read by prompts (generic "Health: Good")

**Issues:**
- Many duplicate fields (acute_conditions vs acute_conditions_detected)
- Most fields stay "Unknown" or empty
- Not actionable - agents just echo it back

**Decision:** **SIMPLIFY**
- Keep: `overall_wellness`, `chronic_conditions`, `wellness_score`
- Remove: `acute_conditions_detected`, `chronic_conditions_flaring`, `recent_mentions`

---

### ⚠️ `physiology`
**Status:** UPDATED by status_inference agent  
**Fields:**
- `energy_level`: "Low", "Normal", "High"
- `hunger_probability`: "Low", "Medium", "High"
- `sleep_deficit`: "None", "Mild", "Severe"
- `hydration_reminder`: "Needed", "Recent", "Unknown"
- `caffeine_window`: "Open", "Cutoff-Reached"
- `physical_activity`: "Sedentary", "Active"
- `hydration_need`: "Low", "Medium", "High"
- `caffeine_state`: "Cutoff-Reached"

**Where Used:**
- Written by `physical_status_inference` agent
- Read by `proactive_orchestrator` (for suggesting breaks)

**Issues:**
- Many redundant fields (hydration_reminder vs hydration_need)
- Most stay "Unknown"
- Could be computed from wellness_activities instead

**Decision:** **SIMPLIFY**
- Keep: `energy_level`, `sleep_deficit`, `caffeine_state`
- Remove: `hunger_probability`, `hydration_reminder`, `hydration_need`, `physical_activity` (redundant with wellness tracking)

---

### ⚠️ `cognitive_state`
**Status:** UPDATED by status_inference agent  
**Fields:**
- `load`: "Low", "Medium", "High"
- `current_context`: "Working", "Planning", "Unknown"
- `interruption_tolerance`: "Low", "Medium", "High"
- `decision_fatigue`: "Low", "High", "Unknown"
- `focus_depth`: "Shallow", "Normal", "Deep"
- `context_switches_today`: 0
- `mental_clarity`: "Foggy", "Clear", "Unknown"

**Where Used:**
- Written by `physical_status_inference` agent
- Read by `proactive_orchestrator` (decides if user can handle interruption)

**Issues:**
- Most fields stay "Unknown"
- `context_switches_today` never increments (no tracking mechanism)
- Highly speculative (agent guessing mental state)

**Decision:** **SIMPLIFY**
- Keep: `load`, `interruption_tolerance`, `focus_depth`
- Remove: `current_context`, `decision_fatigue`, `context_switches_today`, `mental_clarity`

---

### ❌ `emotional_state`
**Status:** UPDATED by status_inference agent  
**Fields:**
- `mood`: "Positive", "Neutral", "Negative"
- `stress_level`: "Low", "Medium", "High", "Unknown"
- `frustration_indicators`: "None", "Mild", "High"
- `accomplishment_boost`: **"Unknown"** ← NEVER CHANGES
- `social_battery`: **"Available"** ← ONLY used by proactive_orchestrator in one condition

**Where Used:**
- Written by `physical_status_inference` agent
- `social_battery` read by `proactive_orchestrator` (lines 428-430) - only displays if "Low" or "Drained"

**Issues:**
- `accomplishment_boost`: **NEVER USED** - always "Unknown"
- `social_battery`: **BARELY USED** - only in orchestrator formatting, never actually tracked
- `mood`, `stress_level`: Highly speculative, agents can't reliably infer this
- `frustration_indicators`: Agent guessing based on chat tone (unreliable)

**Decision:** **REMOVE ENTIRE SECTION** or simplify to just `mood`
- These are too subjective for an agent to infer accurately
- User should explicitly report mood/stress if it matters

---

### ⚠️ `schedule_pressure`
**Status:** UPDATED by status_inference agent  
**Fields:**
- `meetings_remaining`: 0
- `back_to_back_risk`: false
- `deadlines_24h`: []
- `buffer_time_available`: "Unknown"
- `overcommitment_score`: 0.0
- `meeting_density`: "Open", "Moderate", "Packed"
- `next_free_block_minutes`: 165
- `imminent_deadline`: false

**Where Used:**
- Written by `physical_status_inference` agent (from calendar data)
- Read by `proactive_orchestrator` (decides if user has time for suggestions)

**Issues:**
- Some fields computed correctly (`meetings_remaining`, `next_free_block_minutes`)
- Others stay "Unknown" (`buffer_time_available`)
- `overcommitment_score` always 0.0

**Decision:** **KEEP but simplify**
- Keep: `meetings_remaining`, `back_to_back_risk`, `next_free_block_minutes`, `meeting_density`
- Remove: `buffer_time_available`, `overcommitment_score`, `imminent_deadline`

---

## SECTION 3: UNUSED/DEPRECATED

### ❌ `sleep_segments`
**Status:** DEPRECATED (duplicates database)  
**Decision:** **REMOVE** - Now in `sleep_segments` table

### ❌ `status_timeline`
**Status:** NEVER POPULATED  
**Decision:** **REMOVE** - Always empty array

---

## SUMMARY: RECOMMENDATIONS

### REMOVE COMPLETELY:
1. **`sleep_segments`** - Moved to database
2. **`status_timeline`** - Never used
3. **`emotional_state.accomplishment_boost`** - Never changes from "Unknown"
4. **`emotional_state.social_battery`** - Barely used, not tracked
5. **`physiology.hunger_probability`** - Redundant
6. **`physiology.hydration_reminder`** - Redundant with hydration_need
7. **`physiology.hydration_need`** - Can compute from last_hydration
8. **`physiology.physical_activity`** - Redundant with wellness tracking
9. **`cognitive_state.context_switches_today`** - Never increments
10. **`cognitive_state.mental_clarity`** - Always "Unknown"
11. **`cognitive_state.decision_fatigue`** - Always "Unknown"
12. **`cognitive_state.current_context`** - Not useful
13. **`schedule_pressure.buffer_time_available`** - Always "Unknown"
14. **`schedule_pressure.overcommitment_score`** - Always 0.0
15. **`schedule_pressure.imminent_deadline`** - Not used
16. **`health_status.acute_conditions_detected`** - Duplicate
17. **`health_status.chronic_conditions_flaring`** - Duplicate
18. **`health_status.recent_mentions`** - Not used

### SIMPLIFY TO ESSENTIAL:
```json
{
  // Core tracking (keep as-is)
  "day_started": true,
  "day_start_time": "...",
  "last_night_sleep": {...},
  "computer_activity": {...},
  "wellness_activities": {...},
  
  // Health (simplified)
  "health_status": {
    "overall_wellness": "Good",
    "chronic_conditions": [],
    "wellness_score": 0.7
  },
  
  // Physiology (simplified)
  "physiology": {
    "energy_level": "Normal",
    "sleep_deficit": "None",
    "caffeine_state": "Open"
  },
  
  // Cognitive (simplified)
  "cognitive_state": {
    "load": "Low",
    "interruption_tolerance": "High",
    "focus_depth": "Normal"
  },
  
  // Emotional (simplified or remove)
  "emotional_state": {
    "mood": "Neutral",
    "stress_level": "Low"
  },
  
  // Schedule (simplified)
  "schedule_pressure": {
    "meetings_remaining": 0,
    "back_to_back_risk": false,
    "next_free_block_minutes": 165,
    "meeting_density": "Open"
  }
}
```

## IMPACT:
- **Remove ~40% of fields** that are never used or always "Unknown"
- **Keep critical tracking** (wellness activities, computer activity, day state)
- **Keep useful inferences** (energy, focus, meeting pressure)
- **Remove speculation** (accomplishment boost, social battery, decision fatigue)

This makes the status more reliable and easier to maintain!
