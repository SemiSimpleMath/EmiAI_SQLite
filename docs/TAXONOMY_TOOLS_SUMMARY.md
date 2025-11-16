# Taxonomy Tools Summary

## Overview

All 4 taxonomy tools have been created with descriptions and argument schemas.

## Tool 1: taxonomy_merge_categories

### Description
```
taxonomy_merge_categories: Merge one taxonomy category into another, eliminating duplicates.

**Purpose:** Consolidate duplicate or redundant taxonomy categories by merging one into another.

**What it does:**
1. Moves all children from source category to destination category
2. Moves all node classifications from source to destination
3. Deletes the source category

**Parameters:**
- source_id (required): ID of the category to merge (this will be deleted)
- destination_id (required): ID of the category to merge into (this will be kept)

**Use this when:**
- You find duplicate categories (e.g., "email_address" and "email")
- You need to consolidate similar categories
- You want to eliminate redundancy in the taxonomy

**Returns:**
- success: Whether the operation succeeded
- message: Description of what was done
- source_label: Label of the merged category
- destination_label: Label of the category kept
- children_moved: Number of child categories moved
- classifications_moved: Number of node classifications moved

**Safety:** This is a DESTRUCTIVE operation. The source category will be permanently deleted. Use with caution.
```

### Argument Schema
```python
class taxonomy_merge_categories_args(BaseModel):
    """Input schema for taxonomy_merge_categories tool."""
    source_id: int = Field(description="ID of the category to merge (will be deleted)")
    destination_id: int = Field(description="ID of the category to merge into (will be kept)")


class taxonomy_merge_categories_arguments(BaseModel):
    """Tool wrapper for taxonomy_merge_categories."""
    reasoning: str = Field(description="Reasoning for why these categories should be merged")
    tool_name: str
    arguments: taxonomy_merge_categories_args
```

**Notes:**
- ✅ Has `reasoning` field (like `kg_update_node`)
- ✅ Clear Field descriptions
- ✅ Comprehensive tool description

---

## Tool 2: taxonomy_rename_category

### Description
```
taxonomy_rename_category: Rename a taxonomy category.

**Purpose:** Change the label of a taxonomy category (e.g., fix typos, improve naming consistency).

**Parameters:**
- category_id (required): ID of the category to rename
- new_label (required): New label for the category (will be normalized to lowercase_snake_case)

**Use this when:**
- Fixing typos (e.g., "midle_school" -> "middle_school")
- Improving naming consistency
- Making labels more descriptive

**Returns:**
- success: Whether the operation succeeded
- message: Description of what was done
- category_id: ID of the renamed category
- old_label: Previous label
- new_label: New label (normalized)

**Safety:** This is a safe operation. The category structure remains unchanged.
```

### Argument Schema
```python
class taxonomy_rename_category_args(BaseModel):
    """Input schema for taxonomy_rename_category tool."""
    category_id: int = Field(description="ID of the category to rename")        
    new_label: str = Field(description="New label for the category")


class taxonomy_rename_category_arguments(BaseModel):
    """Tool wrapper for taxonomy_rename_category."""
    reasoning: str = Field(description="Reasoning for why this category should be renamed")
    tool_name: str
    arguments: taxonomy_rename_category_args
```

**Notes:**
- ✅ Has `reasoning` field
- ✅ Clear Field descriptions
- ✅ ASCII-only (fixed arrow character: → to ->)

---

## Tool 3: taxonomy_move_category

### Description
```
taxonomy_move_category: Move a taxonomy category to a new parent.

**Purpose:** Change the position of a category in the taxonomy hierarchy (fix misplacements).

**Parameters:**
- category_id (required): ID of the category to move
- new_parent_id (optional): ID of the new parent category (omit or set to null for root level)

**Use this when:**
- Fixing misplaced categories (e.g., moving "dog" from under "vehicle" to under "animal")
- Reorganizing the taxonomy structure
- Moving categories to root level

**Returns:**
- success: Whether the operation succeeded
- message: Description of what was done
- category_id: ID of the moved category
- label: Label of the moved category
- old_parent_id: Previous parent ID
- new_parent_id: New parent ID

**Safety:** This is a safe operation. Checks for circular references are performed automatically.
```

### Argument Schema
```python
class taxonomy_move_category_args(BaseModel):
    """Input schema for taxonomy_move_category tool."""
    category_id: int = Field(description="ID of the category to move")
    new_parent_id: Optional[int] = Field(default=None, description="ID of the new parent category (None or empty for root level)")


class taxonomy_move_category_arguments(BaseModel):
    """Tool wrapper for taxonomy_move_category."""
    reasoning: str = Field(description="Reasoning for why this category should be moved")
    tool_name: str
    arguments: taxonomy_move_category_args
```

