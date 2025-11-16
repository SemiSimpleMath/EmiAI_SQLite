# Unified Item Manager

## Overview

The Unified Item Manager solves the **"repeated triage problem"** where agents see the same events multiple times across restarts and eventually take action out of frustration.

### The Problem (Old System)

```
EventRepository stores raw events
↓
"New" = created_at > last_planner_run (stateless, session-based)
↓
Agent sees "new" events every restart
↓
Agent re-triages the same items repeatedly
↓
Eventually makes a decision out of frustration
```

### The Solution (Unified Items)

```
External events → UnifiedItem (persistent state machine)
↓
"New" = state == NEW (persistent, global truth)
↓
Agent sees only truly untriaged items
↓
Agent makes ONE decision → state transition
↓
Item never re-presented (unless explicitly snoozed)
```

## Architecture

### State Machine

Each `UnifiedItem` progresses through a state machine:

```
NEW → TRIAGED → ACTION_PENDING → ACTION_TAKEN
 ↓              ↓                 ↓
 └─→ DISMISSED ←─────────────────┘
      ↓
   SNOOZED → (waits) → NEW (re-presented)
      ↓
   FAILED
```

**State Definitions:**

- **NEW**: Never seen by agent, needs triage
- **TRIAGED**: Agent reviewed and made decision
- **ACTION_PENDING**: Action planned but not complete
- **ACTION_TAKEN**: Action completed successfully
- **DISMISSED**: No action needed
- **SNOOZED**: Re-present at `snooze_until` time
- **FAILED**: Action attempted but failed

### Core Components

**1. UnifiedItem Model** (`unified_item.py`)
- SQLAlchemy ORM model
- Tracks state, history, metadata
- Stores original event data as JSON

**2. UnifiedItemManager** (`unified_item_manager.py`)
- Business logic for ingestion and state transitions
- Queries for agent triage queues
- Handles series dismissal for recurring events

**3. RecurringEventRuleManager** (`recurring_event_rules.py`)
- Stores user preferences for recurring calendar events
- Auto-applies rules during ingestion (e.g., "always dismiss daily standup")
- Prevents agents from asking about the same recurring event repeatedly

**4. Database Tables**
- `unified_items` - Persistent storage of all tracked items
- `recurring_event_rules` - User preferences for recurring events
- Indexed for fast queries by state and source

## Usage

### Ingestion

```python
from app.assistant.unified_item_manager import UnifiedItemManager

manager = UnifiedItemManager()

# Ingest from all sources
results = manager.ingest_all_sources()
# Returns: {'email': [item1, item2], 'calendar': [item3], ...}

# Ingest from specific source
new_emails = manager.ingest_from_source('email')
```

### Querying for Agent

```python
# Get items needing triage (NEW or expired SNOOZED)
triage_queue = manager.get_items_for_triage(limit=50)

# Get items with pending actions
in_progress = manager.get_items_in_progress()

# Get recently completed actions (context for avoiding duplicates)
recent_actions = manager.get_recent_actions(hours=24)
```

### State Transitions

```python
# Dismiss an item (no action needed)
manager.dismiss_item(item_id=123, reason="Promotional email")

# Start an action
manager.transition_state(
    item_id=456,
    new_state=ItemState.ACTION_PENDING,
    agent_decision="Draft response email to Bob",
    agent_notes="User wants to schedule meeting"
)

# Complete an action
manager.transition_state(
    item_id=456,
    new_state=ItemState.ACTION_TAKEN,
    related_action_id="action_log_789"
)

# Snooze an item
manager.transition_state(
    item_id=789,
    new_state=ItemState.SNOOZED,
    snooze_until=datetime(2025, 11, 10, 9, 0, 0, tzinfo=timezone.utc),
    agent_notes="Deal with this next week"
)
```

### Recurring Events (The Superpower!)

```python
# Dismiss ENTIRE recurring series (blocks all future instances)
manager.dismiss_entire_series(
    recurring_event_id="abc123_recurring",
    reason="User doesn't want to see Monday standups"
)

# Result: All future Monday standups automatically skipped during ingestion!
```

## Unique ID Format

Each source has a specific unique ID format:

