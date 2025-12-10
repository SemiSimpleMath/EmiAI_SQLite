# Quick Start Guide - Migration Steps 2-5

You've successfully exported your data! Now let's import it into SQLite + ChromaDB.

## Prerequisites

✅ Phase 1 & 2 exported (DONE!)
✅ Python virtual environment active
✅ Basic dependencies installed

## Step-by-Step Instructions

### Step 1: Install ChromaDB (2 minutes)

```bash
pip install chromadb
```

### Step 2: Create SQLite Database (1 minute)

```bash
python migration_scripts\2_setup_sqlite.py
```

**What this does:**
- Creates `emi.db` SQLite database
- Creates all necessary tables
- Sets up indexes

**Expected output:**
```
✅ Database created successfully!
   Total tables: 15
💾 Database size: ~20 KB (empty)
```

### Step 3: Setup ChromaDB (1 minute)

```bash
python migration_scripts\3_setup_chromadb.py
```

**What this does:**
- Creates `chroma_db` directory
- Creates collections for KG nodes, edges, and life log
- Initializes vector database

**Expected output:**
```
✅ ChromaDB initialized successfully!
   Total collections: 3
   - kg_nodes
   - kg_edges
   - life_log
```

### Step 4: Import Structured Data (5-10 minutes)

```bash
python migration_scripts\4_import_structured_data.py
```

**What this does:**
- Imports chat history (`unified_log`)
- Imports entity cards
- Imports events (calendar/email/todos)
- Imports all metadata

**Expected output:**
```
✅ Successful: 4/7 tables
📊 Total rows: 9,334
💾 Database size: ~100 MB
```

### Step 5: Import Knowledge Graph (5-10 minutes)

```bash
python migration_scripts\5_import_kg_data.py
```

**What this does:**
- Imports 1,413 nodes with embeddings → ChromaDB
- Imports 2,135 edges → SQLite
- Imports all KG metadata

**Expected output:**
```
✅ Nodes imported:
   - ChromaDB (with embeddings): 1,413
   - SQLite (metadata): 1,413
✅ Edges imported:
   - SQLite (metadata): 2,135
```

### Step 6: Verify Migration (2 minutes)

```bash
python migration_scripts\6_verify_migration.py
```

**What this does:**
- Compares row counts between JSON and databases
- Tests semantic search in ChromaDB
- Verifies data integrity
- Shows sample data

**Expected output:**
```
✅ Migration verification PASSED!
   All core tables match between JSON export and SQLite.
```

## Quick Commands (Run All at Once)

If you want to run all steps sequentially:

```bash
# Install ChromaDB
pip install chromadb

# Run all migration steps
python migration_scripts\2_setup_sqlite.py
python migration_scripts\3_setup_chromadb.py
python migration_scripts\4_import_structured_data.py
python migration_scripts\5_import_kg_data.py
python migration_scripts\6_verify_migration.py
```

**Total time: ~20-30 minutes**

## What You'll Have After

```
E:\EmiAi_sqlite\
├── emi.db                    # SQLite database (~100 MB)
├── chroma_db\                # ChromaDB directory (~45 MB)
│   ├── kg_nodes (1,413 items)
│   ├── kg_edges (0 items)
│   └── life_log (0 items)
└── migration_scripts\
    └── exported_data\        # Original JSON exports (keep as backup)
```

## Troubleshooting

### "ChromaDB not installed"
```bash
pip install chromadb
```

### "Database already exists"
The scripts will ask if you want to delete and recreate. Answer `yes` if you want a fresh start.

### "JSON file not found"
Make sure you ran the export scripts first:
```bash
python migration_scripts\1_export_postgresql.py --phase 1
python migration_scripts\1_export_postgresql.py --phase 2
```

### Import errors
If a table fails to import, you can import it individually:
```bash
python migration_scripts\4_import_structured_data.py --table unified_log
```

## Next Steps After Migration

1. **Test the application** with SQLite + ChromaDB
2. **Verify all features work**
3. **Keep PostgreSQL as backup** until confident
4. **Archive original EmiAi** once everything works

## Files Created

- `emi.db` - Your new SQLite database
- `chroma_db/` - Your new vector database
- Keep `exported_data/` as backup

## Safety

✅ Your original PostgreSQL database is untouched
✅ Original `EmiAi` directory is untouched
✅ All exports are preserved in `exported_data/`
✅ You can always go back if needed

---

**Ready? Start with Step 1!** 🚀






