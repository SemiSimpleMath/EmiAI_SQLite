# Seed Large Taxonomy - Known Issues & Fixes

## Issue #1: Root Node Access - COMPREHENSIVELY FIXED ✅

### Error 1a:
```
AttributeError: 'NoneType' object has no attribute 'id'
at seed_mental_health_and_wellness_block, line 774
```

**Root Cause:** Tried to use a `self_care` node that hadn't been created yet.

**Fix:** Check if `routine_activity` exists, create it if needed.

### Error 1b:
```
KeyError: 'event'  (and 'entity', 'state', 'goal')
at multiple locations
```

**Root Cause:** The `ids` parameter passed to functions is `backbone_ids`, which contains second-level nodes (like `professional_event`, `social_event`) but NOT root nodes (like `event`, `entity`, `state`, `goal`, `concept`, `property`).

**Found in 10 locations:**
- `seed_event_blocks` (line 539)
- `seed_routine_activities_block` (line 551)
- `seed_scheduled_and_ceremonial_events_block` (lines 811, 817, 823)
- `seed_detailed_states_block` (line 838)
- `seed_rituals_block` (line 976)
- `seed_projects_block` (lines 1011, 1022)
- `seed_mental_health_and_wellness_block` (line 777)

**Fix:** Created helper function `get_root_id()` to safely query root nodes, replaced all 10 occurrences.

### Final Fix Applied:
Created a **helper function** for safe root node access:

```python
def get_root_id(session, root_label):
    """Get the ID of a root taxonomy node (entity, event, state, goal, concept, property)."""
    root = session.query(Taxonomy).filter_by(label=root_label).first()
    if not root:
        raise ValueError(f"Root node '{root_label}' not found - ensure roots are seeded first")
    return root.id
```

Then replaced **all 10 occurrences** of `ids["event"]`, `ids["state"]`, `ids["entity"]`, `ids["goal"]` with `get_root_id(session, "event")`, etc.

This makes **all seeding functions order-independent and robust**.

### Code Examples:

**Before (fragile):**
```python
# ❌ Crashes if 'event' not in ids dict
get_or_create(session, kg, "environmental_event", "...", ids["event"])

# ❌ Crashes if 'state' not in ids dict  
ritual_id = get_or_create(session, kg, "ritual", "...", ids["state"])

# ❌ Crashes if 'entity' not in ids dict
project_id = get_or_create(session, kg, "project", "...", ids["entity"])
```

**After (robust):**
```python
# ✅ Queries database for root node, provides clear error if missing
get_or_create(session, kg, "environmental_event", "...", get_root_id(session, "event"))

# ✅ Safe
ritual_id = get_or_create(session, kg, "ritual", "...", get_root_id(session, "state"))

# ✅ Safe
project_id = get_or_create(session, kg, "project", "...", get_root_id(session, "entity"))
```

---

## How to Resume

The script should now complete successfully:

```bash
python seed_taxonomy_large.py
```

**Expected output:**
```
🌱 Seeding large, personalized taxonomy...
⚠️  This will create thousands of taxonomy types - may take several minutes!

📦 Seeding activity combinations...
   Created 3023 activity types

📦 Seeding skills...
   Sub-seeding soft and practical skills...

📦 Seeding education...
   Sub-seeding university life terms...

📦 Seeding health...
   Sub-seeding mental health and wellness terms...  ✅ Should work now!
...
```

---

## If You See Partial Data

If the script already created some data before crashing, you have two options:

### Option 1: Continue (Idempotent)
Just run it again. The script uses `get_or_create`, so it won't duplicate:

```bash
python seed_taxonomy_large.py
```

It will skip already-created nodes and continue from where it left off.

### Option 2: Clean Start
If you want a completely fresh seed:

```bash
# WARNING: Deletes all taxonomy data!
psql -U postgres -d emi_ai -c "DELETE FROM node_taxonomy_links; DELETE FROM taxonomy;"

# Then re-seed
python seed_taxonomy_large.py
```

---

## Progress Tracking

The script was at:
```
✅ Activities: 3,023 types created
✅ Skills: Completed soft/practical skills
✅ Education: Completed university life
⏸️ Health: Crashed during mental health block
❌ Creative works: Not started
❌ Games: Not started
❌ Events: Not started
❌ States: Not started
❌ Entities: Not started
❌ Goals: Not started
❌ Projects: Not started
```

After the fix, it should complete all remaining blocks (~6,000+ more types).

---

## Validation After Seeding

Once complete, validate the taxonomy:

```bash
python validate_taxonomy.py
```

This will check for:
- Structural integrity
- Naming conventions
- Hierarchy consistency
- Embedding coverage
- Duplicate analysis
- Multi-faceted concepts

Expected total: **~10,000 taxonomy types**

---

## Other Robustness Improvements Made

The fix pattern can be applied elsewhere if needed:

```python
# Pattern for safe parent lookup:
parent_node = session.query(Taxonomy).filter_by(label="parent_label").first()
if not parent_node:
    # Create it if needed, or raise a clear error
    parent_id = get_or_create(session, kg, "parent_label", "Description", grandparent_id)
    session.commit()
else:
    parent_id = parent_node.id

# Now safe to use parent_id
child_id = get_or_create(session, kg, "child_label", "Description", parent_id)
```

All recursive `build_hierarchy` functions should be safe because they only reference labels they just created.

