# Knowledge Graph Architecture

## Overview

The Emi Knowledge Graph (KG) system is a sophisticated two-stage pipeline that transforms conversational data into a structured, temporal knowledge graph. It processes messages from various sources (chat, email, Slack) and extracts entities, relationships, and temporal information with provenance tracking.

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     DATA SOURCES                                 │
│  Chat Interface  │  Slack  │  Email  │  Other Sources           │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                    UNIFIED LOG TABLE                             │
│  Raw messages with metadata (timestamp, role, source)            │
│  processed = False (ready for Stage 1)                           │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│              STAGE 1: ENTITY RESOLUTION                          │
│  log_preprocessing.py                                            │
│                                                                   │
│  ┌─────────────────────────────────────────────────────┐        │
│  │ 1. Read Overlapping Chunks (8 msgs + 3 overlap)    │        │
│  │ 2. Filter HTML/Search Results                       │        │
│  │ 3. Entity Resolver Agent                            │        │
│  │    - Resolve pronouns (I → Jukka)                   │        │
│  │    - Resolve references (the UI → Emi UI)           │        │
│  │    - Maintain context across chunks                 │        │
│  │ 4. Save to processed_entity_log                     │        │
│  └─────────────────────────────────────────────────────┘        │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│              PROCESSED ENTITY LOG TABLE                          │
│  Entity-resolved sentences with reasoning                        │
│  processed = False (ready for Stage 2)                           │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│         STAGE 2: KNOWLEDGE GRAPH EXTRACTION                      │
│  kg_pipeline.py                                                  │
│                                                                   │
│  ┌─────────────────────────────────────────────────────┐        │
│  │ Adaptive Window Processing (20 msg windows)         │        │
│  │                                                      │        │
│  │ 1. Conversation Boundary Detection                  │        │
│  │    └─> Find natural conversation breaks             │        │
│  │                                                      │        │
│  │ 2. Parsing (Atomic Sentences)                       │        │
│  │    └─> Break into semantic units                    │        │
│  │                                                      │        │
│  │ 3. Fact Extraction                                  │        │
│  │    └─> Extract nodes (entities) & edges (relations) │        │
│  │                                                      │        │
│  │ 4. Metadata Enrichment                              │        │
│  │    └─> Add temporal data, confidence, importance    │        │
│  │                                                      │        │
│  │ 5. Smart Merging                                    │        │
│  │    ├─> Node Merger: Decide merge vs create         │        │
│  │    ├─> Node Data Merger: Combine information       │        │
│  │    └─> Edge Merger: Merge similar relationships    │        │
│  │                                                      │        │
│  │ 6. Graph Database Commit                            │        │
│  │    └─> Save nodes and edges with provenance        │        │
│  └─────────────────────────────────────────────────────┘        │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                  KNOWLEDGE GRAPH DATABASE                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │    NODES     │  │    EDGES     │  │  NODE/EDGE   │          │
│  │              │  │              │  │    TYPES     │          │
│  │ Entities     │  │ Relationships│  │              │          │
│  │ Events       │  │ with context │  │ Schema       │          │
│  │ Goals        │  │ & provenance │  │ definitions  │          │
│  │ States       │  │              │  │              │          │
│  │ Properties   │  │              │  │              │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
```

## Key Components

### Stage 1: Entity Resolution
- **Purpose:** Resolve ambiguous references before knowledge extraction
- **Input:** Raw conversational messages
- **Output:** Clear, entity-resolved sentences
- **See:** [Entity Resolution Details](./KG_ENTITY_RESOLUTION.md)

### Stage 2: Knowledge Graph Extraction
- **Purpose:** Extract structured knowledge from resolved text
- **Input:** Entity-resolved sentences
- **Output:** Knowledge graph with nodes and edges
- **See:** [Knowledge Graph Pipeline Details](./KG_PIPELINE_DETAILS.md)

## Agent Ecosystem

The KG system uses multiple specialized AI agents:

1. **entity_resolver** - Resolves pronouns and references
2. **conversation_boundary** - Identifies conversation segments
3. **parser** - Breaks text into atomic sentences
4. **fact_extractor** - Extracts entities and relationships
5. **meta_data_add** - Enriches with temporal metadata
6. **node_merger** - Decides on node merging strategy
7. **node_data_merger** - Intelligently combines node data
8. **edge_merger** - Decides on edge merging strategy

**See:** [Agent Details](./KG_AGENTS.md)

## Database Schema

### Core Tables

#### unified_log
Raw messages from all sources
- `id` - Unique identifier
- `message` - Raw message text
- `timestamp` - When message was created
- `role` - user/assistant/system
- `source` - chat/email/slack
- `processed` - Boolean flag

#### processed_entity_log
Entity-resolved sentences
- `id` - Unique identifier
- `original_message_id` - Reference to unified_log
- `original_sentence` - Original text
- `resolved_sentence` - Entity-resolved text
- `reasoning` - Why entities were resolved this way
- `role` - user/assistant
- `original_message_timestamp` - Original timestamp
- `processed` - Boolean flag

#### nodes
Knowledge graph entities
- `id` - Unique identifier
- `label` - Primary name
- `node_type` - Entity/Event/Goal/State/Property
- `aliases` - Alternative names (ARRAY)
- `category` - Semantic category
- `hash_tags` - Tags (ARRAY)
- `start_date` - When entity/event started
- `end_date` - When entity/event ended
- `valid_during` - Temporal qualifier
- `semantic_type` - Fine-grained type
- `goal_status` - For Goal nodes
- `confidence` - Confidence score (0-1)
- `importance` - Importance score (0-1)
- `source` - Where first seen
- `original_message_id` - Source message
- `sentence_id` - Source sentence
- `created_at`, `updated_at` - Timestamps

#### edges
Knowledge graph relationships
- `id` - Unique identifier
- `source_id` - Source node ID
- `target_id` - Target node ID
- `relationship_type` - Type of relationship
- `relationship_descriptor` - Natural language description
- `sentence` - Sentence this edge came from
- `original_message_timestamp` - When relationship was mentioned
- `confidence` - Confidence score (0-1)
- `importance` - Importance score (0-1)
- `source` - Where first seen
- `original_message_id` - Source message
- `sentence_id` - Source sentence
- `created_at` - Timestamp

**See:** [Database Schema Details](./KG_DATABASE_SCHEMA.md)

## Processing Flow

### Stage 1 Flow
1. Poll `unified_log` for unprocessed messages
2. Read in overlapping chunks (8 messages, 3 overlap)
3. Filter out HTML/search results
4. Call entity_resolver agent with context
5. Save resolved sentences to `processed_entity_log`
6. Mark original messages as processed
7. Commit and continue

### Stage 2 Flow
1. Poll `processed_entity_log` for unprocessed sentences
2. Load 20-message adaptive window
3. Find conversation boundaries
4. For each conversation:
   - Parse into atomic sentences
   - Extract facts (nodes + edges)
   - Enrich with metadata
   - Merge with existing knowledge
   - Commit to graph database
5. Mark sentences as processed
6. Slide window forward and repeat

**See:** [Processing Flow Details](./KG_PROCESSING_FLOW.md)

## Key Features

### Temporal Awareness
- Start/end dates for events and states
- Confidence scores for temporal data
- Valid-during qualifiers for context
- Provenance tracking (when info was added)

### Smart Merging
- Prevents duplicate entities
- Intelligently combines information
- Preserves provenance
- Updates confidence/importance algorithmically

### Overlapping Windows
- Stage 1: Overlapping message chunks
- Stage 2: Adaptive conversation windows
- Prevents context loss at boundaries
- Maintains entity resolution quality

### Resumability
- Incremental processing with `processed` flags
- Commits after each window/chunk
- Can restart after failures
- No duplicate processing

### Provenance Tracking
- Source field (chat/email/slack)
- Original message ID
- Sentence ID
- Timestamps (created_at, updated_at)

## Configuration

### Stage 1 Configuration
```python
CHUNK_SIZE = 8        # Messages per chunk
OVERLAP_SIZE = 3      # Messages to overlap
```

### Stage 2 Configuration
```python
WINDOW_SIZE = 20           # Total window size
THRESHOLD_POSITION = 15    # Look for breaks past this
```

**See:** [Configuration Guide](./KG_CONFIGURATION.md)

## Usage

### Running Stage 1 (Entity Resolution)
```python
from app.assistant.kg_core.log_preprocessing import process_unified_log_chunks_with_entity_resolution

