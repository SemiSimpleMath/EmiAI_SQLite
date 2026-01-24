# Template Fixes for resource_tracked_activities.json Schema Change

## Issue
User reworked `resource_tracked_activities.json` structure from:

**Old structure:**
```json
{
  "activity": {
    "threshold_label": "Every 2 hours",
    "threshold_minutes": 120
  }
}
```

**New structure:**
```json
{
  "activity": {
    "threshold": {
      "minutes": 120,
      "label": "Every 2 hours"
    }
  }
}
```

---

## Files Fixed

### 1. ✅ `app/assistant/agents/activity_tracker/prompts/user.j2`

**Line 3:**
```jinja2
# OLD:
- {{ a.display_name }} ({{ a.field_name }}){% if a.threshold_label %}: {{ a.threshold_label }}{% endif %}

# NEW:
- {{ a.display_name }} ({{ a.field_name }}){% if a.threshold %}: {{ a.threshold.label }}{% endif %}
```

**What it does:** Lists tracked activities in the prompt to the activity_tracker agent.

---

### 2. ✅ `app/assistant/agents/proactive_orchestrator/prompts/user.j2`

**Lines 106-111:**
```jinja2
# OLD:
{% set threshold = activity.threshold_minutes if activity.threshold_minutes else activity.threshold_description %}

# NEW:
{% set threshold = activity.threshold.minutes if activity.threshold and activity.threshold.minutes else (activity.threshold.label if activity.threshold else activity.guidance) %}
```

**What it does:** Shows thresholds in the activity timer table for the proactive orchestrator.

**Logic:**
1. If `threshold.minutes` exists, use that (e.g., "120")
2. Else if `threshold.label` exists, use that (e.g., "Every 2 hours")
3. Else use `guidance` (e.g., "Max 2 per day before 4pm")

---

### 3. ✅ `app/assistant/agents/health_status_inference/prompts/user.j2`

**Lines 58-62:**
```jinja2
# OLD:
{% set threshold = activity.threshold_minutes %}

# NEW:
{% set threshold = activity.threshold.minutes if activity.threshold else none %}
```

**What it does:** Shows thresholds in the wellness activity status table for health inference.

---

## Verification

Your new structure from `resource_tracked_activities.json`:

```json
{
  "back_stretch": {
    "threshold": {
      "minutes": 50,
      "label": "Every 45 to 60 min of sitting (chronic pain)"
    }
  },
  "coffee": {
    "guidance": "Max 2 per day before 4pm"
  }
}
```

Should now work correctly in all three agent prompts.

---

## What Else Might Break?

I searched the codebase and found these files **do NOT** access threshold fields directly (safe):

✅ **Safe files (only access `field_name`, `display_name`, `init_on_cold_start`):**
- `app/assistant/physical_status_manager/activity_recorder.py` (line 189)
- `app/assistant/physical_status_manager/physical_status_manager.py` (line 177)
- `app/assistant/physical_status_manager/afk_monitor.py` (line 359 - looks for `reset_on_afk`)
- `app/assistant/agents/proactive_orchestrator/prompts/system.j2` (line 43)

---

## Testing Recommendations

### 1. Test Activity Tracker Agent
Send a chat message like:
```
"drank water and did a finger stretch"
```

Check logs for:
```
✅ Agent parsed activities correctly
```

If you see errors about missing `threshold_label`, the fix didn't apply.

### 2. Test Proactive Orchestrator
Let the system run and check `/debug/status` page.

The "Activity Timers" table should show:
```
| Activity | Time Since | Threshold |
| Hydration | 76 min | 120 |
| Coffee | 23 min | Max 2 per day before 4pm |
```

### 3. Test Health Status Inference
Check logs for health inference agent output. Should see:
```
Wellness activities table with thresholds populated correctly
```

---

## If You See Errors

### Error: `'dict object' has no attribute 'threshold_label'`
**Fix:** Restart the system. Jinja templates are cached.

### Error: `'NoneType' object has no attribute 'minutes'`
**Cause:** An activity has no `threshold` or `guidance` field.
**Fix:** Make sure every activity in your JSON has either:
- `threshold` object with `minutes` and `label`, OR
- `guidance` string

### Error: Agent output is missing threshold info
**Cause:** Might be using old cached resource file.
**Fix:** Check `resources/resource_tracked_activities.json` - is it your new version?

---

## Summary

✅ **Fixed 3 template files** to match your new nested `threshold` structure
✅ **Backwards compatible** (handles activities with no threshold)
✅ **Code files are safe** (they don't access threshold fields)

The system should now work correctly with your reworked structure! 🎉
