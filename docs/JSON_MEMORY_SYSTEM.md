# JSON Memory System Architecture

## Overview

The memory system has been refactored from markdown-based storage to **JSON-based storage** with **LLM semantic understanding** for intelligent editing. This enables:

1. **Structured metadata**: Store `expiry_date`, `confidence`, `durability`, `added`, etc.
2. **Semantic understanding**: LLMs understand context and detect duplicates semantically
3. **Precise execution**: Python applies edits mechanically after LLM decisions
4. **Complex operations**: Handle "delete all X preferences" spanning multiple locations

## Architecture: LLM + Python Division of Labor

### Core Principle
**LLMs provide SEMANTIC UNDERSTANDING, Python provides MECHANICAL PRECISION**

- ❌ **Don't**: Ask Python to understand "eggs" = "scrambled_eggs_with_lox"
- ✅ **Do**: Ask LLM to find locations, then Python deletes by exact path

## Components

### 1. **JSON Resource Files** (`resources/*.json`)

Structured user preferences with metadata:

```json
{
  "_metadata": {
    "resource_id": "resource_user_food_prefs",
    "tags": ["food"],
    "last_updated": "2025-12-28"
  },
  "food": {
    "likes": [
      {
        "item": "pasta_carbonara",
        "display": "Pasta (especially carbonara)",
        "added": "2025-12-28",
        "expiry": null
      }
    ]
  }
}
```

**Converted files:**
- `resource_user_food_prefs.json` (food preferences)
- `resource_user_routine.json` (daily routines, timing rules)
- `resource_user_health.json` (chronic conditions, physical needs)
- `resource_user_general_prefs.json` (communication style, interests)

### 2. **JSON → Markdown Renderer** (`app/assistant/memory/json_to_markdown.py`)

Converts JSON to human-readable markdown for agent prompts:

```python
def json_to_markdown(json_data: Dict[str, Any]) -> str:
    """Render JSON as markdown for LLM consumption"""
```

**Why?** Agents need readable text, but data must be stored as structured JSON.

**Integration:** `ResourceManager` automatically renders JSON files to markdown when loading into the global blackboard.

### 3. **Memory Pipeline** (Switchboard → Memory Runner)

#### Switchboard (`app/assistant/switchboard/switchboard_runner.py`)
- Extracts facts from user conversations
- Tags them (`food`, `routine`, `health`, etc.)
- Saves to `extracted_facts` table with `reasoning` field

#### Memory Runner (`app/assistant/memory/memory_runner.py`)
- Fetches unprocessed facts
- Uses `TagRouter` to find target JSON files
- Orchestrates **Finder → Editor → Handler** workflow

### 4. **Two-Agent JSON Editing System**

#### **Agent 1: `memory::json_finder`** (Nano, Fast)
**Role:** Search JSON semantically for relevant locations

**Input:**
- `json_content`: Full JSON file
- `query`: User preference (e.g., "User likes omelettes")

**Output:**
```json
{
  "locations": [
    {
      "path": "food.likes[2]",
      "current_value": "{'item': 'scrambled_eggs_with_lox', ...}",
      "relevance": "Contains 'eggs' in item and display text"
    }
  ],
  "suggested_insert_path": "food.likes",
  "reasoning": "Found 1 egg-related item..."
}
```

**Key Features:**
- Semantic matching: "eggs" finds "scrambled_eggs_with_lox"
- Multiple locations: "I'm vegan" finds meat across entire JSON
- Insert suggestions: Where to add new data if not found

#### **Agent 2: `memory::json_editor`** (Mini, Smart)
**Role:** Decide what edits to make

**Input:**
- `json_content`: Full JSON file
- `query`: User preference
- `found_locations`: Results from finder
- `suggested_insert_path`: Where to insert new data

**Output:**
```json
{
  "edits": [
    {
      "operation": "delete",
      "path": "food.likes[2]",
      "reason": "User wants to remove egg preferences"
    }
  ],
  "decision": "proceed",
  "reasoning": "Found egg preference, deleting as requested"
}
```

**Supported Operations:**
- `delete`: Remove item from list or field from dict
- `update`: Modify existing item
- `insert`: Add new item
- `no_change`: Reject if duplicate or invalid

**Key Features:**
- Duplicate detection: Rejects "User likes pasta" if pasta already exists
- Multi-edit support: "Remove all eggs" = multiple delete operations
- Semantic merging: Understands when to update vs. insert

### 5. **Memory JSON Handler** (`app/assistant/memory/memory_json_handler.py`)

**Role:** Mechanically execute edit operations from the editor agent

```python
handler.execute_edits([
    {"operation": "delete", "path": "food.likes[2]", "file": "resource_user_food_prefs.json"},
    {"operation": "insert", "path": "food.likes", "new_value": {...}}
])
```

