# Health Status Resource File - Implementation Plan

**Date:** 2026-01-07  
**Status:** Ready to Implement

---

## Final Structure

**File:** `resource_user_health_status.json`

```json
{
  "timestamp": "2026-01-07T16:57:22Z",
  
  // ===== FROM health_status_inference AGENT =====
  "mental": {
    "mood": "neutral",
    "stress_load": "neutral",
    "anxiety": "elevated",
    "mental_energy": "low",
    "social_capacity": "very_low"
  },
  
  "cognitive": {
    "load": "Medium",
    "interruption_tolerance": "Medium",
    "focus_depth": "Deep_Work"
  },
  
  "physical": {
    "energy_level": "Normal",
    "pain_level": "mild"
  },
  
  "physiology": {
    "hunger_probability": "Medium",
    "hydration_need": "Medium",
    "caffeine_state": "Optimal"
  },
  
  // ===== FROM activity_tracker AGENT =====
  "health_concerns_today": [
    "Have the flu",
    "Very anxious",
    "Threw up"
  ],
  
  // ===== GENERATED PYTHONICALLY (from AFK database) =====
  "computer_activity": {
    "active_work_session_minutes": 121.6,
    "active_work_session_start": "2026-01-07 02:55:44 PM PST",
    "idle_minutes": 0,
    "idle_seconds": 0.9,
    "is_active": true,
    "is_afk": false,
    "is_potentially_afk": false,
    "last_afk_start": "2026-01-07 02:36:05 PM PST",
    "last_checked": "2026-01-07 04:57:22 PM PST",
    "status": "active",
    "total_active_time_today": 387,
    "total_afk_time_today": 587.9
  },
  
  // ===== GENERATED PYTHONICALLY (from tracker output) =====
  "wellness_activities": {
    "back_stretchs_today": 0,
    "back_stretchs_today_date": "2026-01-03",
    "coffees_today": 2,
    "coffees_today_date": "2026-01-07",
    "exercises_today": 0,
    "exercises_today_date": "2026-01-03",
    "finger_stretchs_today": 1,
    "finger_stretchs_today_date": "2026-01-04",
    "hydrations_today": 1,
    "hydrations_today_date": "2026-01-04",
    "last_back_stretch": "2026-01-07 04:29:12 PM PST",
    "last_coffee": "2026-01-07 11:14:47 AM PST",
    "last_exercise": null,
    "last_finger_stretch": "2026-01-07 04:29:12 PM PST",
    "last_hydration": "2026-01-07 05:01:02 PM PST",
    "last_meal": "2026-01-07 11:49:50 AM PST",
    "last_rest": "2025-12-29 12:41:20 PM PST",
    "last_snack": "2026-01-07 04:29:12 PM PST",
    "last_standing_break": "2026-01-07 04:29:12 PM PST",
    "last_walk": null,
    "meals_today": 1
  }
}
```

---

## Data Sources

### 1. health_status_inference Agent (LLM)
**Generates interpretive/contextual fields:**
- `mental` (mood, stress_load, anxiety, mental_energy, social_capacity)
- `cognitive` (load, interruption_tolerance, focus_depth)
- `physical` (energy_level, pain_level)
- `physiology` (hunger_probability, hydration_need, caffeine_state)

**Inputs to agent:**
- Sleep data (`resource_user_sleep_current.json`)
- AFK stats (from database)
- Wellness activities (timestamps and counts)
- Calendar events
- Recent chat history
- User health traits (`resource_user_health.json`)

### 2. activity_tracker Agent
**Parses chat for:**
- `health_concerns_today` - User statements like "I have the flu", "I'm very anxious", "I threw up"
- Updates wellness activity timestamps

### 3. Python Code
**Computes from database/tracker:**
- `computer_activity` - From `get_afk_statistics(day_start_dt)`
- `wellness_activities` - From activity_recorder timestamps + daily counts
- `timestamp` - Current datetime

---

## Fields to REMOVE

❌ Remove these from current implementation:
```python
"context_switches_today"
"decision_fatigue"
"accomplishment_boost"
"frustration_indicators"
"acute_conditions"
"acute_conditions_detected"
"chronic_conditions"
"chronic_conditions_flaring"
"overall_wellness"
"recent_mentions"
"wellness_score"
"morning_greeting_sent"
"schedule_pressure" (all fields)
"day_started"
"day_start_time"
"sleep_segments"
"last_night_sleep"
"status_timeline"
"last_activity_tracker_run_time"
```

---

## Implementation Steps

