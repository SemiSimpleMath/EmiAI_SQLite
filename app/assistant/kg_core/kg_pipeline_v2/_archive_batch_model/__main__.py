#!/usr/bin/env python3
"""
Main entry point for KG Pipeline V2

Run from IDE or command line:
python -m app.assistant.kg_core.kg_pipeline_v2
"""

import sys
import logging
from typing import Dict, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def show_menu():
    """Show the main menu"""
    print("\n" + "="*60)
    print("🚀 KG Pipeline V2 - Independent Stage Processing")
    print("="*60)
    print("1. Setup Database - Create pipeline tables")
    print("2. Check Database - Check database status")
    print("3. Load Data - Load conversation data into pipeline")
    print("4. Run Stage - Process a specific stage")
    print("5. Check Status - Check pipeline status")
    print("6. Resume Failed - Resume failed nodes for a stage")
    print("7. Show Help - Show detailed help")
    print("8. Exit")
    print("="*60)


def setup_database_interactive():
    """Interactive database setup"""
    print("\n🏗️ Setup Database")
    print("-" * 40)
    
    try:
        from .create_pipeline_tables import create_pipeline_tables, check_tables_exist
        
        # Check if tables already exist
        if check_tables_exist():
            print("⚠️ Some pipeline tables already exist")
            force = input("Force recreate? (y/N): ").strip().lower() == 'y'
            if not force:
                print("❌ Database setup cancelled")
                return
        else:
            print("📭 No pipeline tables found - creating new ones")
        
        print("\n🔄 Creating pipeline tables...")
        success = create_pipeline_tables()
        
        if success:
            print("✅ Database setup completed successfully!")
            print("💡 You can now load data and run stages")
        else:
            print("❌ Database setup failed")
            
    except Exception as e:
        print(f"❌ Error setting up database: {str(e)}")


def check_database_interactive():
    """Interactive database status check"""
    print("\n🔍 Check Database Status")
    print("-" * 40)
    
    try:
        from .check_database_status import main as check_status
        check_status()
        
    except Exception as e:
        print(f"❌ Error checking database: {str(e)}")


def load_data_interactive():
    """Interactive data loading"""
    print("\n📥 Load Data into Pipeline")
    print("-" * 40)
    
    batch_name = input("Enter batch name: ").strip()
    if not batch_name:
        print("❌ Batch name is required")
        return
    
    limit_input = input("Enter limit (number of conversations, or press Enter for all): ").strip()
    limit = int(limit_input) if limit_input else None
    
    print(f"\n🔄 Loading data...")
    print(f"   Batch name: {batch_name}")
    print(f"   Limit: {limit or 'All'}")
    
    try:
        from .load_data import load_conversation_data
        batch_id = load_conversation_data(batch_name, limit)
        print(f"✅ Data loaded successfully!")
        print(f"   Batch ID: {batch_id}")
        print(f"   Check status: python -m app.assistant.kg_core.kg_pipeline_v2")
        
    except Exception as e:
        print(f"❌ Error loading data: {str(e)}")
        logger.error(f"Data loading failed: {str(e)}")


def run_stage_interactive():
    """Interactive stage running"""
    print("\n🏃 Run Stage")
    print("-" * 40)
    
    stages = ['conversation_boundary', 'parser', 'fact_extraction', 'metadata', 'merge', 'taxonomy']
    
    print("Available stages:")
    for i, stage in enumerate(stages, 1):
        print(f"  {i}. {stage}")
    
    try:
        stage_choice = int(input("Select stage (1-5): ")) - 1
        if stage_choice < 0 or stage_choice >= len(stages):
            print("❌ Invalid stage selection")
            return
        
        stage_name = stages[stage_choice]
        
        batch_id_input = input("Enter batch ID (or press Enter for all batches): ").strip()
        batch_id = int(batch_id_input) if batch_id_input else None
        
        batch_size_input = input("Enter batch size (default 100): ").strip()
        batch_size = int(batch_size_input) if batch_size_input else 100
        
        resume_failed = input("Resume failed nodes? (y/N): ").strip().lower() == 'y'
        
        print(f"\n🔄 Running stage: {stage_name}")
        print(f"   Batch ID: {batch_id or 'All'}")
        print(f"   Batch size: {batch_size}")
        print(f"   Resume failed: {resume_failed}")
        
        from .run_stage import run_stage
        result = run_stage(stage_name, batch_id, batch_size, resume_failed)
        
        if result['success']:
            print(f"✅ Stage completed successfully!")
            print(f"   Processed: {result['processed']}")
            print(f"   Failed: {result['failed']}")
        else:
            print(f"❌ Stage failed: {result['error']}")
            
    except ValueError:
        print("❌ Invalid input")
    except Exception as e:
        print(f"❌ Error running stage: {str(e)}")
        logger.error(f"Stage running failed: {str(e)}")


