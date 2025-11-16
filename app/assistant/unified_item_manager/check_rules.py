"""Quick script to see what's in recurring_event_rules table"""

from app.assistant.unified_item_manager.recurring_event_rules import RecurringEventRuleManager
from app.models.base import get_session

print("\n" + "="*80)
print("📊 CHECKING RECURRING_EVENT_RULES TABLE")
print("="*80 + "\n")

session = get_session()

# Check if table exists
try:
    result = session.execute("SELECT COUNT(*) FROM recurring_event_rules")
    count = result.scalar()
    print(f"✅ Table exists with {count} rules\n")
    
    if count > 0:
        # Get all rules
        result = session.execute("""
            SELECT id, event_title, action, reason, created_at 
            FROM recurring_event_rules 
            ORDER BY created_at DESC
        """)
        
        print("Rules found:")
        print("─" * 80)
        for row in result:
            print(f"\nEvent: {row[1]}")
            print(f"  ID: {row[0]}")
            print(f"  Action: {row[2]}")
            print(f"  Reason: {row[3]}")
            print(f"  Created: {row[4]}")
    else:
        print("⚠️  No rules in table - this is correct if you haven't created any yet")
        
except Exception as e:
    print(f"❌ Error: {e}")
    print("\nTable might not exist yet. Run recurring_event_rules.py first.")

print("\n" + "="*80 + "\n")


