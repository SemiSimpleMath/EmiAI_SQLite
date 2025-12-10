"""
Process New Recurring Events

Called during maintenance cycles to identify and handle new recurring calendar events.
This is the integration point between UnifiedItemManager and RecurringEventQuestioner.
"""

from datetime import datetime, timezone
from app.assistant.unified_item_manager import (
    UnifiedItemManager,
    ItemState,
    RecurringEventQuestioner,
)
from app.assistant.unified_item_manager.recurring_event_rules import (
    RecurringEventRuleManager,
    RecurringEventRuleAction,
)
from app.assistant.unified_item_manager.unified_item import UnifiedItem
from app.assistant.utils.logging_config import get_maintenance_logger

logger = get_maintenance_logger(__name__)


def process_new_recurring_events(max_events: int = 3) -> dict:
    """
    Check for new recurring calendar events and ask user how to handle them.

    This function:
    1. Queries EventRepository for recurring calendar events without rules (NOT UnifiedItems)
    2. Asks user about each one (using questioner_manager + ask_user tool)
    3. Creates rules based on user responses
    4. If rule is NORMAL/CUSTOM: creates UnifiedItems from EventRepository
    5. If rule is IGNORE: skips creating UnifiedItems (never go into unified_items)

    Args:
        max_events: Maximum number of events to process in one call (rate limiting)

    Returns:
        Dict with processing stats
    """
    try:
        print("🔍 Querying EventRepository for recurring calendar events without rules...")
        logger.info("🔄 Checking for new recurring calendar events...")

        manager = UnifiedItemManager()
        questioner = RecurringEventQuestioner()
        rule_manager = RecurringEventRuleManager()

        # Query EventRepository (not UnifiedItems) for recurring calendar events
        # NOTE: We do NOT keep a long-running session open here to avoid holding
        # database locks during LLM calls. Each database operation gets its own session.
        import json

        # Get all calendar events from EventRepository (uses its own session internally)
        repo_events_json = manager.event_repo.search_events(data_type="calendar")
        repo_events = json.loads(repo_events_json) if repo_events_json else []

        print(f"   Found {len(repo_events)} calendar events in EventRepository")

        # Extract recurring events and group by unique recurring_event_id
        recurring_events_by_id = {}  # recurring_id -> list of event data

        for event in repo_events:
            event_data = event.get('data', {})
            recurring_event_id = event_data.get('recurring_event_id')
            recurrence_rule = event_data.get('recurrence_rule')

            # For parent recurring events, use event's own ID as recurring_event_id
            if not recurring_event_id and recurrence_rule:
                if isinstance(recurrence_rule, list) and len(recurrence_rule) > 0:
                    recurring_event_id = event_data.get('id')
                elif recurrence_rule and not isinstance(recurrence_rule, list):
                    recurring_event_id = event_data.get('id')

            # Normalize to parent ID (remove _R suffix if present)
            if recurring_event_id:
                recurring_event_id = RecurringEventRuleManager.extract_parent_id(recurring_event_id)

            if recurring_event_id:
                if recurring_event_id not in recurring_events_by_id:
                    recurring_events_by_id[recurring_event_id] = []
                recurring_events_by_id[recurring_event_id].append(event_data)

        print(f"   Found {len(recurring_events_by_id)} unique recurring event series")

        if not recurring_events_by_id:
            print("   ✅ No recurring events found")
            logger.info("✅ No recurring events to process")
            return {"processed": 0, "rules_created": 0, "skipped": 0, "errors": 0, "unified_items_created": 0}

        # Check which series already have rules (rule_manager uses its own sessions)
        print("\n🔍 Checking for existing rules...")
        series_with_rules = set()
        series_needing_rules = {}  # recurring_id -> first event data

        for recurring_id, event_data_list in recurring_events_by_id.items():
            existing_rule = rule_manager.get_rule(recurring_id)
            if existing_rule:
                series_with_rules.add(recurring_id)
                logger.debug(f"   Series {recurring_id[:20]}... already has rule: {existing_rule.action}")
            else:
                # Track one event data per unique series (use first one)
                if recurring_id not in series_needing_rules:
                    series_needing_rules[recurring_id] = event_data_list[0]

        logger.info(f"   Found {len(series_with_rules)} series that already have rules")
        logger.info(f"   Found {len(series_needing_rules)} series needing rules")

        # Get unique series that need rules (one per series, up to max_events)
        series_to_process = list(series_needing_rules.items())[:max_events]

        print(f"\n📊 Summary:")
        print(f"   Total recurring series: {len(recurring_events_by_id)}")
        print(f"   Series with rules: {len(series_with_rules)}")
        print(f"   Series needing rules: {len(series_needing_rules)} (processing up to {max_events})")

        if not series_to_process:
            logger.info("✅ All recurring events already have rules")
            return {
                "processed": len(recurring_events_by_id),
                "rules_created": 0,
                "skipped": len(series_with_rules),
                "errors": 0,
                "unified_items_created": 0,
            }

        print(f"\n{'=' * 80}")
        print(f"🤖 ASKING USER ABOUT {len(series_to_process)} RECURRING EVENTS")
        print(f"{'=' * 80}\n")
        logger.info(f"❓ Asking user about {len(series_to_process)} recurring events...")

        # Process each series
        rules_created = 0
        errors = 0
        unified_items_created = 0

        for idx, (recurring_id, event_data) in enumerate(series_to_process, 1):
            try:
                print(f"\n{'─' * 80}")
                print(f"📅 [{idx}/{len(series_to_process)}] PROCESSING SERIES: '{event_data.get('summary', 'No Title')}'")
                print(f"   Recurrence: {event_data.get('recurrence_rule', 'N/A')}")
                print(f"   Recurring ID: {recurring_id}")
                print(f"{'─' * 80}\n")
                logger.info(f"\n📅 Processing: {event_data.get('summary')}")

                # Create a temporary UnifiedItem for the questioner (it expects a UnifiedItem)
                # This is just for asking - we'll create real unified_items after rule is created
                temp_unified_item = UnifiedItem(
                    unique_id=f"temp:{recurring_id}",
                    source_type="calendar",
                    state=ItemState.NEW,
                    title=event_data.get('summary', 'No Title'),
                    content=event_data.get('description', ''),
                    data=event_data,
                    item_metadata={'recurring_event_id': recurring_id},
                    source_timestamp=None,
                    importance=6
                )

                print("🔄 Calling recurring_event_questioner_manager...")
                # Ask user and create rule
                result = questioner.ask_user_about_recurring_event(temp_unified_item)

                if result and result.get("success"):
                    action = result.get('action')
                    print(f"\n✅ AGENT RETURNED:")
                    print(f"   Action: {action}")
                    print(f"   Reason: {result.get('reason')}")
                    if result.get("custom_instructions"):
                        print(f"   Custom: {result.get('custom_instructions')}")

                    rules_created += 1
                    logger.info(f"✅ Rule created: {action}")

                    # After rule is created, decide what to do based on action
                    if action == RecurringEventRuleAction.IGNORE:
                        # IGNORE rule - never create UnifiedItems
                        print(f"\n⏭️  Rule is IGNORE - skipping UnifiedItem creation")
                        logger.info(f"⏭️  Skipping UnifiedItem creation for IGNORE rule: {recurring_id}")
                    else:
                        # NORMAL or CUSTOM rule - create UnifiedItems from EventRepository
                        # Use a fresh session for the database operations to avoid holding locks
                        print(f"\n💾 Creating UnifiedItems for rule action: {action}")
                        all_instances = recurring_events_by_id[recurring_id]

                        created_count = 0
                        db_session = manager.session_factory()
                        try:
                            for instance_data in all_instances:
                                # Check if it already exists
                                unique_id = manager._generate_unique_id('calendar', instance_data)
                                existing = db_session.query(UnifiedItem).filter_by(unique_id=unique_id).first()

                                if existing:
                                    # Update existing
                                    existing.data = instance_data
                                    existing.updated_at = datetime.now(timezone.utc)
                                    continue

                                # Create new UnifiedItem
                                unified_item = manager._create_unified_item('calendar', instance_data, db_session)
                                created_count += 1

                                # Apply the rule to the new item (uses its own session)
                                rule_manager.apply_rule(recurring_id, unified_item)

                            db_session.commit()
                        except Exception as e:
                            db_session.rollback()
                            logger.error(f"Error creating UnifiedItems: {e}")
                            raise
                        finally:
                            db_session.close()

                        unified_items_created += created_count
                        print(f"✅ Created {created_count} new UnifiedItems for this series")
                        print(f"✅ Applied rule ({action}) to all instances")
                        logger.info(f"✅ Created {created_count} UnifiedItems and applied rule {action} to series {recurring_id}")
                else:
                    print(f"\n❌ FAILED: {result.get('error', 'Unknown error')}")
                    errors += 1
                    logger.error(f"❌ Failed to create rule for: {event_data.get('summary')}")

            except Exception as e:
                print(f"\n❌ ERROR: {e}")
                errors += 1
                logger.error(
                    f"❌ Error processing event {event_data.get('summary')}: {e}",
                    exc_info=True,
                )
                continue

        # Calculate total instances processed
        total_instances = sum(len(events) for events in recurring_events_by_id.values())
        skipped_instances = sum(
            len(recurring_events_by_id[rec_id])
            for rec_id in series_with_rules
        )

        return {
            "processed": total_instances,
            "rules_created": rules_created,
            "skipped": skipped_instances,
            "errors": errors,
            "unified_items_created": unified_items_created,
        }

    except Exception as e:
        logger.error(f"❌ Failed to process new recurring events: {e}", exc_info=True)
        return {
            "processed": 0,
            "rules_created": 0,
            "skipped": 0,
            "errors": 1,
            "unified_items_created": 0,
            "error_message": str(e),
        }


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("🔄 PROCESSING NEW RECURRING CALENDAR EVENTS")
    print("=" * 80 + "\n")

    print("This will:")
    print("  1. Find recurring calendar events without rules in EventRepository")
    print("  2. Ask you how to handle each one")
    print("  3. Create rules based on your responses")
    print("  4. If NORMAL/CUSTOM: create UnifiedItems")
    print("  5. If IGNORE: skip UnifiedItem creation\n")

    import app.assistant.tests.test_setup  # Initialize DI
    from app.assistant.ServiceLocator.service_locator import DI

    # Preload all managers (required for recurring_event_questioner_manager)
    print("🔄 Preloading managers...")
    DI.manager_registry.preload_all()
    print("✅ Managers loaded\n")

    result = process_new_recurring_events(max_events=5)

    print("\n" + "=" * 80)
    print("✅ PROCESSING COMPLETE")
    print("=" * 80)
    print(f"\n📊 FINAL SUMMARY:")
    print(f"   Total instances:  {result['processed']} recurring event instances")
    print(f"   Rules created:    {result['rules_created']} new rules")
    print(f"   Skipped:          {result['skipped']} (already had rules)")
    print(f"   UnifiedItems:     {result['unified_items_created']} created")
    print(f"   Errors:           {result['errors']}")

    if result.get("error_message"):
        print(f"\n❌ Error: {result['error_message']}")

    if result["rules_created"] > 0:
        print(f"\n💾 Database changes:")
        print(f"   - {result['rules_created']} rows added to recurring_event_rules table")
        if result['unified_items_created'] > 0:
            print(f"   - {result['unified_items_created']} rows added to unified_items table")

    print()