# LLM Agent Outputs Added to Debug UI

**Date:** 2026-01-07  
**Status:** ✅ Complete

---

## What Was Added

### Last Agent Outputs Section

The debug UI now displays the most recent structured outputs from all LLM agents in the pipeline.

**Agents tracked:**
1. `activity_tracker` - Detects wellness activities from chat, calendar, tickets
2. `health_status_inference` - Generates mental, cognitive, physical, physiology assessments

---

## Implementation

### 1. PhysicalStatusManager Tracking

**File:** `app/assistant/physical_status_manager/physical_status_manager.py`

Added tracking dictionary in `__init__`:
```python
self.last_agent_outputs = {
    "activity_tracker": None,
    "health_status_inference": None
}
```

Updated refresh cycle to capture outputs:
```python
# After activity_tracker runs:
self.last_agent_outputs["activity_tracker"] = {
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "output": tracker_result
}

# After health_status_inference runs:
self.last_agent_outputs["health_status_inference"] = {
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "output": result
}
```

Added accessor method:
```python
def get_last_agent_outputs(self) -> Dict[str, Any]:
    """Get the last outputs from LLM agents for debugging."""
    return self.last_agent_outputs
```

### 2. Debug Route Integration

**File:** `app/routes/debug_status.py`

Added helper function:
```python
def _get_last_agent_outputs():
    """Get last LLM agent outputs for debugging."""
    manager = get_physical_status_manager()
    agent_outputs = manager.get_last_agent_outputs()
    # Convert timestamps to local time
    return result
```

Updated data endpoint to include agent outputs:
```python
return jsonify({
    # ... other data ...
    "agent_outputs": agent_outputs
})
```

### 3. Frontend Display

**File:** `app/templates/debug_status.html`

Added new section at TOP of page (priority):
- **🤖 LLM Agent Outputs (Last Run)**
- Full-width card spanning grid
- Shows both agents with timestamps
- Syntax-highlighted JSON output
- Red label: "Debug: Last structured outputs from pipeline agents"

---

## Display Format

### Agent Output Card

Each agent shows:
```
activity_tracker
Last run: 2026-01-07 07:03:38 PM PST

{
  "activity_counts": {
    "hydration": 3,
    "coffee": 2
  },
  "activities_to_reset": ["finger_stretch"],
  "sleep_events": [],
  "wake_segments": [],
  "day_start_signal": null,
  "reasoning": "User mentioned drinking water..."
}
```

```
health_status_inference
Last run: 2026-01-07 07:03:38 PM PST

{
  "mental": {
    "mood": "neutral",
    "stress_load": "elevated",
    ...
  },
  "cognitive": {...},
  "physical": {...},
  "physiology": {...},
  "health_concerns_today": [],
  "general_health_assessment": "User is moderately stressed..."
}
```

---

## Benefits

### 1. Pipeline Debugging
- See exactly what agents detected/inferred
- Verify agent outputs are correct
- Spot issues with agent logic

### 2. Data Flow Visibility
- Trace from agent output → resource file → orchestrator input
- Understand how inferences propagate
- Identify where data gets lost/transformed

### 3. Agent Quality Assurance
- Check if activity_tracker is detecting activities correctly
- Verify health_status_inference assessments are reasonable
- See agent reasoning/explanations

### 4. Troubleshooting
- If suggestions are wrong, check agent outputs first
- See if agent detected the right activities
- Verify mental/physical state assessments match reality

---

## Updated Page Layout

The orchestrator pipeline debug UI now shows (in order):

### 1. LLM Agent Outputs (RED - Debug Priority)
- activity_tracker output
- health_status_inference output

### 2. Orchestrator Inputs (GREEN)
- Health Status (generated)
- User Health (traits)
- Sleep Data (24h summary)
- Tracked Activities (config)
- Location
- Daily Context
- User Routine

### 3. Database Telemetry (BLUE)
- Sleep Segments Log
- AFK Events Log
- Wake Segments Log

### 4. Legacy (YELLOW Warning)
- Physical Status (old format)

**Total: 12 sections showing complete data flow from agents → resources → database!**

---

## Usage

### View Agent Outputs

1. Navigate to: `http://localhost:5000/debug/status`
2. Agent outputs are at the TOP of the page
3. Auto-refreshes every 60 seconds
4. Click "⚡ Trigger Status Refresh" to run agents and see new outputs

### What to Look For

**activity_tracker:**
- Are activities being detected from chat?
- Are activity_counts correct?
- Are sleep_events being parsed?
- Is reasoning sensible?

**health_status_inference:**
- Do mental/physical assessments match reality?
- Is general_health_assessment meaningful?
- Are health_concerns_today populated?
- Do cognitive/physiology assessments make sense?

---

## Example Scenarios

### Scenario 1: Activity Not Detected

**Problem:** Said "grabbed water" but hydration counter didn't increase

**Debug:**
1. Check activity_tracker output
2. Look for "hydration" in activity_counts
3. Check reasoning field for why it was/wasn't detected
4. Verify chat was included in recent_chat_excerpts

### Scenario 2: Wrong Energy Assessment

**Problem:** Health status shows "High" energy but user is exhausted

**Debug:**
1. Check health_status_inference output
2. Look at physical.energy_level
3. Check inputs (sleep_summary, afk_data, wellness_activities)
4. Verify agent had correct context

### Scenario 3: Missing Health Concern

**Problem:** User mentioned being sick but health_concerns_today is empty

**Debug:**
1. Check activity_tracker output (should have health_concerns field soon)
2. Or check health_status_inference output
3. Verify chat was in recent_chat_history
4. Check if agent's reasoning explains why it was missed

---

## Next Steps

**All pipeline components are now visible:**
- ✅ Agent outputs (debug)
- ✅ Resource files (orchestrator inputs)
- ✅ Database logs (telemetry)
- ✅ Auto-refresh + manual trigger

**The debug UI is complete!** 🎯
