# Health Data Architecture: Permanent vs Temporary

## Three Layers of Health Information

### LAYER 1: Permanent Health Traits (Semi-Static)
**File:** `resource_user_health.json`  
**Purpose:** Long-term health conditions, allergies, accommodations  
**Updated:** Rarely (when conditions change, new diagnosis, etc.)

**Contents:**
```json
{
  "chronic_conditions": [
    {
      "condition": "finger_pain",
      "severity": "Moderate, chronic",
      "accommodation": "Frequent finger stretch breaks when typing",
      "suggested_interval_minutes": 25,
      "expiry": null  // Permanent unless explicitly removed
    },
    {
      "condition": "back_pain",
      "severity": "Moderate, chronic",
      "accommodation": "Standing breaks and back stretches",
      "suggested_interval_minutes": 50
    }
  ],
  "allergies": [
    // e.g., "peanuts", "shellfish"
  ],
  "medications": [
    // e.g., "blood pressure medication at 8 AM"
  ],
  "sleep": {
    "target_bedtime": "10:30-11:00 PM",
    "caffeine_cutoff": "2:00 PM"
  }
}
```

**Used for:**
- ✅ Proactive suggestion rules (finger stretch every 25 min)
- ✅ Health context for agents ("User has chronic back pain")
- ✅ Accommodation requirements (frequent breaks needed)
- ✅ Dietary restrictions (allergies)

**User edits via:** Manual file editing or future health settings UI

---

### LAYER 2: Daily Health Status (Changes Throughout Day)
**File:** `resource_user_physical_status.json`  
**Purpose:** Current state - how are the chronic conditions TODAY?  
**Updated:** Every refresh cycle (2-5 min)

**Contents:**
```json
{
  "health_status": {
    "overall_wellness": "Good | Fair | Poor",
    "chronic_conditions": ["finger_pain", "back_pain"],  // Copy from health.json
    "acute_conditions_detected": ["Headache"],  // New, temporary issues
    "chronic_conditions_flaring": ["back_pain"],  // Which chronic ones are bad today
    "wellness_score": 0.7
  },
  "pain_today": "mild | moderate | severe",  // NEW - daily pain level
  
  // Daily mental state
  "mental_state": {
    "stress_load": "neutral",
    "mood": "neutral",
    "anxiety": "low",
    "mental_energy": "normal",
    "social_capacity": "normal"
  }
}
```

**Used for:**
- ✅ Adjust suggestion urgency (flaring = more urgent)
- ✅ Detect new acute issues (headache detected from chat)
- ✅ Daily pain level affects activity suggestions

**Updated by:**
- physical_status_inference agent (AI infers from timers + chat)
- activity_tracker agent (user reports pain/mood)

---

### LAYER 3: Activity Timers (Real-Time Tracking)
**File:** `resource_user_physical_status.json` → `wellness_activities`  
**Purpose:** When did accommodations last happen?  
**Updated:** Every time activity occurs

**Contents:**
```json
{
  "wellness_activities": {
    "last_finger_stretch": "2026-01-07T22:56:18...",
    "last_back_stretch": "2026-01-07T22:55:41...",
    "last_standing_break": "2026-01-07T22:55:41...",
    // ... all other wellness activities
  }
}
```

**Used for:**
- ✅ Calculate: "30 minutes overdue for finger stretch"
- ✅ Trigger suggestions: "Time for your accommodation activity"
- ✅ Track compliance with chronic condition management

---

## How They Work Together

### Example: Chronic Back Pain Management

**Step 1: Permanent trait** (resource_user_health.json)
```json
{
  "condition": "back_pain",
  "suggested_interval_minutes": 50
}
```

**Step 2: Track when accommodation done** (wellness_activities)
```json
{
  "last_back_stretch": "2026-01-07 10:00 AM"
}
```

**Step 3: Calculate overdue status** (computed)
```python
minutes_since = now - last_back_stretch  # 60 minutes
is_overdue = minutes_since > 50  # True
urgency = "high" if minutes_since > 75 else "medium"
```

