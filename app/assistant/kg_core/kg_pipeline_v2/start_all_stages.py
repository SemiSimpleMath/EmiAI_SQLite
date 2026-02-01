#!/usr/bin/env python3
"""
Simple Orchestrator - Start All Pipeline Stages

This script starts all 5 pipeline stages in separate processes.
Each stage runs continuously until you stop this script (Ctrl+C).

Usage:
    python app/assistant/kg_core/kg_pipeline_v2/start_all_stages.py
"""

import subprocess
import sys
import time
import os
from pathlib import Path

# Get the project root directory
project_root = Path(__file__).parent.parent.parent.parent.parent
os.chdir(project_root)

print("=" * 70)
print("KG Pipeline V2 - Starting All Stages")
print("=" * 70)
print()
print("This will start 5 continuous processing stages:")
print("   Stage 0: Conversation Boundary (reads from processed_entity_log)")
print("   Stage 1: Parser (waits for Stage 0)")
print("   Stage 2: Fact Extraction (waits for Stage 1)")
print("   Stage 3: Metadata (waits for Stage 2)")
print("   Stage 4: Merge (waits for Stage 3)")
print()
print("Press Ctrl+C to stop all stages")
print("=" * 70)
print()

# Define stage scripts
stages = [
    ("Stage 0: Conversation Boundary", "app/assistant/kg_core/kg_pipeline_v2/stages/conversation_boundary.py"),
    ("Stage 1: Parser", "app/assistant/kg_core/kg_pipeline_v2/stages/parser.py"),
    ("Stage 2: Fact Extraction", "app/assistant/kg_core/kg_pipeline_v2/stages/fact_extraction.py"),
    ("Stage 3: Metadata", "app/assistant/kg_core/kg_pipeline_v2/stages/metadata.py"),
    ("Stage 4: Merge", "app/assistant/kg_core/kg_pipeline_v2/stages/merge.py"),
]

# Store process handles
processes = []

try:
    # Start each stage in a separate process
    for stage_name, stage_script in stages:
        print(f"[START] {stage_name} ...")
        
        # Start the process - don't pipe output so we can see errors
        # Note: All output will be mixed in the terminal
        process = subprocess.Popen(
            [sys.executable, stage_script],
            # stdout and stderr go directly to terminal (not captured)
        )
        
        processes.append((stage_name, process))
        print(f"[OK] {stage_name} started (PID: {process.pid})")
        time.sleep(5)  # Longer delay to let each stage initialize before starting next
    
    print()
    print("=" * 70)
    print("[OK] All stages started successfully!")
    print("=" * 70)
    print()
    print("Stage Status:")
    for stage_name, process in processes:
        status = "Running" if process.poll() is None else "Stopped"
        print(f"   {stage_name}: {status} (PID: {process.pid})")
    print()
    print("Tips:")
    print("   - Each stage runs in the background")
    print("   - Check logs in app/assistant/kg_core/kg_pipeline_v2/stages/logs/")
    print("   - Monitor progress: python app/assistant/kg_core/kg_pipeline_v2/check_results.py")
    print("   - Press Ctrl+C to stop all stages")
    print()
    print("Waiting... (Press Ctrl+C to stop)")
    print("=" * 70)
    
    # Keep the script running and monitor processes
    while True:
        time.sleep(5)
        
        # Check if any process has died
        for stage_name, process in processes:
            if process.poll() is not None:
                # Process has terminated
                returncode = process.returncode
                if returncode != 0:
                    print(f"\n[ERR] {stage_name} stopped unexpectedly (exit code: {returncode})")
                    print(f"   Error output should be visible above in the terminal")

except KeyboardInterrupt:
    print("\n")
    print("=" * 70)
    print("Stopping all stages...")
    print("=" * 70)
    
    # Terminate all processes
    for stage_name, process in processes:
        if process.poll() is None:  # Process is still running
            print(f"[STOP] {stage_name} (PID: {process.pid}) ...")
            process.terminate()
            
            # Wait up to 5 seconds for graceful shutdown
            try:
                process.wait(timeout=5)
                print(f"[OK] {stage_name} stopped gracefully")
            except subprocess.TimeoutExpired:
                # Force kill if it doesn't stop
                print(f"[WARN] Force killing {stage_name} ...")
                process.kill()
                process.wait()
                print(f"[OK] {stage_name} force killed")
        else:
            print(f"[INFO] {stage_name} already stopped")
    
    print()
    print("[OK] All stages stopped")
    print("=" * 70)

except Exception as e:
    print(f"\n[ERR] Error: {e}")
    import traceback
    traceback.print_exc()
    
    # Clean up processes
    print("\n[STOP] Stopping all stages due to error...")
    for stage_name, process in processes:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
    
    sys.exit(1)

finally:
    # Ensure all processes are cleaned up
    for stage_name, process in processes:
        if process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=2)
            except Exception:
                try:
                    process.kill()
                except Exception as e:
                    print(f"[STOP] Failed to kill process for stage={stage_name}: {e}")

