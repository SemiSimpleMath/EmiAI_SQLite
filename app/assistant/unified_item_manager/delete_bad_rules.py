"""Delete the auto-created fallback rules that were created without user input"""

from app.models.base import get_session
from sqlalchemy import text

session = get_session()

print("\n" + "="*80)
print("🗑️  DELETING BAD AUTO-CREATED RULES")
print("="*80 + "\n")

try:
    # Delete rules with "No response from user" in the reason
    result = session.execute(text("""
        DELETE FROM recurring_event_rules 
        WHERE reason LIKE '%No response from user%'
        RETURNING id, event_title, action
    """))
    
    deleted = result.fetchall()
    
    if deleted:
        print(f"✅ Deleted {len(deleted)} bad rules:\n")
        for row in deleted:
            print(f"   • {row[1]} (ID: {row[0]}, Action: {row[2]})")
        
        session.commit()
        print(f"\n💾 Changes committed to database")
    else:
        print("⚠️  No bad rules found")
    
except Exception as e:
    print(f"❌ Error: {e}")
    session.rollback()

print("\n" + "="*80 + "\n")


