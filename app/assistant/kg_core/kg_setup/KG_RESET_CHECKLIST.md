# Knowledge Graph Complete Reset Checklist

## 🎯 Quick Start (Automated)

```bash
# Step 1: Drop all tables
python app/assistant/kg_core/kg_setup/drop_all_kg_tables.py

# Step 2: Create and seed all tables
python app/assistant/kg_core/kg_setup/setup_all_kg_tables.py
```

**OR run from within the kg_setup directory:**
```bash
cd app/assistant/kg_core/kg_setup
python drop_all_kg_tables.py
python setup_all_kg_tables.py
```

**Done!** Skip to "Verification" section below.

---

## 📋 Manual Checklist (If Automated Fails)

### Step 1: Drop Tables ⚠️

```bash
cd app/assistant/kg_core/kg_setup
python drop_all_kg_tables.py
```

**Manual SQL (if script fails):**
```sql
DROP TABLE IF EXISTS edges CASCADE;
DROP TABLE IF EXISTS node_taxonomy_links CASCADE;
DROP TABLE IF EXISTS taxonomy_suggestions CASCADE;
DROP TABLE IF EXISTS nodes CASCADE;
DROP TABLE IF EXISTS taxonomy CASCADE;
DROP TABLE IF EXISTS edge_alias CASCADE;
DROP TABLE IF EXISTS edge_canon CASCADE;
DROP TABLE IF EXISTS label_alias CASCADE;
DROP TABLE IF EXISTS label_canon CASCADE;
DROP TABLE IF EXISTS review_queue CASCADE;
DROP TYPE IF EXISTS node_type_enum CASCADE;
```

---

### Step 2: Create Core Tables

```bash
cd app/assistant/kg_core/kg_setup
python create_core_tables.py
```

This creates:
- `node_type_enum` - Entity, Event, State, Goal, Concept, Property
- `nodes` table - KG nodes
- `edges` table - KG relationships

**Manual SQL (only if script fails):**
```sql
CREATE TYPE node_type_enum AS ENUM ('Entity', 'Event', 'State', 'Goal', 'Concept', 'Property');
-- Then run your app - SQLAlchemy will create nodes/edges tables
```

---

### Step 3: Create Taxonomy Tables

```bash
cd app/assistant/kg_core/kg_setup
python create_taxonomy_tables.py
python create_taxonomy_suggestions_table.py
python add_count_and_last_seen_to_taxonomy_links.py
```

---

### Step 4: Create Standardization Tables

```bash
cd app/assistant/kg_core/kg_setup
python setup_standardization_tables.py
```

**OR (if above fails):**
```bash
python create_edge_tables.py
# (label tables should be in setup_standardization_tables.py)
```

---

### Step 5: Seed Data

```bash
cd app/assistant/kg_core/kg_setup

# 1. Core entities (Jukka & Emi)
python seed_core_nodes.py

# 2. Taxonomy (~6.8K types) - takes ~1-2 minutes
python seed_taxonomy_large.py

# 3. Edge types registry (~240 types + aliases)
python seed_edge_types.py
```

---

## ✅ Verification

### Check Tables Exist
```bash
python -c "
from app.assistant.kg_core.knowledge_graph_db import get_session
from sqlalchemy import inspect

session = get_session()
inspector = inspect(session.bind)
tables = inspector.get_table_names()

expected = ['nodes', 'edges', 'taxonomy', 'node_taxonomy_links', 
            'taxonomy_suggestions', 'edge_canon', 'edge_alias',
            'label_canon', 'label_alias', 'review_queue']

print('✅ Tables found:')
for table in expected:
    status = '✅' if table in tables else '❌'
    print(f'  {status} {table}')
"
```

### Check Seeded Data
```bash
python -c "
from app.assistant.kg_core.knowledge_graph_db import get_session, Node
from app.assistant.kg_core.taxonomy_db import Taxonomy
from app.assistant.kg_core.models_standardization import EdgeCanon

session = get_session()

nodes = session.query(Node).count()
taxonomy = session.query(Taxonomy).count()
edges_canon = session.query(EdgeCanon).count()

print(f'📊 Data counts:')
print(f'   Nodes: {nodes} (expect: 2 - Jukka & Emi)')
print(f'   Taxonomy types: {taxonomy} (expect: ~6,800)')
print(f'   Edge types: {edges_canon} (expect: ~240)')
"
```

---

## 🚀 Start Using

### Process Your Data
```bash
# Process 10 entity logs as a test
python -c "from app.assistant.kg_core.kg_pipeline import main; main(limit=10)"
```

### View in Visualizer
```
http://localhost:5000/graph-visualizer
```

---

## 📂 Script Reference

| Script | Purpose |
|--------|---------|
| `drop_all_kg_tables.py` | Drop all KG tables |
| `setup_all_kg_tables.py` | **Master script - runs all below** |
| `create_taxonomy_tables.py` | Create taxonomy & links tables |
| `create_taxonomy_suggestions_table.py` | Create suggestions table |
| `add_count_and_last_seen_to_taxonomy_links.py` | Add counting columns |
| `setup_standardization_tables.py` | Create canon/alias tables |
| `create_edge_tables.py` | Create edge canon/alias tables |
| `app/assistant/kg_core/seed_core_nodes.py` | Seed Jukka & Emi |
| `seed_taxonomy_large.py` | Seed ~6.8K taxonomy types |
| `seed_edge_types.py` | Seed ~240 edge types |

---

## ⚠️ Troubleshooting

### "Table already exists"
```bash
# Just drop and retry
python drop_all_kg_tables.py
python setup_all_kg_tables.py
```

### "ENUM already exists"
```sql
-- Drop and recreate
DROP TYPE IF EXISTS node_type_enum CASCADE;
CREATE TYPE node_type_enum AS ENUM ('Entity', 'Event', 'State', 'Goal', 'Concept', 'Property');
```

### "Permission denied"
```bash
# Ensure you're connected to the correct database
# Check config.py for database connection string
```

### "Timeout during seeding"
```bash
# seed_taxonomy_large.py can take 1-2 minutes
# Just wait - it's creating 6,800+ entries
```

---

## 📊 Expected Timings

- **Drop tables**: < 5 seconds
- **Create tables**: < 10 seconds
- **Seed core nodes**: < 5 seconds
- **Seed taxonomy**: 1-2 minutes (~6,800 types)
- **Seed edge types**: 10-20 seconds (~240 types)

**Total time: ~2-3 minutes**

