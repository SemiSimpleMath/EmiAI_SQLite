# Physical Status - Refined for Proactive Orchestration

## Philosophy
**Goal:** Give `proactive_orchestrator` clean, actionable data to make smart decisions about:
- **When** to interrupt (is user deep in focus? in a meeting? stressed?)
- **What** to suggest (tired → rest, caffeinated → water, sedentary → walk)
- **How** to present it (light touch vs urgent)

**NOT the goal:** Speculate about emotional states or social dynamics

---

## KEEP: Critical for Suggestion Timing

### 1. Cognitive Load Indicators
**Purpose:** Decide if user can handle an interruption

```json
"cognitive_state": {
  "load": "Low | Medium | High",
  "interruption_tolerance": "Low | Medium | High",
  "focus_depth": "Shallow | Normal | Deep"
}
```

**Actionable decisions:**
- `load: High, focus_depth: Deep` → Only critical/urgent suggestions
- `interruption_tolerance: Low` → Batch suggestions, don't interrupt
- `load: Low` → Good time for stretch breaks, task suggestions

**How to infer:**
- Check calendar (meeting = high load)
- Check AFK patterns (long active session = focused)
- Check chat tone (short responses = busy)

---

### 2. Physical State
**Purpose:** Suggest the right wellness activity

```json
"physiology": {
  "energy_level": "Low | Normal | High",
  "sleep_deficit": "None | Mild | Severe",
  "caffeine_state": "Available | Peak | Cutoff-Reached"
}
```

**Actionable decisions:**
- `energy_level: Low, caffeine_state: Available` → Suggest coffee
- `sleep_deficit: Severe` → Suggest nap/rest instead of more activity
- `caffeine_state: Peak` → Don't suggest more coffee, suggest water

**How to infer:**
- Energy from time-of-day, sleep quality, last meal
- Sleep deficit from `last_night_sleep` data
- Caffeine state from wellness_activities (last_coffee + cutoff config)

---

### 3. Schedule Pressure
**Purpose:** Know if user has time for suggestions

```json
"schedule_pressure": {
  "meetings_remaining": 2,
  "back_to_back_risk": true,
  "next_free_block_minutes": 15,
  "meeting_density": "Packed | Moderate | Open"
}
```

**Actionable decisions:**
- `back_to_back_risk: true` → Suggest quick breaks between meetings
- `next_free_block_minutes: 5` → Only suggest 5-min activities
- `meeting_density: Packed` → Reduce suggestion frequency

**How to compute:**
- Query calendar for upcoming meetings
- Calculate gaps between events
- Count meetings remaining today

---

### 4. Health Context
**Purpose:** Respect chronic conditions when suggesting activities

```json
"health_status": {
  "overall_wellness": "Good | Fair | Poor",
  "chronic_conditions": ["finger_pain", "back_pain"],
  "wellness_score": 0.7
}
```

**Actionable decisions:**
- `chronic_conditions: ["finger_pain"]` → More frequent finger stretch suggestions
- `overall_wellness: Poor` → Focus on rest, not exercise
- `wellness_score: Low` → Prioritize health suggestions

**How to track:**
- Read from user_health.json (chronic conditions)
- Infer overall_wellness from chat mentions + sleep + activity
- Calculate wellness_score from compliance with wellness activities

---

## REMOVE: Too Speculative / Not Actionable

### ❌ `accomplishment_boost`
**Why remove:** 
- Always "Unknown"
- Can't reliably detect from chat
- Not actionable (what would you do differently?)

**Better approach:** Let proactive_orchestrator read recent chat naturally. If user says "just finished big project!", the LLM will understand context.

---

### ❌ `social_battery`
**Why remove:**
- Not trackable (no social events in calendar ≠ low battery)
- Too personal/speculative
- Not actionable for health suggestions

**Better approach:** If this matters, let user explicitly set it ("I'm feeling introverted today") and track that preference.

---

### ❌ `decision_fatigue`, `mental_clarity`
**Why remove:**
- Always "Unknown"
- Too vague to be actionable
- Covered by `cognitive_load` + `focus_depth`

---

### ❌ Redundant physiology fields
- `hunger_probability` - Just check time since last_meal
- `hydration_reminder` - Just check time since last_hydration
- `physical_activity` - Just check time since last_walk/exercise

---

## MAYBE: Trackable Cognitive Metrics

### 🤔 `context_switches_today`
**How to track:**
```python
# Increment when:
1. User switches between different apps (if we have window tracking)
2. User changes project/task in chat ("ok switching to X now")
3. User responds to interruption after deep focus
```

**Actionable:**
- `context_switches_today > 10` → User having fragmented day, suggest focus block
- Low switches → User in flow, reduce interruptions

**Decision:** Worth tracking IF we have window/app tracking. Otherwise skip.

---

## PROPOSED SIMPLIFIED STRUCTURE

```json
{
  // Core state (keep)
  "day_started": true,
  "day_start_time": "...",
  "last_night_sleep": {...},
  "computer_activity": {...},
  "wellness_activities": {...},
  
  // Actionable inferences
  "health_status": {
    "overall_wellness": "Good",
    "chronic_conditions": ["finger_pain"],
    "wellness_score": 0.7
  },
  
  "physiology": {
    "energy_level": "Normal",
    "sleep_deficit": "None",
    "caffeine_state": "Available"
  },
  
  "cognitive_state": {
    "load": "Medium",
    "interruption_tolerance": "High",
    "focus_depth": "Normal"
    // Optional: "context_switches_today": 5
  },
  
  "schedule_pressure": {
    "meetings_remaining": 1,
    "back_to_back_risk": false,
    "next_free_block_minutes": 45,
    "meeting_density": "Moderate"
  }
}
```

---

## HOW PROACTIVE_ORCHESTRATOR USES THIS

### Example 1: Coffee suggestion
```python
if physiology.energy_level == "Low" and \
   physiology.caffeine_state == "Available" and \
   cognitive_state.interruption_tolerance != "Low" and \
   schedule_pressure.next_free_block_minutes >= 5:
    suggest("coffee", priority=medium)
```

### Example 2: Deep work protection
```python
if cognitive_state.load == "High" and \
   cognitive_state.focus_depth == "Deep":
    # Only suggest if URGENT (chronic pain reminder)
    min_priority = "high"
```

### Example 3: Meeting buffer suggestion
```python
if schedule_pressure.back_to_back_risk and \
   schedule_pressure.next_free_block_minutes < 15:
    suggest("quick_stretch", priority=high, timing="now")
```

---

## MOOD/TONE DETECTION

**Instead of storing `emotional_state.mood`:**

Let the LLM naturally read chat context:
```
User recent messages:
- "ugh this is frustrating"
- "can't focus today"
- "too many meetings"

LLM interprets: User is stressed/frustrated
Decision: Reduce non-critical suggestions, focus on stress relief
```

**Benefits:**
- More accurate (based on actual words, not inference)
- No storage of speculative data
- LLM is better at understanding tone than rule-based system

---

## SUMMARY

**KEEP (Actionable):**
- Cognitive load, interruption tolerance, focus depth
- Energy level, sleep deficit, caffeine state
- Schedule pressure, meeting density
- Chronic conditions, overall wellness

**REMOVE (Speculative):**
- Accomplishment boost, social battery
- Decision fatigue, mental clarity
- Redundant physiology fields

**BETTER APPROACH:**
- Let proactive_orchestrator read chat context directly for mood/tone
- Focus on observable/measurable data
- Every field should answer: "What decision does this enable?"