### Step 1: Rename Agent
```bash
# Rename directory
mv app/assistant/agents/physical_status_inference app/assistant/agents/health_status_inference

# Update all imports in codebase
# Search for: from app.assistant.agents.physical_status_inference
# Replace with: from app.assistant.agents.health_status_inference
```

### Step 2: Update Agent Output Schema
**File:** `app/assistant/agents/health_status_inference/agent_form.py`

```python
from pydantic import BaseModel, Field
from typing import List, Optional

class MentalState(BaseModel):
    mood: str = Field(description="neutral | positive | negative")
    stress_load: str = Field(description="neutral | elevated | high")
    anxiety: str = Field(description="low | neutral | elevated | high")
    mental_energy: str = Field(description="high | normal | low | depleted")
    social_capacity: str = Field(description="high | normal | low | very_low")

class CognitiveState(BaseModel):
    load: str = Field(description="Low | Medium | High")
    interruption_tolerance: str = Field(description="High | Medium | Low | Zero")
    focus_depth: str = Field(description="Scattered | Normal | Deep_Work")

class PhysicalState(BaseModel):
    energy_level: str = Field(description="Depleted | Low | Normal | High")
    pain_level: str = Field(description="none | mild | moderate | severe")

class Physiology(BaseModel):
    hunger_probability: str = Field(description="Low | Medium | High")
    hydration_need: str = Field(description="Low | Medium | High")
    caffeine_state: str = Field(description="Under-caffeinated | Optimal | Over-caffeinated | Cutoff-Reached")

class AgentForm(BaseModel):
    mental: MentalState
    cognitive: CognitiveState
    physical: PhysicalState
    physiology: Physiology
```

### Step 3: Update PhysicalStatusManager
**File:** `app/assistant/physical_status_manager/physical_status_manager.py`

```python
def refresh(self):
    """Generate resource_user_health_status.json"""

    now = datetime.now(timezone.utc)

    # 1. Run activity_tracker agent
    activity_results = self._run_activity_tracker()
    self._apply_activity_updates(activity_results)

    # 2. Get AFK statistics (pythonic)
    from app.assistant.day_flow_manager.afk_manager.afk_statistics import get_afk_statistics
    day_start_dt = self.day_start_manager.get_day_start_datetime()
    afk_stats = get_afk_statistics(day_start_dt=day_start_dt)

    # 3. Build context for health_status_inference agent
    context = self._build_context_for_health_inference(afk_stats)

    # 4. Run health_status_inference agent
    inference = self._run_health_status_inference(context)

    # 5. Get wellness activities (pythonic from tracker)
    wellness_activities = self.activity_recorder.get_wellness_activities_full()

    # 6. Assemble resource file
    health_status = {
        "timestamp": now.isoformat(),

        # From agent
        "mental": {
            "mood": inference.mental.mood,
            "stress_load": inference.mental.stress_load,
            "anxiety": inference.mental.anxiety,
            "mental_energy": inference.mental.mental_energy,
            "social_capacity": inference.mental.social_capacity
        },
        "cognitive": {
            "load": inference.cognitive.load,
            "interruption_tolerance": inference.cognitive.interruption_tolerance,
            "focus_depth": inference.cognitive.focus_depth
        },
        "physical": {
            "energy_level": inference.physical.energy_level,
            "pain_level": inference.physical.pain_level
        },
        "physiology": {
            "hunger_probability": inference.physiology.hunger_probability,
            "hydration_need": inference.physiology.hydration_need,
            "caffeine_state": inference.physiology.caffeine_state
        },

        # From activity_tracker
        "health_concerns_today": activity_results.health_concerns,

        # Pythonic
        "computer_activity": {
            "active_work_session_minutes": afk_stats["current_work_session_minutes"],
            "active_work_session_start": afk_stats.get("work_session_start_time"),
            "idle_minutes": afk_stats.get("idle_minutes", 0),
            "idle_seconds": afk_stats.get("idle_seconds", 0),
            "is_active": afk_stats["is_currently_active"],
            "is_afk": afk_stats["is_currently_afk"],
            "is_potentially_afk": afk_stats.get("is_potentially_afk", False),
            "last_afk_start": afk_stats.get("last_afk_start"),
            "last_checked": now.isoformat(),
            "status": "active" if afk_stats["is_currently_active"] else "afk",
            "total_active_time_today": afk_stats["total_active_minutes"],
            "total_afk_time_today": afk_stats["total_afk_minutes"]
        },

        "wellness_activities": wellness_activities
    }

    # 7. Save
    self._save_health_status(health_status)
```

