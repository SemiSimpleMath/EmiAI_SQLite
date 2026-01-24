"""
Migration: Add category column to unified_log table

This column was defined in the model but never added to the database.
It's marked as deprecated but kept for backwards compatibility.
"""

import sqlite3
from pathlib import Path

def run_migration():
    """Add category column to unified_log table."""
    
    # Get database path (at project root)
    project_root = Path(__file__).parent.parent.parent.parent.parent
    db_path = project_root / 'emi.db'
    
    if not db_path.exists():
        print(f"[ERROR] Database not found at {db_path}")
        return False
    
    print(f"[INFO] Using database: {db_path}")
    
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    try:
        # Check if column already exists
        cursor.execute("PRAGMA table_info(unified_log)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'category' in columns:
            print("[OK] Column 'category' already exists in unified_log")
            return True
        
        # Add column
        print("[INFO] Adding 'category' column to unified_log...")
        cursor.execute("ALTER TABLE unified_log ADD COLUMN category VARCHAR")
        conn.commit()
        print("[OK] Column 'category' added successfully")
        
        # Verify
        cursor.execute("PRAGMA table_info(unified_log)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'category' in columns:
            print("[OK] Verification passed: 'category' column exists")
            return True
        else:
            print("[ERROR] Verification failed: 'category' column not found after addition")
            return False
        
    except sqlite3.Error as e:
        print(f"[ERROR] {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

if __name__ == '__main__':
    print("="*60)
    print("Migration: Add category column to unified_log")
    print("="*60)
    success = run_migration()
    print("="*60)
    print("[OK] Migration completed successfully" if success else "[ERROR] Migration failed")
    print("="*60)