result = process_unified_log_chunks_with_entity_resolution(
    chunk_size=8,
    overlap_size=3,
    role_filter=['user', 'assistant']
)
```

### Running Stage 2 (Knowledge Graph Extraction)
```python
from app.assistant.kg_core.kg_pipeline import process_all_processed_entity_logs_to_kg

process_all_processed_entity_logs_to_kg(
    batch_size=100,
    max_batches=20,
    role_filter=['user', 'assistant']
)
```

### Running Both Stages
```bash
# Stage 1
python app/assistant/kg_core/log_preprocessing.py

# Stage 2
python app/assistant/kg_core/kg_pipeline.py
```

## Monitoring & Debugging

### Database Queries
```sql
-- Check processing status
SELECT 
    COUNT(*) as total,
    SUM(CASE WHEN processed THEN 1 ELSE 0 END) as processed,
    SUM(CASE WHEN NOT processed THEN 1 ELSE 0 END) as unprocessed
FROM unified_log;

-- View recent nodes
SELECT label, node_type, created_at 
FROM nodes 
ORDER BY created_at DESC 
LIMIT 10;

-- View recent edges
SELECT n1.label, e.relationship_type, n2.label, e.created_at
FROM edges e
JOIN nodes n1 ON e.source_id = n1.id
JOIN nodes n2 ON e.target_id = n2.id
ORDER BY e.created_at DESC
LIMIT 10;
```

### Log Output
Both stages produce detailed console output showing:
- Processing progress
- Agent decisions and reasoning
- Merge operations
- Database commits
- Error handling

## Performance Considerations

### Throughput
- Stage 1: ~5-10 messages/second (entity resolution is LLM-heavy)
- Stage 2: ~2-5 messages/second (multiple agents per message)

### Bottlenecks
- LLM API calls (main bottleneck)
- Database commits (minimized via batching)
- Embedding calculations for similarity search

### Optimization Strategies
- Batch processing with resumability
- Parallel agent calls where possible
- Efficient database indexing
- Smart caching of embeddings

**See:** [Performance Tuning Guide](./KG_PERFORMANCE.md)

## Future Enhancements

### Planned Features
- [ ] Parallel processing of independent chunks
- [ ] Incremental embeddings update
- [ ] Advanced temporal reasoning
- [ ] Cross-source entity linking
- [ ] Automated knowledge graph maintenance
- [ ] Query interface for KG exploration

### Research Directions
- [ ] Multi-modal entity resolution (images, audio)
- [ ] Uncertainty quantification
- [ ] Active learning for edge cases
- [ ] Knowledge graph reasoning engines

## Related Documentation

- [Entity Resolution Details](./KG_ENTITY_RESOLUTION.md)
- [Knowledge Graph Pipeline Details](./KG_PIPELINE_DETAILS.md)
- [Agent Details](./KG_AGENTS.md)
- [Database Schema Details](./KG_DATABASE_SCHEMA.md)
- [Processing Flow Details](./KG_PROCESSING_FLOW.md)
- [Configuration Guide](./KG_CONFIGURATION.md)
- [Performance Tuning Guide](./KG_PERFORMANCE.md)
- [Troubleshooting Guide](./KG_TROUBLESHOOTING.md)

## Support

For questions or issues:
1. Check the troubleshooting guide
2. Review the detailed documentation
3. Examine log output for error messages
4. Contact the development team
