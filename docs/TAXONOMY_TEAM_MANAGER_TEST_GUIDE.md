# Taxonomy Team Manager Test Guide

## Overview

This guide explains how to test the `taxonomy_team_manager` using the test files in `app/assistant/tests/manager_tests/taxonomy_team/`.

## Test Files

### 1. Main Test: `taxonomy_team_manager.py`

**Location**: `app/assistant/tests/manager_tests/taxonomy_team/taxonomy_team_manager.py`

**Purpose**: Full integration test with a realistic taxonomy integrity issue (duplicate machine/robot categories)

**How to run**:
```bash
python app/assistant/tests/manager_tests/taxonomy_team/taxonomy_team_manager.py
```

### 2. Simple Test: `test_taxonomy_team_simple.py`

**Location**: `test_taxonomy_team_simple.py` (root directory)

**Purpose**: Minimal test to verify the manager can be invoked with a simple merge task

**How to run**:
```bash
python test_taxonomy_team_simple.py
```

## Input Format Verification

### ✅ Correct Format

The test uses the **exact same format** as `kg_team_manager`:

```python
request_message = Message(
    data_type="agent_activation",
    sender="User",
    receiver="Delegator",  # This kicks off the agent loop
    content="",
    task=task,              # Short summary
    information=info,       # Full context
)
```

### Message Fields Used

From `app/assistant/utils/pydantic_classes.py`:

- ✅ `data_type` (line 9): Set to "agent_activation"
- ✅ `sender` (line 11): Set to "User"
- ✅ `receiver` (line 12): Set to "Delegator"
- ✅ `content` (line 13): Empty string
- ✅ `task` (line 15): Short task summary (max 200 chars)
- ✅ `information` (line 21): Full detailed context

### Planner Context Items

From `app/assistant/agents/taxonomy_team/planner/config.yaml`:

```yaml
user_context_items:
  - date_time         # Auto-provided
  - task              # From Message.task ✅
  - information       # From Message.information ✅
  - recent_history    # Auto-managed
  - checklist         # Auto-managed
  - action_count      # Auto-managed
```

**Verification**: ✅ The test provides `task` and `information`, which are the only required user inputs.

## Expected Input Format

The `information` field should contain:

```
PROBLEM:
<Description of what's wrong>

AFFECTED CATEGORIES:

  [CATEGORY] '<label>' (DUPLICATE - N instances):
    - ID: <id>
      Path: <full path>
      Parent: <parent label>
      Description: <description or "(no description)">

  [CATEGORY] '<label>' (ID: <id>)
    Path: <full path>
    Parent: <parent label>
    Description: <description>

ACTIONS TO TAKE (IN ORDER):
  1. <action_function>(<params>)
     => <human-readable explanation>
  2. <action_function>(<params>)
     => <human-readable explanation>

CONFIDENCE: <percentage>%

NOTE: All category IDs, paths, and parent relationships are provided above.
The team manager should verify each action before execution.
```

## Available Tools

The planner has access to these tools (verified in `config.yaml`):

1. ✅ `taxonomy_merge_categories` - Exists at `app/assistant/lib/tools/taxonomy_merge_categories/`
2. ✅ `taxonomy_rename_category` - Exists at `app/assistant/lib/tools/taxonomy_rename_category/`
3. ✅ `taxonomy_move_category` - Exists at `app/assistant/lib/tools/taxonomy_move_category/`
4. ✅ `taxonomy_update_description` - Exists at `app/assistant/lib/tools/taxonomy_update_description/`
5. ✅ `ask_user` - Standard tool

## Test Mode

**IMPORTANT**: All taxonomy tools are currently in **TEST MODE**.

From `app/assistant/lib/core_tools/taxonomy_tool/taxonomy_tool.py`:

```python
# ============================================================
# TEST MODE: All database operations are COMMENTED OUT
# This allows testing without modifying the actual taxonomy
# ============================================================
```

This means:
- ✅ Tools will execute and return success messages
- ✅ No actual database changes will be made
- ✅ Safe to run tests repeatedly

## What Happens When You Run the Test

### Step-by-Step Execution

1. **Initialization**
   - Services are initialized
   - Manager registry is preloaded
   - `taxonomy_team_manager` is created

2. **Message Sent**
   - Message with `task` and `information` is sent
   - Receiver is "Delegator"

3. **Delegator Routes to Planner**
   - Delegator receives the message
   - Routes to `taxonomy_team::planner`

4. **Planner Receives Context**
   - Planner gets `task` in user prompt
   - Planner gets `information` in user prompt
   - Planner sees available tools

5. **Planner Creates Plan**
   - Reads PROBLEM
   - Reviews AFFECTED CATEGORIES
   - Parses ACTIONS TO TAKE
   - Creates checklist

6. **Planner Executes Actions**
   - For each action in order:
     - Calls appropriate tool (e.g., `taxonomy_merge_categories`)
     - Tool returns mock success (TEST MODE)
     - Updates checklist
     - Records in summary

7. **Planner Exits**
   - When all actions complete
   - Sets `action` to `flow_exit_node`

8. **Final Answer**
   - `taxonomy_team::final_answer` summarizes results
   - Returns to manager
   - Manager returns to test

## Expected Output

### Successful Test

You should see:
```
initialize system...
Preloading completed in X.XX seconds.

Creating taxonomy_team_manager...

[Agent logs showing planner execution]
[Tool calls to taxonomy_merge_categories, etc.]
[Checklist updates]

Final result: <summary of what was done>
```

### Common Issues

**Issue 1: Manager not found**
```
ERROR creating manager: Manager 'taxonomy_team_manager' not found
```
**Solution**: Check `app/assistant/multi_agents/taxonomy_team_manager/config.yaml` exists

**Issue 2: Tool not found**
```
ERROR: Tool 'taxonomy_merge_categories' not found
```
**Solution**: Check tool exists in `app/assistant/lib/tools/taxonomy_merge_categories/`

**Issue 3: Planner not found**
```
ERROR: Agent 'taxonomy_team::planner' not found
```
**Solution**: Check `app/assistant/agents/taxonomy_team/planner/config.yaml` exists

## Verifying Tool Registration

To check if tools are properly registered, you can add this to your test:

```python
from app.assistant.ServiceLocator.service_locator import DI

# After initialization
tool_registry = DI.tool_registry
print("Available tools:")
for tool_name in ['taxonomy_merge_categories', 'taxonomy_rename_category', 
                  'taxonomy_move_category', 'taxonomy_update_description']:
    if tool_registry.has_tool(tool_name):
        print(f"  ✅ {tool_name}")
    else:
        print(f"  ❌ {tool_name} - NOT FOUND")
```

## Next Steps After Testing

1. **If test passes in TEST MODE**:
   - Review the planner's execution logs
   - Verify it called the right tools in the right order
   - Check that checklist was updated correctly

2. **To enable real database operations**:
   - Edit `app/assistant/lib/core_tools/taxonomy_tool/taxonomy_tool.py`
   - Uncomment the actual database calls
   - Comment out the mock responses
   - Remove the TEST MODE warning

3. **To run with real taxonomy data**:
   - Run `taxonomy_integrity_pipeline.py` to get real issues
   - Copy the formatted output to the test
   - Run the test to execute the fixes

## Summary

✅ **Input Format**: Correct - matches `kg_team_manager` pattern
✅ **Message Fields**: Correct - `task` and `information` are provided
✅ **Planner Config**: Correct - expects `task` and `information`
✅ **Tools**: All 4 taxonomy tools exist and are registered
✅ **Test Mode**: Enabled - safe to run without database changes

**The test is ready to run!** 🎯