- **Email**: `email:{message_id}` (e.g., `email:ABC123@gmail.com`)
- **Calendar**: `calendar:{event_id}` (e.g., `calendar:abc123def`)
- **Calendar Series**: `calendar_series:{recurring_event_id}` (e.g., `calendar_series:recurring_xyz789`)
- **Todo**: `todo:{task_id}` (e.g., `todo:task456`)
- **Scheduler**: `scheduler:{event_id}:{occurrence}` (e.g., `scheduler:reminder_123:2025-11-03T09:00:00`)

## Agent Context Structure

The new context presented to agents:

```json
{
  "items_for_triage": [
    {
      "id": 1,
      "unique_id": "email:msg123",
      "title": "Project update from Sarah",
      "state": "new",
      "importance": 7,
      "source_timestamp": "2025-11-03T09:00:00Z"
    }
  ],
  "items_in_progress": [
    {
      "id": 99,
      "unique_id": "email:msg100",
      "title": "Meeting request from Bob",
      "state": "action_pending",
      "agent_decision": "Find available times and respond",
      "updated_at": "2025-11-03T07:00:00Z"
    }
  ],
  "recent_actions": [
    {
      "id": 150,
      "unique_id": "email:msg88",
      "title": "Invoice from vendor",
      "state": "action_taken",
      "agent_decision": "Forwarded to accounting",
      "updated_at": "2025-11-03T08:30:00Z"
    }
  ]
}
```

## Recurring Event Rules

### The Problem
Recurring calendar events (e.g., "Daily Standup" every weekday) generate a new instance every day. Without rules, agents would ask about the same event repeatedly:

```
Day 1: "What should I do about Daily Standup?" → User: "Ignore it"
Day 2: "What should I do about Daily Standup?" → User: "I said ignore it!"
Day 3: "What should I do about Daily Standup?" → User: "STILL ignore it!!"
```

### The Solution
Create a rule once, apply it forever:

```python
from app.assistant.unified_item_manager import RecurringEventRuleManager, RecurringEventRuleAction

rule_manager = RecurringEventRuleManager()

# User decides once: "Always dismiss Daily Standup"
rule_manager.create_rule(
    recurring_event_id="abc123xyz",  # Google Calendar recurring_event_id
    event_title="Daily Standup",
    action=RecurringEventRuleAction.AUTO_DISMISS,
    reason="Routine meeting I never need reminders for"
)

# All future instances of this event are automatically dismissed
```

### Workflow

**First Occurrence:**
1. Recurring event ingested → `state=NEW`
2. `process_new_recurring_events()` called during maintenance
3. `RecurringEventQuestioner` uses `recurring_event_questioner_manager` + `ask_user` tool
4. User responds: "Ignore it" or provides custom instructions
5. Rule created and applied → `state=DISMISSED` (or CUSTOM action)

**Subsequent Occurrences:**
1. Recurring event ingested → Rule found!
2. Auto-apply: `state=DISMISSED` (no agent interaction)
3. Agent never sees it, never asks

### Integration (Auto-Processing)

The system can automatically process new recurring events during maintenance cycles:

```python
# In maintenance_manager.py or similar
from app.assistant.unified_item_manager.process_new_recurring_events import process_new_recurring_events

# Check for new recurring events every idle cycle
result = process_new_recurring_events(max_events=3)  # Rate-limited to 3 per cycle
print(f"Rules created: {result['rules_created']}")
```

**How it works:**
1. Queries `UnifiedItems` for NEW recurring calendar events
2. Filters out events that already have rules
3. For each new recurring event:
   - Uses `recurring_event_questioner_manager` (dedicated multi-agent manager with custom prompts)
   - Agent asks user via `ask_user` tool
   - Parses user response ("ignore it", "notify me", or custom)
   - Creates appropriate rule in `recurring_event_rules` table
   - Applies rule to current instance
4. Returns stats (processed, rules_created, skipped, errors)

**User Experience:**
```
🔔 Emi: "I see a recurring event: 'Daily Standup'. How should I handle future occurrences?"

User: "Ignore it"

✅ Emi: "Got it! I'll automatically dismiss 'Daily Standup' from now on."
```

**Or run standalone:**
```python
# Run from IDE to process pending recurring events
python app/assistant/unified_item_manager/process_new_recurring_events.py
```

### Rule Actions