**Features:**
- Path parsing: Handles `food.likes[2]` array indices
- Atomic operations: All-or-nothing execution
- Metadata updates: Auto-updates `last_updated`, adds `added` timestamps
- File safety: Validates paths before writing

### 6. **Tag Router** (`app/assistant/memory/tag_router.py`)

Maps fact tags to JSON resource files:

```python
tag_router.get_target_files_for_fact({'tags': ['food']})
# Returns: ['resource_user_food_prefs.json']
```

Reads tags from JSON `_metadata.tags` field.

## Data Flow

```
User Chat
    ↓
Switchboard Agent (extracts facts + tags)
    ↓
extracted_facts table
    ↓
Memory Runner
    ↓
Tag Router → target JSON files
    ↓
FOR EACH FILE:
    json_finder → locations
    json_editor → edits
    ↓
Memory JSON Handler → execute edits
    ↓
Updated JSON files
```

## Example: "Remove all egg preferences"

### 1. Finder Stage
```json
{
  "locations": [
    {
      "path": "food.likes[2]",
      "current_value": "scrambled_eggs_with_lox",
      "relevance": "Contains 'eggs'"
    }
  ],
  "reasoning": "Found 1 location with egg-related preferences"
}
```

### 2. Editor Stage
```json
{
  "edits": [
    {
      "operation": "delete",
      "path": "food.likes[2]",
      "reason": "User requested removal of egg preferences"
    }
  ],
  "decision": "proceed",
  "reasoning": "Clear intent to remove eggs"
}
```

### 3. Handler Stage
```python
# Loads resource_user_food_prefs.json
# Parses path: food.likes[2]
# Executes: del data['food']['likes'][2]
# Saves file with updated metadata
```

## Testing

Run end-to-end test:
```bash
python test_json_memory_system.py
```

**Test cases:**
1. ✅ **INSERT**: Add new preference (omelettes) → inserts into `food.likes`
2. ✅ **DELETE**: Remove egg preferences → deletes `food.likes[2]`
3. ✅ **DUPLICATE**: "User likes pasta" → rejects (already exists)

## Benefits Over Markdown

| Feature | Markdown | JSON |
|---------|----------|------|
| Metadata | ❌ YAML frontmatter only | ✅ Per-item metadata |
| Expiry dates | ❌ Not supported | ✅ `expiry: "2025-12-31"` |
| Duplicate detection | ❌ Text-based, unreliable | ✅ Semantic + structural |
| Complex edits | ❌ LLM rewrites sections | ✅ Precise path-based ops |
| Multi-location edits | ❌ Hard to coordinate | ✅ Single edit list |
| Array operations | ❌ Manual text parsing | ✅ Native `array[index]` |

## Configuration Files

### Finder Agent
- **Config**: `app/assistant/agents/memory/json_finder/config.yaml`
- **Model**: `gpt-4.1-nano` (fast, cheap)
- **Temp**: 0.1 (consistent)
- **Prompt**: `prompts/system.j2` - "Find ALL relevant locations"

### Editor Agent
- **Config**: `app/assistant/agents/memory/json_editor/config.yaml`
- **Model**: `gpt-4.1-mini` (smart decisions)
- **Temp**: 0.2 (balanced)
- **Prompt**: `prompts/system.j2` - "Decide delete/update/insert/reject"

## Future Enhancements

1. **Confidence decay**: Lower confidence for old preferences
2. **Expiry enforcement**: Auto-delete expired items
3. **Conflict resolution**: Handle contradictory preferences
4. **Batch operations**: Optimize multiple edits to same file
5. **Undo/rollback**: Version control for preference changes

## Migration Notes

**Archived files** (`.md.archive`):
- `resource_user_food_prefs.md`
- `resource_user_routine.md`
- `resource_user_health.md`
- `resource_user_general_prefs.md`

**Deleted agents** (no longer needed):
- `memory::section_finder` (replaced by `json_finder`)
- `memory::section_editor` (replaced by `json_editor`)
- `memory::planner` (replaced by direct finder→editor workflow)

## Key Design Decisions

1. **Why two agents?**
   - Finder is fast (Nano) for search
   - Editor is smart (Mini) for decisions
   - Separation of concerns: locate vs. decide

2. **Why not one LLM call?**
   - Finder can cache results across multiple queries
   - Editor focuses purely on decision logic
   - Better debugging: see what was found vs. what was decided

3. **Why path-based operations?**
   - Precise: No ambiguity about what to change
   - Atomic: Easy to rollback on error
   - Composable: Multiple operations in one transaction

4. **Why LLM + Python split?**
   - LLMs excel at semantic understanding
   - Python excels at precise execution
   - Best of both worlds: intelligence + reliability

