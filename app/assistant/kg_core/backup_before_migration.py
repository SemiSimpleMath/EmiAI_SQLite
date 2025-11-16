#!/usr/bin/env python3
"""
Backup script to run BEFORE the node type consistency migration.

This creates a complete backup of the node_types_new table to ensure
we can recover if anything goes wrong.
"""

import os
import sys
import json
from datetime import datetime
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Add the project root to the path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.assistant.kg_core.knowledge_graph_db import get_session

def create_backup():
    """Create a complete backup of node_types_new table"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = f"node_types_backup_{timestamp}.json"
    
    print(f"🔄 Creating backup of node_types_new table...")
    print(f"📁 Backup file: {backup_file}")
    
    session = get_session()
    try:
        # Get all node types
        result = session.execute(text("""
            SELECT type_name, json_schema 
            FROM node_types_new 
            ORDER BY type_name;
        """)).fetchall()
        
        # Create backup data
        backup_data = {
            "timestamp": timestamp,
            "table": "node_types_new",
            "total_records": len(result),
            "data": [
                {
                    "type_name": row[0],
                    "json_schema": row[1] if row[1] else {}
                }
                for row in result
            ]
        }
        
        # Write backup to file
        with open(backup_file, 'w') as f:
            json.dump(backup_data, f, indent=2, default=str)
        
        print(f"✅ Backup created successfully!")
        print(f"📊 Backed up {len(result)} node types")
        print(f"💾 File size: {os.path.getsize(backup_file)} bytes")
        
        # Also create a SQL backup
        sql_backup_file = f"node_types_backup_{timestamp}.sql"
        with open(sql_backup_file, 'w') as f:
            f.write("-- Node Types Backup\n")
            f.write(f"-- Created: {timestamp}\n")
            f.write("-- Table: node_types_new\n\n")
            
            for row in result:
                type_name = row[0].replace("'", "''")  # Escape single quotes
                json_schema = json.dumps(row[1] if row[1] else {})
                f.write(f"INSERT INTO node_types_new (type_name, json_schema) VALUES ('{type_name}', '{json_schema}');\n")
        
        print(f"📄 SQL backup also created: {sql_backup_file}")
        
        return backup_file, sql_backup_file
        
    except Exception as e:
        print(f"❌ Error creating backup: {e}")
        raise
    finally:
        session.close()

def verify_backup(backup_file):
    """Verify the backup file is valid"""
    print(f"🔍 Verifying backup file: {backup_file}")
    
    try:
        with open(backup_file, 'r') as f:
            backup_data = json.load(f)
        
        # Check structure
        required_keys = ["timestamp", "table", "total_records", "data"]
        for key in required_keys:
            if key not in backup_data:
                print(f"❌ Missing key in backup: {key}")
                return False
        
        # Check data
        if not isinstance(backup_data["data"], list):
            print("❌ Backup data is not a list")
            return False
        
        print(f"✅ Backup verification passed!")
        print(f"📊 Records in backup: {backup_data['total_records']}")
        print(f"⏰ Backup timestamp: {backup_data['timestamp']}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error verifying backup: {e}")
        return False

def restore_from_backup(backup_file):
    """Restore node_types_new table from backup (emergency use only)"""
    print(f"🚨 RESTORING FROM BACKUP: {backup_file}")
    print("⚠️  This will DELETE all current node types and restore from backup!")
    
    # Ask for confirmation
    response = input("Type 'RESTORE' to confirm: ")
    if response != "RESTORE":
        print("❌ Restore cancelled")
        return False
    
    session = get_session()
    try:
        # Load backup data
        with open(backup_file, 'r') as f:
            backup_data = json.load(f)
        
        # Clear current table
        session.execute(text("DELETE FROM node_types_new;"))
        print("🗑️  Cleared current node types")
        
        # Restore data
        for record in backup_data["data"]:
            session.execute(text("""
                INSERT INTO node_types_new (type_name, json_schema) 
                VALUES (:type_name, :json_schema)
            """), {
                "type_name": record["type_name"],
                "json_schema": record["json_schema"]
            })
        
        session.commit()
        print(f"✅ Restored {len(backup_data['data'])} node types from backup")
        return True
        
    except Exception as e:
        session.rollback()
        print(f"❌ Error restoring from backup: {e}")
        return False
    finally:
        session.close()

def main():
    """Main backup function"""
    print("🛡️  Node Types Migration Backup Tool")
    print("=" * 50)
    
    if len(sys.argv) > 1 and sys.argv[1] == "restore":
        if len(sys.argv) < 3:
            print("❌ Usage: python backup_before_migration.py restore <backup_file>")
            return
        
        backup_file = sys.argv[2]
        if not os.path.exists(backup_file):
            print(f"❌ Backup file not found: {backup_file}")
            return
        
        restore_from_backup(backup_file)
        return
    
    # Create backup
    backup_file, sql_backup_file = create_backup()
    
    # Verify backup
    if verify_backup(backup_file):
        print()
        print("🎉 Backup completed successfully!")
        print(f"📁 JSON backup: {backup_file}")
        print(f"📄 SQL backup: {sql_backup_file}")
        print()
        print("✅ You can now safely run the migration script")
        print("🚨 If something goes wrong, restore with:")
        print(f"   python {__file__} restore {backup_file}")
    else:
        print("❌ Backup verification failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()
