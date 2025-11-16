#!/usr/bin/env python3
"""
Initialize the maintenance logs table for the description creator
"""

import app.assistant.tests.test_setup
from app.models.maintenance_logs import initialize_maintenance_logs_db

def main():
    print("🔧 Initializing maintenance logs table...")
    
    try:
        initialize_maintenance_logs_db()
        print("✅ Maintenance logs table initialized successfully!")
        print("🎯 You can now run the description creator.")
        
    except Exception as e:
        print(f"❌ Error initializing maintenance logs: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())
