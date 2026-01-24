# Physical Status Structure - SUPERSEDED

> ⚠️ **IMPORTANT:** This document has been superseded by `RESOURCE_FILE_ARCHITECTURE.md`

## Why This Was Superseded

This design mixed traits, state, telemetry, and session flags in one file, which causes:
1. **Invalid JSON** - Comments (//) and enum schemas mixed with data
2. **Duplicate fields** - Multiple representations of same data (sleep_deficit as enum and number)
3. **Stale data** - Computed values not refreshed
4. **Race conditions** - Concurrent writes to different sections
5. **Coupling** - Health model tied to UI behaviors (greeting_sent)
6. **No timestamps** - Volatile fields lack observed_at metadata

## The Correct Architecture

See `RESOURCE_FILE_ARCHITECTURE.md` for the proper separation:

**Four distinct layers:**
1. **Traits** (`resource_user_traits.json`) - Chronic conditions, preferences, slow-changing
2. **Day State** (`resource_user_day_state.json`) - Today's status, resets daily, includes observed_at
3. **Telemetry** (Database) - AFK events, sleep segments, high-frequency, append-only
4. **Derived** (Optional cache) - Computed summaries with confidence + source

**Key principles:**
- Pure JSON (no comments, no schema in data)
- Timestamps on volatile fields (`observed_at`)
- Canonical source for each data point (no duplication)
- Session flags separate from health data
- Compute aggregates on-read, don't store

---

## Original Design (FOR HISTORICAL REFERENCE)



```json
{
  // ============================================
  // META
  // ============================================
  "timestamp": "2026-01-07T23:15:29Z",
  "last_updated": "2026-01-07T23:15:29Z",
  
  // Day state
  "day_started": true,
  "day_start_time": "2026-01-07T06:45:01Z",
  "morning_greeting_sent": false,
  
  // ============================================
  // 1. PHYSICAL STATE
  // ============================================
  "physical": {
    "energy_level": "normal | low | depleted | high",
    "fatigue": "none | mild | moderate | severe",
    "pain_level": "none | mild | moderate | severe",
    "hunger": "not_hungry | mild | hungry | very_hungry",
    "hydration_state": "hydrated | thirsty | dehydrated",
    "physical_activity": "sedentary | light | moderate | active"
  },
  
  // ============================================
  // 2. EMOTIONAL/MENTAL STATE
  // ============================================
  "mental": {
    "mood": "positive | neutral | negative | frustrated",
    "stress_load": "low | neutral | elevated | high",
    "anxiety": "low | neutral | elevated | high",
    "mental_energy": "high | normal | low | depleted",
    "mental_clarity": "clear | foggy | impaired",  // For drunk/medicated
    "social_capacity": "high | normal | low | very_low"
  },
  
  // ============================================
  // 3. HEALTH STATUS
  // ============================================
  "health": {
    // Overall
    "overall_wellness": "excellent | good | fair | poor",
    "wellness_score": 0.7,
    
    // Chronic (from resource_user_health.json)
    "chronic_conditions": ["finger_pain", "back_pain"],
    "conditions_flaring_today": ["back_pain"],  // Which ones are bad today
    
    // Acute (temporary, today only)
    "acute_conditions": [
      {"condition": "headache", "severity": "mild", "since": "14:00"},
      {"condition": "cold", "severity": "moderate", "since": "2026-01-06"}
    ],
    
    // Sickness (flu, covid, etc.)
    "sick_today": false,
    "illness": null,  // or "flu", "cold", "covid", etc.
    
    // Sleep-related health
    "sleep_deficit": "none | mild | moderate | severe"
  },
  
  // ============================================
  // 4. COMPUTER ACTIVITY (AFK)
  // ============================================
  "computer_activity": {
    "is_afk": false,
    "is_potentially_afk": false,
    "idle_seconds": 0.1,
    "idle_minutes": 0.0,
    "last_checked": "2026-01-07T23:15:27Z",
    
    // Work session tracking
    "active_work_session_start": "2026-01-07T22:55:44Z",
    "active_work_session_minutes": 19.7,
    
    // Daily totals (reset at day boundary)
    "total_afk_time_today": 587.9,
    "total_active_time_today": 387.0,
    
    // Last AFK context
    "last_afk_start": "2026-01-07T22:36:05Z",
    "last_afk_duration_minutes": 0
  },
  
  // ============================================
  // 5. SLEEP DATA
  // ============================================
  "sleep": {
    "last_night": {
      "total_hours": 8.5,
      "quality": "poor | fair | good | excellent",
      "fragmented": false,
      "bedtime": "2026-01-06 22:30",
      "wake_time": "2026-01-07 07:00",
      "source": "afk_detection | user_chat | database"
    },
    "sleep_deficit_hours": 0.5  // Cumulative over multiple days
  },
  
  // ============================================
  // 6. WELLNESS ACTIVITIES (Timestamps)
  // ============================================
  "wellness_activities": {
    // Timestamps
    "last_hydration": "2026-01-07T22:59:59Z",
    "last_coffee": "2026-01-07T19:14:47Z",
    "last_meal": "2026-01-07T19:49:50Z",
    "last_snack": "2026-01-07T22:09:16Z",
    "last_finger_stretch": "2026-01-07T22:56:18Z",
    "last_back_stretch": "2026-01-07T22:55:41Z",
    "last_standing_break": "2026-01-07T22:55:41Z",
    "last_walk": null,
    "last_exercise": null,
    
    // Daily counters
    "coffees_today": 2,
    "coffees_today_date": "2026-01-07"
  },
  
  // ============================================
  // 7. COGNITIVE STATE (How busy/available)
  // ============================================
  "cognitive": {
    "load": "low | medium | high",
    "focus_depth": "scattered | normal | deep",
    "interruption_tolerance": "high | medium | low | zero",
    "current_context": "working | meeting | personal_time | break"
  },
  
  // ============================================
  // 8. SCHEDULE PRESSURE
  // ============================================
  "schedule": {
    "meetings_remaining": 1,
    "back_to_back_risk": false,
    "next_free_block_minutes": 45,
    "meeting_density": "open | moderate | packed"
  },
  
  // ============================================
  // 9. TRACKING (Internal state)
  // ============================================
  "tracking": {
    "last_activity_tracker_run": "2026-01-07T23:15:20Z"
  }
}
```

---

## Section Breakdown & Rationale

### 1. PHYSICAL STATE
**What:** Body sensations and needs  
**Contains:**
- Energy (physical, not mental)
- Fatigue (tiredness)
- Pain (overall level, not specific to conditions)
- Hunger/hydration
- Physical activity level

**Why separate from health:**
- These change hourly
- Not medical conditions, just body state
- "I'm tired" vs "I have chronic fatigue syndrome"

---

### 2. MENTAL/EMOTIONAL STATE
**What:** Psychological state  
**Contains:**
- Mood (emotional)
- Stress/anxiety (emotional pressure)
- Mental energy (mental, not physical)
- Mental clarity (drunk/medicated)
- Social capacity

**Why separate from physical:**
- Mental energy ≠ physical energy
- You can be physically energized but mentally drained
- "I'm stressed" is mental, not physical

---

### 3. HEALTH STATUS
**What:** Medical/health conditions  
**Contains:**
- Overall wellness assessment
- Chronic conditions (permanent, from health.json)
- Which chronic ones are flaring TODAY
- Acute conditions (headache, cold - temporary)
- Sickness (flu, covid)
- Sleep deficit (health impact)

**Why separate from physical:**
- Medical conditions vs sensations
- "I have back pain" (condition) vs "my pain is moderate today" (sensation)
- Chronic = permanent trait, flaring = today's state

**Key distinction:**
```
physical.pain_level = "moderate"      // Overall pain sensation today
health.conditions_flaring_today = ["back_pain"]  // Which condition causing it
```

---

### 4. COMPUTER ACTIVITY (AFK)
**What:** Computer usage patterns  
**Contains:**
- Current AFK status
- Work session duration
- Daily totals

**Why separate section:**
- Pure telemetry
- Not a "state" like mood/energy
- Used for inference but not itself inferred

---

### 5. SLEEP DATA
**What:** Sleep quality and history  
**Contains:**
- Last night's sleep summary
- Sleep deficit (cumulative)

**Why separate section:**
- Important enough for its own section
- Feeds into physical.energy and health.sleep_deficit
- More than just a timestamp

---

### 6. WELLNESS ACTIVITIES
**What:** When did wellness activities occur  
**Contains:**
- Timestamps for all tracked activities
- Daily counters (coffees)

**Why separate section:**
- Pure tracking data
- Not a "state" or "condition"
- Used to calculate time_since values

---

### 7. COGNITIVE STATE
**What:** Mental workload and availability  
**Contains:**
- Cognitive load (how busy)
- Focus depth
- Interruption tolerance
- Current context (what you're doing)

**Why separate from mental:**
- Cognitive = work capacity
- Mental = emotional state
- You can be happy (mental) but overloaded (cognitive)

---

### 8. SCHEDULE PRESSURE
**What:** Calendar-driven constraints  
**Contains:**
- Meetings remaining
- Back-to-back risk
- Free time available

**Why separate section:**
- Computed from calendar
- Not a personal state
- External pressure, not internal state

---

## Key Design Principles

### 1. Physical vs Mental vs Health
**Physical:** Body sensations (tired, hungry, in pain)  
**Mental:** Psychological state (stressed, happy, anxious)  
**Health:** Medical conditions (has back pain, has flu)

### 2. State vs Condition
**State:** Changes hourly ("I'm in pain today")  
**Condition:** Permanent or semi-permanent ("I have chronic back pain")

### 3. Sensation vs Diagnosis
**Sensation:** `physical.pain_level = "moderate"`  
**Diagnosis:** `health.conditions_flaring_today = ["back_pain"]`

### 4. Computed vs Tracked
**Tracked:** Timestamps, AFK status (facts)  
**Computed:** Energy level, stress (inferences)

---

## Example Scenario

**User has chronic back pain (from health.json)**

**Morning after bad sleep:**
```json
{
  "physical": {
    "energy_level": "low",        // From poor sleep
    "pain_level": "mild"          // Back isn't flaring yet
  },
  "mental": {
    "mental_energy": "low",       // From poor sleep
    "stress_load": "neutral"
  },
  "health": {
    "chronic_conditions": ["back_pain"],  // Has the condition
    "conditions_flaring_today": [],       // Not flaring yet
    "sleep_deficit": "mild"               // From poor sleep
  },
  "sleep": {
    "last_night": {"quality": "poor", "total_hours": 5.5}
  }
}
```

**Afternoon after working 3 hours without stretch:**
```json
{
  "physical": {
    "energy_level": "low",        // Still tired
    "pain_level": "moderate"      // Pain increased!
  },
  "mental": {
    "mental_energy": "depleted",  // Mental fatigue from focus
    "stress_load": "elevated"     // Deadline pressure
  },
  "health": {
    "conditions_flaring_today": ["back_pain"],  // NOW flaring
    "acute_conditions": [
      {"condition": "headache", "severity": "mild"}  // New today
    ]
  },
  "wellness_activities": {
    "last_back_stretch": "10:00 AM"  // 3 hours ago (OVERDUE)
  }
}
```

**Result:** 
- High priority back stretch suggestion (flaring + overdue)
- Gentle tone (stressed + mentally depleted)
- Offer rest (low energy + headache)

---

## What Goes Where?

| Data Point | Section | Why |
|------------|---------|-----|
| Pain level | physical | Body sensation |
| Which condition hurting | health.conditions_flaring | Medical diagnosis |
| Tired/fatigued | physical | Body sensation |
| Low energy | physical | Physical capacity |
| Mentally drained | mental.mental_energy | Mental capacity |
| Stressed | mental.stress_load | Emotional state |
| Has chronic back pain | health.chronic_conditions | Medical condition |
| Back is bad today | health.conditions_flaring_today | Today's status |
| Has a headache | health.acute_conditions | Temporary condition |
| Has the flu | health.sick_today + illness | Sickness |
| Drunk/medicated | mental.mental_clarity = "impaired" | Mental impairment |
| Is AFK | computer_activity.is_afk | Telemetry |
| Slept poorly | sleep.last_night.quality | Sleep data |

---

## Next Steps

1. Restructure resource_user_physical_status.json with these sections
2. Update physical_status_inference agent to output this structure
3. Update all readers to use new paths
4. Migrate existing data to new structure

This gives us a **logical, maintainable structure** where everything has a clear home!
