# Knowledge Graph to Entity Card Pipeline

This pipeline converts Knowledge Graph entities into comprehensive entity cards for prompt injection when entities are mentioned in conversations.

## Overview

The pipeline takes important entities from your robust knowledge graph (created from user chats) and converts them into detailed entity cards that can be injected into prompts when those entities are mentioned. This provides rich context without overwhelming the system with individual relationship entries.

### Key Features

- **Intelligent Entity Extraction**: Extracts important entities with sufficient relationships from the KG
- **Smart Card Generation**: Uses standard AI agents to generate comprehensive entity cards
- **Rich Context**: Incorporates all relationships, descriptions, and metadata for each entity
- **Batch Processing**: Processes entities in configurable batches
- **Incremental Updates**: Supports incremental processing of new entities
- **Quality Control**: Includes confidence scoring and error handling
- **Prompt Injection Ready**: Cards are formatted for direct injection into prompts

## Two Approaches

### 1. Simple Pipeline (Recommended)

The **Simple Pipeline** follows the same pattern as the existing `description_creator.py`:

- Uses existing `inspect_node_neighborhood` function from `kg_tools.py`
- Processes all nodes in the knowledge graph
- Uses batch processing for nodes with many relationships
- Simple and straightforward implementation

**Files:**
- `simple_entity_card_pipeline.py` - Main pipeline logic
- `test_simple_pipeline.py` - Test script

### 2. Advanced Pipeline

The **Advanced Pipeline** provides more sophisticated features:

- Filters for important entities based on relationship count
- More complex entity extraction and processing
- Advanced storage and retrieval capabilities
- Incremental processing options

**Files:**
- `kg_rag_pipeline.py` - Main orchestrator
- `entity_card_storage.py` - Storage management
- `test_pipeline.py` - Test script

## Architecture

### Simple Pipeline
```
Knowledge Graph → inspect_node_neighborhood → EntityCardGenerator Agent → Storage
```

### Advanced Pipeline
```
Knowledge Graph → EntityExtractor → EntityCardGenerator Agent → EntityCardStorage → Prompt Injection
```

### Components

1. **EntityCardGenerator Agent** (`app/assistant/agents/entity_card_generator/`)
   - Standard agent following Emi's agent architecture
   - Uses Jinja2 templates for prompts (`prompts/system.j2`, `prompts/user.j2`)
   - Structured output via `agent_form.py`
   - Configuration via `config.yaml`
   - Converts entity information into comprehensive cards

2. **Simple Pipeline** (`app/assistant/kg_rag_pipeline/simple_entity_card_pipeline.py`)
   - Uses existing `inspect_node_neighborhood` function
   - Processes all nodes in batches
   - Simple storage (currently logging, can be extended)
   - Follows the same pattern as `description_creator.py`

3. **Advanced Pipeline** (`app/assistant/kg_rag_pipeline/kg_rag_pipeline.py`)
   - Main orchestrator for the advanced pipeline
   - Handles batch processing and error management
   - Provides statistics and monitoring
   - Offers single entity processing

4. **EntityCardStorage** (`app/assistant/kg_rag_pipeline/entity_card_storage.py`)
   - Stores and retrieves entity cards
   - Supports search by name, aliases, and content
   - Provides prompt-injection-ready formatting
   - Maintains index for fast retrieval

## Agent Structure

The EntityCardGenerator follows the standard Emi agent format:

```
app/assistant/agents/entity_card_generator/
├── agent_form.py          # Structured output schema
├── config.yaml           # Agent configuration
├── entity_extractor.py   # KG extraction functions
└── prompts/
    ├── system.j2         # System prompt template
    ├── user.j2           # User prompt template
    └── description.j2    # Agent description
```

## Usage

### Simple Pipeline (Recommended)

