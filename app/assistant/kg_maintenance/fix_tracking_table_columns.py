#!/usr/bin/env python3
"""
Migration Script: Fix column length issues in duplicate_analysis_tracking table

This script:
1. Ensures the duplicate_analysis_tracking table exists
2. Changes suggested_action from VARCHAR(100) to TEXT (unlimited length)
3. Ensures the table can handle long agent responses
"""

import logging
import os
from sqlalchemy import text
from app.models.base import get_default_engine

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def debug_database_connection():
    """Debug which database we're connecting to"""
    logger.info("🔍 Database Connection Debug:")
    logger.info(f"  USE_TEST_DB: {os.environ.get('USE_TEST_DB')}")
    logger.info(f"  TEST_DB_NAME: {os.environ.get('TEST_DB_NAME')}")
    logger.info(f"  DEV_DATABASE_URI_EMI: {os.environ.get('DEV_DATABASE_URI_EMI', 'NOT_SET')}")
    logger.info(f"  TEST_DATABASE_URI_EMI: {os.environ.get('TEST_DATABASE_URI_EMI', 'NOT_SET')}")
    
    # Get the actual engine and show what we're connecting to
    engine = get_default_engine()
    logger.info(f"  Actual Database URL: {engine.url}")
    
    # Test the connection to see what tables we have
    try:
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name LIKE '%tracking%'
                ORDER BY table_name
            """))
            tracking_tables = [row[0] for row in result]
            logger.info(f"  Found tracking tables: {tracking_tables}")
            
            # Check if our target table exists
            if 'duplicate_analysis_tracking' in tracking_tables:
                result = conn.execute(text("SELECT COUNT(*) FROM duplicate_analysis_tracking"))
                record_count = result.fetchone()[0]
                logger.info(f"  duplicate_analysis_tracking table has {record_count} records")
            else:
                logger.info("  duplicate_analysis_tracking table does not exist yet")
                
    except Exception as e:
        logger.error(f"  Failed to connect: {e}")

def ensure_tracking_table_exists():
    """Ensure the duplicate_analysis_tracking table exists by importing and initializing it"""
    try:
        # Import the tracking system and initialize it
        from app.models.node_analysis_tracking import initialize_node_analysis_tracking_db
        logger.info("🔧 Initializing tracking table...")
        initialize_node_analysis_tracking_db()
        logger.info("✅ Tracking table initialized successfully")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to initialize tracking table: {e}")
        return False

def check_column_types():
    """Check the current column types in the duplicate_analysis_tracking table"""
    engine = get_default_engine()
    
    try:
        with engine.connect() as conn:
            # Check if table exists
            result = conn.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_name = 'duplicate_analysis_tracking'
            """))
            
            if not result.fetchone():
                logger.warning("⚠️ Table duplicate_analysis_tracking does not exist")
                return False
            
            # Check column types
            result = conn.execute(text("""
                SELECT column_name, data_type, character_maximum_length
                FROM information_schema.columns 
                WHERE table_name = 'duplicate_analysis_tracking' 
                AND column_name IN ('suggested_action', 'suspect_reason')
                ORDER BY column_name
            """))
            
            columns = result.fetchall()
            logger.info("📊 Current column configuration:")
            
            for column_name, data_type, max_length in columns:
                max_length_str = f"({max_length})" if max_length else ""
                logger.info(f"  - {column_name}: {data_type}{max_length_str}")
            
            return True
            
    except Exception as e:
        logger.error(f"❌ Failed to check column types: {e}")
        return False

