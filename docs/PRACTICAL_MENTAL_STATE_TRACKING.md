# Practical Mental State Tracking

## Why These Work Better

Your proposed fields are:
- ✅ **Simple scales** (3-4 levels, not complex speculation)
- ✅ **User-reportable** (user can explicitly set them)
- ✅ **AI-inferable** (as backup when user doesn't report)
- ✅ **Actionable** (directly affect suggestion behavior)
- ✅ **Daily scope** (reset each day, not trying to maintain long-term psychological profiles)

---

## Proposed Fields (Analysis)

### 1. `current_stress_load`
**Values:** `low | neutral | elevated | high`

**How to determine:**
- **From user:** "I'm stressed", "stressful day", "overwhelming"
- **From AI:** Packed calendar (5+ meetings), late work hours, short/terse chat responses
- **From behavior:** Working through breaks, skipping meals

**How it affects behavior:**
```python
if current_stress_load == "high":
    - Only critical/health-related suggestions
    - Shorter, gentler messages
    - Offer help: "Want me to reschedule non-urgent meetings?"
    - Check in: "Tough day - need anything?"
```

**Reset:** Daily (start of day = neutral)

---

### 2. `current_mood`
**Values:** `positive | neutral | negative | frustrated`

**How to determine:**
- **From user:** "great day!", "feeling down", "frustrated"
- **From AI:** Emoji use, chat tone, exclamation marks vs complaints
- **From context:** Just finished big project (positive), just had issues (negative)

**How it affects behavior:**
```python
if current_mood == "positive":
    - Celebrate with user
    - Good time for bigger asks ("Want to tackle that task?")

if current_mood == "negative" or "frustrated":
    - More supportive tone
    - Focus on easy wins
    - "Want to talk about it?"
```

**Reset:** Multiple times per day (mood changes)

---

### 3. `current_anxiety`
**Values:** `low | neutral | elevated | high`

**How to determine:**
- **From user:** "anxious about X", "worried", "nervous"
- **From AI:** Deadline proximity, big meeting coming up, repeated questions
- **From behavior:** Checking time frequently, asking about same thing

**How it affects behavior:**
```python
if current_anxiety == "elevated":
    - Offer specific help: "Want me to prep you for the meeting?"
    - Reduce unknowns: "Here's what to expect..."
    - Grounding suggestions: "Quick breathing exercise?"
```

**Different from stress:** Anxiety is future-focused (worried about what's coming), stress is present-focused (overwhelmed right now)

**Reset:** Event-based (after anxiety trigger resolves)

---

### 4. `mental_energy_today`
**Values:** `depleted | low | normal | high`

**How to determine:**
- **From user:** "exhausted", "drained", "feeling sharp"
- **From AI:** Sleep quality (poor = low), time awake, caffeine consumed, meal timing
- **From behavior:** Slower responses, simpler tasks chosen

**How it affects behavior:**
```python
if mental_energy_today == "low":
    - Suggest rest/nap
    - Reduce suggestion complexity
    - Don't ask open-ended questions
    - Focus on routine/simple tasks

if mental_energy_today == "high":
    - Good time for challenging tasks
    - Can handle interruptions better
```

**Reset:** Daily, but can change based on naps/coffee

---

### 5. `sleep_last_night`
**Values:** `poor | fair | good | excellent`

**How to determine:**
- **From data:** Already computed from sleep_segments (duration + fragmentation)
- **From user:** "slept terribly", "great sleep"
- **Override user report** if they say different from data

**How it affects behavior:**
```python
if sleep_last_night == "poor":
    - Sets mental_energy_today = low
    - Suggests afternoon nap
    - Reduces cognitive expectations
    - "Rough night - take it easy today"
```

**Reset:** Daily (computed from last_night_sleep)

---

### 6. `pain_today`
**Values:** `none | mild | moderate | severe`

**How to determine:**
- **From user:** "my back hurts", "headache", "fingers killing me"
- **From AI:** Chronic condition timers way overdue
- **From behavior:** Frequent break mentions

**How it affects behavior:**
```python
if pain_today >= "moderate":
    - Prioritize pain relief suggestions
    - More urgent reminders for stretches
    - Offer rest: "Take a break - your back needs it"
    - Adjust activity suggestions (no exercise if severe)
```

**Reset:** Hourly (pain can improve/worsen throughout day)

---

### 7. `social_capacity_today`
**Values:** `very_low | low | normal | high`

**How to determine:**
- **From user:** "not feeling social", "people'd out", "introverted today"
- **From AI:** After many meetings (drained), after social events
- **Hard to infer otherwise** - mostly user-reported

**How it affects behavior:**
```python
if social_capacity_today == "very_low":
    - Shorter messages
    - No open-ended questions ("How's it going?")
    - Direct suggestions only
    - Respect silence (don't push for engagement)

if social_capacity_today == "high":
    - Can be more conversational
    - Ask open questions
    - Longer check-ins
```

**Reset:** Daily or after solitude/socializing

---

## Implementation Strategy

### Approach 1: User Self-Report (Primary)
```python
# User can explicitly set these via chat
"I'm stressed" → current_stress_load = "elevated"
"Feeling good today" → current_mood = "positive"
"Not feeling social" → social_capacity_today = "low"
"I'm exhausted" → mental_energy_today = "low"
```

### Approach 2: AI Inference (Backup)
```python
# When user hasn't reported, AI infers from:
- Sleep data → mental_energy_today
- Calendar density → current_stress_load
- Chat tone → current_mood
- Deadline proximity → current_anxiety
- Pain mentions → pain_today
```

### Approach 3: Default Values
```python
# Start of day defaults
{
  "current_stress_load": "neutral",
  "current_mood": "neutral",
  "current_anxiety": "low",
  "mental_energy_today": "normal",  # Unless poor sleep
  "sleep_last_night": "good",       # From actual data
  "pain_today": "none",
  "social_capacity_today": "normal"
}
```

---

## Storage Location

**Option A: Add to physical_status**
```json
"mental_state": {
  "stress_load": "neutral",
  "mood": "neutral",
  "anxiety": "low",
  "mental_energy": "normal",
  "pain": "none",
  "social_capacity": "normal"
},
"sleep_last_night": "good"  // Already exists
```

**Option B: Separate resource file**
```json
// resource_user_mental_state.json
{
  "date": "2026-01-07",
  "stress_load": "neutral",
  "mood": "neutral",
  "anxiety": "low",
  "mental_energy": "normal",
  "pain": "none",
  "social_capacity": "normal",
  "sleep_last_night": "good",
  "last_updated": "...",
  "source": {
    "stress_load": "inferred",  // or "user_reported"
    "mood": "user_reported",
    "// ...": "..."
  }
}
```

**Recommendation:** Option A - keep it in physical_status under a new `mental_state` section

---

## Activity Tracker Updates

Update the activity_tracker agent to detect these:

```python
# New schema fields
class MentalStateUpdate(BaseModel):
    stress_load: Optional[Literal["low", "neutral", "elevated", "high"]]
    mood: Optional[Literal["positive", "neutral", "negative", "frustrated"]]
    anxiety: Optional[Literal["low", "neutral", "elevated", "high"]]
    mental_energy: Optional[Literal["depleted", "low", "normal", "high"]]
    pain: Optional[Literal["none", "mild", "moderate", "severe"]]
    social_capacity: Optional[Literal["very_low", "low", "normal", "high"]]
    raw_mention: str

class AgentForm(BaseModel):
    # ... existing fields ...
    mental_state_update: Optional[MentalStateUpdate] = None
```

---

## Proactive Orchestrator Integration

```python
def should_suggest(suggestion_type, mental_state):
    # Respect mental capacity
    if mental_state.mental_energy == "depleted":
        return False  # No suggestions when exhausted
    
    # Respect stress
    if mental_state.stress_load == "high" and suggestion_type not in ["rest", "break"]:
        return False  # Only wellness suggestions when stressed
    
    # Respect social capacity
    if mental_state.social_capacity == "very_low":
        # Use minimal, directive messages
        message_style = "brief"
    
    # Prioritize pain relief
    if mental_state.pain in ["moderate", "severe"]:
        priority_boost = "high"
    
    return should_suggest
```

---

## Key Advantages

1. **User has control** - Can explicitly set these
2. **AI provides backup** - Infers when user doesn't report
3. **Simple scales** - 3-4 levels, easy to understand
4. **Daily reset** - Not trying to maintain complex long-term state
5. **Directly actionable** - Each field changes behavior
6. **Trackable** - Can see how these change over time
7. **Not over-engineered** - Focused on what matters

---

## Next Steps

1. Add `mental_state` section to physical_status
2. Update activity_tracker to detect mental state mentions
3. Add user commands: `/mood frustrated`, `/stress high`, `/energy low`
4. Update proactive_orchestrator to respect mental_state
5. Add simple inference rules (poor sleep → low mental energy)

This is much better than speculative fields like "accomplishment_boost"!