### Step 4: Update activity_tracker Schema
**File:** `app/assistant/agents/activity_tracker/agent_form.py`

Add field for health concerns:
```python
class AgentForm(BaseModel):
    # ... existing fields ...
    health_concerns: List[str] = Field(
        default_factory=list,
        description="Health issues mentioned by user today (e.g., 'Have the flu', 'Very anxious', 'Threw up')"
    )
```

### Step 5: Update activity_tracker Prompt
**File:** `app/assistant/agents/activity_tracker/prompts/system.j2`

Add section for detecting health concerns:
```jinja2
## 5. Health Concerns

*Detect explicit health statements from user chat.*

**Your Task:**
- Identify when user mentions feeling sick, anxious, in pain, etc.
- Extract the exact concern as a short phrase
- Focus on TODAY's concerns (not chronic conditions)

**Examples:**
- User: "I have the flu"
  → `"health_concerns": ["Have the flu"]`
- User: "I'm feeling very anxious about the meeting"
  → `"health_concerns": ["Very anxious"]`
- User: "I threw up this morning"
  → `"health_concerns": ["Threw up"]`
```

### Step 6: Update ActivityRecorder
**File:** `app/assistant/physical_status_manager/activity_recorder.py`

Add method to get full wellness activities dict:
```python
def get_wellness_activities_full(self) -> Dict[str, Any]:
    """Get complete wellness activities dict with counts and timestamps."""
    activities = {}
    
    for activity_key in self.tracked_activities:
        # Add last_* timestamp
        last_time = self.get_last(activity_key)
        activities[f"last_{activity_key}"] = last_time
        
        # Add *_today count and date
        count = self.get_count(activity_key)
        activities[f"{activity_key}s_today"] = count
        activities[f"{activity_key}s_today_date"] = self.get_count_date(activity_key)
    
    return activities
```

### Step 7: Move Session Flags
Create new file: `app/assistant/session_state_manager.py`

```python
class SessionStateManager:
    """Manages application session state (not health data)."""
    
    def __init__(self):
        self.state_file = Path("app_state/assistant_session.json")
        self.state = self._load_state()
    
    def _load_state(self) -> Dict[str, Any]:
        if self.state_file.exists():
            with open(self.state_file, 'r') as f:
                return json.load(f)
        return {
            "day_started": False,
            "day_start_time": None,
            "morning_greeting_sent": False,
            "last_activity_tracker_run_time": None
        }
    
    def save_state(self):
        self.state_file.parent.mkdir(exist_ok=True)
        with open(self.state_file, 'w') as f:
            json.dump(self.state, f, indent=2)
    
    def set_day_started(self, day_start_time: datetime):
        self.state["day_started"] = True
        self.state["day_start_time"] = day_start_time.isoformat()
        self.save_state()
    
    def set_greeting_sent(self):
        self.state["morning_greeting_sent"] = True
        self.save_state()
    
    def reset_daily_flags(self):
        self.state["day_started"] = False
        self.state["morning_greeting_sent"] = False
        self.save_state()
```

### Step 8: Update All Readers
Search codebase for references to:
- `resource_user_physical_status.json`
- Old field names (health_status, physiology, cognitive_state, emotional_state)

Update to use new structure:
- `resource_user_health_status.json`
- New field names (mental, cognitive, physical, physiology)

---

## Testing

### Unit Tests
1. Test `health_status_inference` agent output schema
2. Test `activity_tracker` health_concerns parsing
3. Test AFK statistics computation
4. Test wellness activities assembly

### Integration Tests
1. Run full refresh cycle
2. Verify resource file structure matches spec
3. Verify all old fields removed
4. Verify proactive_orchestrator can read new file

---

## Timeline

**Phase 1: Rename agent (30 min)**
- Rename directory
- Update imports

**Phase 2: Update schemas (1 hour)**
- Update agent output schemas
- Update prompts

**Phase 3: Update PhysicalStatusManager (2 hours)**
- Update refresh() method
- Update assembly logic
- Add session state manager

**Phase 4: Update readers (1 hour)**
- Update all code reading old file
- Test end-to-end

**Total: ~4-5 hours**

---

## Success Criteria

✅ Agent renamed to `health_status_inference`  
✅ Resource file has correct structure (only fields listed above)  
✅ All unwanted fields removed  
✅ Session flags moved to separate file  
✅ Proactive orchestrator works with new structure  
✅ All tests pass  

---

## Ready to Implement

This plan is complete and ready for execution. All specifications are clear, no ambiguity.
