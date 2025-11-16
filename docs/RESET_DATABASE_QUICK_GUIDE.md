# Quick Database Reset Guide

## The Problem
The taxonomy pipeline had a bug that:
1. Overwrote node labels with taxonomy type names
2. Used those corrupted labels to create wrong classifications
3. Corrupted both labels AND classifications

## The Solution

### Run This Command
```bash
psql -d emidb -f database_reset_keep_taxonomy_tree.sql
```

### What It Does
| Action | What Gets Affected | Result |
|--------|-------------------|--------|
| ✅ Reset labels | `nodes.label` → `nodes.semantic_label` | All node labels restored |
| ✅ Keep taxonomy | `taxonomy` table | **PRESERVED** - your hierarchy is safe |
| ✅ Clear classifications | `node_taxonomy_links` table | All cleared - ready for reclassification |
| ✅ Clear pending items | `taxonomy_suggestions_review`, `node_taxonomy_review_queue` | All cleared - fresh start |

### After Reset

**Option 1: Automatic (Recommended)**
- Just wait - the `MaintenanceManager` will reclassify during idle time
- Monitor progress in taxonomy reviewer UI

**Option 2: Manual Batch**
```bash
cd app/assistant/kg_core/taxonomy
python taxonomy_pipeline.py --batch-size 100 --max-batches 10
```

## Verification

```sql
-- All should return 0
SELECT COUNT(*) FROM nodes WHERE label != semantic_label AND semantic_label IS NOT NULL;
SELECT COUNT(*) FROM node_taxonomy_links;
SELECT COUNT(*) FROM taxonomy_suggestions_review WHERE status = 'pending';
SELECT COUNT(*) FROM node_taxonomy_review_queue WHERE status = 'pending';

-- Show your taxonomy tree is still intact
SELECT COUNT(*) as taxonomy_types, COUNT(*) FILTER (WHERE parent_id IS NULL) as root_types FROM taxonomy;
```

## What's Safe
- ✅ Your taxonomy tree structure is INTACT
- ✅ All your nodes are INTACT (with correct labels)
- ✅ All your edges/relationships are INTACT
- ✅ You just need to reclassify nodes into the taxonomy

## The Bug Is Fixed
The code that modified `node.label` has been removed from `taxonomy_pipeline.py`.
This will never happen again.

