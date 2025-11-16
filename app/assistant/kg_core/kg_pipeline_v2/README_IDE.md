# KG Pipeline V2 - IDE Usage Guide

This guide shows how to use the KG Pipeline V2 directly from your IDE with **continuous processing**.

## 🚀 Quick Start

### Step 1: Setup Database
**File:** `create_pipeline_tables.py`
- **Run directly from IDE** - Right-click → Run
- **What it does:** Creates all pipeline database tables
- **When to use:** First time setup only

### Step 2: Check Database Status  
**File:** `check_database_status.py`
- **Run directly from IDE** - Right-click → Run
- **What it does:** Verifies database tables and shows status
- **When to use:** After setup or to troubleshoot

### Step 3: Start Pipeline Stages (Continuous Processing)
Run each stage in a **separate terminal/IDE window**. Each stage runs continuously until stopped with Ctrl+C.

**Stage 0 - Conversation Boundary:**
- **File:** `stages/conversation_boundary.py`
- **What it does:** Reads from `processed_entity_log` and chunks conversations
- **Waits for:** New log entries (checks every 60 seconds)

**Stage 1 - Parser:**
- **File:** `stages/parser.py`
- **What it does:** Parses chunks into atomic sentences
- **Waits for:** Stage 0 output (checks every 60 seconds)

**Stage 2 - Fact Extraction:**
- **File:** `stages/fact_extraction.py`
- **What it does:** Extracts facts from sentences
- **Waits for:** Stage 1 output (checks every 60 seconds)

**Stage 3 - Metadata:**
- **File:** `stages/metadata.py`
- **What it does:** Enriches nodes with metadata
- **Waits for:** Stage 2 output (checks every 60 seconds)

**Stage 4 - Merge:**
- **File:** `stages/merge.py`
- **What it does:** Merges nodes/edges into KG database
- **Waits for:** Stage 3 output (checks every 60 seconds)

### Step 4: Monitor Progress
**File:** `check_results.py`
- **Run directly from IDE** - Right-click → Run
- **What it does:** Shows data in pipeline tables
- **When to use:** To monitor what's in the waiting areas

## 📁 File Overview

### Database Setup
- **`create_pipeline_tables.py`** - Create database tables
- **`recreate_tables.py`** - Drop and recreate tables (for schema changes)
- **`check_database_status.py`** - Check database health

### Monitoring
- **`check_results.py`** - Inspect pipeline table contents
- **`inspect_fact_extraction_data.py`** - Debug fact extraction results

### Orchestrator
- **`start_all_stages.py`** - Start all 5 stages at once (easiest way to run)

### Stage Processors (Continuous Processing)
- **`stages/conversation_boundary.py`** - Stage 0: Chunk conversations from logs
- **`stages/parser.py`** - Stage 1: Parse into atomic sentences
- **`stages/fact_extraction.py`** - Stage 2: Extract facts
- **`stages/metadata.py`** - Stage 3: Enrich with metadata
- **`stages/merge.py`** - Stage 4: Merge into KG database

### Core Infrastructure
- **`database_schema.py`** - Database schema (PipelineChunk, StageResult, etc.)
- **`pipeline_coordinator.py`** - Coordinator for managing stages
- **`utils/thread_safe_waiting.py`** - Thread-safe data availability checking

### Documentation
- **`README.md`** - General documentation
- **`README_IDE.md`** - This file
- **`FILE_INVENTORY.md`** - Complete file inventory
- **`ARCHIVE_SUMMARY.md`** - Archive cleanup summary

### Archived Files
- **`_archive_batch_model/`** - Old batch processing model files (obsolete)

## 🔄 Complete Workflow

### First Time Setup
1. **Run:** `create_pipeline_tables.py`
   - Creates all pipeline database tables
   - Only needs to be done once

2. **Run:** `check_database_status.py`
   - Verifies tables were created successfully
   - Shows table counts

### Running the Pipeline (Continuous Mode)

**Option A: Use the Orchestrator (Easiest)**

