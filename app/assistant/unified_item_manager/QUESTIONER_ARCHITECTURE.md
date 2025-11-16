# Recurring Event Questioner Architecture

## Overview

The Recurring Event Questioner uses the **multi-agent manager pattern** to ask users about recurring calendar events and create persistent rules.

## Components

### 1. Manager: `recurring_event_questioner_manager`

**Location:** `app/assistant/multi_agents/recurring_event_questioner_manager/config.yaml`

**Purpose:** Multi-agent manager that orchestrates the questioning workflow

**Key Config:**
- Uses `recurring_event_questioner::planner` agent (calendar-specific prompts)
- Allows only `ask_user` tool
- Exits via `flow_exit_node` when complete

### 2. Agent: `recurring_event_questioner::planner`

**Location:** `app/assistant/agents/recurring_event_questioner/planner/`

**Purpose:** Planner agent with prompts specific to recurring calendar events

**Files:**
- `config.yaml` - Agent configuration
- `prompts/system.j2` - System prompt (explains the recurring event context)
- `prompts/user.j2` - User prompt (includes event details)
- `agent_form.py` - Pydantic output model

**User Context Items:**
```yaml
- event_title
- recurring_event_id
- event_description
- start_time
- end_time
- recurrence_rule
- calendar
- checklist
- found_information
- recent_history
```

**Output Format:**
```python
{
    "action": "ask_user" | "flow_exit_node",
    "action_input": "question text",
    "final_answer": {
        "rule_action": "ignore" | "notify" | "custom",
        "user_response": "raw user text",
        "custom_instructions": "specific instructions"
    }
}
```

### 3. Stage/Wrapper: `RecurringEventQuestioner`

**Location:** `app/assistant/unified_item_manager/recurring_event_questioner.py`

**Purpose:** Wrapper that invokes the manager and parses results

**Methods:**
- `ask_user_about_recurring_event(unified_item)` - Main entry point
- `_create_question_for_event()` - Formats initial question
- `_parse_response_and_create_rule()` - Parses agent output and creates rule
- `_interpret_user_response()` - Keyword matching for user intent

### 4. Integration: `process_new_recurring_events()`

**Location:** `app/assistant/unified_item_manager/process_new_recurring_events.py`

**Purpose:** Batch processor for maintenance cycles

**Workflow:**
1. Query `UnifiedItems` for NEW recurring calendar events
2. Filter out events with existing rules
3. For each event: call `RecurringEventQuestioner`
4. Return stats

## Why a Separate Manager?

The `kg_repair_pipeline` already has a `questioner_manager`, but we need a **separate one** because:

1. **Different Prompts**: KG repair prompts talk about "nodes", "types", "temporal data". Calendar prompts talk about "events", "recurrence", "schedules".

2. **Different Context**: The agent needs different context items:
   - KG: `node_label`, `node_type`, `problem_instructions`
   - Calendar: `event_title`, `recurrence_rule`, `calendar`

3. **Different Output Format**: 
   - KG: `instructions`, `skip_this_node`, `postpone_until`
   - Calendar: `rule_action`, `custom_instructions`

4. **Single Responsibility**: Each manager has one clear purpose, making the system easier to understand and maintain.

## Comparison with KG Repair Pipeline

| Component | KG Repair Pipeline | Recurring Events |
|-----------|-------------------|------------------|
| Manager | `questioner_manager` | `recurring_event_questioner_manager` |
| Agent | `kg_repair_pipeline::questioner::planner` | `recurring_event_questioner::planner` |
| Stage | `KGQuestioner` | `RecurringEventQuestioner` |
| Tool | `ask_user` | `ask_user` (same!) |
| Context | Node info, problem description | Event info, recurrence rule |
| Output | Fix instructions, skip/postpone | Rule action (ignore/notify/custom) |

## Flow Diagram

```
process_new_recurring_events()
    ↓
RecurringEventQuestioner.ask_user_about_recurring_event(item)
    ↓
Create message with event context
    ↓
recurring_event_questioner_manager.request_handler(message)
    ↓
recurring_event_questioner::planner agent
    ↓
action: "ask_user" → invoke ask_user tool
    ↓
User responds
    ↓
Agent parses response → final_answer
    ↓
action: "flow_exit_node" → return to manager
    ↓
Return result to RecurringEventQuestioner
    ↓
Parse final_answer → create rule
    ↓
RecurringEventRuleManager.create_rule(...)
    ↓
Apply rule to current instance
```

## Testing

**Standalone Test:**
```python
# Run from IDE
python app/assistant/unified_item_manager/process_new_recurring_events.py
```

**Integration Test:**
```python
# Add to maintenance_manager.py
from app.assistant.unified_item_manager.process_new_recurring_events import process_new_recurring_events

result = process_new_recurring_events(max_events=3)
```

## Future Enhancements

- [ ] Support for "notify only on specific days" logic
- [ ] Rule expiration (e.g., "ignore for 3 months")
- [ ] Bulk rule creation UI
- [ ] ML-based rule suggestions


