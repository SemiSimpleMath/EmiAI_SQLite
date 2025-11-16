"""Diagnostic script to understand why recurring events aren't being processed"""

from app.models.base import get_session
from app.assistant.unified_item_manager.unified_item import UnifiedItem, ItemState
from app.assistant.event_repository.event_repository import EventRepositoryManager
from sqlalchemy import text
import json

print("\n" + "="*80)
print("🔍 DIAGNOSING RECURRING EVENTS")
print("="*80 + "\n")

session = get_session()

# 1. Check EventRepository for recurring calendar events
print("1️⃣  CHECKING EventRepository for recurring calendar events...")
repo_manager = EventRepositoryManager()
calendar_events_json = repo_manager.search_events("calendar")
calendar_events = json.loads(calendar_events_json) if calendar_events_json else []

recurring_in_repo = []
for event in calendar_events:
    if event.get('recurringEventId') or event.get('recurrence'):
        recurring_in_repo.append({
            'id': event.get('id', 'unknown'),
            'title': event.get('summary', 'No title'),
            'recurringEventId': event.get('recurringEventId'),
            'recurrence': event.get('recurrence', [])
        })

print(f"   Found {len(recurring_in_repo)} recurring events in EventRepository")
if recurring_in_repo:
    print("   Recurring events:")
    for idx, ev in enumerate(recurring_in_repo[:10], 1):  # Show first 10
        print(f"      [{idx}] {ev['title']} (ID: {ev['recurringEventId']})")
    if len(recurring_in_repo) > 10:
        print(f"      ... and {len(recurring_in_repo) - 10} more")

print("\n" + "-"*80 + "\n")

# 2. Check UnifiedItems for calendar events
print("2️⃣  CHECKING UnifiedItems for calendar events...")
all_calendar_items = session.query(UnifiedItem).filter(
    UnifiedItem.source_type == 'calendar'
).all()

print(f"   Total calendar items in UnifiedItems: {len(all_calendar_items)}")

# Group by state
by_state = {}
for item in all_calendar_items:
    state = item.state
    if state not in by_state:
        by_state[state] = []
    by_state[state].append(item)

print("\n   By state:")
for state, items in sorted(by_state.items()):
    print(f"      {state}: {len(items)} items")

print("\n" + "-"*80 + "\n")

# 3. Check for recurring events specifically
print("3️⃣  CHECKING UnifiedItems for recurring calendar events...")

recurring_items = session.query(UnifiedItem).filter(
    UnifiedItem.source_type == 'calendar',
    UnifiedItem.item_metadata['recurring_event_id'].isnot(None)
).all()

print(f"   Total recurring calendar items: {len(recurring_items)}")

# Group by state
recurring_by_state = {}
for item in recurring_items:
    state = item.state
    if state not in recurring_by_state:
        recurring_by_state[state] = []
    recurring_by_state[state].append(item)

print("\n   Recurring events by state:")
for state, items in sorted(recurring_by_state.items()):
    print(f"      {state}: {len(items)} items")
    if state == 'new':
        print("      NEW recurring events:")
        for idx, item in enumerate(items[:5], 1):
            recurring_id = item.item_metadata.get('recurring_event_id', 'unknown')
            print(f"         [{idx}] '{item.title}' (recurring_id: {recurring_id})")

print("\n" + "-"*80 + "\n")

# 4. Check recurring_event_rules table
print("4️⃣  CHECKING recurring_event_rules table...")
rules_result = session.execute(text("SELECT id, event_title, action FROM recurring_event_rules"))
rules = rules_result.fetchall()

print(f"   Total rules: {len(rules)}")
for rule in rules:
    print(f"      '{rule[1]}' (ID: {rule[0]}, Action: {rule[2]})")

print("\n" + "-"*80 + "\n")

# 5. Find NEW recurring events without rules
print("5️⃣  FINDING NEW recurring events WITHOUT rules...")
new_recurring_without_rules = []

for item in recurring_items:
    if item.state == ItemState.NEW:
        recurring_id = item.item_metadata.get('recurring_event_id')
        if recurring_id:
            # Check if rule exists
            rule_exists = session.execute(
                text("SELECT COUNT(*) FROM recurring_event_rules WHERE id = :id"),
                {"id": recurring_id}
            ).scalar() > 0
            
            if not rule_exists:
                new_recurring_without_rules.append({
                    'title': item.title,
                    'recurring_id': recurring_id,
                    'unified_item_id': item.id
                })

print(f"   Found {len(new_recurring_without_rules)} NEW recurring events WITHOUT rules:")
for idx, ev in enumerate(new_recurring_without_rules, 1):
    print(f"      [{idx}] '{ev['title']}' (recurring_id: {ev['recurring_id']}, unified_item_id: {ev['unified_item_id']})")

print("\n" + "="*80 + "\n")

if new_recurring_without_rules:
    print("✅ These events SHOULD be processed by process_new_recurring_events()")
else:
    print("⚠️  No NEW recurring events without rules found.")
    print("   Possible reasons:")
    print("   - All recurring events already have rules")
    print("   - Events are not in NEW state")
    print("   - Events don't have recurring_event_id in metadata")
    print("   - Events haven't been ingested from EventRepository yet")

print()


