# KG Pipeline V2 - File Inventory

**Date:** 2025-10-18  
**Purpose:** Identify outdated files and recommend keeping or archiving

---

## ✅ KEEP - Core Active Files

### Database & Schema
| File | Purpose | Status |
|------|---------|--------|
| `database_schema.py` | **ACTIVE** - Current database schema with `PipelineChunk`, `StageResult`, `StageCompletion` | ✅ KEEP |
| `create_pipeline_tables.py` | **ACTIVE** - Creates all pipeline tables, can drop/recreate | ✅ KEEP |
| `pipeline_coordinator.py` | **ACTIVE** - Core coordinator for managing stages, batches, chunks | ✅ KEEP |

### Stage Processors (All Active - Continuous Processing)
| File | Purpose | Status |
|------|---------|--------|
| `stages/conversation_boundary.py` | **ACTIVE** - Stage 0: Reads from `processed_entity_log`, chunks conversations | ✅ KEEP |
| `stages/parser.py` | **ACTIVE** - Stage 1: Parses chunks into atomic sentences | ✅ KEEP |
| `stages/fact_extraction.py` | **ACTIVE** - Stage 2: Extracts facts from sentences | ✅ KEEP |
| `stages/metadata.py` | **ACTIVE** - Stage 3: Enriches nodes with metadata | ✅ KEEP |
| `stages/merge.py` | **ACTIVE** - Stage 4: Merges nodes/edges into KG database | ✅ KEEP |
| `stages/taxonomy.py` | **SEMI-ACTIVE** - Stage 5: Taxonomy classification (needs continuous processing update) | ⚠️ KEEP (needs update) |
| `stages/__init__.py` | Exports all stage processors | ✅ KEEP |

### Utilities
| File | Purpose | Status |
|------|---------|--------|
| `utils/thread_safe_waiting.py` | Thread-safe data availability checking | ✅ KEEP |
| `utils/__init__.py` | Exports utility functions | ✅ KEEP |

### Status & Monitoring
| File | Purpose | Status |
|------|---------|--------|
| `check_database_status.py` | **ACTIVE** - Checks DB connection, tables, data counts | ✅ KEEP |
| `check_results.py` | **ACTIVE** - Inspects pipeline table contents | ✅ KEEP |
| `recreate_tables.py` | **ACTIVE** - Drops and recreates tables (useful for schema changes) | ✅ KEEP |

### Documentation
| File | Purpose | Status |
|------|---------|--------|
| `README_IDE.md` | **ACTIVE** - IDE-friendly instructions for running pipeline | ✅ KEEP |
| `README.md` | General pipeline documentation | ✅ KEEP |

### Module Files
| File | Purpose | Status |
|------|---------|--------|
| `__init__.py` | Module initialization, exports | ✅ KEEP |

---

## ⚠️ OUTDATED - Consider Archiving

### Orchestrator Scripts (Pre-Continuous Processing)
| File | Purpose | Why Outdated | Recommendation |
|------|---------|--------------|----------------|
| `__main__.py` | Interactive menu-driven orchestrator | Built for old batch processing model, not continuous | 🗄️ ARCHIVE - Replaced by direct stage execution |
| `run_pipeline.py` | Simple wrapper to call `__main__.py` | Just calls outdated `__main__.py` | 🗄️ ARCHIVE |
| `run_stage.py` | CLI-based stage runner with argparse | Pre-dates continuous processing, uses old batch model | 🗄️ ARCHIVE |
| `run_stage_with_data_flow.py` | Stage runner with data flow logic | Pre-dates continuous processing, stages now self-contained | 🗄️ ARCHIVE |

### Data Loading Scripts (Pre-Continuous Processing)
| File | Purpose | Why Outdated | Recommendation |
|------|---------|--------------|----------------|
| `load_data.py` | CLI-based data loader from `processed_entity_log` | Not needed - Stage 0 reads directly from `processed_entity_log` | 🗄️ ARCHIVE |
| `load_data_simple.py` | Simplified data loader | Not needed - Stage 0 reads directly from `processed_entity_log` | 🗄️ ARCHIVE |

