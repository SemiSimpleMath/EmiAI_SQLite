# Taxonomy Integrity Auto-Processing

## Overview

The `taxonomy_integrity_pipeline.py` now supports automated processing of taxonomy issues through the `taxonomy_team_manager`. This enables a complete workflow:

1. **Validator finds issues** → 2. **Team manager fixes issues** → 3. **Repeat for all issues**

## How It Works

### Step 1: Integrity Validation
The `taxonomy_integrity_validator` agent analyzes a taxonomy branch (e.g., Entity, Event) and identifies:
- Duplicate categories
- Misplaced categories
- Missing descriptions
- Organizational issues

### Step 2: Issue Formatting
Each issue is formatted with rich context for the team manager:
- Full category paths
- Parent relationships
- Descriptions
- Ordered list of actions to take
- Confidence scores

### Step 3: Sequential Processing
The pipeline loops through issues one at a time:
- Displays the issue to the user
- Asks: Process / Skip / Exit
- Calls `taxonomy_team_manager` if user chooses to process
- Shows the result
- Moves to next issue

## Usage

### From IDE (Interactive)

```bash
python app/assistant/kg_core/taxonomy/taxonomy_integrity_pipeline.py
```

Then select:
- **Option 1**: Analyze specific branch (e.g., "Entity") with team manager
- **Option 2**: Analyze all branches with team manager
- **Option 3**: Analyze only (no fixes)

### Example Session

```
🏷️  TAXONOMY INTEGRITY PIPELINE
================================================================================

Options:
1. Analyze specific branch (with team manager processing)
2. Analyze all branches (with team manager processing)
3. Analyze only (no team manager)
4. Exit

Select option (1-4): 1

Enter branch name (e.g., Entity, Event, State): Entity

📥 Loading taxonomy from database...
   Filtering for branch: Entity
   Found branch: Entity (ID: 123)

🔍 Analyzing Entity branch...
   Total categories: 245
   Calling LLM for analysis...

================================================================================
📊 INTEGRITY ANALYSIS SUMMARY
================================================================================

🌳 Branch: Entity
   Categories: 245
   Issues found: 3

   📋 Issue #1:
      Problem: Duplicate 'machine' subtree at 'entity > artifact > machine' (id: 746) with children...
      Actions: 3 step(s)
      Confidence: 95.0%

✅ Analysis complete. Found 3 issue(s).

Process issues with team manager? (y/n): y

================================================================================
🤖 PROCESSING ISSUES WITH TAXONOMY TEAM MANAGER
================================================================================

Total issues to process: 3

================================================================================
📋 ISSUE 1/3
================================================================================

🎯 Task: Duplicate 'machine' subtree at 'entity > artifact > machine' (id: 746) with children...

Options:
  1. Process this issue with team manager
  2. Skip this issue
  3. Exit (stop processing)

Select option (1-3): 1

🚀 Calling taxonomy_team_manager for issue 1...
--------------------------------------------------------------------------------
[Team manager processes the issue...]
--------------------------------------------------------------------------------
📊 TEAM MANAGER RESULT:
--------------------------------------------------------------------------------
✅ Successfully merged categories...
```

## Key Features

### 1. **User Control**
- User decides whether to process each issue
- Can skip issues or exit at any time
- Errors don't stop the entire pipeline

### 2. **Rich Context**
Each issue includes:
```
PROBLEM:
Duplicate 'machine' subtree...

AFFECTED CATEGORIES:
  [CATEGORY] 'machine' (DUPLICATE - 2 instances):
    - ID: 746
      Path: entity > artifact > machine
      Parent: artifact
      Description: (no description)
    - ID: 492
      Path: entity > artifact > product > physical_product > machine
      Parent: physical_product
      Description: Mechanical devices

ACTIONS TO TAKE (IN ORDER):
  1. merge_categories(746, 492)
     => Merge 'machine' (ID 746) at 'entity > artifact > machine' 
        INTO 'machine' (ID 492) at 'entity > artifact > product > physical_product > machine'
  2. merge_categories(747, 493)
     => Merge 'robot' (ID 747) at 'entity > artifact > machine > robot' 
        INTO 'robot' (ID 493) at 'entity > artifact > product > physical_product > machine > robot'
```

### 3. **Sequential Processing**
- One issue at a time
- Clear results after each issue
- Option to continue or stop

### 4. **Error Handling**
- If team manager fails, user can choose to continue or stop
- Full traceback displayed for debugging
- Pipeline doesn't crash on errors

## Architecture

### Files Modified
- `app/assistant/kg_core/taxonomy/taxonomy_integrity_pipeline.py`
  - Added `process_issues_with_team_manager()` function
  - Updated `run()` to return formatted issues
  - Enhanced `if __name__ == "__main__"` with team manager options

### Files Used
- `app/assistant/agents/knowledge_graph_add/taxonomy_integrity_validator/`
  - Finds issues (updated to understand merge cascading)
- `app/assistant/multi_agents/taxonomy_team_manager/`
  - Fixes issues using taxonomy tools
- `app/assistant/lib/core_tools/taxonomy_tool/`
  - Executes actual database operations
- `app/assistant/kg_core/taxonomy/utils.py`
  - Core taxonomy manipulation functions

## Merge Cascade Behavior

The validator now understands that:

1. **`merge_categories(source, dest)` moves children, doesn't merge them**
   - If both categories have a child named "robot", you'll end up with 2 children named "robot"
   - Must merge those duplicate children in separate actions

2. **Correct order for duplicate subtrees:**
   ```
   merge_categories(746, 492)  # Parent
   merge_categories(747, 493)  # Child level 1
   merge_categories(748, 494)  # Child level 2
   ```

This is now documented in the validator's system prompt with examples.

## Benefits

1. **Automation**: Reduces manual work in taxonomy maintenance
2. **Consistency**: Ensures all fixes follow the same process
3. **Transparency**: User sees and approves each fix
4. **Safety**: Can skip problematic issues without breaking the pipeline
5. **Completeness**: Processes all issues found in one session


