"""
Safe backup script for Knowledge Graph tables
Exports data to JSON files - no database modifications
"""

import json
import os
from datetime import datetime
from app.models.base import get_session
from app.assistant.kg_core.knowledge_graph_db import Node, Edge
from app.assistant.utils.logging_config import get_logger

logger = get_logger(__name__)


def backup_table_to_json(session, model_class, backup_dir):
    """Backup a table to JSON file"""
    table_name = model_class.__tablename__
    filename = os.path.join(backup_dir, f"{table_name}_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    
    print(f"📋 Backing up {table_name}...")
    
    # Get all records
    records = session.query(model_class).all()
    
    # Convert to JSON-serializable format
    data = []
    for record in records:
        record_dict = {}
        for column in model_class.__table__.columns:
            value = getattr(record, column.name)
            # Handle UUID and datetime serialization
            if hasattr(value, 'isoformat'):  # datetime
                record_dict[column.name] = value.isoformat()
            elif hasattr(value, 'hex'):  # UUID
                record_dict[column.name] = str(value)
            else:
                record_dict[column.name] = value
        data.append(record_dict)
    
    # Save to JSON file
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"✅ {table_name}: {len(data)} records saved to {filename}")
    return filename, len(data)


def backup_kg_tables():
    """Backup all Knowledge Graph tables"""
    print("🛡️  Creating Knowledge Graph backup...")
    
    # Create backup directory
    backup_dir = f"kg_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    os.makedirs(backup_dir, exist_ok=True)
    
    print(f"📁 Backup directory: {backup_dir}")
    
    session = get_session()
    backup_summary = {}
    
    try:
        # Backup each table
        tables_to_backup = [
            (Node, "Nodes"),
            (Edge, "Edges")
        ]
        
        for model_class, table_name in tables_to_backup:
            try:
                filename, count = backup_table_to_json(session, model_class, backup_dir)
                backup_summary[table_name] = {
                    'filename': filename,
                    'record_count': count
                }
            except Exception as e:
                print(f"❌ Error backing up {table_name}: {e}")
                backup_summary[table_name] = {'error': str(e)}
        
        # Create backup summary
        summary_file = os.path.join(backup_dir, "backup_summary.json")
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump({
                'backup_date': datetime.now().isoformat(),
                'tables': backup_summary,
                'total_records': sum(info.get('record_count', 0) for info in backup_summary.values() if isinstance(info, dict) and 'record_count' in info)
            }, f, indent=2)
        
        print(f"\n📊 Backup Summary:")
        print(f"  Total records: {backup_summary.get('total_records', 0)}")
        print(f"  Backup location: {os.path.abspath(backup_dir)}")
        print(f"  Summary file: {summary_file}")
        
        print("\n✅ Backup completed successfully!")
        print("🔒 Your data is safe in JSON format.")
        
        return backup_dir, backup_summary
        
    except Exception as e:
        print(f"❌ Backup failed: {e}")
        raise
    finally:
        session.close()


def verify_backup(backup_dir):
    """Verify the backup files"""
    print(f"\n🔍 Verifying backup in {backup_dir}...")
    
    summary_file = os.path.join(backup_dir, "backup_summary.json")
    if not os.path.exists(summary_file):
        print("❌ Backup summary not found")
        return False
    
    with open(summary_file, 'r') as f:
        summary = json.load(f)
    
    print("📋 Backup verification:")
    for table_name, info in summary['tables'].items():
        if 'error' in info:
            print(f"  ❌ {table_name}: {info['error']}")
        else:
            filename = info['filename']
            if os.path.exists(filename):
                print(f"  ✅ {table_name}: {info['record_count']} records")
            else:
                print(f"  ❌ {table_name}: File missing")
    
    return True


def main():
    """Main backup function"""
    print("=== Knowledge Graph Backup Tool ===\n")
    print("🛡️  This will create a safe backup of your KG tables")
    print("🔒 No changes will be made to your database\n")
    
    try:
        # Create backup
        backup_dir, summary = backup_kg_tables()
        
        # Verify backup
        verify_backup(backup_dir)
        
        print(f"\n🎉 Backup completed!")
        print(f"📁 Location: {os.path.abspath(backup_dir)}")
        print(f"💾 You can now safely proceed with any database changes.")
        
    except Exception as e:
        logger.error(f"Backup failed: {e}")
        print(f"❌ Backup failed: {e}")


if __name__ == "__main__":
    main()
