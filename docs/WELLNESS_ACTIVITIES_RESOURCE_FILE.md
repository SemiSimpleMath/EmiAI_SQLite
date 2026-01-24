# Wellness Activities Resource File - Implementation Plan

## Problem
Currently `wellness_activities` data (timestamps and counts) is:
1. Stored in memory: `status_data["wellness_activities"]`
2. Saved embedded in `resource_user_physical_status.json` (big mixed file)
3. Not accessible as its own resource for agents

## Solution: Create `resource_user_wellness_activities.json`

### Schema
```json
{
  "_metadata": {
    "resource_id": "resource_user_wellness_activities",
    "description": "Timestamps and counts for tracked wellness activities",
    "last_updated": "2026-01-08T11:45:00Z"
  },
  "activities": {
    "last_hydration": "2026-01-08T11:30:00Z",
    "last_coffee": "2026-01-08T09:00:00Z",
    "last_meal": "2026-01-08T12:00:00Z",
    "last_snack": "2026-01-08T10:30:00Z",
    "last_finger_stretch": "2026-01-08T11:20:00Z",
    "last_back_stretch": "2026-01-08T11:20:00Z",
    "last_standing_break": "2026-01-08T11:20:00Z",
    "last_walk": null,
    "last_exercise": null
  },
  "counters": {
    "coffees_today": 2,
    "coffees_today_date": "2026-01-08"
  }
}
```

---

## Implementation Steps

### 1. Add Save Function to `activity_recorder.py`

```python
def save_wellness_activities_resource(self):
    """Save wellness activities to dedicated resource file."""
    try:
        from pathlib import Path
        import json
        from datetime import datetime, timezone
        
        # Path to resource file
        resources_dir = Path(__file__).resolve().parents[3] / 'resources'
        resource_file = resources_dir / 'resource_user_wellness_activities.json'
        
        activities = self.status_data.get("wellness_activities", {})
        
        # Separate timestamps from counters
        timestamps = {}
        counters = {}
        
        for key, value in activities.items():
            if key.startswith("coffees_today"):
                counters[key] = value
            else:
                timestamps[key] = value
        
        # Build resource structure
        resource_data = {
            "_metadata": {
                "resource_id": "resource_user_wellness_activities",
                "description": "Timestamps and counts for tracked wellness activities",
                "last_updated": datetime.now(timezone.utc).isoformat()
            },
            "activities": timestamps,
            "counters": counters
        }
        
        # Write to file
        resources_dir.mkdir(parents=True, exist_ok=True)
        with open(resource_file, 'w', encoding='utf-8') as f:
            json.dump(resource_data, f, indent=2, ensure_ascii=False)
        
        logger.debug(f"Saved wellness activities resource file")
        
    except Exception as e:
        logger.error(f"Error saving wellness activities resource: {e}")
```

### 2. Call Save Function After Activity Updates

In `activity_recorder.py`:

```python
def record_activity(self, activity_type: str, timestamp: datetime = None):
    # ... existing code ...
    
    logger.info(f"Recorded activity: {activity_type} at {timestamp_iso}")
    
    # Save to resource file
    self.save_wellness_activities_resource()  # ← NEW
```

And in:
- `set_activity_count()`
- `reset_daily_counters()`
- `reset_all_activities()`

### 3. Register in ResourceManager (Automatic)

The file will be automatically loaded by `ResourceManager.load_all_from_directory()` at startup because it follows the naming convention `resource_*.json`.

### 4. Use in Agent Prompts

Agents can now directly reference it:

```yaml
# In agent config.yaml
user_context_items:
- resource_user_wellness_activities
```

```jinja2
# In agent prompt template
Last hydration: {{ resource_user_wellness_activities.activities.last_hydration }}
Coffees today: {{ resource_user_wellness_activities.counters.coffees_today }}
```

---

## Benefits

1. **Separation of Concerns:**
   - Config (what to track) → `resource_tracked_activities.json`
   - Data (tracking values) → `resource_user_wellness_activities.json`

2. **Agent Access:**
   - Any agent can now inject wellness activities without needing entire physical_status

3. **Cleaner Structure:**
   - No more embedding in `resource_user_physical_status.json`
   - Dedicated file is easier to understand and debug

4. **Persistent Storage:**
   - Data survives restarts
   - Can be backed up independently

5. **Debugging:**
   - Easy to inspect: just open the JSON file
   - Shows in debug UI automatically

---

## Migration (Optional)

If we want to remove `wellness_activities` from `resource_user_physical_status.json`:

1. Keep it for now (backward compatibility)
2. Deprecate over time
3. Eventually remove from `_save_status()` and `_create_empty_status_data()`

Or just keep both:
- `resource_user_physical_status.json` keeps a copy (for legacy)
- `resource_user_wellness_activities.json` is the source of truth

---

## Next Step

Should I implement this? It's a ~30 line addition to `activity_recorder.py` + creating the initial resource file.
