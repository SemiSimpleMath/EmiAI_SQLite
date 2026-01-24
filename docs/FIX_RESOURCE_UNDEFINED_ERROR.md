# Fix: 'resource_tracked_activities' is undefined

## Error
```
ERROR - [activity_tracker] ERROR while rendering user prompt: 'resource_tracked_activities' is undefined
```

## Root Cause

The `resource_tracked_activities` is not loaded into `DI.global_blackboard` because **the system wasn't restarted** after you updated the JSON file structure.

`ResourceManager` loads all resources at startup (in `bootstrap.py` line 56), so changes to resource files require a restart.

---

## Solution: Restart the System

### Step 1: Stop the Application
Stop your assistant (however you normally stop it).

### Step 2: Restart
Start it again (however you normally start it).

The startup logs should show:
```
✅ Loaded JSON resource 'resource_tracked_activities' from resource_tracked_activities.json
```

---

## Verification (Optional)

After restart, you can verify the resource is loaded by running:

```bash
# This will only work AFTER the app has started and initialized DI.global_blackboard
python check_resource_loaded.py
```

Expected output:
```
✅ DI.global_blackboard exists
✅ 'resource_tracked_activities' is loaded in global blackboard

📋 Contents:
  Type: dict
  Keys: ['version', 'description', 'activities']
  Activities (7): ['back_stretch', 'finger_stretch', 'standing_break', 'hydration', 'coffee', 'meal', 'snack']
  
  Sample ('back_stretch'):
    display_name: Back Stretch
    field_name: back_stretch
    threshold.minutes: 50
    threshold.label: Every 45 to 60 min of sitting (chronic pain)

✅ Resource is properly loaded - templates should work!
```

---

## Why This Happens

1. **Resources load at startup:** `bootstrap.py` calls `resource_manager.load_all_from_directory("resources")` once during initialization
2. **No hot reload:** If you edit a resource file while the app is running, the old version stays in memory
3. **Template error:** When the agent tries to render its prompt, Jinja can't find `resource_tracked_activities` in the context

---

## Prevention

In the future, always **restart the application** after editing:
- `resources/*.json` files
- `resources/*.md` files
- Agent config files (`config.yaml`)
- Agent prompts (`prompts/*.j2`)

Some files support hot reload (like code), but resource files don't.

---

## If Restart Doesn't Fix It

### 1. Check for JSON syntax errors
```bash
python -c "import json; json.load(open('resources/resource_tracked_activities.json')); print('Valid JSON')"
```

### 2. Check startup logs
Look for:
```
✅ Loaded JSON resource 'resource_tracked_activities' from resource_tracked_activities.json
```

Or errors:
```
❌ Failed to load JSON resource 'resource_tracked_activities' from ...
```

### 3. Check file permissions
Make sure the file is readable:
```bash
# Windows
dir resources\resource_tracked_activities.json

# Should show file size and timestamp
```

---

## Summary

**Problem:** System using old cached version of resource file (or no version at all)

**Solution:** Restart the application

**After restart:** The error should disappear and templates should render correctly! ✅