```python
from app.assistant.kg_rag_pipeline.simple_entity_card_pipeline import run_entity_card_pipeline, process_single_node

# Process all nodes
result = run_entity_card_pipeline()
print(f"Processed {result['processed']} entities")

# Process a single node
entity_card = process_single_node("Jukka")
if entity_card:
    print(f"Generated card for: {entity_card['entity_name']}")
```

### Advanced Pipeline

```python
from app.assistant.kg_rag_pipeline.kg_rag_pipeline import KGEntityCardPipeline

# Initialize the pipeline
pipeline = KGEntityCardPipeline()

# Run the complete pipeline
result = pipeline.run_full_pipeline(min_relationships=2, batch_size=5)
print(f"Processed {result['processed']} entities")
```

### Single Entity Processing

```python
# Process a single entity by name
result = pipeline.process_single_entity("Jukka")
if result['status'] == 'success':
    print(f"Generated card for: {result['entity_name']}")
```

### Prompt Injection

```python
# Get an entity card ready for prompt injection
entity_card = pipeline.get_entity_card("Jukka")
if entity_card:
    prompt = f"User asked about Jukka. Here's what I know:\n{entity_card}\n\nPlease answer their question."
```

### Direct Agent Usage

```python
from app.assistant.ServiceLocator.service_locator import DI
from app.assistant.utils.pydantic_classes import Message

# Create and use the agent directly
agent = DI.agent_factory.create_agent('entity_card_generator')
message = Message(
    data_type="entity_card_generation",
    sender="Test",
    receiver="entity_card_generator",
    content="Generate entity card",
    agent_input=entity_info
)
result = agent.action_handler(message)
```

### Incremental Processing

```python
# Process only new entities since a timestamp
result = pipeline.run_incremental_pipeline(since_timestamp="2024-01-01")
```

### Testing

```python
# Test the simple pipeline
python app/assistant/kg_rag_pipeline/test_simple_pipeline.py

# Test the advanced pipeline
python app/assistant/kg_rag_pipeline/test_pipeline.py
```

## Entity Card Format

Each entity card contains:

- **Entity Name**: The primary name/label of the entity
- **Entity Type**: The type/category (person, organization, location, etc.)
- **Summary**: A comprehensive 2-4 sentence summary
- **Key Facts**: List of 3-8 most important facts
- **Relationships**: Structured summary of key relationships
- **Metadata**: Additional context, timestamps, confidence scores

## Example

### Input (KG Entity)
```json
{
  "label": "Jukka",
  "type": "person",
  "description": "Software engineer and researcher",
  "relationships": [
    {
      "edge_type": "attended",
      "other_entity": {"label": "Berkeley", "type": "university"},
      "context": "Jukka attended Berkeley between 1993 and 1997 where he majored in math and physics"
    },
    {
      "edge_type": "works_at",
      "other_entity": {"label": "Google", "type": "company"},
      "context": "Jukka works at Google as a senior software engineer"
    }
  ]
}
```

### Output (Entity Card)
```json
{
  "entity_name": "Jukka",
  "entity_type": "person",
  "summary": "Jukka is a software engineer and researcher who attended the University of California, Berkeley from 1993 to 1997, where he majored in mathematics and physics. He currently works at Google as a senior software engineer.",
  "key_facts": [
    "Attended UC Berkeley from 1993-1997",
    "Majored in mathematics and physics",
    "Works at Google as senior software engineer",
    "Software engineer and researcher by profession"
  ],
  "relationships": [
    "Education: Attended UC Berkeley (1993-1997)",
    "Employment: Senior software engineer at Google"
  ],
  "metadata": {
    "confidence": 0.95,
    "relationship_count": 2
  }
}
```

### Prompt Injection Format
```
ENTITY CARD: Jukka
Type: person

Summary:
Jukka is a software engineer and researcher who attended the University of California, Berkeley from 1993 to 1997, where he majored in mathematics and physics. He currently works at Google as a senior software engineer.

Key Facts:
• Attended UC Berkeley from 1993-1997
• Majored in mathematics and physics
• Works at Google as senior software engineer
• Software engineer and researcher by profession

Key Relationships:
• Education: Attended UC Berkeley (1993-1997)
• Employment: Senior software engineer at Google
```

