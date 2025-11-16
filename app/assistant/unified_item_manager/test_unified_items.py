"""
Test Script for UnifiedItemManager
===================================

Run this to test the unified item system:
    python -m app.assistant.unified_item_manager.test_unified_items
"""

if __name__ == "__main__":
    import sys
    import os
    
    # Ensure we're in the project root
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    
    from app.assistant.unified_item_manager import UnifiedItemManager, ItemState
    from datetime import datetime, timezone, timedelta
    
    print("="*80)
    print("UNIFIED ITEM MANAGER TEST")
    print("="*80)
    
    manager = UnifiedItemManager()
    
    # Test 1: Get statistics
    print("\n📊 System Statistics:")
    stats = manager.get_stats()
    print(f"Total items: {stats['total']}")
    print(f"By state: {stats['by_state']}")
    print(f"By source: {stats['by_source']}")
    
    # Test 2: Ingest from all sources
    print("\n📥 Ingesting from all sources...")
    try:
        results = manager.ingest_all_sources()
        for source, items in results.items():
            print(f"  {source}: {len(items)} new items")
    except Exception as e:
        print(f"  Error: {e}")
    
    # Test 3: Get items for triage
    print("\n🔍 Items needing triage:")
    triage_items = manager.get_items_for_triage(limit=10)
    print(f"  Found {len(triage_items)} items")
    for item in triage_items[:5]:  # Show first 5
        print(f"  - [{item.source_type}] {item.title[:50]}...")
    
    # Test 4: Get items in progress
    print("\n⏳ Items in progress:")
    progress_items = manager.get_items_in_progress()
    print(f"  Found {len(progress_items)} items")
    for item in progress_items[:5]:
        print(f"  - [{item.source_type}] {item.title[:50]}...")
    
    # Test 5: Get recent actions
    print("\n✅ Recent actions (last 24 hours):")
    recent = manager.get_recent_actions(hours=24)
    print(f"  Found {len(recent)} completed actions")
    for item in recent[:5]:
        print(f"  - [{item.source_type}] {item.title[:50]}...")
    
    # Test 6: State transition example (if items exist)
    if triage_items:
        print("\n🔄 Testing state transition...")
        item = triage_items[0]
        print(f"  Item: {item.title[:50]}")
        print(f"  Current state: {item.state}")
        
        # Don't actually transition in test mode - just show how it would work
        print(f"  Would transition to: DISMISSED")
        # manager.dismiss_item(item.id, reason="Test dismissal")
    
    print("\n" + "="*80)
    print("✅ Test complete!")
    print("="*80)

