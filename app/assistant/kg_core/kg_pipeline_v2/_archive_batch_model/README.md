# Archived Files - Batch Processing Model

**Date Archived:** 2025-10-18  
**Reason:** Pipeline evolved from batch processing to continuous processing model

---

## 🗄️ What's in this archive?

These files were part of the original **Batch Processing Model** of the KG Pipeline V2. They have been superseded by the **Continuous Processing Model** where each stage runs independently and continuously.

---

## 📁 Archived Files

### Orchestrator Scripts
- **`__main__.py`** - Interactive menu-driven orchestrator
  - Provided a menu to setup DB, load data, run stages, check status
  - Required manual intervention at each step
  - **Replaced by:** Direct execution of stage files

- **`run_pipeline.py`** - Simple wrapper to call `__main__.py`
  - Just called `__main__.main()`
  - **Replaced by:** Direct execution of stage files

- **`run_stage.py`** - CLI-based stage runner with argparse
  - Ran individual stages via command-line arguments
  - **Replaced by:** Direct execution of stage files with `if __name__ == "__main__"`

- **`run_stage_with_data_flow.py`** - Stage runner with data flow logic
  - Attempted to pass data between stages as parameters
  - **Replaced by:** Stages reading from database waiting areas

### Data Loading Scripts
- **`load_data.py`** - CLI-based data loader from `processed_entity_log`
  - Loaded conversation data into pipeline tables
  - **Replaced by:** Stage 0 (conversation_boundary) reads directly from `processed_entity_log`

- **`load_data_simple.py`** - Simplified data loader
  - Simpler version of `load_data.py`
  - **Replaced by:** Stage 0 (conversation_boundary) reads directly from `processed_entity_log`

### Status Checkers
- **`check_pipeline_status.py`** - Checks batch/stage status via coordinator
  - Queried `PipelineBatch` and `StageCompletion` tables
  - **Replaced by:** `check_database_status.py` and `check_results.py`

- **`check_status_simple.py`** - Simplified status checker
  - Simpler version of `check_pipeline_status.py`
  - **Replaced by:** `check_database_status.py`

### Schema Files
- **`database_schema_refactored.py`** - Experimental refactored schema
  - Was an experiment to simplify the schema
  - **Replaced by:** `database_schema.py` (active version)

### Module Files
- **`stage_processors.py`** - Re-exports stage processors from `stages/`
  - Just a pass-through file
  - **Replaced by:** Direct imports from `stages/` directory

---

## 🔄 What Changed?

### Old Model (Batch Processing)
```bash
# Step 1: Setup database
python -m app.assistant.kg_core.kg_pipeline_v2
# Choose option 1

# Step 2: Load data
python -m app.assistant.kg_core.kg_pipeline_v2
# Choose option 3

# Step 3: Run stage 1
python run_stage.py --stage parser --batch-size 100

# Step 4: Run stage 2
python run_stage.py --stage fact_extraction --batch-size 100

# ... and so on
```

**Problems:**
- Manual intervention required at each step
- Stages processed all data and exited
- No automatic waiting for upstream data
- Complex orchestration logic

### New Model (Continuous Processing)
```bash
# Just start all stages in separate terminals
python app/assistant/kg_core/kg_pipeline_v2/stages/conversation_boundary.py
python app/assistant/kg_core/kg_pipeline_v2/stages/parser.py
python app/assistant/kg_core/kg_pipeline_v2/stages/fact_extraction.py
python app/assistant/kg_core/kg_pipeline_v2/stages/metadata.py
python app/assistant/kg_core/kg_pipeline_v2/stages/merge.py
```

**Benefits:**
- No manual intervention - stages run continuously
- Automatic waiting for upstream data (60-second intervals)
- Each stage is self-contained
- Simple, parallel execution

---

## 🚮 Can I delete these files?

**Yes, eventually.** These files are kept for reference in case we need to:
1. Understand how the old batch model worked
2. Port any useful logic to the new model
3. Debug issues related to the migration

After a few weeks of successful continuous processing, these can be safely deleted.

---

## 📚 See Also

- `../FILE_INVENTORY.md` - Complete file inventory and recommendations
- `../README_IDE.md` - Current instructions for running the pipeline
- `../stages/` - Active stage processors (continuous model)

