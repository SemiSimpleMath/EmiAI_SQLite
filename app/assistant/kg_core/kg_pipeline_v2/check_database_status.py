#!/usr/bin/env python3
"""
Check Database Status for KG Pipeline V2

This script checks the database connection and table status.
"""

import logging
from app.models.base import get_session
from app.assistant.kg_core.kg_pipeline_v2.database_schema import Base

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def check_database_connection():
    """Check if database connection works"""
    try:
        print("🔌 Testing database connection...")
        session = get_session()
        engine = session.bind
        print(f"🔍 Database URL: {engine.url}")
        
        # Test connection
        with engine.connect() as conn:
            from sqlalchemy import text
            result = conn.execute(text("SELECT 1"))
            print("✅ Database connection successful!")
            session.close()
            return True
            
    except Exception as e:
        print(f"❌ Database connection failed: {str(e)}")
        return False


def check_pipeline_tables():
    """Check which pipeline tables exist"""
    try:
        print("📊 Checking pipeline tables...")
        session = get_session()
        engine = session.bind
        from sqlalchemy import inspect
        inspector = inspect(engine)
        
        existing_tables = inspector.get_table_names()
        session.close()
        
        pipeline_tables = {
            'pipeline_batches': 'Batch management',
            'pipeline_chunks': 'Chunk data storage (processing units)',
            'pipeline_edges': 'Edge data storage', 
            'stage_results': 'Stage output storage',
            'stage_completion': 'Stage completion tracking',
            'fact_extraction_results': 'Fact extraction details',
            'parser_results': 'Parser details',
            'metadata_results': 'Metadata details',
            'merge_results': 'Merge details',
            'taxonomy_results': 'Taxonomy details'
        }
        
        print("📋 Pipeline table status:")
        for table, description in pipeline_tables.items():
            if table in existing_tables:
                print(f"   ✅ {table} - {description}")
            else:
                print(f"   ❌ {table} - {description} (MISSING)")
        
        # Count existing tables
        existing_count = sum(1 for table in pipeline_tables.keys() if table in existing_tables)
        total_count = len(pipeline_tables)
        
        print(f"📊 Pipeline tables: {existing_count}/{total_count} exist")
        
        if existing_count == total_count:
            print("🎉 All pipeline tables are ready!")
            return True
        elif existing_count > 0:
            print("⚠️ Some pipeline tables are missing")
            return False
        else:
            print("❌ No pipeline tables found - need to create them")
            return False
            
    except Exception as e:
        print(f"❌ Error checking tables: {str(e)}")
        return False


def check_table_data():
    """Check if tables have data"""
    try:
        print("📊 Checking table data...")
        session = get_session()
        engine = session.bind
        
        with engine.connect() as conn:
            from sqlalchemy import text
            
            # Check pipeline_batches
            result = conn.execute(text("SELECT COUNT(*) FROM pipeline_batches"))
            batch_count = result.scalar()
            print(f"   📦 Batches: {batch_count}")
            
            # Check pipeline_chunks
            result = conn.execute(text("SELECT COUNT(*) FROM pipeline_chunks"))
            chunk_count = result.scalar()
            print(f"   🔗 Chunks: {chunk_count}")
            
            # Check pipeline_edges
            result = conn.execute(text("SELECT COUNT(*) FROM pipeline_edges"))
            edge_count = result.scalar()
            print(f"   🔗 Edges: {edge_count}")
            
            # Check stage_results
            result = conn.execute(text("SELECT COUNT(*) FROM stage_results"))
            result_count = result.scalar()
            print(f"   📊 Stage results: {result_count}")
            
            # Check stage_completion
            result = conn.execute(text("SELECT COUNT(*) FROM stage_completion"))
            completion_count = result.scalar()
            print(f"   ✅ Stage completions: {completion_count}")
            
        session.close()
        return True
        
    except Exception as e:
        print(f"❌ Error checking table data: {str(e)}")
        return False


def main():
    """Main function to check database status"""
    print("🔍 Checking KG Pipeline V2 Database Status")
    print("=" * 50)
    
    # Check database connection
    if not check_database_connection():
        print("❌ Cannot proceed - database connection failed")
        exit(1)
    
    # Check pipeline tables
    if not check_pipeline_tables():
        print("⚠️ Pipeline tables are not ready")
        print("💡 Run: create_pipeline_tables.py")
        exit(1)
    
    # Check table data
    check_table_data()
    
    print("🎉 Database status check complete!")


if __name__ == '__main__':
    """
    Run this file directly from IDE to check database status
    """
    main()
