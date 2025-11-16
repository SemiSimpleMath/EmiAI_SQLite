# Knowledge Graph Setup Scripts

This directory contains all scripts needed to set up, configure, and seed the Knowledge Graph database.

---

## 📁 Directory Structure

```
kg_setup/
├── README.md                                      ← You are here
├── KG_RESET_CHECKLIST.md                         ← Step-by-step reset guide
├── PROGRESSIVE_TAXONOMY_CLASSIFICATION.md        ← Taxonomy counting documentation
│
├── setup_all_kg_tables.py                        ← 🚀 MASTER SCRIPT (run this!)
├── drop_all_kg_tables.py                         ← Drop all KG tables
│
├── create_core_tables.py                         ← Create nodes, edges, ENUM
├── create_taxonomy_tables.py                     ← Create taxonomy tables
├── create_taxonomy_suggestions_table.py          ← Create suggestions table
├── add_count_and_last_seen_to_taxonomy_links.py  ← Add counting columns
├── create_edge_tables.py                         ← Create edge canon/alias tables
├── setup_standardization_tables.py               ← Create standardization tables
│
├── add_original_sentence_column.py               ← Migration: add provenance
├── rename_relationship_type_snake_to_edge_type.py ← Migration: rename edge columns
├── drop_edge_tables.py                           ← Drop edge tables only
│
├── seed_core_nodes.py                            ← Seed Jukka & Emi
├── seed_taxonomy_minimal_curated.py              ← Seed ~250-300 curated types (IS-A compliant)
├── seed_taxonomy_large.py                        ← [DEPRECATED] Legacy ~6.8K types
└── seed_edge_types.py                            ← Seed ~240 edge types
```

---

## 🚀 Quick Start

### Complete Reset & Setup (Recommended)

```bash
# From project root:
python app/assistant/kg_core/kg_setup/drop_all_kg_tables.py
python app/assistant/kg_core/kg_setup/setup_all_kg_tables.py
```

**OR from this directory:**
```bash
cd app/assistant/kg_core/kg_setup
python drop_all_kg_tables.py
python setup_all_kg_tables.py
```

**Time: ~2-3 minutes**

---

## 📋 What Gets Created

### Tables (10)
1. **`nodes`** - KG nodes (entities, events, states, goals, concepts, properties)
2. **`edges`** - KG relationships
3. **`taxonomy`** - Hierarchical type system (~6.8K types)
4. **`node_taxonomy_links`** - Node classifications (with counting!)
5. **`taxonomy_suggestions`** - Agent-suggested new types
6. **`edge_canon`** - Canonical edge types (~240)
7. **`edge_alias`** - Edge type aliases (~500)
8. **`label_canon`** - Canonical labels
9. **`label_alias`** - Label aliases
10. **`review_queue`** - Human review queue

### ENUMs (1)
- **`node_type_enum`** - Entity, Event, State, Goal, Concept, Property

### Seeded Data
- **2 core nodes** - Jukka (user) & Emi (AI assistant)
- **~6,800 taxonomy types** - Comprehensive hierarchy
- **~240 edge types** - Participation role patterns
- **~500 edge aliases** - Common variations

---

## 📖 Individual Scripts

### Setup Scripts

**`setup_all_kg_tables.py`** 🚀
- Master script that runs everything
- Creates tables → Seeds data
- Progress tracking & error reporting

**`drop_all_kg_tables.py`** ⚠️
- Drops ALL KG tables
- 5-second safety delay
- Handles CASCADE dependencies

### Table Creation

**`create_core_tables.py`** ⚠️ **Run First!**
- Creates `nodes` table via SQLAlchemy
- Creates `edges` table via SQLAlchemy
- Creates `node_type_enum` (6 types)
- **Must run before taxonomy tables** (foreign key dependency)

**`create_taxonomy_tables.py`**
- Creates `taxonomy` table (adjacency list model)
- Creates `node_taxonomy_links` table (many-to-many)
- Includes confidence, source, count, last_seen columns

**`create_taxonomy_suggestions_table.py`**
- Creates `taxonomy_suggestions` table
- Tracks agent-proposed new types for curation

