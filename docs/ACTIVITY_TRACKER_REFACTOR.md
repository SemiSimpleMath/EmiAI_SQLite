# Activity Tracker Refactor - Implementation Summary

## Overview
Refactored the wellness activity tracking system to have clearer separation of concerns with `activity_tracker` as the single LLM responsible for determining which activity timers should be reset.

## Architecture Changes

### Before
- `activity_tracker`: Detected activities from chat + calendar
- `proactive_api.py`: Directly recorded wellness from accepted tickets via `status_effect`
- `proactive_executor`: Processed every accepted ticket
- Complex flow with multiple points updating timestamps

### After
- **`activity_tracker`** (LLM): Single source of truth for activity detection
  - Inputs: Chat messages, calendar events, **accepted tickets**
  - Output: Simple list of activity field names to reset
  - Example: `["hydration", "finger_stretch", "meal"]`

- **Python (`physical_status_manager`)**: Executes the resets
  - Calls `activity_tracker` agent
  - For each returned activity: `record_activity(activity_name)`
  - Updates timestamps directly

- **`proactive_executor`**: Only runs for special cases
  - Tool approval tickets
  - Memory edit tickets
  - User provides custom response message

- **Python AFK Monitor**: Continues to handle AFK-based resets independently

## Flow Diagram

```
User Activity → Chat/Calendar/Ticket Acceptance
                          ↓
         ┌────────────────────────────────┐
         │  activity_tracker (LLM Agent)  │
         │                                │
         │  Analyzes:                     │
         │  - Chat: "just drank water"    │
         │  - Calendar: "Lunch" ended     │
         │  - Tickets: "Finger stretch"   │
         │           ACCEPTED             │
         │                                │
         │  Returns: ["hydration",        │
         │           "finger_stretch"]    │
         └────────────┬───────────────────┘
                      │
         ┌────────────▼───────────────────┐
         │  Python: Execute Resets        │
         │                                │
         │  for activity in list:         │
         │    record_activity(activity)   │
         │    # Updates last_X timestamp  │
         └────────────┬───────────────────┘
                      │
         ┌────────────▼───────────────────┐
         │  physical_status_inference     │
         │  (LLM Agent)                   │
         │                                │
         │  Reads updated time_since_X    │
         │  Infers: energy, cognitive     │
         │  load, chronic flares, etc.    │
         └────────────┬───────────────────┘
                      │
         ┌────────────▼───────────────────┐
         │  proactive_orchestrator        │
         │  (LLM Agent)                   │
         │                                │
         │  Generates wellness            │
         │  suggestions                   │
         └────────────────────────────────┘

Parallel:
┌────────────────────────┐
│  Python AFK Monitor    │
│  Auto-resets while AFK │
└────────────────────────┘
```

## Files Changed

### 1. `app/assistant/agents/activity_tracker/agent_form.py`
**Change**: Simplified output schema
```python
# Before: List of {activity_name, detected, evidence}
# After: Simple list of field names to reset
class AgentForm(BaseModel):
    activities_to_reset: List[str]
    reasoning: str
```

### 2. `app/assistant/agents/activity_tracker/config.yaml`
**Added**: `recent_accepted_tickets` to user context items

### 3. `app/assistant/agents/activity_tracker/prompts/system.j2`
**Rewrote**: Updated instructions to focus on deciding which activities to reset
- Emphasizes accepted tickets as strongest signal
- Clearer detection rules for chat/calendar/tickets
- Simplified output format

### 4. `app/assistant/agents/activity_tracker/prompts/user.j2`
**Added**: Recently Accepted Tickets section
```jinja2
## Recently Accepted Tickets
{% for ticket in recent_accepted_tickets %}
- **"{{ ticket.title }}"**
  - Message: {{ ticket.message }}
  - Type: {{ ticket.suggestion_type }}
  - Accepted at: {{ ticket.accepted_at_local }}
{% endfor %}
```

### 5. `app/assistant/physical_status_manager/physical_status_manager.py`

#### `_run_activity_tracker()` method:
- **Return type**: Changed from `Dict[str, bool]` to `List[str]`
- **Added**: `recent_accepted_tickets` to context
- **Output**: Now returns simple list of activity names

#### `refresh()` method:
- **Updated**: Processing of tracker results to use list format
```python
# Before:
for activity_name, detected in detected_activities.items():
    if detected:
        self.record_activity(activity_name)

# After:
for activity_name in activities_to_reset:
    self.record_activity(activity_name)
```

#### `_get_recent_accepted_tickets()` method:
- **Added**: `message` field to ticket dict
- **Changed**: `type` → `suggestion_type` for consistency

### 6. `app/routes/proactive_api.py`
**Removed**: Direct wellness recording from ticket acceptance
**Added**: Conditional executor logic - only runs for:
- Tool approval tickets (`tool_*`)
- Memory edit tickets
- User provided custom response message

```python
# Before: Always ran executor
_record_wellness_from_ticket(ticket_id)
_execute_ticket_action(ticket_id, user_message)

# After: Conditional
needs_executor = (
    (ticket.action_type.startswith('tool_')) or
    (ticket.action_type == 'memory_edit') or
    (user_message and len(user_message.strip()) > 0)
)
if needs_executor:
    _execute_ticket_action(ticket_id, user_message)
```

## Benefits

1. **Single Responsibility**: `activity_tracker` is the only LLM deciding which activities to reset
2. **Clearer Flow**: Python orchestrates, LLM decides, Python executes
3. **Less Redundancy**: Removed duplicate wellness recording logic
4. **Better Semantics**: LLM can parse complex ticket titles (e.g., "Stretch & Water" → both activities)
5. **Consistency**: All activity sources (chat, calendar, tickets) go through same decision logic
6. **Performance**: Executor only runs when actually needed

## Testing Checklist

- [ ] Test chat message detection ("just drank water" → resets hydration)
- [ ] Test calendar event detection ("Lunch meeting" ends → resets meal)
- [ ] Test ticket acceptance (Accept "Finger stretch break" → resets finger_stretch)
- [ ] Test multi-activity ticket (Accept "Stretch & Water" → resets both)
- [ ] Test AFK reset logic still works independently
- [ ] Test tool approval tickets still trigger executor
- [ ] Test custom user response still triggers executor
- [ ] Verify no duplicate timestamp updates

## Future Considerations

- **Remove `proactive_executor` entirely?** Currently kept for edge cases, but may become fully redundant
- **Add validation**: Ensure activity names in tracker output match tracked activities
- **Logging**: Add debug mode to show LLM reasoning for activity detection

---

**Date**: 2025-12-27  
**Status**: Implementation Complete, Testing Pending

