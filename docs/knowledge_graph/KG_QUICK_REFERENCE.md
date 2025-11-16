# Knowledge Graph: Quick Reference

## System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    KNOWLEDGE GRAPH SYSTEM                    │
│                      Two-Stage Pipeline                      │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  STAGE 1: ENTITY RESOLUTION (log_preprocessing.py)          │
│  ─────────────────────────────────────────────────────────  │
│  Input:  "I want to work on it"                             │
│  Output: "Jukka wants to work on the Emi UI"                │
│  ─────────────────────────────────────────────────────────  │
│  • Resolve pronouns (I → Jukka)                             │
│  • Resolve references (it → Emi UI)                         │
│  • Overlapping chunks (8 msgs + 3 overlap)                  │
│  • Filter HTML content                                       │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  STAGE 2: KNOWLEDGE EXTRACTION (kg_pipeline.py)             │
│  ─────────────────────────────────────────────────────────  │
│  Input:  "Jukka wants to work on the Emi UI"                │
│  Output: [Nodes] Jukka, Emi UI                              │
│          [Edge] Jukka --[WantsToWorkOn]--> Emi UI           │
│  ─────────────────────────────────────────────────────────  │
│  • Adaptive windows (20 msgs)                               │
│  • 7 specialized agents                                      │
│  • Smart merging                                             │
│  • Temporal metadata                                         │
└─────────────────────────────────────────────────────────────┘
```

## Quick Commands

### Run Stage 1 (Entity Resolution)
```python
from app.assistant.kg_core.log_preprocessing import process_unified_log_chunks_with_entity_resolution

result = process_unified_log_chunks_with_entity_resolution(
    chunk_size=8,
    overlap_size=3,
    role_filter=['user', 'assistant']
)
```

### Run Stage 2 (Knowledge Extraction)
```python
from app.assistant.kg_core.kg_pipeline import process_all_processed_entity_logs_to_kg

process_all_processed_entity_logs_to_kg(
    batch_size=100,
    max_batches=20,
    role_filter=['user', 'assistant']
)
```

### Run Both Stages
```bash
# Stage 1
python app/assistant/kg_core/log_preprocessing.py

# Stage 2
python app/assistant/kg_core/kg_pipeline.py
```

## 8 Agents at a Glance

| # | Agent | Stage | Purpose | Input | Output |
|---|-------|-------|---------|-------|--------|
| 1 | **entity_resolver** | 1 | Resolve pronouns & references | Raw text | Resolved text |
| 2 | **conversation_boundary** | 2 | Find conversation breaks | 20 messages | Conversation bounds |
| 3 | **parser** | 2 | Split into atomic sentences | Conversation | Atomic sentences |
| 4 | **fact_extractor** | 2 | Extract nodes & edges | Sentences | Nodes + Edges |
| 5 | **meta_data_add** | 2 | Add temporal metadata | Nodes | Enriched nodes |
| 6 | **node_merger** | 2 | Decide merge vs create | New + Candidates | Merge decision |
| 7 | **node_data_merger** | 2 | Combine node info | Two nodes | Merged data |
| 8 | **edge_merger** | 2 | Decide edge merge | New + Candidates | Merge decision |

## Database Tables

### Stage 1 Tables
```sql
unified_log                    →  processed_entity_log
├─ id                          →  ├─ id
├─ message                     →  ├─ original_message_id (FK)
├─ timestamp                   →  ├─ original_sentence
├─ role                        →  ├─ resolved_sentence
├─ source                      →  ├─ reasoning
└─ processed (bool)            →  ├─ role
                                  └─ processed (bool)
