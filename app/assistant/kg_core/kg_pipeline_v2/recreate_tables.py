#!/usr/bin/env python3
"""
Recreate Pipeline V2 Database Tables

This script drops and recreates all pipeline tables with the fixed schema.
"""

import logging
from app.models.base import get_session
from app.assistant.kg_core.kg_pipeline_v2.database_schema import Base

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def drop_pipeline_tables():
    """Drop all pipeline V2 tables"""
    session = get_session()
    engine = session.bind
    print(f"🗑️ Dropping pipeline tables...")
    
    # Drop all tables
    Base.metadata.drop_all(engine, tables=[
        Base.metadata.tables['pipeline_batches'],
        Base.metadata.tables['pipeline_nodes'],
        Base.metadata.tables['pipeline_edges'],
        Base.metadata.tables['stage_results'],
        Base.metadata.tables['stage_completion'],
        Base.metadata.tables['fact_extraction_results'],
        Base.metadata.tables['parser_results'],
        Base.metadata.tables['metadata_results'],
        Base.metadata.tables['merge_results'],
        Base.metadata.tables['taxonomy_results'],
    ], checkfirst=True)
    
    session.close()
    print("✅ Pipeline tables dropped successfully.")


def create_pipeline_tables():
    """Create all pipeline V2 database tables"""
    session = get_session()
    engine = session.bind
    print(f"🔍 Pipeline V2 Debug: Connecting to database: {engine.url}")
    Base.metadata.create_all(engine, checkfirst=True)
    session.close()
    print("Pipeline V2 tables initialized successfully.")
    print("💡 Tip: Run 'load_data_simple.py' to load data into the pipeline.")


if __name__ == '__main__':
    """
    Run this file directly from IDE to recreate pipeline tables
    """
    print("🔄 KG Pipeline V2 - Recreate Tables")
    print("=" * 50)
    
    print("⚠️ This will drop all existing pipeline tables!")
    confirm = input("Continue? (y/N): ").strip().lower()
    if confirm != 'y':
        print("❌ Operation cancelled")
        exit(1)
    
    print("\n🔄 Dropping existing tables...")
    drop_pipeline_tables()
    
    print("\n🔄 Creating new tables...")
    create_pipeline_tables()
    
    print("✅ Database recreation completed successfully!")
    print("💡 You can now load data and run stages")
