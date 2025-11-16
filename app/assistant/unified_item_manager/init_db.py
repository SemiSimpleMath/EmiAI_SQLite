#!/usr/bin/env python3
"""
Initialize UnifiedItems Database
=================================

Simple script to create the unified_items table.

Usage:
    python app/assistant/unified_item_manager/init_db.py [init|drop|reset]
    
Or import:
    python -m app.assistant.unified_item_manager.unified_item init
"""

if __name__ == "__main__":
    import sys
    import os
    
    # Ensure we're in the project root
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    
    from app.assistant.unified_item_manager.unified_item import (
        initialize_unified_items_db,
        drop_unified_items_db,
        reset_unified_items_db
    )
    
    command = sys.argv[1].lower() if len(sys.argv) > 1 else "init"
    
    if command == "init":
        print("\n🚀 Initializing unified_items table...")
        initialize_unified_items_db()
    elif command == "drop":
        print("\n⚠️  Dropping unified_items table...")
        response = input("Are you sure? This will delete all data! (yes/no): ")
        if response.lower() == "yes":
            drop_unified_items_db()
        else:
            print("❌ Cancelled.")
    elif command == "reset":
        print("\n⚠️  Resetting unified_items table...")
        response = input("Are you sure? This will delete all data and recreate the table! (yes/no): ")
        if response.lower() == "yes":
            reset_unified_items_db()
        else:
            print("❌ Cancelled.")
    else:
        print("Usage: python init_db.py [init|drop|reset]")
        sys.exit(1)
    
    print("\n✅ Done!\n")

