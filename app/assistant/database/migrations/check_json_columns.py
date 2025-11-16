"""
Safe read-only script to check JSON column types
This will NOT make any changes to your database
"""

from app.models.base import engine
from app.assistant.utils.logging_config import get_logger

logger = get_logger(__name__)


def check_json_columns():
    """Check which columns are JSON vs JSONB (READ-ONLY)"""
    print("🔍 Checking JSON column types (READ-ONLY)...")
    
    with engine.connect() as connection:
        try:
            # Check all JSON/JSONB columns in the database
            result = connection.execute("""
                SELECT 
                    table_name, 
                    column_name, 
                    data_type,
                    is_nullable,
                    column_default
                FROM information_schema.columns 
                WHERE table_schema = 'public'
                AND data_type IN ('json', 'jsonb')
                ORDER BY table_name, column_name
            """)
            
            columns = result.fetchall()
            
            if not columns:
                print("✅ No JSON/JSONB columns found in the database.")
                return
            
            print(f"Found {len(columns)} JSON/JSONB columns:")
            print()
            
            json_columns = []
            jsonb_columns = []
            
            for col in columns:
                table_name, column_name, data_type, is_nullable, column_default = col
                print(f"  📋 {table_name}.{column_name}: {data_type}")
                print(f"      Nullable: {is_nullable}, Default: {column_default or 'None'}")
                
                if data_type == 'json':
                    json_columns.append((table_name, column_name))
                else:
                    jsonb_columns.append((table_name, column_name))
            
            print()
            print("📊 Summary:")
            print(f"  JSON columns: {len(json_columns)}")
            print(f"  JSONB columns: {len(jsonb_columns)}")
            
            if json_columns:
                print()
                print("⚠️  JSON columns that need migration:")
                for table, col in json_columns:
                    print(f"  - {table}.{col}")
                print()
                print("💡 These columns may cause the equality operator error.")
                print("   Consider migrating them to JSONB for better performance.")
            else:
                print()
                print("✅ All JSON columns are already JSONB!")
                
        except Exception as e:
            print(f"❌ Error checking columns: {e}")
            raise


def check_table_sizes():
    """Check the size of tables (READ-ONLY)"""
    print("\n📏 Checking table sizes (READ-ONLY)...")
    
    with engine.connect() as connection:
        try:
            result = connection.execute("""
                SELECT 
                    schemaname,
                    tablename,
                    attname,
                    n_distinct,
                    correlation
                FROM pg_stats 
                WHERE schemaname = 'public'
                AND tablename IN ('nodes', 'edges')
                ORDER BY tablename, attname
            """)
            
            stats = result.fetchall()
            
            if stats:
                print("Table statistics:")
                for stat in stats:
                    schemaname, tablename, attname, n_distinct, correlation = stat
                    print(f"  {tablename}.{attname}: {n_distinct} distinct values")
            else:
                print("No statistics available.")
                
        except Exception as e:
            print(f"❌ Error checking table sizes: {e}")


def main():
    """Main function - READ ONLY"""
    print("=== Safe JSON Column Check (READ-ONLY) ===\n")
    print("🔒 This script will NOT make any changes to your database!")
    print()
    
    try:
        check_json_columns()
        check_table_sizes()
        
        print("\n🎯 Next Steps:")
        print("1. Review the column types above")
        print("2. If you see JSON columns, consider creating a backup first")
        print("3. Test the migration on a copy of your data")
        print("4. Only then run the migration on your main database")
        
    except Exception as e:
        logger.error(f"Check failed: {e}")
        print(f"❌ Check failed: {e}")


if __name__ == "__main__":
    main()
