"""
Drop edge_canon and edge_alias tables to recreate with new schema.
"""

from app.assistant.kg_core.knowledge_graph_db import get_session
from sqlalchemy import text

def main():
    print("🗑️  Dropping edge_canon and edge_alias tables...")
    
    session = get_session()
    engine = session.bind
    
    print(f"🔍 Database: {engine.url}")
    
    try:
        with engine.connect() as conn:
            # Drop tables in correct order (aliases first due to foreign key)
            print("📝 Dropping edge_alias table...")
            conn.execute(text("DROP TABLE IF EXISTS edge_alias CASCADE"))
            conn.commit()
            print("✅ Dropped edge_alias")
            
            print("📝 Dropping edge_canon table...")
            conn.execute(text("DROP TABLE IF EXISTS edge_canon CASCADE"))
            conn.commit()
            print("✅ Dropped edge_canon")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        session.rollback()
        raise
    finally:
        session.close()
    
    print("🎉 Tables dropped successfully!")
    print("\n📋 Next step: Run create_edge_tables.py")

if __name__ == "__main__":
    main()

