"""
Cleanup script to remove duplicate recurring event rules for child instances.

Child events have IDs like: {parent_id}_R{timestamp}
Parent events have IDs like: {parent_id}

We should only have rules for parent IDs. This script removes rules for child IDs.
"""

from app.models.base import get_session
from app.assistant.unified_item_manager.recurring_event_rules import RecurringEventRule, RecurringEventRuleManager

def cleanup_duplicate_rules():
    """Remove rules for child event IDs (those with _R suffix)"""
    session = get_session()
    try:
        # Get all rules
        all_rules = session.query(RecurringEventRule).all()
        
        child_rules = []
        parent_rules = {}
        
        for rule in all_rules:
            if '_R' in rule.id:
                # This is a child rule
                child_rules.append(rule)
                parent_id = rule.id.split('_R')[0]
                
                # Check if parent rule exists
                if parent_id not in parent_rules:
                    parent_rule = session.query(RecurringEventRule).filter_by(id=parent_id).first()
                    if parent_rule:
                        parent_rules[parent_id] = parent_rule
            else:
                # This is a parent rule
                parent_rules[rule.id] = rule
        
        print(f"Found {len(child_rules)} child rules and {len(parent_rules)} parent rules")
        
        # Delete child rules
        deleted_count = 0
        for child_rule in child_rules:
            parent_id = child_rule.id.split('_R')[0]
            if parent_id in parent_rules:
                print(f"Deleting child rule: {child_rule.id} (parent {parent_id} exists)")
                session.delete(child_rule)
                deleted_count += 1
            else:
                print(f"WARNING: Child rule {child_rule.id} has no parent rule {parent_id} - keeping it for now")
        
        session.commit()
        print(f"✅ Deleted {deleted_count} duplicate child rules")
        
    except Exception as e:
        session.rollback()
        print(f"❌ Error cleaning up rules: {e}")
        raise
    finally:
        session.close()

if __name__ == "__main__":
    cleanup_duplicate_rules()