**Notes:**
- ✅ Has `reasoning` field
- ✅ Clear Field descriptions
- ✅ Uses `Optional[int]` for nullable parent_id
- ✅ Includes circular reference safety check

---

## Tool 4: taxonomy_update_description

### Description
```
taxonomy_update_description: Update the description of a taxonomy category.

**Purpose:** Add or update the description text for a taxonomy category.

**Parameters:**
- category_id (required): ID of the category to update
- new_description (required): New description text (use empty string to clear the description)

**Use this when:**
- Adding missing descriptions to important categories
- Clarifying what a category represents
- Improving taxonomy documentation

**Returns:**
- success: Whether the operation succeeded
- message: Description of what was done
- category_id: ID of the updated category
- label: Label of the category
- old_description: Previous description
- new_description: New description

**Safety:** This is a safe operation. Only the description text is modified.
```

### Argument Schema
```python
class taxonomy_update_description_args(BaseModel):
    """Input schema for taxonomy_update_description tool."""
    category_id: int = Field(description="ID of the category to update")        
    new_description: str = Field(description="New description for the category (empty string to clear)")


class taxonomy_update_description_arguments(BaseModel):
    """Tool wrapper for taxonomy_update_description."""
    reasoning: str = Field(description="Reasoning for why this description should be added/updated")
    tool_name: str
    arguments: taxonomy_update_description_arguments
```

**Notes:**
- ✅ Has `reasoning` field
- ✅ Clear Field descriptions
- ✅ Allows empty string to clear description

---

## Comparison with KG Tools

### Schema Pattern Consistency

**KG Tools Pattern** (varies):
- `kg_create_node`: NO reasoning field
- `kg_update_node`: HAS reasoning field
- `kg_delete_node`: NO reasoning field

**Taxonomy Tools Pattern** (consistent):
- ALL taxonomy tools: HAVE reasoning field ✅

**Decision**: We chose to include `reasoning` in all taxonomy tools because:
1. Taxonomy operations are structural changes that benefit from documented reasoning
2. Consistency across all taxonomy tools makes them easier to use
3. The reasoning helps with debugging and audit trails

### Field Description Pattern

**All taxonomy tools follow this pattern**:
```python
class tool_name_args(BaseModel):
    """Input schema for tool_name tool."""
    param1: type = Field(description="Clear description")
    param2: type = Field(description="Clear description")

class tool_name_arguments(BaseModel):
    """Tool wrapper for tool_name."""
    reasoning: str = Field(description="Reasoning for why...")
    tool_name: str
    arguments: tool_name_args
```

This matches the pattern used by `kg_update_node` and other KG tools that have reasoning.

---

## Files

### Tool Implementations
- `app/assistant/lib/tools/taxonomy_merge_categories/taxonomy_merge_categories.py`
- `app/assistant/lib/tools/taxonomy_rename_category/taxonomy_rename_category.py`
- `app/assistant/lib/tools/taxonomy_move_category/taxonomy_move_category.py`
- `app/assistant/lib/tools/taxonomy_update_description/taxonomy_update_description.py`

### Tool Descriptions
- `app/assistant/lib/tools/taxonomy_merge_categories/prompts/taxonomy_merge_categories_description.j2`
- `app/assistant/lib/tools/taxonomy_rename_category/prompts/taxonomy_rename_category_description.j2`
- `app/assistant/lib/tools/taxonomy_move_category/prompts/taxonomy_move_category_description.j2`
- `app/assistant/lib/tools/taxonomy_update_description/prompts/taxonomy_update_description_description.j2`

### Tool Schemas
- `app/assistant/lib/tools/taxonomy_merge_categories/tool_forms/tool_forms.py`
- `app/assistant/lib/tools/taxonomy_rename_category/tool_forms/tool_forms.py`
- `app/assistant/lib/tools/taxonomy_move_category/tool_forms/tool_forms.py`
- `app/assistant/lib/tools/taxonomy_update_description/tool_forms/tool_forms.py`

---

## Summary

✅ **All 4 taxonomy tools have:**
1. Comprehensive descriptions with Purpose, Parameters, Use Cases, Returns, and Safety notes
2. Proper Pydantic schemas with Field descriptions
3. Consistent `reasoning` field in all tools
4. ASCII-only characters (no emojis or special arrows)
5. Clear, actionable documentation

✅ **All tools are ready for use by the taxonomy_team_manager planner!**


