"""
Migration: Add tags column to extracted_facts table

This enables tag-based routing from Switchboard to downstream agents.
"""

import sqlite3
from pathlib import Path


def run_migration():
    """Add tags column to extracted_facts table."""
    
    # Get database path (emi.db in project root)
    db_path = Path(__file__).parent.parent.parent.parent.parent / 'emi.db'
    
    if not db_path.exists():
        print(f"[ERROR] Database not found at {db_path}")
        print("The database will be created when Flask starts.")
        print("Run this migration after starting Flask once.")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check if column already exists
        cursor.execute("PRAGMA table_info(extracted_facts)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'tags' in columns:
            print("[OK] Column 'tags' already exists in extracted_facts")
            return
        
        # Add tags column (JSON type stored as TEXT in SQLite)
        print("Adding 'tags' column to extracted_facts...")
        cursor.execute("""
            ALTER TABLE extracted_facts 
            ADD COLUMN tags TEXT NOT NULL DEFAULT '[]'
        """)
        
        conn.commit()
        print("[OK] Successfully added 'tags' column to extracted_facts")
        
        # Verify
        cursor.execute("PRAGMA table_info(extracted_facts)")
        columns = [row[1] for row in cursor.fetchall()]
        print(f"Current columns: {columns}")
        
    except Exception as e:
        conn.rollback()
        print(f"[ERROR] Error adding tags column: {e}")
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    run_migration()

