"""
Migration: Simplify edge_canon table columns
1. Rename relationship_type_snake to edge_type
2. Rename embedding (JSONB) to edge_type_embedding (VECTOR(384))
"""

from app.assistant.kg_core.knowledge_graph_db import get_session
from sqlalchemy import text, inspect

def main():
    print("🔧 Simplifying edge_canon table columns...")
    
    session = get_session()
    engine = session.bind
    
    print(f"🔍 Database: {engine.url}")
    
    try:
        # Check if the table exists
        inspector = inspect(engine)
        if 'edge_canon' not in inspector.get_table_names():
            print("⚠️  Table 'edge_canon' does not exist - skipping migration")
            return
        
        # Check current columns
        columns = inspector.get_columns('edge_canon')
        column_names = [col['name'] for col in columns]
        
        with engine.connect() as conn:
            # 1. Rename relationship_type_snake to edge_type
            if 'edge_type' in column_names:
                print("✅ Column 'edge_type' already exists - skipping rename")
            elif 'relationship_type_snake' in column_names:
                print("📝 Renaming 'relationship_type_snake' to 'edge_type'...")
                conn.execute(text("ALTER TABLE edge_canon RENAME COLUMN relationship_type_snake TO edge_type"))
                conn.commit()
                print("✅ Successfully renamed to 'edge_type'!")
            else:
                print("⚠️  Neither column exists - skipping rename")
            
            # Refresh column list
            columns = inspector.get_columns('edge_canon')
            column_names = [col['name'] for col in columns]
            
            # 2. Handle embedding column
            if 'edge_type_embedding' in column_names:
                print("✅ Column 'edge_type_embedding' already exists - skipping embedding migration")
            elif 'embedding' in column_names:
                print("📝 Migrating 'embedding' to 'edge_type_embedding' (VECTOR(384))...")
                # Drop old JSONB column and create new VECTOR column
                conn.execute(text("ALTER TABLE edge_canon DROP COLUMN IF EXISTS embedding"))
                conn.execute(text("ALTER TABLE edge_canon ADD COLUMN edge_type_embedding VECTOR(384)"))
                conn.commit()
                print("✅ Successfully created 'edge_type_embedding' column!")
            else:
                print("📝 Creating 'edge_type_embedding' column...")
                conn.execute(text("ALTER TABLE edge_canon ADD COLUMN edge_type_embedding VECTOR(384)"))
                conn.commit()
                print("✅ Successfully created 'edge_type_embedding' column!")
        
    except Exception as e:
        print(f"❌ Error during migration: {e}")
        session.rollback()
        raise
    finally:
        session.close()
    
    print("🎉 Migration complete!")

if __name__ == "__main__":
    main()

