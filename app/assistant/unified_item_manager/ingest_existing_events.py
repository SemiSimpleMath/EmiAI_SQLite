"""
Initial ingestion script: Populate UnifiedItems from EventRepository
Run this once to migrate existing events into the unified item state machine.
"""

from app.assistant.unified_item_manager import UnifiedItemManager

if __name__ == "__main__":
    print("\n" + "="*80)
    print("🔄 INITIAL INGESTION: EventRepository → UnifiedItems")
    print("="*80 + "\n")
    
    manager = UnifiedItemManager()
    
    print("📥 Ingesting all events from EventRepository...")
    print("   - Emails")
    print("   - Calendar events")
    print("   - Todo tasks")
    print("   - Scheduler reminders\n")
    
    results = manager.ingest_all_sources()
    
    print("\n" + "="*80)
    print("✅ INGESTION COMPLETE!")
    print("="*80)
    print(f"\n📊 Summary:")
    print(f"   • Emails:     {len(results.get('email', [])):>4} new")
    print(f"   • Calendar:   {len(results.get('calendar', [])):>4} new")
    print(f"   • Todos:      {len(results.get('todo_task', [])):>4} new")
    print(f"   • Scheduler:  {len(results.get('scheduler', [])):>4} new")
    print(f"\n   TOTAL NEW:    {sum(len(items) for items in results.values())} items\n")
    
    # Show current state breakdown
    print("📈 Current UnifiedItems state breakdown:")
    stats = manager.get_stats()
    print(f"   Total items: {stats['total']}")
    for state, count in stats['by_state'].items():
        if count > 0:
            print(f"   • {state:>20}: {count:>4} items")
    
    print("\n💡 Next steps:")
    print("   - All items are now in 'NEW' state")
    print("   - system_state_monitor will use get_items_for_triage()")
    print("   - Agents can transition items through the state machine\n")