```

### Stage 2 Tables
```sql
nodes                          edges
├─ id                          ├─ id
├─ label                       ├─ source_id (FK → nodes)
├─ node_type                   ├─ target_id (FK → nodes)
├─ aliases (array)             ├─ relationship_type
├─ category                    ├─ relationship_descriptor
├─ start_date                  ├─ sentence
├─ end_date                    ├─ original_message_timestamp
├─ start_date_confidence       ├─ confidence
├─ end_date_confidence         ├─ importance
├─ valid_during                ├─ source
├─ semantic_type               ├─ original_message_id
├─ goal_status                 ├─ sentence_id
├─ confidence                  └─ created_at
├─ importance
├─ hash_tags (array)
├─ source
├─ original_message_id
├─ sentence_id
├─ created_at
└─ updated_at
```

## Node Types

| Type | Purpose | Examples | Has Temporal Data? |
|------|---------|----------|-------------------|
| **Entity** | Physical/abstract entities | People, organizations, concepts | No |
| **Event** | Things that happened | "Started project", "Meeting held" | Yes (start/end dates) |
| **Goal** | Objectives/intentions | "Build feature", "Improve UI" | Yes (start/end dates) |
| **State** | Conditions/states | "In development", "Operational" | Yes (valid_during) |
| **Property** | Attributes | "Runs at 9 AM", "User-friendly" | Optional |

## Configuration Cheatsheet

### Stage 1 (Entity Resolution)
```python
CHUNK_SIZE = 8        # Messages per chunk
OVERLAP_SIZE = 3      # Messages to overlap

# Trade-offs:
# Larger chunks    → Better context, slower, more tokens
# Smaller chunks   → Faster, less context, more API calls
# Larger overlap   → Better quality, more duplicates filtered
```

### Stage 2 (Knowledge Extraction)
```python
WINDOW_SIZE = 20           # Total window size
THRESHOLD_POSITION = 15    # Look for breaks past this

# Trade-offs:
# Larger windows     → Better conversation detection, slower
# Smaller windows    → Faster, risk splitting conversations
# Higher threshold   → Prefer future breaks (less conservative)
# Lower threshold    → Prefer past breaks (more conservative)
```

## Monitoring Queries

### Check Processing Status
```sql
-- Stage 1 progress
SELECT 
    COUNT(*) as total,
    SUM(CASE WHEN processed THEN 1 ELSE 0 END) as processed,
    SUM(CASE WHEN NOT processed THEN 1 ELSE 0 END) as remaining
FROM unified_log;

-- Stage 2 progress
SELECT 
    COUNT(*) as total,
    SUM(CASE WHEN processed THEN 1 ELSE 0 END) as processed,
    SUM(CASE WHEN NOT processed THEN 1 ELSE 0 END) as remaining
FROM processed_entity_log;
```

### View Recent Results
```sql
-- Recent nodes
SELECT label, node_type, confidence, importance, created_at 
FROM nodes 
ORDER BY created_at DESC 
LIMIT 20;

-- Recent edges
SELECT 
    n1.label as source,
    e.relationship_type,
    n2.label as target,
    e.confidence,
    e.created_at
FROM edges e
JOIN nodes n1 ON e.source_id = n1.id
JOIN nodes n2 ON e.target_id = n2.id
ORDER BY e.created_at DESC
LIMIT 20;
```

### Graph Statistics
```sql
-- Node type distribution
SELECT node_type, COUNT(*) as count
FROM nodes
GROUP BY node_type
ORDER BY count DESC;

-- Relationship type distribution
SELECT relationship_type, COUNT(*) as count
FROM edges
GROUP BY relationship_type
ORDER BY count DESC;

-- High importance entities
SELECT label, node_type, importance, confidence
FROM nodes
WHERE importance > 0.7
ORDER BY importance DESC, confidence DESC
LIMIT 20;
```

## Common Patterns

### Example 1: Goal Tracking
```sql
-- Find all goals and their status
SELECT 
    label,
    goal_status,
    start_date,
    end_date,
    importance,
    confidence
FROM nodes
WHERE node_type = 'Goal'
ORDER BY importance DESC, start_date DESC;
```

### Example 2: Entity Relationships
```sql
-- Find all of Jukka's relationships
SELECT 
    e.relationship_type,
    n2.label as related_to,
    n2.node_type,
    e.sentence,
    e.created_at
FROM edges e
JOIN nodes n1 ON e.source_id = n1.id
JOIN nodes n2 ON e.target_id = n2.id
WHERE n1.label = 'Jukka'
ORDER BY e.created_at DESC;
```

### Example 3: Temporal Timeline
```sql
-- Events in chronological order
SELECT 
    label,
    start_date,
    end_date,
    valid_during,
    start_date_confidence
