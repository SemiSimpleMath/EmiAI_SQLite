#!/usr/bin/env python3
"""
Initialize centralized maintenance tracking system
"""

import app.assistant.tests.test_setup
from app.models.maintenance_logs import (
    initialize_maintenance_logs_db,
    initialize_with_yesterday_runs,
    get_maintenance_run_history
)

def main():
    print("=== Initializing Centralized Maintenance Tracking System ===\n")
    
    # Step 1: Create the maintenance logs table
    print("1. Creating maintenance logs table...")
    initialize_maintenance_logs_db()
    
    # Step 2: Initialize with yesterday's timestamps
    print("\n2. Initializing with yesterday's timestamps...")
    initialize_with_yesterday_runs()
    
    # Step 3: Show the current state
    print("\n3. Current maintenance run history:")
    history = get_maintenance_run_history()
    if history:
        for run in history:
            print(f"  {run['task_name']}: {run['last_run_time']} - {run['nodes_processed']} processed, {run['nodes_updated']} updated")
    else:
        print("  No maintenance runs found")
    
    print("\n✅ Maintenance tracking system initialized successfully!")
    print("\nYou can now run:")
    print("  python app/assistant/kg_maintenance/description_creator/run_description_creation.py --mode today_only")

if __name__ == "__main__":
    main()
