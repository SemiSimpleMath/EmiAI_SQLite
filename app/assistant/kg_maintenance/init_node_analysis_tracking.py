#!/usr/bin/env python3
"""
Initialize Node Analysis Tracking System
Creates the tracking database and shows current analysis coverage
"""

import app.assistant.tests.test_setup
from app.models.node_analysis_tracking import (
    initialize_node_analysis_tracking_db,
    get_analysis_statistics,
    cleanup_old_analysis_records
)
from app.models.base import get_session


def main():
    print("=== Initializing Node Analysis Tracking System ===\n")
    
    # Step 1: Create the tracking table
    print("1. Creating node analysis tracking table...")
    initialize_node_analysis_tracking_db()
    print("✅ Tracking table created successfully")
    
    # Step 2: Show current statistics
    print("\n2. Current analysis coverage:")
    session = get_session()
    try:
        stats = get_analysis_statistics(session)
        print(f"   Total nodes in database: {stats['total_nodes']}")
        print(f"   Nodes already analyzed: {stats['analyzed_nodes']}")
        print(f"   Nodes needing analysis: {stats['unanalyzed_nodes']}")
        print(f"   Coverage percentage: {stats['coverage_percentage']:.1f}%")
        print(f"   Suspect nodes found: {stats['suspect_nodes']}")
        
        if stats['priority_breakdown']:
            print(f"\n   Priority breakdown:")
            for priority, count in stats['priority_breakdown'].items():
                if count > 0:
                    print(f"     {priority.upper()}: {count} nodes")
        
        print(f"   Recent analysis (24h): {stats['recent_analysis_24h']} nodes")
        
    finally:
        session.close()
    
    # Step 3: Clean up old records (optional)
    print("\n3. Cleaning up old analysis records...")
    try:
        deleted_count = cleanup_old_analysis_records(session, days_to_keep=30)
        print(f"   Deleted {deleted_count} old analysis records (keeping last 30 days)")
    except Exception as e:
        print(f"   Warning: Could not clean up old records: {e}")
    
    print("\n✅ Node analysis tracking system initialized successfully!")
    print("\nYou can now run:")
    print("  python app/assistant/kg_maintenance/node_cleanup_pipeline.py")
    print("\nThe pipeline will automatically:")
    print("  - Skip already analyzed nodes")
    print("  - Track analysis results and timing")
    print("  - Show progress and coverage statistics")


if __name__ == "__main__":
    main()