FROM nodes
WHERE node_type = 'Event'
  AND start_date IS NOT NULL
ORDER BY start_date ASC;
```

## Troubleshooting Quick Guide

| Issue | Likely Cause | Solution |
|-------|-------------|----------|
| No messages processing | All marked as processed | Check `processed` flags |
| Low quality resolution | Chunk size too small | Increase chunk_size |
| Duplicate entities | Merge threshold too high | Review node_merger agent |
| Missing relationships | Boundary detection splitting | Check conversation_boundary |
| Wrong dates | Timestamp not passed correctly | Verify message_timestamp param |
| Slow processing | LLM API bottleneck | Reduce batch size, check API |

## Performance Benchmarks

### Throughput
- **Stage 1:** ~5-10 messages/second
- **Stage 2:** ~2-5 messages/second
- **Combined:** ~2-4 messages/second (bottleneck)

### Agent Response Times
- entity_resolver: 2-4s
- conversation_boundary: 1-2s
- parser: 1-2s
- fact_extractor: 2-5s
- meta_data_add: 1-3s (per node)
- node_merger: 1-2s
- node_data_merger: 1-2s
- edge_merger: 1-2s

### Bottlenecks
1. 🔴 LLM API calls (main)
2. 🟡 Embedding calculations
3. 🟢 Database operations (optimized)

## Best Practices

### ✅ DO
- Process in batches (100-200 messages)
- Monitor merge decisions
- Review temporal metadata quality
- Use role_filter to focus on relevant messages
- Check processed flags regularly
- Commit after each window/chunk

### ❌ DON'T
- Process entire log at once (too slow)
- Skip HTML filtering (pollutes graph)
- Ignore confidence/importance scores
- Process without monitoring
- Modify processed flags manually
- Skip entity resolution stage

## Key Metrics to Track

### Quality Metrics
- ✅ Merge rate (should be 20-40%)
- ✅ Confidence scores (average > 0.7)
- ✅ Importance scores (meaningful distribution)
- ✅ Temporal metadata coverage (60-80% for temporal nodes)

### Performance Metrics
- ✅ Processing speed (messages/second)
- ✅ API response times
- ✅ Database commit times
- ✅ Memory usage

### Data Quality
- ✅ Orphaned nodes (should be 0)
- ✅ Duplicate entities (check aliases)
- ✅ Edge connectivity (every node should have edges)
- ✅ Provenance completeness (all nodes have source)

## Pipeline Flow Summary

```
1. READ unprocessed messages from unified_log
   ↓
2. CHUNK into overlapping windows (Stage 1)
   ↓
3. RESOLVE entities with context
   ↓
4. SAVE to processed_entity_log
   ↓
5. MARK original messages as processed
   ═══════════════════════════════════════
6. READ unprocessed sentences from processed_entity_log
   ↓
7. WINDOW into adaptive 20-message windows
   ↓
8. DETECT conversation boundaries
   ↓
9. PARSE into atomic sentences
   ↓
10. EXTRACT facts (nodes + edges)
   ↓
11. ENRICH with metadata
   ↓
12. MERGE with existing knowledge
   ↓
13. COMMIT to graph database
   ↓
14. MARK sentences as processed
```

## Documentation Map

```
README.md                      ← Start here
├─ KG_ARCHITECTURE.md          ← System overview
├─ KG_ENTITY_RESOLUTION.md     ← Stage 1 details
├─ KG_PIPELINE_DETAILS.md      ← Stage 2 details
├─ KG_AGENTS.md                ← All 8 agents
└─ KG_QUICK_REFERENCE.md       ← This file!
```

## Getting Help

1. **Read the docs** - Start with README.md
2. **Check logs** - Detailed output shows decisions
3. **Test small batch** - Isolate issues
4. **Review queries** - Verify data quality
5. **Contact team** - If still stuck

---

**Quick Links:**
- [Full Architecture](./KG_ARCHITECTURE.md)
- [Entity Resolution](./KG_ENTITY_RESOLUTION.md)
- [Pipeline Details](./KG_PIPELINE_DETAILS.md)
- [Agent Details](./KG_AGENTS.md)
- [Main README](./README.md)

**Last Updated:** September 29, 2025
