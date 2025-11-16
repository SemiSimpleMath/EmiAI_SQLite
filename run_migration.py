#!/usr/bin/env python3
"""
Simple script to run the semantic_type to semantic_label migration.
"""

import sys
import os

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from migrate_semantic_type_to_semantic_label import migrate_semantic_type_to_semantic_label, rollback_migration

def main():
    print("🚀 Semantic Type to Semantic Label Migration")
    print("=" * 50)
    
    if len(sys.argv) > 1 and sys.argv[1] == "--rollback":
        print("🔄 Running rollback...")
        rollback_migration()
    else:
        print("🔄 Running migration...")
        migrate_semantic_type_to_semantic_label()
    
    print("✅ Done!")

if __name__ == "__main__":
    main()
