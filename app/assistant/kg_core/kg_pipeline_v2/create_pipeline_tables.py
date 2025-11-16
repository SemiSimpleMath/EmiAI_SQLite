#!/usr/bin/env python3
"""
Create Pipeline V2 Database Tables

This script creates all the database tables needed for the KG Pipeline V2.
Run this before using the pipeline.
"""

import logging
from app.models.base import get_session
from app.assistant.kg_core.kg_pipeline_v2.database_schema import Base

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def create_pipeline_tables():
    """Create all pipeline V2 database tables"""
    session = get_session()
    engine = session.bind
    print(f"🔍 Pipeline V2 Debug: Connecting to database: {engine.url}")
    Base.metadata.create_all(engine, checkfirst=True)
    session.close()
    print("Pipeline V2 tables initialized successfully.")
    print("💡 Tip: Run 'load_data_simple.py' to load data into the pipeline.")


def check_tables_exist():
    """Check if pipeline tables already exist"""
    try:
        session = get_session()
        engine = session.bind
        from sqlalchemy import inspect
        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()
        session.close()
        
        pipeline_tables = [
            'pipeline_batches',
            'pipeline_chunks',
            'pipeline_edges',
            'stage_results',
            'stage_completion'
        ]
        
        existing_pipeline_tables = [table for table in pipeline_tables if table in existing_tables]
        
        if existing_pipeline_tables:
            print(f"⚠️ Some pipeline tables already exist: {existing_pipeline_tables}")
            return True
        else:
            print("📭 No pipeline tables found - safe to create")
            return False
            
    except Exception as e:
        print(f"❌ Error checking tables: {str(e)}")
        return False


def drop_pipeline_tables():
    """Drop all pipeline V2 tables (use with caution!)"""
    from sqlalchemy import text
    session = get_session()
    engine = session.bind
    
    # Drop tables in reverse dependency order with CASCADE to handle old schema
    tables_to_drop = [
        'taxonomy_results',
        'merge_results', 
        'metadata_results',
        'parser_results',
        'fact_extraction_results',
        'stage_completion',
        'stage_results',
        'pipeline_edges',
        'pipeline_chunks',
        'pipeline_nodes',  # Old table name - drop if exists
        'pipeline_batches'
    ]
    
    with engine.connect() as conn:
        for table in tables_to_drop:
            try:
                conn.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))
                conn.commit()
                print(f"  ✓ Dropped {table}")
            except Exception as e:
                print(f"  ⚠ Could not drop {table}: {e}")
    
    session.close()
    print("✅ Pipeline V2 tables dropped successfully.")


if __name__ == '__main__':
    """
    Run this file directly from IDE to create pipeline tables
    """
    print("🏗️ KG Pipeline V2 - Database Setup")
    print("=" * 50)
    
    # Check if tables already exist
    if check_tables_exist():
        print("⚠️ Pipeline tables already exist!")
        print("\nOptions:")
        print("  1. Drop existing tables and recreate (⚠️ ALL DATA WILL BE LOST)")
        print("  2. Exit")
        
        choice = input("\nEnter your choice (1 or 2): ").strip()
        
        if choice == "1":
            print("\n⚠️ WARNING: This will delete ALL pipeline data!")
            confirm = input("Type 'yes' to confirm: ").strip().lower()
            
            if confirm == "yes":
                print("\n🗑️ Dropping existing tables...")
                drop_pipeline_tables()
                print("✅ Tables dropped successfully")
            else:
                print("❌ Operation cancelled")
                exit(0)
        else:
            print("❌ Operation cancelled")
            exit(0)
    else:
        print("📭 No pipeline tables found - creating new ones")
    
    print("\n🔄 Creating pipeline tables...")
    create_pipeline_tables()
    print("✅ Database setup completed successfully!")
    print("💡 You can now load data and run stages")
