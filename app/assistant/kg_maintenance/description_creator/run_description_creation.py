#!/usr/bin/env python3
"""
Command-line interface for running description creation
"""

import argparse
import sys
import app.assistant.tests.test_setup
from app.assistant.kg_maintenance.description_creator.description_creator import (
    run_incremental_description_pass,
    run_full_description_pass,
    run_today_only_description_pass,
    get_description_run_history
)

def main():
    parser = argparse.ArgumentParser(description='Run knowledge graph description creation')
    parser.add_argument(
        '--mode', 
        choices=['incremental', 'full', 'today_only'], 
        default='incremental',
        help='Run mode: incremental (default), full, or today_only (temporary fix)'
    )
    parser.add_argument(
        '--history', 
        action='store_true',
        help='Show run history and exit'
    )
    parser.add_argument(
        '--limit', 
        type=int, 
        default=10,
        help='Number of history entries to show (default: 10)'
    )
    
    args = parser.parse_args()
    
    if args.history:
        print("=== Description Creation Run History ===\n")
        history = get_description_run_history(limit=args.limit)
        if history:
            for run in history:
                print(f"  {run['last_run_time']}: {run['nodes_processed']} processed, {run['nodes_updated']} updated")
                print(f"    Duration: {run['run_duration_seconds']:.2f}s")
        else:
            print("  No previous runs found")
        return
    
    print(f"=== Running Description Creation ({args.mode} mode) ===\n")
    
    try:
        if args.mode == 'incremental':
            result = run_incremental_description_pass()
        elif args.mode == 'full':
            result = run_full_description_pass()
        elif args.mode == 'today_only':
            result = run_today_only_description_pass()
        else:
            raise ValueError(f"Unknown mode: {args.mode}")
        
        print(f"\n✅ Description creation completed successfully!")
        print(f"   Requested mode: {args.mode}")
        print(f"   Actual mode: {result['mode']}")
        print(f"   Nodes processed: {result['processed']}")
        print(f"   Nodes updated: {result['updated']}")
        print(f"   Errors: {result['errors']}")
        print(f"   Duration: {result['run_duration_seconds']:.2f} seconds")
        
    except Exception as e:
        print(f"\n❌ Error running description creation: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
