# Database Setup Guide

This guide explains how to initialize the EmiAi database for a fresh installation.

## Quick Start

For a complete setup with all tables and data:

```bash
cd app/assistant/kg_core/kg_setup
python setup_all_kg_tables.py
```

This will:
1. Create core KG tables (nodes, edges)
2. Create taxonomy tables
3. Create standardization tables
4. Seed core nodes (Jukka, Emi)
5. **Seed taxonomy from official ontology** (~1500 curated types)
6. Seed edge types

## Taxonomy Ontology

The taxonomy is now seeded from a curated JSON ontology file:
```
app/assistant/kg_core/taxonomy/taxonomy_ontology/taxonomy_export_tree_*.json
```

This ensures all installations have the same, high-quality taxonomy structure.

### Manual Taxonomy Seeding

To manually seed or update the taxonomy:

```bash
cd app/assistant/kg_core/kg_setup

# First time - import taxonomy
python seed_taxonomy_from_ontology.py

# Update - clear existing and reimport
python seed_taxonomy_from_ontology.py --clear

# Use a specific ontology file
python seed_taxonomy_from_ontology.py --file /path/to/taxonomy.json
```

The script will:
- Find the latest ontology file automatically
- Flatten the hierarchical tree structure
- Create taxonomy nodes in correct order (parents before children)
- Maintain ID relationships

## Individual Table Setup

If you need to create specific tables only:

### Core KG Tables
```bash
python -c "from app.assistant.kg_core.knowledge_graph_db_sqlite import initialize_knowledge_graph_db; initialize_knowledge_graph_db()"
```

### Taxonomy Tables
```bash
cd app/assistant/kg_core/kg_setup
python create_taxonomy_tables.py
python create_taxonomy_suggestions_table.py
python create_taxonomy_review_tables.py
```

### Seed Core Nodes
```bash
cd app/assistant/kg_core/kg_setup
python seed_core_nodes.py
```

## Database Location

SQLite database is located at:
```
e:\EmiAi_sqlite\emi.db
```

## Troubleshooting

### Tables Already Exist
If you get "table already exists" errors, you may need to drop existing tables first:

```bash
python -c "from app.assistant.kg_core.knowledge_graph_db_sqlite import drop_knowledge_graph_db; drop_knowledge_graph_db()"
```

### Taxonomy Already Exists
To replace existing taxonomy:

```bash
python seed_taxonomy_from_ontology.py --clear
```

### Check Table Status
Use the query tool to check what tables exist:

```bash
python query_db.py
```

Then type: `tables`

## Migration from Old Setup

If you have an existing installation using the old seed scripts (`seed_core_taxonomy.py`, `seed_expanded_taxonomy.py`):

1. Back up your database
2. Clear existing taxonomy: `python seed_taxonomy_from_ontology.py --clear`
3. The new ontology-based taxonomy will be imported

The new approach ensures:
- ✅ Consistent taxonomy across installations
- ✅ Single source of truth (JSON ontology file)
- ✅ Easy updates and versioning
- ✅ Hierarchical structure preserved
- ✅ No manual script maintenance

## Next Steps

After setup:
1. Start Flask app: `python run_flask.py`
2. View KG Visualizer: http://localhost:5000/kg-visualizer
3. View Taxonomy Viewer: http://localhost:5000/taxonomy_webviewer
4. Process messages to build knowledge graph