**`create_edge_tables.py`**
- Creates `edge_canon` table (canonical edge types)
- Creates `edge_alias` table (edge type aliases)

**`setup_standardization_tables.py`**
- Creates label and edge standardization tables
- Canonical forms + aliases

### Migrations

**`add_count_and_last_seen_to_taxonomy_links.py`**
- Adds counting columns to `node_taxonomy_links`
- Enables progressive classification
- See: `PROGRESSIVE_TAXONOMY_CLASSIFICATION.md`

**`add_original_sentence_column.py`**
- Adds provenance tracking to nodes
- Stores immutable original sentence

**`rename_relationship_type_snake_to_edge_type.py`**
- Renames columns in edge_canon table
- Updates to simplified naming

### Seeding

**`seed_core_nodes.py`**
- Seeds Jukka (user) node
- Seeds Emi (AI assistant) node
- Creates their relationship edge

**`seed_taxonomy_minimal_curated.py`** ✅ **RECOMMENDED**
- Seeds ~250-300 hand-curated taxonomy types
- **Strictly follows IS-A relationships** (no instances, only types)
- High-quality hierarchy covering:
  - Entities (person, organization, location, creative_work, etc.)
  - Events (communication, social_event, physical_activity, etc.)
  - States (relationship, employment_status, emotional_state, etc.)
  - Goals (personal, professional, financial, etc.)
  - Concepts (technology, academic_subject, business, etc.)
  - Properties (demographic, physical, quantitative, etc.)
- **Takes 30-60 seconds**

**`seed_taxonomy_large.py`** ⚠️ **DEPRECATED**
- Legacy script with ~6,800 auto-generated types
- Contains many nonsensical combinations (e.g., "activity_meditate_robotics")
- Violates IS-A rule in many places
- **Not recommended for new setups**

**`seed_edge_types.py`**
- Seeds ~240 canonical edge types
- Seeds ~500 edge type aliases
- Based on reified relationship model
- Participation roles pattern

---

## 🔄 Common Workflows

### Fresh Start
```bash
python drop_all_kg_tables.py
python setup_all_kg_tables.py
```

### Add Missing Table
```bash
# Just run the specific create script
python create_taxonomy_suggestions_table.py
```

### Reseed Data
```bash
# Drop existing data, keep tables
python -c "from app.assistant.kg_core.knowledge_graph_db import get_session, Node, Edge; s = get_session(); s.query(Edge).delete(); s.query(Node).delete(); s.commit()"

# Then reseed
python seed_core_nodes.py
python seed_taxonomy_minimal_curated.py
python seed_edge_types.py
```

### Run Migration
```bash
python add_count_and_last_seen_to_taxonomy_links.py
```

---

## ✅ Verification

**Check tables exist:**
```python
from sqlalchemy import inspect
from app.assistant.kg_core.knowledge_graph_db import get_session

session = get_session()
tables = inspect(session.bind).get_table_names()
print("Tables:", tables)
```

**Check seeded data:**
```python
from app.assistant.kg_core.knowledge_graph_db import get_session, Node
from app.assistant.kg_core.taxonomy_db import Taxonomy

session = get_session()
print(f"Nodes: {session.query(Node).count()}")
print(f"Taxonomy: {session.query(Taxonomy).count()}")
```

---

## 📚 Documentation

- **`KG_RESET_CHECKLIST.md`** - Complete reset guide with troubleshooting
- **`PROGRESSIVE_TAXONOMY_CLASSIFICATION.md`** - Taxonomy counting system docs

---

## ⚠️ Important Notes

1. **Always drop before recreate** - Ensures clean slate
2. **Fast seeding** - `seed_taxonomy_minimal_curated.py` takes 30-60 seconds (vs 1-2 minutes for old script)
3. **Idempotent migrations** - Safe to run multiple times
4. **Backup first** - If resetting production data
5. **Quality over quantity** - Minimal curated taxonomy is maintained, validated, and follows IS-A rule

---

## 🔗 Related

- `../knowledge_graph_db.py` - Core table models
- `../taxonomy_db.py` - Taxonomy table models
- `../models_standardization.py` - Standardization table models
- `../kg_pipeline.py` - Main processing pipeline