def check_status_interactive():
    """Interactive status checking"""
    print("\n📊 Check Pipeline Status")
    print("-" * 40)
    
    batch_id_input = input("Enter batch ID (or press Enter for all batches): ").strip()
    batch_id = int(batch_id_input) if batch_id_input else None
    
    print(f"\n🔄 Checking status...")
    
    try:
        from .check_pipeline_status import check_pipeline_status, print_status
        status = check_pipeline_status(batch_id)
        print_status(status)
        
    except Exception as e:
        print(f"❌ Error checking status: {str(e)}")
        logger.error(f"Status checking failed: {str(e)}")


def resume_failed_interactive():
    """Interactive resume failed processing"""
    print("\n🔄 Resume Failed Processing")
    print("-" * 40)
    
    stages = ['conversation_boundary', 'parser', 'fact_extraction', 'metadata', 'merge', 'taxonomy']
    
    print("Available stages:")
    for i, stage in enumerate(stages, 1):
        print(f"  {i}. {stage}")
    
    try:
        stage_choice = int(input("Select stage (1-5): ")) - 1
        if stage_choice < 0 or stage_choice >= len(stages):
            print("❌ Invalid stage selection")
            return
        
        stage_name = stages[stage_choice]
        
        batch_id_input = input("Enter batch ID (or press Enter for all batches): ").strip()
        batch_id = int(batch_id_input) if batch_id_input else None
        
        print(f"\n🔄 Resuming failed {stage_name} processing...")
        
        from .run_stage import run_stage
        result = run_stage(stage_name, batch_id, 100, resume_failed=True)
        
        if result['success']:
            print(f"✅ Resume completed!")
            print(f"   Processed: {result['processed']}")
            print(f"   Failed: {result['failed']}")
        else:
            print(f"❌ Resume failed: {result['error']}")
            
    except ValueError:
        print("❌ Invalid input")
    except Exception as e:
        print(f"❌ Error resuming: {str(e)}")
        logger.error(f"Resume failed: {str(e)}")


def show_help():
    """Show detailed help"""
    print("\n📚 KG Pipeline V2 Help")
    print("="*60)
    print("""
This is an independent stage processing system for the knowledge graph pipeline.

STAGES:
0. conversation_boundary - Parse input sentences and detect boundaries
1. fact_extraction - Extract facts from conversations
2. parser - Parse entities and relationships  
3. metadata - Enrich with metadata
4. merge - Merge and consolidate results
5. taxonomy - Classify into taxonomy

WORKFLOW:
1. Setup Database - Create pipeline tables (first time only)
2. Check Database - Verify database status
3. Load Data - Load conversation data into the pipeline
4. Run Stages - Process stages in order (or independently)
5. Check Status - Monitor progress
6. Resume Failed - Retry failed processing

STAGE DEPENDENCIES:
- conversation_boundary: No dependencies (stage 0)
- fact_extraction: Needs conversation_boundary
- parser: Needs conversation_boundary
- metadata: Needs fact_extraction + parser
- merge: Needs fact_extraction + parser + metadata
- taxonomy: Needs merge

PARALLEL PROCESSING:
- Stages can run on different machines
- Database coordinates between stages
- Each stage is completely independent
- Fault tolerant with resume capability

DATABASE:
- All intermediate results are stored
- Complete provenance tracking
- No data loss if stages fail
- Can restart any stage independently
""")


def main():
    """Main interactive loop"""
    while True:
        show_menu()
        
        try:
            choice = input("\nSelect option (1-8): ").strip()
            
            if choice == '1':
                setup_database_interactive()
            elif choice == '2':
                check_database_interactive()
            elif choice == '3':
                load_data_interactive()
            elif choice == '4':
                run_stage_interactive()
            elif choice == '5':
                check_status_interactive()
            elif choice == '6':
                resume_failed_interactive()
            elif choice == '7':
                show_help()
            elif choice == '8':
                print("\n👋 Goodbye!")
                break
            else:
                print("❌ Invalid option. Please select 1-8.")
                
        except KeyboardInterrupt:
            print("\n\n👋 Goodbye!")
            break
        except Exception as e:
            print(f"❌ Unexpected error: {str(e)}")
            logger.error(f"Unexpected error: {str(e)}")
        
        input("\nPress Enter to continue...")


if __name__ == '__main__':
    main()