## Configuration

### Agent Configuration (`app/assistant/agents/entity_card_generator/config.yaml`)
```yaml
name: entity_card_generator
class_name: Agent
llm_params:
  llm_provider: "openai"
  engine: "gpt-4o-mini"
  temperature: 0.1
structured_output: "app.assistant.agents.entity_card_generator.agent_form.EntityCardForm"
```

### Pipeline Parameters
- `min_relationships`: Minimum number of relationships for an entity to be considered important (default: 2)
- `batch_size`: Number of entities to process in each batch (default: 5)
- `since_timestamp`: For incremental processing, only process entities updated after this timestamp

## Integration

### With Knowledge Graph
Uses your existing KG models:

```python
from app.assistant.kg_core.kg_tools import Node, Edge, inspect_node_neighborhood
```

### With Agent System
Entity cards can be injected into any agent's prompt when entities are mentioned:
```python
# In your agent's prompt processing
entity_card = pipeline.get_entity_card(entity_name)
if entity_card:
    enhanced_prompt = f"{entity_card}\n\n{original_prompt}"
```

### With Standard Agent Factory
The entity card generator integrates seamlessly with Emi's agent system:
```python
agent = DI.agent_factory.create_agent('entity_card_generator')
```

## Monitoring and Statistics

```python
# Get pipeline statistics
stats = pipeline.get_pipeline_stats()
print(f"Total KG entities: {stats['total_kg_entities']}")
print(f"Total stored cards: {stats['total_stored_cards']}")
print(f"Conversion rate: {stats['conversion_rate']:.2%}")

# Search for entities
results = pipeline.search_entities("Jukka", limit=5)
for result in results:
    print(f"Found: {result['entity_name']} (score: {result['score']})")
```

## Error Handling

The pipeline includes comprehensive error handling:
- Individual entity processing errors don't stop the pipeline
- Failed cards are logged with details
- Success rates are tracked and reported
- Database connection errors are handled gracefully
- Invalid entity data is filtered out

## Performance Considerations

- **Batch Processing**: Process entities in batches to avoid overwhelming the LLM
- **Rate Limiting**: Built-in delays between batches
- **Memory Management**: Processes entities one at a time to manage memory usage
- **Storage Efficiency**: Uses JSON storage for fast retrieval
- **Indexing**: Maintains search index for quick entity lookups

## Future Enhancements

- **Parallel Processing**: Process multiple entities concurrently
- **Quality Filtering**: Filter out low-confidence cards
- **Custom Prompts**: Allow customization of generation prompts
- **Entity Types**: Specialized handling for different entity types
- **Real-time Updates**: Process new entities as they're added to KG
- **Vector Search**: Add semantic search capabilities

## Troubleshooting

### Common Issues

1. **No entities found**: Check if your KG has nodes with relationships
2. **LLM errors**: Verify OpenAI API key and model availability
3. **Storage errors**: Check file permissions for entity card storage
4. **Memory issues**: Reduce batch size for large KGs
5. **Agent not found**: Ensure the agent is properly registered in the agent factory

### Debug Mode

Enable detailed logging:
```python
import logging
logging.getLogger('app.assistant.kg_rag_pipeline').setLevel(logging.DEBUG)
logging.getLogger('app.assistant.agents.entity_card_generator').setLevel(logging.DEBUG)
```

## Contributing

To extend the pipeline:
1. Add new extraction methods to `entity_extractor.py`
2. Customize the generation prompts in `prompts/` directory
3. Add new pipeline features to `KGEntityCardPipeline`
4. Update the agent form schema in `agent_form.py`
5. Enhance storage capabilities in `EntityCardStorage`
6. Follow the standard agent format for consistency
