# add_active_segments_table.py
"""
Migration: Create active_segments table for Active-First presence tracking.

This replaces the AFK-First model where we tracked AFK segments.
Now we track ACTIVE segments (when user is at keyboard).
AFK time is derived from gaps between active segments.

Run: python -m app.assistant.database.migrations.add_active_segments_table
"""

import sqlite3
from pathlib import Path


def get_db_path() -> Path:
    """Get the database path."""
    return Path(__file__).resolve().parents[4] / "emi.db"


def migrate():
    """Add active_segments table."""
    db_path = get_db_path()
    print(f"[*] Migrating database: {db_path}")
    
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    try:
        # Check if table already exists
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='active_segments'
        """)
        
        if cursor.fetchone():
            print("[*] active_segments table already exists")
            return
        
        # Create the active_segments table
        cursor.execute("""
            CREATE TABLE active_segments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                start_time DATETIME NOT NULL,
                end_time DATETIME NOT NULL,
                duration_minutes REAL NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create indexes
        cursor.execute("""
            CREATE INDEX idx_active_segment_start ON active_segments(start_time)
        """)
        cursor.execute("""
            CREATE INDEX idx_active_segment_end ON active_segments(end_time)
        """)
        
        conn.commit()
        print("[+] Created active_segments table with indexes")
        
        # Show table info
        cursor.execute("PRAGMA table_info(active_segments)")
        columns = cursor.fetchall()
        print("\n    Columns:")
        for col in columns:
            print(f"      - {col[1]} ({col[2]})")
        
    except Exception as e:
        conn.rollback()
        print(f"[!] Migration failed: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
