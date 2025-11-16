# Knowledge Graph Documentation

Welcome to the Emi Knowledge Graph documentation! This directory contains comprehensive documentation about the KG system architecture, implementation, and usage.

## Quick Start

**New to the KG system?** Start here:
1. Read [KG_ARCHITECTURE.md](./KG_ARCHITECTURE.md) for system overview
2. Review [KG_ENTITY_RESOLUTION.md](./KG_ENTITY_RESOLUTION.md) for Stage 1
3. Review [KG_PIPELINE_DETAILS.md](./KG_PIPELINE_DETAILS.md) for Stage 2

**Want to run the pipeline?**
```bash
# Stage 1: Entity Resolution
python app/assistant/kg_core/log_preprocessing.py

# Stage 2: Knowledge Graph Extraction
python app/assistant/kg_core/kg_pipeline.py
```

## Documentation Index

### Core Documentation

#### [KG_ARCHITECTURE.md](./KG_ARCHITECTURE.md)
**Main architecture document** - Start here for system overview
- System architecture diagram
- Two-stage pipeline overview
- Key components and features
- Database schema overview
- Processing flow summary
- Configuration basics
- Performance considerations

### Stage-Specific Documentation

#### [KG_ENTITY_RESOLUTION.md](./KG_ENTITY_RESOLUTION.md)
**Stage 1: Entity Resolution** - Preprocessing layer
- Purpose and architecture
- Overlapping chunk processing
- Entity resolver agent details
- HTML filtering
- Database tables (unified_log, processed_entity_log)
- Configuration and tuning
- Performance metrics
- Best practices

#### [KG_PIPELINE_DETAILS.md](./KG_PIPELINE_DETAILS.md)
**Stage 2: Knowledge Graph Extraction** - Main pipeline
- Adaptive window processing
- Multi-agent pipeline (8 agents)
- Conversation boundary detection
- Fact extraction process
- Metadata enrichment
- Smart merging strategies
- Database commit flow
- Data integrity checks

### Agent Documentation

#### [KG_AGENTS.md](./KG_AGENTS.md)
**Complete agent reference** - All 8 agents detailed
- entity_resolver - Pronoun and reference resolution
- conversation_boundary - Conversation segmentation
- parser - Atomic sentence extraction
- fact_extractor - Node and edge extraction
- meta_data_add - Temporal metadata enrichment
- node_merger - Merge decision making
- node_data_merger - Intelligent data combination
- edge_merger - Edge merge decisions

Each agent section includes:
- Purpose and input/output schemas
- Examples and decision criteria
- Key behaviors and strategies
- Performance characteristics

## What is the Knowledge Graph?

The Emi Knowledge Graph is a **two-stage pipeline** that transforms conversational data into structured knowledge:

### Stage 1: Entity Resolution
**Input:** "I want to work on it tomorrow"  
**Output:** "Jukka wants to work on the Emi UI tomorrow"

Resolves ambiguous pronouns and references before knowledge extraction.

### Stage 2: Knowledge Graph Extraction
**Input:** "Jukka wants to work on the Emi UI tomorrow"  
**Output:** 
- Node: Jukka (Entity, Person)
- Node: Emi UI (Goal, Feature)
- Edge: Jukka --[WantsToWorkOn]--> Emi UI
- Metadata: start_date="2025-09-30", confidence=0.85

Extracts structured knowledge with temporal awareness and provenance.

## Key Features

✅ **Two-Stage Processing** - Separate entity resolution from knowledge extraction  
✅ **Temporal Awareness** - Start/end dates, confidence scores, valid-during qualifiers  
✅ **Smart Merging** - Prevents duplicates while preserving information  
✅ **Overlapping Windows** - Maintains context at chunk/window boundaries  
✅ **Resumability** - Incremental processing with automatic resume  
✅ **Provenance Tracking** - Full source tracking for every node and edge  
✅ **Multi-Agent System** - 8 specialized agents for different tasks  
✅ **Quality Scores** - Confidence and importance for every entity and relationship  

## Architecture Diagram

```
Raw Messages (unified_log)
    ↓
[Entity Resolution - Stage 1]
    ↓
Entity-Resolved Sentences (processed_entity_log)
    ↓
[Knowledge Graph Extraction - Stage 2]
    ↓
Knowledge Graph (nodes + edges + metadata)
```

## Database Tables

### Input Tables
- `unified_log` - Raw messages from all sources
- `processed_entity_log` - Entity-resolved sentences

### Output Tables
- `nodes` - KG entities (Entity, Event, Goal, State, Property)
- `edges` - KG relationships with provenance
- `node_types`, `edge_types` - Schema definitions

## Common Use Cases

### Running Full Pipeline
```python
# Stage 1: Resolve entities
from app.assistant.kg_core.log_preprocessing import process_unified_log_chunks_with_entity_resolution

result = process_unified_log_chunks_with_entity_resolution(
    chunk_size=8,
    overlap_size=3,
    role_filter=['user', 'assistant']
)

# Stage 2: Extract knowledge
from app.assistant.kg_core.kg_pipeline import process_all_processed_entity_logs_to_kg

process_all_processed_entity_logs_to_kg(
    batch_size=100,
    max_batches=20,
    role_filter=['user', 'assistant']
)
```

