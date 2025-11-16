"""
Reset Stage Completion

Clears the StageCompletion records for a specific stage so it will reprocess chunks.
"""

from app.models.base import get_session
from app.assistant.kg_core.kg_pipeline_v2.database_schema import StageCompletion, StageResult


def reset_stage_completion(stage_name: str, show_preview: bool = True):
    """
    Clear StageCompletion records for a specific stage.
    
    Args:
        stage_name: Name of the stage to reset ('merge', 'metadata', etc.)
        show_preview: If True, show what will be deleted before deleting
    """
    session = get_session()
    
    try:
        # Find all completion records for this stage
        completions = session.query(StageCompletion).filter(
            StageCompletion.stage_name == stage_name
        ).all()
        
        if not completions:
            print(f"✅ No completion records found for stage '{stage_name}'")
            return
        
        print(f"📊 Found {len(completions)} completion records for stage '{stage_name}'")
        
        if show_preview:
            print(f"\n🔍 Preview of what will be reset:")
            for i, completion in enumerate(completions[:10], 1):
                print(f"   {i}. Chunk ID: {completion.chunk_id}, Status: {completion.status}, Completed: {completion.completed_at}")
            if len(completions) > 10:
                print(f"   ... and {len(completions) - 10} more")
            print()
        
        # Ask for confirmation
        confirmation = input(f"⚠️  Reset {len(completions)} completion records for '{stage_name}'? (yes/no): ")
        
        if confirmation.lower() != 'yes':
            print("❌ Reset cancelled")
            return
        
        # Delete completion records
        print(f"🗑️  Deleting {len(completions)} completion records...")
        for completion in completions:
            session.delete(completion)
        
        session.commit()
        
        print(f"✅ Successfully reset {len(completions)} completion records for stage '{stage_name}'")
        print(f"   Stage '{stage_name}' will now reprocess all chunks in its waiting area")
        
    except Exception as e:
        print(f"❌ Error resetting stage completion: {e}")
        session.rollback()
        raise
    finally:
        session.close()


def show_stage_status():
    """Show completion status for all stages"""
    session = get_session()
    
    try:
        print("📊 Stage Completion Status")
        print("=" * 60)
        
        stages = ['conversation_boundary', 'parser', 'fact_extraction', 'metadata', 'merge', 'taxonomy']
        
        for stage in stages:
            completed_count = session.query(StageCompletion).filter(
                StageCompletion.stage_name == stage,
                StageCompletion.status == 'completed'
            ).count()
            
            failed_count = session.query(StageCompletion).filter(
                StageCompletion.stage_name == stage,
                StageCompletion.status == 'failed'
            ).count()
            
            # Count waiting area (StageResult)
            waiting_count = session.query(StageResult).filter(
                StageResult.stage_name == stage
            ).count()
            
            print(f"\n{stage}:")
            print(f"   Completed: {completed_count}")
            print(f"   Failed: {failed_count}")
            print(f"   In waiting area: {waiting_count}")
        
        print("\n" + "=" * 60)
        
    finally:
        session.close()


if __name__ == "__main__":
    import sys
    
    print("🔄 Reset Stage Completion")
    print("=" * 60)
    print()
    
    # Initialize test setup
    try:
        import app.assistant.tests.test_setup
    except ImportError as e:
        print(f"⚠️  Could not import test setup: {e}")
    
    # Show current status
    show_stage_status()
    
    print()
    print("Which stage do you want to reset?")
    print("0. conversation_boundary (Stage 0)")
    print("1. parser (Stage 1)")
    print("2. fact_extraction (Stage 2)")
    print("3. metadata (Stage 3)")
    print("4. merge (Stage 4)")
    print("5. taxonomy (Stage 5)")
    print("6. Exit")
    print()
    
    choice = input("Enter choice (0-6): ").strip()
    
    stage_map = {
        "0": "conversation_boundary",
        "1": "parser",
        "2": "fact_extraction",
        "3": "metadata",
        "4": "merge",
        "5": "taxonomy"
    }
    
    if choice == "6":
        print("👋 Exiting")
        sys.exit(0)
    
    if choice not in stage_map:
        print("❌ Invalid choice")
        sys.exit(1)
    
    stage_name = stage_map[choice]
    print(f"\n📋 Resetting stage: {stage_name}")
    print()
    
    reset_stage_completion(stage_name)

