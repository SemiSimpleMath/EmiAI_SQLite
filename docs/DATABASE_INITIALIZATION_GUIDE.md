# Database Initialization Guide

## Overview

EmiAi uses SQLite with automatic table creation on startup. All tables are created automatically - **no manual migration scripts needed**.

---

## Table Organization

### Always Created (19 tables)

#### Core Tables (9)
- `unified_log` - All messages and logs
- `agent_activity_log` - Agent action tracking
- `info_database` - General information storage
- `rag_database` - RAG document storage
- `event_repository` - Event storage
- `email_check_state` - Email fetch state tracking
- `processed_entity_log` - Entity-resolved sentences
- `unified_items` - State machine for external events
- `recurring_event_rules` - User preferences for recurring events

#### Entity Cards (5)
- `entity_cards` - Entity card storage
- `entity_card_usage` - Usage tracking
- `entity_card_index` - Search index
- `entity_card_run_log` - Generation tracking
- `description_run_log` - Description creation tracking

#### News (5)
- `news_categories` - News category definitions
- `news_labels` - News label taxonomy
- `news_scores` - News scoring data
- `news_articles` - Cached news articles
- `news_feedbacks` - User feedback on news

---

### Optional: Knowledge Graph (13 tables)

**Requires:**
- Feature enabled: `can_run_feature('kg')` or `can_run_feature('taxonomy')`
- ChromaDB installed: `pip install chromadb`

#### KG Core (3)
- `kg_node_metadata` - Node metadata (embeddings in ChromaDB)
- `kg_edge_metadata` - Edge relationships
- `message_source_mapping` - Message provenance

#### Taxonomy (5)
- `taxonomy` - Hierarchical type system
- `node_taxonomy_links` - Node classifications
- `taxonomy_suggestions` - New type suggestions
- `taxonomy_suggestions_review` - Review queue
- `node_taxonomy_review_queue` - Low-confidence reviews

#### Standardization (5)
- `label_canon` - Canonical node labels
- `label_alias` - Label aliases
- `edge_canon` - Canonical edge predicates
- `edge_alias` - Edge aliases
- `review_queue` - Standardization reviews

---

## How It Works

### On Every Startup:

1. **Check Settings**
   - Reads `user_settings.json` for feature toggles
   - Checks environment for API keys

2. **Create Always-On Tables**
   - Core (9 tables)
   - Entity Cards (5 tables)
   - News (5 tables)
   - Total: **19 tables**

3. **Create Optional Tables (if enabled)**
   - Knowledge Graph (13 tables) - only if feature enabled
   - Total with KG: **32 tables**

4. **Idempotent**
   - Uses `checkfirst=True` - only creates if missing
   - Safe to run multiple times
   - No manual intervention needed

---

## For Alpha Users

### Minimum Setup (No KG):
```bash
# 1. Install Python dependencies
pip install -r requirements.txt

# 2. Start Flask
python run_flask.py

# Tables auto-created:
# - 19 tables (Core + Entity Cards + News)
```

### With Knowledge Graph:
```bash
# 1. Install Python dependencies including ChromaDB
pip install -r requirements.txt
pip install chromadb

# 2. Enable KG in settings
# Edit user_settings.json:
{
  "features": {
    "enable_kg": true,
    "enable_taxonomy": true,
    ...
  }
}

# 3. Start Flask
python run_flask.py

# Tables auto-created:
# - 32 tables (Core + Entity Cards + News + KG)
```

---

## Implementation Details

### Location
- **Code**: `app/database/table_initializer.py`
- **Called from**: `app/create_app.py` (line 29)

### Functions
```python
initialize_all_tables()         # Main entry point
├── initialize_always_on_tables()
│   ├── initialize_core_tables()
│   ├── initialize_entity_card_tables()
│   └── initialize_news_tables()
└── initialize_optional_tables()
    └── initialize_kg_tables()  # If enabled
```

### Model Organization
Models stay in their original locations:
- `app/assistant/database/db_handler.py` - Core models
- `app/assistant/entity_management/entity_cards.py` - Entity models
- `app/assistant/news/news_schema.py` - News models
- `app/assistant/kg_core/` - KG models

---

## Troubleshooting

### "No module named 'chromadb'"
**Solution**: KG feature enabled but ChromaDB not installed
```bash
pip install chromadb
```

### "Table already exists"
**This is normal!** Tables are checked before creation (`checkfirst=True`).

### Check Current Tables
```python
from app.database.table_initializer import check_missing_tables

result = check_missing_tables()
print(f"Existing: {len(result['existing'])} tables")
print(f"Missing: {len(result['missing'])} tables")
```

### Force Re-create All Tables
```bash
# Delete database file
rm instance/app.db  # or emi.db

# Restart Flask (tables auto-created)
python run_flask.py
```

---

## Adding New Tables (Developers)

1. **Create model in appropriate file**
   ```python
   from app.models.base import Base
   
   class MyNewTable(Base):
       __tablename__ = 'my_new_table'
       # ...
   ```

2. **Add import to table_initializer.py**
   ```python
   def initialize_core_tables():
       from app.assistant.database.db_handler import MyNewTable
       # ...
   ```

3. **Restart Flask** - table created automatically!

---

## Migration from Old System

### Old Way (DEPRECATED):
```python
# Manual migration scripts
python migration_scripts/add_agent_activity_log.py
python migration_scripts/2_setup_sqlite_correct.py
```

### New Way:
```python
# Just start Flask!
python run_flask.py
# All tables created automatically
```

---

## Summary

✅ **No manual migrations needed**  
✅ **Tables organized by feature**  
✅ **Automatic creation on startup**  
✅ **Idempotent (safe to run multiple times)**  
✅ **Feature-based (only create what's needed)**  

Perfect for alpha release! 🚀