**File:** `start_all_stages.py`
- **Run directly from IDE** - Right-click → Run
- **What it does:** Starts all 5 stages in background processes
- **Stop:** Press Ctrl+C to stop all stages at once

```bash
python app/assistant/kg_core/kg_pipeline_v2/start_all_stages.py
```

**Option B: Run Each Stage Separately**

Open 5 separate terminals/IDE windows and run:

1. **Terminal 1:** `python app/assistant/kg_core/kg_pipeline_v2/stages/conversation_boundary.py`
   - Reads from `processed_entity_log`
   - Chunks conversations
   - Runs until you stop it (Ctrl+C)

2. **Terminal 2:** `python app/assistant/kg_core/kg_pipeline_v2/stages/parser.py`
   - Waits for Stage 0 output
   - Parses into atomic sentences
   - Runs until you stop it (Ctrl+C)

3. **Terminal 3:** `python app/assistant/kg_core/kg_pipeline_v2/stages/fact_extraction.py`
   - Waits for Stage 1 output
   - Extracts facts
   - Runs until you stop it (Ctrl+C)

4. **Terminal 4:** `python app/assistant/kg_core/kg_pipeline_v2/stages/metadata.py`
   - Waits for Stage 2 output
   - Enriches with metadata
   - Runs until you stop it (Ctrl+C)

5. **Terminal 5:** `python app/assistant/kg_core/kg_pipeline_v2/stages/merge.py`
   - Waits for Stage 3 output
   - Merges into KG database
   - Runs until you stop it (Ctrl+C)

### Monitoring Progress
- **Run:** `check_results.py` (see what's in the waiting areas)
- **Run:** `check_database_status.py` (check database health)
- **Watch:** Terminal output from each stage shows real-time progress

## 🎯 Stage Dependencies

The pipeline has a **fixed sequential order**:

```
Stage 0 → Stage 1 → Stage 2 → Stage 3 → Stage 4
   ↓         ↓         ↓         ↓         ↓
  Logs    Chunks   Sentences   Facts   Metadata → KG Database
```

- **Stage 0 (conversation_boundary):** Reads from `processed_entity_log`
- **Stage 1 (parser):** Reads from Stage 0 results
- **Stage 2 (fact_extraction):** Reads from Stage 1 results
- **Stage 3 (metadata):** Reads from Stage 2 results
- **Stage 4 (merge):** Reads from Stage 3 results → Writes to KG database

## 💡 Tips

1. **Always run database setup first** - `create_pipeline_tables.py`
2. **Check database status** - `check_database_status.py` if things don't work
3. **Start all stages at once** - They'll wait for each other automatically
4. **Monitor terminal output** - Each stage shows real-time progress
5. **Check waiting areas** - `check_results.py` to see what's queued

## 🚨 Troubleshooting

### Database Issues
- **Missing tables:** Run `create_pipeline_tables.py`
- **Schema changes:** Run `recreate_tables.py` to drop and recreate
- **Connection errors:** Run `check_database_status.py`

### Stage Issues
- **Stage not processing:** Check if previous stage is running
- **No data in waiting area:** Check `check_results.py`
- **Stage stuck waiting:** Verify previous stage completed successfully
- **Errors in terminal:** Read the error message - stages fail hard with clear errors

### Data Flow Issues
- **Stage 0 not finding data:** Check if `processed_entity_log` has unprocessed entries
- **Stage N waiting forever:** Check if Stage N-1 is running and producing output
- **Duplicate processing:** Check `StageCompletion` table for tracking issues

## 🎉 Benefits of Continuous Processing

- **Automatic data flow** - Stages wait for upstream data automatically
- **Parallel processing** - All stages run simultaneously
- **No manual orchestration** - Just start the stages and let them run
- **Real-time progress** - See what's happening in each terminal
- **Graceful shutdown** - Ctrl+C stops any stage cleanly
- **Resume-friendly** - Stages track what's been processed via `StageCompletion`
- **Thread safe** - Multiple stages can run simultaneously without conflicts
