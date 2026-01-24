# Wellness Activities Resource - Smart Reconciliation ✅

## How It Works

The `save_wellness_activities_resource()` function now implements **smart reconciliation**:

---

## The Logic

### On Every Save:

```python
tracked_fields = get_all_tracked_fields()  # Read from config

for field_name in tracked_fields:
    last_field = f"last_{field_name}"
    
    # Keep existing value if present, otherwise null
    activities_dict[last_field] = activities.get(last_field, None)
```

---

## Three Scenarios

### 1. File Doesn't Exist (First Save)
```
Config: ['hydration', 'coffee', 'meal']
Data in memory: {}

Result:
{
  "activities": {
    "last_hydration": null,
    "last_coffee": null,
    "last_meal": null
  }
}
```

✅ **Generated from config with null values**

---

### 2. Field Added to Config
```
Config: ['hydration', 'coffee', 'meal', 'walk']  ← NEW!
Existing file: {
  "last_hydration": "2026-01-08T10:00:00Z",
  "last_coffee": "2026-01-08T09:00:00Z",
  "last_meal": "2026-01-08T12:00:00Z"
}

Result:
{
  "activities": {
    "last_hydration": "2026-01-08T10:00:00Z",  ✅ Preserved
    "last_coffee": "2026-01-08T09:00:00Z",     ✅ Preserved
    "last_meal": "2026-01-08T12:00:00Z",       ✅ Preserved
    "last_walk": null                           ✅ Added with null
  }
}
```

✅ **Existing values preserved, new field added**

---

### 3. Field Removed from Config
```
Config: ['hydration', 'coffee']  ← 'meal' removed
Existing file: {
  "last_hydration": "2026-01-08T10:00:00Z",
  "last_coffee": "2026-01-08T09:00:00Z",
  "last_meal": "2026-01-08T12:00:00Z"
}

Result:
{
  "activities": {
    "last_hydration": "2026-01-08T10:00:00Z",  ✅ Preserved
    "last_coffee": "2026-01-08T09:00:00Z"      ✅ Preserved
    // last_meal is gone ✅
  }
}
```

✅ **Removed fields not in config, preserved remaining**

---

## Key Behaviors

### ✅ Preserves Existing Data
If you record `last_hydration` and then save again, the value is kept.

### ✅ Adds New Fields
Add an activity to config → next save adds it to file with `null` value.

### ✅ Removes Old Fields  
Remove an activity from config → next save removes it from file (even if it had a value).

### ✅ Day Start Reset
When `reset_all_activities()` is called:
1. Memory values are set to `null`
2. Then `save_wellness_activities_resource()` is called
3. File gets all fields from config with `null` values

---

## Example Flow

### Day 1: Initial Setup
```
1. Config has: ['hydration', 'coffee', 'meal']
2. User records: "drank water"
3. Save creates file with:
   - last_hydration: "2026-01-08T10:00:00Z"
   - last_coffee: null
   - last_meal: null
```

### Day 2: Add Walking to Config
```
1. Edit config, add 'walk'
2. Restart app (config reloaded)
3. Next save updates file:
   - last_hydration: (previous value)
   - last_coffee: (previous value)
   - last_meal: (previous value)
   - last_walk: null  ← NEW
```

### Day 3: Remove Meal from Config
```
1. Edit config, remove 'meal'
2. Restart app
3. Next save updates file:
   - last_hydration: (previous value)
   - last_coffee: (previous value)
   - last_walk: (previous value)
   // last_meal removed ← GONE
```

### Day 4: Day Start Reset
```
1. Day start triggers reset_all_activities()
2. All values in memory set to null
3. save_wellness_activities_resource() called
4. File updated:
   - last_hydration: null
   - last_coffee: null
   - last_walk: null
   // All reset, structure from config
```

---

## Benefits

### 1. **Data Preservation** 💾
Existing activity timestamps are never lost unless:
- Field removed from config (intentional)
- Day start reset (intentional)

### 2. **Config Sync** 🔄
File structure **always** matches config:
- Add to config → appears in file
- Remove from config → removed from file

### 3. **No Manual Intervention** 🤖
Just edit config and restart. File auto-updates on next save.

### 4. **Safe Migrations** 🛡️
Adding/removing activities doesn't break anything:
- No orphaned fields
- No missing fields
- No data loss for active fields

---

## Technical Details

### What Gets Reconciled

**Activities Section:**
```python
# For each field in config:
activities_dict[last_field] = activities.get(last_field, None)
```

- If field exists in memory → use that value
- If field doesn't exist in memory → use `null`
- If field not in config → don't include it

**Counters Section:**
```python
# Only include if exists in data:
if count_field in activities:
    counters[count_field] = activities[count_field]
```

- Only include counters that actually have values
- Don't create empty counters for all activities

---

## Log Output

```
✅ Saved wellness activities resource file (7 activities, reconciled with config)
```

Shows:
- Number of activities (from config)
- Confirmation that reconciliation happened

---

## Summary

✅ **Smart merge** - preserves data, updates structure  
✅ **Config-driven** - file structure always matches config  
✅ **Safe** - no data loss on config changes  
✅ **Automatic** - happens on every save

**The file is now a perfect blend of config structure + actual data!** 🎯