**Step 4: Check if flaring today** (health_status)
```json
{
  "chronic_conditions_flaring": ["back_pain"],  // User mentioned "my back hurts"
  "pain_today": "moderate"
}
```

**Step 5: Adjust suggestion** (proactive_orchestrator)
```python
if "back_pain" in chronic_conditions_flaring:
    # Flaring + overdue = URGENT
    priority = "high"
    message = "Your back needs attention - time for a stretch"
else:
    # Not flaring, just routine
    priority = "medium"
    message = "Back stretch time (50 min)"
```

---

## Proposed Mental State Fields (NEW)

Add to `resource_user_physical_status.json`:

```json
{
  "mental_state": {
    "stress_load": "low | neutral | elevated | high",
    "mood": "positive | neutral | negative | frustrated",
    "anxiety": "low | neutral | elevated | high",
    "mental_energy": "depleted | low | normal | high",
    "social_capacity": "very_low | low | normal | high",
    "last_updated": "2026-01-07T15:30:00Z",
    "source": {
      "stress_load": "inferred",  // or "user_reported"
      "mood": "user_reported",
      "mental_energy": "inferred"
    }
  },
  "pain_today": "none | mild | moderate | severe",  // Overall pain level
  "sleep_last_night": "poor | fair | good | excellent"  // Already exists
}
```

---

## Clear Separation of Concerns

| Data | File | Frequency | Source | Example |
|------|------|-----------|--------|---------|
| **Chronic conditions** | resource_user_health.json | Rarely (months) | User config | "finger_pain" |
| **Condition flaring** | resource_user_physical_status.json | Daily | User report / AI | "back_pain flaring today" |
| **Pain level today** | resource_user_physical_status.json | Hourly | User report / AI | "moderate pain" |
| **Last stretch** | resource_user_physical_status.json | Real-time | Activity tracking | "10 min ago" |
| **Mental state** | resource_user_physical_status.json | Hourly | User report / AI | "stressed, low energy" |

---

## Agent Behavior Example

**Proactive_orchestrator reads:**

1. **resource_user_health.json:**
   - "User has chronic back_pain, needs stretch every 50 min"

2. **resource_user_physical_status.json:**
   - last_back_stretch: "70 min ago" (overdue!)
   - chronic_conditions_flaring: ["back_pain"] (flaring!)
   - pain_today: "moderate"
   - mental_state.stress_load: "high"
   - mental_state.mental_energy: "low"

**Decision logic:**
```python
# Back stretch is overdue AND flaring
urgent_health_need = True
priority = "critical"

# BUT user is stressed and low energy
if mental_state.stress_load == "high" and mental_state.mental_energy == "low":
    # Keep it gentle, supportive
    message = "I know you're having a tough day, but your back really needs attention. Quick 2-min stretch?"
    tone = "supportive"
else:
    message = "Back stretch time - you're 20 min overdue"
    tone = "directive"
```

---

## Key Principles

1. **Permanent traits → health.json**
   - Chronic conditions, allergies, accommodations
   - Rarely changes

2. **Daily state → physical_status.json**
   - How are those conditions TODAY?
   - Mental state (stress, mood, energy)
   - Changes throughout the day

3. **Real-time tracking → physical_status.json (wellness_activities)**
   - When did activities occur?
   - Updated immediately

4. **Don't duplicate**
   - Chronic conditions defined ONCE in health.json
   - Physical_status just references them ("back_pain flaring")

---

## TODO: Potential Improvements

1. **Add to resource_user_health.json:**
   ```json
   "allergies": ["shellfish", "peanuts"],
   "medications": [
     {"name": "Blood pressure med", "time": "08:00 AM", "with_food": true}
   ],
   "dietary_restrictions": ["lactose_intolerant"]
   ```

2. **Add mental_state section to physical_status**
3. **Add explicit pain_today field** (separate from health_status)
4. **Track medication compliance** (did user take meds today?)
5. **Alert on dangerous combinations** (alcohol + medication)

This keeps permanent health traits separate from daily fluctuating state!
