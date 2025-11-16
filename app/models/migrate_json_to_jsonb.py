"""
Migration script to convert JSON columns to JSONB
This fixes the PostgreSQL equality operator error
"""

from app.models.base import engine
from app.assistant.utils.logging_config import get_logger

logger = get_logger(__name__)


def migrate_json_to_jsonb():
    """Migrate JSON columns to JSONB in the knowledge graph tables"""
    print("Migrating JSON columns to JSONB...")
    
    with engine.connect() as connection:
        try:
            # Check if columns exist and are JSON type
            result = connection.execute("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name IN ('nodes', 'edges') 
                AND column_name = 'embedding' 
                AND data_type = 'json'
            """)
            
            json_columns = result.fetchall()
            
            if not json_columns:
                print("No JSON columns found to migrate.")
                return
            
            print(f"Found {len(json_columns)} JSON columns to migrate:")
            for col in json_columns:
                print(f"  - {col[0]} in table")
            
            # Migrate each column
            for col in json_columns:
                table_name = 'nodes' if col[0] in ['embedding'] else 'edges'
                print(f"Migrating {table_name}.{col[0]} from JSON to JSONB...")
                
                # Convert JSON to JSONB
                connection.execute(f"""
                    ALTER TABLE {table_name} 
                    ALTER COLUMN {col[0]} TYPE jsonb USING {col[0]}::jsonb
                """)
                
                print(f"✅ Successfully migrated {table_name}.{col[0]}")
            
            connection.commit()
            print("🎉 Migration completed successfully!")
            
        except Exception as e:
            print(f"❌ Error during migration: {e}")
            connection.rollback()
            raise


def verify_migration():
    """Verify that all columns are now JSONB"""
    print("Verifying migration...")
    
    with engine.connect() as connection:
        result = connection.execute("""
            SELECT table_name, column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name IN ('nodes', 'edges') 
            AND column_name = 'embedding'
        """)
        
        columns = result.fetchall()
        
        print("Current column types:")
        for col in columns:
            print(f"  {col[0]}.{col[1]}: {col[2]}")
            
        jsonb_columns = [col for col in columns if col[2] == 'jsonb']
        if len(jsonb_columns) == len(columns):
            print("✅ All columns are now JSONB!")
        else:
            print("❌ Some columns are still not JSONB")


def main():
    """Main migration function"""
    print("=== JSON to JSONB Migration ===\n")
    
    try:
        migrate_json_to_jsonb()
        print()
        verify_migration()
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        print(f"❌ Migration failed: {e}")


if __name__ == "__main__":
    main()
