"""
Migration: Add is_provisional column to active_segments table.

This column tracks whether a segment is still being actively tracked (provisional)
or has been finalized (user went AFK).

Run this script once to add the column to existing databases.
"""

import sqlite3
from pathlib import Path


def migrate():
    """Add is_provisional column to active_segments table."""
    # Find the database
    db_path = Path(__file__).resolve().parents[4] / "emi.db"
    
    if not db_path.exists():
        print(f"Database not found at {db_path}")
        return False
    
    print(f"Migrating database: {db_path}")
    
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    try:
        # Check if column already exists
        cursor.execute("PRAGMA table_info(active_segments)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'is_provisional' in columns:
            print("Column 'is_provisional' already exists. Skipping.")
            return True
        
        # Add the column with default value False (all existing segments are finalized)
        print("Adding 'is_provisional' column to active_segments table...")
        cursor.execute("""
            ALTER TABLE active_segments
            ADD COLUMN is_provisional BOOLEAN NOT NULL DEFAULT 0
        """)
        
        conn.commit()
        print("Migration complete: Added is_provisional column")
        
        # Verify
        cursor.execute("PRAGMA table_info(active_segments)")
        columns = [row[1] for row in cursor.fetchall()]
        print(f"Current columns: {columns}")
        
        return True
        
    except sqlite3.Error as e:
        print(f"Migration failed: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


if __name__ == "__main__":
    success = migrate()
    exit(0 if success else 1)
