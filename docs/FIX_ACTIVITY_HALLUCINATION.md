# Fix: Activity Tracker Hallucinating Activities - Complete ✅

## Problem

The `activity_tracker` agent was returning counts for `walk` and `exercise` activities that don't exist in `resource_tracked_activities.json`:

```json
{
  "activity_counts": {
    "walk": "1",        // ❌ Not in config
    "exercise": "0"     // ❌ Not in config
  }
}
```

**Root Cause:** The code had **hardcoded activity lists** that were out of sync with the config file.

---

## What Was Fixed

### 1. ✅ Made `reset_all_activities()` Dynamic

**File:** `app/assistant/physical_status_manager/activity_recorder.py`

**Before (Hardcoded):**
```python
activities["last_meal"] = None
activities["last_snack"] = None
activities["last_hydration"] = grace_period_iso
activities["last_coffee"] = None
activities["last_walk"] = None          # ❌ Hardcoded
activities["last_exercise"] = None      # ❌ Hardcoded
activities["last_finger_stretch"] = None
...
```

**After (Dynamic):**
```python
# Get all tracked fields from config
tracked_fields = self.get_all_tracked_fields()

# Reset all tracked activities dynamically
for field_name in tracked_fields:
    last_field = f"last_{field_name}"
    
    # Hydration gets grace period, others get None
    if field_name == "hydration" and grace_period_iso:
        activities[last_field] = grace_period_iso
    else:
        activities[last_field] = None
```

**Now:** Activities come from `resource_tracked_activities.json` config, not hardcoded lists.

---

### 2. ✅ Made `get_activity_summary()` Dynamic

**Before (Hardcoded):**
```python
key_activities = ['hydration', 'meal', 'coffee', 'walk']  # ❌ Hardcoded

for activity in key_activities:
    ...
```

**After (Dynamic):**
```python
# Get all tracked activities from config
tracked_fields = self.get_all_tracked_fields()

# Prioritize some common ones if they exist
priority_order = ['hydration', 'meal', 'coffee', 'snack']
ordered_fields = [f for f in priority_order if f in tracked_fields]
ordered_fields.extend([f for f in tracked_fields if f not in priority_order])

for activity in ordered_fields[:4]:  # Limit to first 4
    ...
```

---

### 3. ✅ Removed `walk` and `exercise` from Resource File

**File:** `resources/resource_user_wellness_activities.json`

**Before:**
```json
{
  "activities": {
    "last_walk": null,       // ❌ Removed
    "last_exercise": null    // ❌ Removed
  }
}
```

**After:**
```json
{
  "activities": {
    "last_hydration": null,
    "last_coffee": null,
    "last_meal": null,
    "last_snack": null,
    "last_finger_stretch": null,
    "last_back_stretch": null,
    "last_standing_break": null
  }
}
```

Only activities defined in `resource_tracked_activities.json` are included.

---

### 4. ✅ Updated Class Docstring

**Before:**
```python
"""
Activities tracked:
- hydration (water/drinks)
- meal (main meals)
- snack (light eating)
- coffee (coffee consumption + daily counter)
- walk (movement/walking)           # ❌ Hardcoded list
- exercise (exercise sessions)       # ❌ Hardcoded list
- finger_stretch (...)
...
"""
```

**After:**
```python
"""
Activities are loaded dynamically from resource_tracked_activities.json.
No hardcoded activity list - all activities come from config.
"""
```

---

## Why This Happened

### The Old Way (Broken) ❌
```
Code has hardcoded list: ['walk', 'exercise']
    ↓
reset_all_activities() creates last_walk, last_exercise
    ↓
Agent sees these fields in wellness_activities
    ↓
Agent returns counts for them (even though they're not in config)
```

### The New Way (Fixed) ✅
```
resource_tracked_activities.json defines activities
    ↓
Code reads config: get_all_tracked_fields()
    ↓
Only creates fields for configured activities
    ↓
Agent can only return counts for real activities
```

---

## Current Flow

### Single Source of Truth: `resource_tracked_activities.json`

```json
{
  "activities": {
    "hydration": {...},
    "coffee": {...},
    "meal": {...},
    "snack": {...},
    "finger_stretch": {...},
    "back_stretch": {...},
    "standing_break": {...}
  }
}
```

### Everything Derives From Config

1. **`get_all_tracked_fields()`** reads config → `['hydration', 'coffee', 'meal', ...]`
2. **`reset_all_activities()`** loops through fields → creates `last_hydration`, `last_coffee`, etc.
3. **Agent prompt** shows fields from config → only lists real activities
4. **Agent output** can only return activities that exist in config

---

## Benefits

### 1. **No More Hallucinations** 🎯
Agent can't return counts for non-existent activities because they're not in the data structure.

### 2. **Easy to Add/Remove Activities** ⚙️
Just edit `resource_tracked_activities.json`:
- Add an activity → automatically tracked
- Remove an activity → automatically removed from system

### 3. **Single Source of Truth** 📋
One file (`resource_tracked_activities.json`) controls:
- What activities exist
- What thresholds they have
- What guidance to show
- What fields to create in data structures

### 4. **No Code Changes Needed** 🚫
To add/remove activities, just edit the JSON config. No code changes required.

---

## Testing

After restart:

### 1. Check Agent Output
Run a refresh and check activity_tracker output:
```json
{
  "activity_counts": {
    "coffee": "2",
    "hydration": "1",
    "snack": "0",
    "finger_stretch": "1",
    "back_stretch": "0",
    "standing_break": "0",
    "meal": "1"
  }
}
```

**No more `walk` or `exercise`!** ✅

### 2. Check Resource File
Open `resources/resource_user_wellness_activities.json`:
```json
{
  "activities": {
    // Only activities from config
    // No last_walk or last_exercise
  }
}
```

### 3. Check Debug UI
Visit `/debug/status` and check "✅ Wellness Activities (Tracking Data)":
```json
{
  "activities": {
    "last_hydration": "...",
    "last_coffee": "...",
    "last_meal": "...",
    "last_snack": "...",
    "last_finger_stretch": "...",
    "last_back_stretch": "...",
    "last_standing_break": "..."
    // No walk or exercise ✅
  }
}
```

---

## Future-Proof

Want to add `walk` back? Just add it to the config:

```json
{
  "activities": {
    "walk": {
      "display_name": "Walk",
      "field_name": "walk",
      "threshold": {
        "minutes": 180,
        "label": "Every 3 hours"
      }
    }
  }
}
```

**That's it!** The system will automatically:
- Create `last_walk` field
- Reset it at day start
- Show it in agent prompts
- Track it in resource file
- Display it in debug UI

No code changes needed! 🎉

---

## Summary

✅ **Removed hardcoded activity lists** from `reset_all_activities()` and `get_activity_summary()`  
✅ **Made everything dynamic** based on `resource_tracked_activities.json`  
✅ **Removed `walk` and `exercise`** from resource file  
✅ **Updated documentation** to reflect dynamic loading  

**Result:** Agent can no longer hallucinate activities that don't exist in config! 🎯
