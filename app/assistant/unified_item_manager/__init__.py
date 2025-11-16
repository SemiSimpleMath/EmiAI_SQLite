"""
Unified Item Manager
====================

State-based tracking system for external events (emails, calendar, todos, scheduler).

Core Concept:
- External events are ingested and converted to UnifiedItems
- Each UnifiedItem has a persistent state (NEW, TRIAGED, DISMISSED, etc.)
- Agents only see items in NEW or SNOOZED state
- Once triaged, items never re-appear unless explicitly snoozed

This solves the "repeated triage" problem where agents see the same items
multiple times and eventually take action out of frustration.
"""

from .unified_item import UnifiedItem, ItemState
from .unified_item_manager import UnifiedItemManager
from .recurring_event_rules import (
    RecurringEventRule,
    RecurringEventRuleAction,
    RecurringEventRuleManager
)
from .recurring_event_questioner import (
    RecurringEventQuestioner,
    process_new_recurring_event
)

__all__ = [
    'UnifiedItemManager',
    'UnifiedItem',
    'ItemState',
    'RecurringEventRule',
    'RecurringEventRuleAction',
    'RecurringEventRuleManager',
    'RecurringEventQuestioner',
    'process_new_recurring_event'
]