### Monitoring Progress
```sql
-- Check Stage 1 progress
SELECT 
    COUNT(*) as total,
    SUM(CASE WHEN processed THEN 1 ELSE 0 END) as processed
FROM unified_log;

-- Check Stage 2 progress
SELECT 
    COUNT(*) as total,
    SUM(CASE WHEN processed THEN 1 ELSE 0 END) as processed
FROM processed_entity_log;

-- View recent nodes
SELECT label, node_type, created_at 
FROM nodes 
ORDER BY created_at DESC 
LIMIT 10;
```

### Querying the Graph
```sql
-- Find all goals
SELECT label, goal_status, start_date 
FROM nodes 
WHERE node_type = 'Goal'
ORDER BY importance DESC;

-- Find relationships
SELECT n1.label, e.relationship_type, n2.label, e.created_at
FROM edges e
JOIN nodes n1 ON e.source_id = n1.id
JOIN nodes n2 ON e.target_id = n2.id
WHERE n1.label = 'Jukka'
ORDER BY e.created_at DESC;
```

## Configuration

### Stage 1 Configuration
```python
CHUNK_SIZE = 8        # Messages per chunk
OVERLAP_SIZE = 3      # Messages to overlap between chunks
```

### Stage 2 Configuration
```python
WINDOW_SIZE = 20           # Total window size
THRESHOLD_POSITION = 15    # Look for breaks past this position
```

See individual documentation files for detailed configuration options.

## Performance

### Typical Throughput
- **Stage 1:** ~5-10 messages/second (LLM-bound)
- **Stage 2:** ~2-5 messages/second (multi-agent, LLM-bound)

### Bottlenecks
- LLM API calls (main bottleneck)
- Embedding calculations for similarity search
- Database commits (optimized via batching)

### Optimization Tips
1. Use batch processing (100-200 messages)
2. Adjust chunk/window sizes based on conversation patterns
3. Enable parallel processing where possible (future enhancement)
4. Monitor merge decisions for quality

## Troubleshooting

### No Messages Processing
- Check `processed` flags in unified_log
- Verify role_filter settings
- Check for HTML content filtering

### Low Quality Extractions
- Review entity resolution quality (Stage 1)
- Check conversation boundary detection
- Verify temporal metadata accuracy
- Review merge decisions

### Performance Issues
- Reduce batch size
- Check LLM API response times
- Review database query performance
- Monitor embedding calculations

## Development

### Adding New Agent
1. Create agent in `app/assistant/agent_registry/`
2. Define prompt template (`.j2`)
3. Define schema (`.yaml`)
4. Register in agent factory
5. Integrate into pipeline
6. Update documentation

### Modifying Pipeline
1. Understand current flow (read docs)
2. Make changes to `kg_pipeline.py`
3. Test with small batch
4. Monitor quality and performance
5. Update documentation

### Testing
```python
# Test entity resolution
from app.assistant.kg_core.log_preprocessing import process_text_chunk_with_entity_resolver

# Test knowledge extraction
from app.assistant.kg_core.kg_pipeline import process_text_to_kg

# Test individual agents
from app.assistant.ServiceLocator.service_locator import DI
agent = DI.agent_factory.create_agent("knowledge_graph_add::fact_extractor")
```

## Contributing

When updating the KG system:
1. ✅ Read relevant documentation first
2. ✅ Make changes incrementally
3. ✅ Test with small batches
4. ✅ Monitor quality and performance
5. ✅ Update documentation
6. ✅ Review merge decisions

## Support

For questions or issues:
1. Check this documentation
2. Review log output for errors
3. Test with small batch
4. Contact development team

## Future Enhancements

Planned improvements:
- [ ] Parallel agent processing
- [ ] Advanced temporal reasoning
- [ ] Cross-source entity linking
- [ ] Automated graph maintenance
- [ ] Query interface for exploration
- [ ] Multi-modal entity resolution
- [ ] Active learning for edge cases

## Related Files

### Source Code
- `app/assistant/kg_core/log_preprocessing.py` - Stage 1
- `app/assistant/kg_core/kg_pipeline.py` - Stage 2
- `app/assistant/kg_core/knowledge_graph_utils.py` - Utilities
- `app/assistant/kg_core/knowledge_graph_db.py` - Database models
- `app/assistant/agent_registry/knowledge_graph_add/` - Agents

### Database
- `app/assistant/database/db_handler.py` - unified_log model
- `app/assistant/database/processed_entity_log.py` - processed_entity_log model
- `app/models/base.py` - Database session management

## License

Part of the Emi AI project.

---

**Last Updated:** September 29, 2025  
**Documentation Version:** 1.0  
**Pipeline Version:** 2.0 (Two-stage architecture)
