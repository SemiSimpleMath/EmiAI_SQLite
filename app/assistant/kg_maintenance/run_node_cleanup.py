#!/usr/bin/env python3
"""
Command-line interface for Node Cleanup Pipeline
Provides various options for running the pipeline with different modes
"""

import argparse
import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

import app.assistant.tests.test_setup
from app.assistant.kg_maintenance.node_cleanup_pipeline import (
    run_node_cleanup_pipeline,
    print_suspect_summary,
    save_suspect_report
)
from app.models.node_analysis_tracking import (
    initialize_node_analysis_tracking_db,
    get_analysis_statistics,
    cleanup_old_analysis_records
)
from app.models.base import get_session


def show_coverage_stats():
    """Show current analysis coverage statistics"""
    session = get_session()
    try:
        initialize_node_analysis_tracking_db()
        stats = get_analysis_statistics(session)
        
        print("📊 NODE ANALYSIS COVERAGE STATISTICS")
        print("=" * 50)
        print(f"Total nodes in database: {stats['total_nodes']}")
        print(f"Nodes already analyzed: {stats['analyzed_nodes']}")
        print(f"Nodes needing analysis: {stats['unanalyzed_nodes']}")
        print(f"Coverage percentage: {stats['coverage_percentage']:.1f}%")
        print(f"Suspect nodes found: {stats['suspect_nodes']}")
        
        if stats['priority_breakdown']:
            print(f"\nPriority breakdown:")
            for priority, count in stats['priority_breakdown'].items():
                if count > 0:
                    print(f"  {priority.upper()}: {count} nodes")
        
        print(f"Recent analysis (24h): {stats['recent_analysis_24h']} nodes")
        
    finally:
        session.close()


def run_pipeline(mode, max_nodes=None, output_file=None):
    """Run the pipeline with specified mode"""
    print(f"🚀 Starting Node Cleanup Pipeline...")
    print(f"Mode: {mode}")
    if max_nodes:
        print(f"Max nodes to process: {max_nodes}")
    print("=" * 60)
    
    try:
        if mode == "unanalyzed":
            result = run_node_cleanup_pipeline(skip_analyzed=True, force_reanalyze=False, max_nodes=max_nodes)
        elif mode == "force_reanalyze":
            result = run_node_cleanup_pipeline(skip_analyzed=False, force_reanalyze=True, max_nodes=max_nodes)
        elif mode == "legacy":
            result = run_node_cleanup_pipeline(skip_analyzed=False, force_reanalyze=False, max_nodes=max_nodes)
        else:
            print(f"❌ Unknown mode: {mode}")
            return
        
        # Print summary
        print_suspect_summary(result['suspect_nodes'])
        
        # Save report
        if output_file:
            filename = save_suspect_report(result['suspect_nodes'], output_file)
        else:
            filename = save_suspect_report(result['suspect_nodes'])
        
        print(f"\n📄 Detailed report saved to: {filename}")
        
        # Print completion summary
        print(f"\n✅ Pipeline completed!")
        print(f"  Processed: {result['processed']} nodes")
        print(f"  Suspect: {result['suspect_count']} nodes")
        print(f"  Errors: {result['errors']} nodes")
        print(f"  Skipped: {result.get('skipped', 0)} nodes")
        
        if 'coverage' in result:
            coverage = result['coverage']
            print(f"  Coverage: {coverage['analyzed_nodes']}/{coverage['total_nodes']} nodes ({coverage['coverage_percentage']:.1f}%)")
        
    except Exception as e:
        print(f"❌ Pipeline execution failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def cleanup_old_records(days_to_keep=30):
    """Clean up old analysis records"""
    print(f"🧹 Cleaning up analysis records older than {days_to_keep} days...")
    
    session = get_session()
    try:
        deleted_count = cleanup_old_analysis_records(session, days_to_keep=days_to_keep)
        print(f"✅ Deleted {deleted_count} old analysis records")
    except Exception as e:
        print(f"❌ Error cleaning up old records: {e}")
        sys.exit(1)
    finally:
        session.close()


def main():
    parser = argparse.ArgumentParser(
        description="Node Cleanup Pipeline - Identify suspect nodes for potential deletion",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Show current coverage statistics
  python run_node_cleanup.py --stats
  
  # Process only unanalyzed nodes (default)
  python run_node_cleanup.py
  
  # Process only unanalyzed nodes with limit
  python run_node_cleanup.py --max-nodes 100
  
  # Force reanalyze all nodes
  python run_node_cleanup.py --mode force_reanalyze
  
  # Legacy mode (process all nodes)
  python run_node_cleanup.py --mode legacy
  
  # Clean up old records
  python run_node_cleanup.py --cleanup-old --days 30
  
  # Save report to specific file
  python run_node_cleanup.py --output my_report.json
        """
    )
    
    parser.add_argument(
        '--mode',
        choices=['unanalyzed', 'force_reanalyze', 'legacy'],
        default='unanalyzed',
        help='Processing mode (default: unanalyzed)'
    )
    
    parser.add_argument(
        '--max-nodes',
        type=int,
        help='Maximum number of nodes to process'
    )
    
    parser.add_argument(
        '--output',
        help='Output file for the suspect nodes report'
    )
    
    parser.add_argument(
        '--stats',
        action='store_true',
        help='Show current analysis coverage statistics'
    )
    
    parser.add_argument(
        '--cleanup-old',
        action='store_true',
        help='Clean up old analysis records'
    )
    
    parser.add_argument(
        '--days',
        type=int,
        default=30,
        help='Days of analysis history to keep (default: 30)'
    )
    
    args = parser.parse_args()
    
    # Initialize the tracking system
    try:
        initialize_node_analysis_tracking_db()
    except Exception as e:
        print(f"❌ Failed to initialize tracking system: {e}")
        sys.exit(1)
    
    # Handle different commands
    if args.stats:
        show_coverage_stats()
    elif args.cleanup_old:
        cleanup_old_records(args.days)
    else:
        # Run the pipeline
        run_pipeline(args.mode, args.max_nodes, args.output)


if __name__ == "__main__":
    main()
