# Memory System Refactor: Markdown → JSON

## Summary
Refactored the memory/preference management system from LLM-edited markdown files to structured JSON operations. This solves text surgery bugs, enables metadata tracking (expiry dates), and makes the system faster and more reliable.

## Architecture Change

### Before (LLM Text Surgery):
1. Switchboard extracts fact
2. Memory Manager multi-agent:
   - Section Finder (LLM) finds relevant lines
   - Section Editor (LLM) edits markdown text
   - Update tool patches file
3. **Problems**: Formatting errors, duplicates, slow, expensive

### After (Structured Operations):
1. Switchboard extracts fact with tags
2. Memory Planner (single LLM) outputs structured operations:
   ```json
   {
     "operation": "append",
     "file": "resource_user_food_prefs.json",
     "path": "food.likes",
     "value": {"item": "kung_pao_chicken", "display": "Kung pao chicken"},
     "expiry": null
   }
   ```
3. MemoryJsonHandler (Python) executes operations mechanically
4. **Benefits**: No formatting errors, bulletproof duplicates, fast, cheap

## Files Changed

### Created:
- `resources/resource_user_food_prefs.json` - Food/drink preferences with metadata
- `resources/resource_user_routine.json` - Daily routine preferences
- `resources/resource_user_health.json` - Health conditions & accommodations
- `resources/resource_user_general_prefs.json` - Communication, entertainment, misc
- `app/assistant/memory/memory_json_handler.py` - Python executor for JSON operations
- `app/assistant/agents/memory/planner/prompts/system.j2` (NEW) - Outputs structured ops

### Modified:
- `app/assistant/memory/tag_router.py` - Reads JSON metadata instead of YAML front-matter
- `app/assistant/memory/memory_runner.py` - Calls planner + handler instead of multi-agent manager
- `app/assistant/agents/memory/planner/agent_form.py` - New output schema with operations

### Archived:
- `resources/resource_user_*.md` → `.md.archive` (4 files)
- `app/assistant/agents/memory/section_editor/` → `.archive`
- `app/assistant/agents/memory/section_finder/` → `.archive`

## JSON Schema

All preference files follow this structure:

```json
{
  "_metadata": {
    "resource_id": "resource_user_food_prefs",
    "version": "2.0",
    "last_updated": "2025-12-28",
    "tags": ["food", "drink"],
    "description": "..."
  },
  "food": {
    "likes": [
      {
        "item": "pasta_carbonara",
        "display": "Pasta (especially carbonara)",
        "added": "2025-12-28",
        "expiry": null
      }
    ],
    "dislikes": [...],
    "preferences": [...],
    "allergies": []
  },
  "drinks": {...}
}
```

### Key Fields:
- **`item`**: Unique key for duplicate detection
- **`display`**: Human-readable text
- **`added`**: Date first mentioned
- **`expiry`**: Optional expiry date (YYYY-MM-DD) for temporary facts

## Operation Types

1. **`append`**: Add new item to list (with duplicate check by `item` key)
2. **`update`**: Modify existing item/object
3. **`remove`**: Delete item from list
4. **`no_change`**: Duplicate detected, skip gracefully

## LLM Responsibilities

**Memory Planner decides:**
- Is this new, duplicate, or conflicting?
- Which operation(s) to perform?
- Initial values (display, expiry)

**Python executes:**
- Navigate JSON paths
- Check duplicates
- Insert/update/delete
- Add metadata (added date)
- Save file

## Testing Status

✅ All code changes complete
⚠️ End-to-end testing pending (need to enable memory runner and test with real chat)

## Next Steps

1. Enable memory runner in background tasks
2. Test with chat: "I like kung pao chicken"
3. Verify JSON file is updated correctly
4. Test duplicate detection
5. Test expiry dates with temporary facts


