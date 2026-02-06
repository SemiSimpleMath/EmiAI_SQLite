"""
Migration: Add vibe columns to played_songs table

Adds:
- last_energy (INTEGER): Energy level 1-10 when song was picked
- last_valence (VARCHAR): Valence -1.0 to 1.0 when song was picked
- last_vocal_tolerance (INTEGER): Vocal tolerance 1-10 when song was picked
"""

import sqlite3
from pathlib import Path


def migrate():
    """Add vibe columns to played_songs table."""
    db_path = Path("emi.db")
    
    if not db_path.exists():
        print("Database not found at emi.db")
        return False
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check which columns already exist
    cursor.execute("PRAGMA table_info(played_songs)")
    existing_columns = {row[1] for row in cursor.fetchall()}
    
    columns_to_add = [
        ("last_energy", "INTEGER"),
        ("last_valence", "VARCHAR(10)"),
        ("last_vocal_tolerance", "INTEGER"),
    ]
    
    added = []
    for col_name, col_type in columns_to_add:
        if col_name not in existing_columns:
            try:
                cursor.execute(f"ALTER TABLE played_songs ADD COLUMN {col_name} {col_type}")
                added.append(col_name)
                print(f"[OK] Added column: {col_name}")
            except sqlite3.OperationalError as e:
                print(f"[FAIL] Failed to add {col_name}: {e}")
        else:
            print(f"[SKIP] Column {col_name} already exists")
    
    conn.commit()
    conn.close()
    
    if added:
        print(f"\nMigration complete. Added {len(added)} column(s).")
    else:
        print("\nNo changes needed - all columns already exist.")
    
    return True


if __name__ == "__main__":
    migrate()