**AUTO_DISMISS** (most common)
```python
# "I never need to see this event"
action=RecurringEventRuleAction.AUTO_DISMISS
```

**AUTO_NOTIFY**
```python
# "Show me a notification but don't wait for action"
action=RecurringEventRuleAction.AUTO_NOTIFY
```

**CUSTOM**
```python
# "Apply specific instructions"
action=RecurringEventRuleAction.CUSTOM,
agent_instructions="Only notify if it's on a Friday"
```

### Managing Rules

```python
# Get all rules
rules = rule_manager.get_all_rules()
for rule in rules:
    print(f"{rule.event_title}: {rule.action}")

# Delete a rule (future instances will be NEW again)
rule_manager.delete_rule(recurring_event_id="abc123xyz")

# Update a rule (just create with same ID)
rule_manager.create_rule(
    recurring_event_id="abc123xyz",
    event_title="Daily Standup",
    action=RecurringEventRuleAction.AUTO_NOTIFY,  # Changed!
    reason="Actually I do want to be notified"
)
```

### Statistics

Rules track usage:
```python
rule = rule_manager.get_rule("abc123xyz")
print(rule.application_count)
# {
#   "2025-11-01": 1,  # Applied once on Nov 1
#   "2025-11-02": 1,  # Applied once on Nov 2
#   "2025-11-03": 0   # Weekend, no instance
# }
print(rule.last_applied)  # 2025-11-02T15:30:00+00:00
```

## Database Setup

**Step 1: Create unified_items table**

*Option A: Run from IDE (Recommended)*
```python
# Just run this file from your IDE
app/assistant/unified_item_manager/unified_item.py
```

*Option B: SQL*
```bash
psql -d your_database < app/assistant/unified_item_manager/migration_add_unified_items.sql
```

**Step 2: Create recurring_event_rules table**

*Option A: Run from IDE (Recommended)*
```python
# Just run this file from your IDE
app/assistant/unified_item_manager/recurring_event_rules.py
```

*Option B: SQL*
```bash
psql -d your_database < app/assistant/unified_item_manager/migration_add_recurring_event_rules.sql
```

**Step 3: Initial ingestion (optional)**
```python
# Populate UnifiedItems from existing EventRepository data
# Run from IDE:
app/assistant/unified_item_manager/ingest_existing_events.py
```

**Other Commands:**
```bash
# Drop the table
python -m app.assistant.unified_item_manager.unified_item drop

# Reset the table (drop + recreate)
python -m app.assistant.unified_item_manager.unified_item reset
```

## Benefits

✅ **No Repeated Triage**: Items are seen once, decided once
✅ **Persistent State**: Survives agent restarts
✅ **Recurring Event Control**: Dismiss entire series forever
✅ **Action Tracking**: See what's pending vs. completed
✅ **Snooze Capability**: Defer decisions to later
✅ **Audit Trail**: Full state history in JSON
✅ **Performance**: Indexed queries, only load NEW items
✅ **Flexibility**: Easy to add new sources or states

## Statistics

```python
# Get system stats
stats = manager.get_stats()
print(stats)
# {
#   'total': 1250,
#   'by_state': {
#     'new': 15,
#     'dismissed': 800,
#     'action_taken': 400,
#     'action_pending': 10,
#     ...
#   },
#   'by_source': {
#     'email': 900,
#     'calendar': 200,
#     'todo_task': 100,
#     'scheduler': 50
#   }
# }
```

## Migration from Old System

The old `system_state_monitor.py` can coexist with this system during migration:

1. ✅ Keep `EventRepository` - it's the raw event store
2. ✅ Keep `system_state_monitor.py` - reference for best practices
3. ✅ Add `UnifiedItemManager` - new stateful layer on top
4. ✅ Update `auto_planner` to use UnifiedItems instead of raw events
5. ✅ Gradually migrate other agents to use UnifiedItems

## Future Enhancements

- [ ] Automatic importance scoring based on content analysis
- [ ] ML-based suggestions for dismiss vs. action
- [ ] Bulk operations (dismiss all from sender, snooze all by type)
- [ ] User preferences (always dismiss certain patterns)
- [ ] Integration with knowledge graph (link items to entities)
- [ ] Mobile/web UI for manual triage