def fix_tracking_table_columns():
    """Fix the column length issues in the duplicate_analysis_tracking table"""
    engine = get_default_engine()
    
    try:
        with engine.connect() as conn:
            # Check current column type for suggested_action
            result = conn.execute(text("""
                SELECT column_name, data_type, character_maximum_length
                FROM information_schema.columns 
                WHERE table_name = 'duplicate_analysis_tracking' 
                AND column_name = 'suggested_action'
            """))
            
            column_info = result.fetchone()
            if column_info:
                column_name, data_type, max_length = column_info
                logger.info(f"Current column: {column_name}, type: {data_type}, max_length: {max_length}")
                
                if data_type == 'character varying' and max_length == 100:
                    # Change the column type from VARCHAR(100) to TEXT
                    logger.info("🔧 Changing suggested_action column from VARCHAR(100) to TEXT...")
                    conn.execute(text("""
                        ALTER TABLE duplicate_analysis_tracking 
                        ALTER COLUMN suggested_action TYPE TEXT
                    """))
                    conn.commit()
                    logger.info("✅ Successfully changed suggested_action column to TEXT")
                else:
                    logger.info("✅ Column is already TEXT or has different configuration")
            else:
                logger.warning("⚠️ Column suggested_action not found in table")
                
            # Also check suspect_reason column
            result = conn.execute(text("""
                SELECT column_name, data_type, character_maximum_length
                FROM information_schema.columns 
                WHERE table_name = 'duplicate_analysis_tracking' 
                AND column_name = 'suspect_reason'
            """))
            
            column_info = result.fetchone()
            if column_info:
                column_name, data_type, max_length = column_info
                logger.info(f"Current column: {column_name}, type: {data_type}, max_length: {max_length}")
                
                if data_type == 'character varying' and max_length:
                    # Change any VARCHAR with length limit to TEXT
                    logger.info(f"🔧 Changing {column_name} column from {data_type}({max_length}) to TEXT...")
                    conn.execute(text(f"""
                        ALTER TABLE duplicate_analysis_tracking 
                        ALTER COLUMN {column_name} TYPE TEXT
                    """))
                    conn.commit()
                    logger.info(f"✅ Successfully changed {column_name} column to TEXT")
                else:
                    logger.info(f"✅ Column {column_name} is already TEXT or unlimited")
                
    except Exception as e:
        logger.error(f"❌ Failed to fix tracking table columns: {e}")
        return False
    
    return True

def verify_fix():
    """Verify that the column fix was successful"""
    engine = get_default_engine()
    
    try:
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT column_name, data_type, character_maximum_length
                FROM information_schema.columns 
                WHERE table_name = 'duplicate_analysis_tracking' 
                AND column_name IN ('suggested_action', 'suspect_reason')
                ORDER BY column_name
            """))
            
            columns = result.fetchall()
            logger.info("✅ Verification Results:")
            
            all_fixed = True
            for column_name, data_type, max_length in columns:
                max_length_str = f"({max_length})" if max_length else ""
                logger.info(f"  - {column_name}: {data_type}{max_length_str}")
                
                if data_type == 'character varying' and max_length:
                    logger.warning(f"⚠️ Column {column_name} still has length limit - fix may not have worked")
                    all_fixed = False
                elif data_type == 'text':
                    logger.info(f"✅ Column {column_name} is now TEXT (unlimited)")
                else:
                    logger.info(f"ℹ️ Column {column_name} has type {data_type}")
            
            if all_fixed:
                logger.info("🎉 All columns are now TEXT (unlimited length)")
                return True
            else:
                logger.warning("⚠️ Some columns still have length limits")
                return False
                
    except Exception as e:
        logger.error(f"❌ Verification failed: {e}")
        return False

def main():
    """Main migration function"""
    logger.info("🔧 Starting tracking table column fix...")
    
    # Set environment variable to use test database
    os.environ['USE_TEST_DB'] = 'true'
    os.environ['TEST_DB_NAME'] = 'test_emidb'
    logger.info("🔧 Set USE_TEST_DB=true to target test database")
    
    # Debug database connection first
    debug_database_connection()
    
    # Step 1: Ensure the tracking table exists
    if not ensure_tracking_table_exists():
        logger.error("❌ Failed to create tracking table. Aborting.")
        return
    
    # Step 2: Check current column configuration
    if not check_column_types():
        logger.error("❌ Failed to check column types. Aborting.")
        return
    
    # Step 3: Fix the columns
    if not fix_tracking_table_columns():
        logger.error("❌ Failed to fix tracking table columns. Aborting.")
        return
    
    # Step 4: Verify the fix
    if verify_fix():
        logger.info("🎉 Migration completed successfully!")
    else:
        logger.error("❌ Migration verification failed")

if __name__ == "__main__":
    main()