### Status Checkers (Redundant)
| File | Purpose | Why Outdated | Recommendation |
|------|---------|--------------|----------------|
| `check_pipeline_status.py` | Checks batch/stage status via coordinator | Redundant with `check_database_status.py` and `check_results.py` | 🗄️ ARCHIVE |
| `check_status_simple.py` | Simplified status checker | Redundant with `check_database_status.py` | 🗄️ ARCHIVE |

### Schema Files (Superseded)
| File | Purpose | Why Outdated | Recommendation |
|------|---------|--------------|----------------|
| `database_schema_refactored.py` | Experimental refactored schema | Was an experiment, `database_schema.py` is the active version | 🗄️ ARCHIVE |

### Module Files (Redundant)
| File | Purpose | Why Outdated | Recommendation |
|------|---------|--------------|----------------|
| `stage_processors.py` | Re-exports stage processors from `stages/` | Just a pass-through, can import from `stages/` directly | 🗄️ ARCHIVE (low priority) |

### Debug/Inspection Scripts
| File | Purpose | Why Outdated | Recommendation |
|------|---------|--------------|----------------|
| `inspect_fact_extraction_data.py` | Inspects fact extraction results | Useful for debugging, but `check_results.py` covers this | 🔍 KEEP (for now) - Useful for debugging |

---

## 📊 Summary

### Keep: 19 files
- 1 schema file
- 2 coordinator/utility files
- 6 stage processors
- 3 status/monitoring scripts
- 3 utility files
- 2 documentation files
- 2 module init files

### Archive: 9 files
- 4 orchestrator scripts (pre-continuous processing)
- 2 data loading scripts (not needed)
- 2 status checkers (redundant)
- 1 experimental schema file

### Needs Update: 1 file
- `stages/taxonomy.py` - Needs continuous processing implementation

---

## 🎯 Recommended Actions

### Immediate
1. **Update `stages/taxonomy.py`** to implement continuous processing like other stages
2. **Archive outdated orchestrator scripts** to `_archive/kg_pipeline_v2_batch_model/`
3. **Update `README_IDE.md`** to remove references to archived scripts

### Future
1. Consider creating a **simple orchestrator** that just starts all 5 stages in separate processes
2. Add **monitoring dashboard** to track stage progress in real-time
3. Add **graceful shutdown** mechanism to stop all stages at once

---

## 📝 Notes

### Why These Files Are Outdated

The pipeline has evolved from:
- **Batch Processing Model** → **Continuous Processing Model**
- **Orchestrator-driven** → **Self-contained stages**
- **Data passed as parameters** → **Data read from database waiting areas**
- **Manual stage execution** → **Automatic wait-and-process loops**

The old orchestrator scripts (`__main__.py`, `run_stage.py`, etc.) were designed for the batch model where:
- You manually loaded data into the pipeline
- You manually ran each stage
- Stages processed all available data and exited

The new continuous model:
- Stage 0 automatically reads from `processed_entity_log`
- Each stage runs indefinitely, waiting for upstream data
- Stages process one chunk at a time and loop
- No manual orchestration needed - just start all stages

### Current Workflow (Continuous Model)

```bash
# Terminal 1 - Stage 0
python app/assistant/kg_core/kg_pipeline_v2/stages/conversation_boundary.py

# Terminal 2 - Stage 1
python app/assistant/kg_core/kg_pipeline_v2/stages/parser.py

# Terminal 3 - Stage 2
python app/assistant/kg_core/kg_pipeline_v2/stages/fact_extraction.py

# Terminal 4 - Stage 3
python app/assistant/kg_core/kg_pipeline_v2/stages/metadata.py

# Terminal 5 - Stage 4
python app/assistant/kg_core/kg_pipeline_v2/stages/merge.py
```

Each stage runs continuously until stopped with Ctrl+C.

