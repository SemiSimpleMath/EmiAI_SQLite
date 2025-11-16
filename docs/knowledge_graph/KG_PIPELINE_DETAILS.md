# Knowledge Graph: Pipeline Details (Stage 2)

## Overview

Stage 2 of the KG system takes entity-resolved sentences and extracts structured knowledge in the form of nodes (entities) and edges (relationships). This stage uses a multi-agent pipeline with adaptive window processing to build a temporal knowledge graph with provenance tracking.

## Purpose

Transform entity-resolved sentences like:
```
"Jukka wants to build a daily summary generator"
```

Into structured knowledge:
```
Node: Jukka (Entity, Person)
Node: daily summary generator (Goal, Feature)
Edge: Jukka --[WANTS_TO_BUILD]--> daily summary generator
```

With temporal metadata, confidence scores, and full provenance.

## Architecture

### File Location
`app/assistant/kg_core/kg_pipeline.py`

### Main Entry Point

```python
def process_text_to_kg(
    log_context_items: List[Dict[str, Any]], 
    kg_utils: Optional[KnowledgeGraphUtils] = None
):
    """
    Main pipeline function to process text entries and add them to KG.
    Uses adaptive sliding windows to prevent false conversation starts.
    """
```

## Adaptive Window Processing

### Configuration
```python
WINDOW_SIZE = 20           # Total window size for processing
THRESHOLD_POSITION = 15    # Look for breaks past this position first
```

### Strategy

The pipeline uses an elegant sliding window approach:

```
1. Assume message 1 is always start of new conversation
2. Look for breaks between positions 15-20 first (future breaks)
3. If no future break, look for last break between positions 1-15 (past fallback)
4. If no break anywhere, use full 20-message window
5. Move window forward by processed size, repeat
```

### Why Adaptive Windows?

**Problem:** Fixed windows can split conversations awkwardly
```
Window 1: [msg1...msg20]  ← Conversation ends at msg15
Window 2: [msg21...msg40] ← New conversation starts at msg16
```

**Solution:** Find natural conversation boundaries
```
Window 1: [msg1...msg15]  ← Process complete conversation
Window 2: [msg16...msg35] ← Start at new conversation
```

### Boundary Detection Flow

```python
def find_optimal_window_boundary(message_bounds, window_size=20, threshold=15):
    # 1. Look for breaks in future (15-20)
    future_breaks = [end for end in bounds if end >= threshold]
    if future_breaks:
        return min(future_breaks) + 1  # Use first future break
    
    # 2. Look for breaks in past (1-15)
    past_breaks = [end for end in bounds if end < threshold]
    if past_breaks:
        return max(past_breaks) + 1  # Use last past break
    
    # 3. No breaks found, use full window
    return window_size
```

## Multi-Agent Pipeline

### Pipeline Stages

```
1. CONVERSATION BOUNDARY DETECTION
   ↓
2. ATOMIC SENTENCE PARSING
   ↓
3. FACT EXTRACTION (Nodes + Edges)
   ↓
4. METADATA ENRICHMENT
   ↓
5. SMART MERGING
   ↓
6. DATABASE COMMIT
```

### 1. Conversation Boundary Detection

**Agent:** `conversation_boundary`

**Purpose:** Identify where conversations start and end

**Input:**
```python
{
    "messages": [
        {"id": "msg_0", "role": "user", "message": "...", "timestamp": "..."},
        {"id": "msg_1", "role": "assistant", "message": "...", "timestamp": "..."},
        # ... more messages
    ],
    "analysis_window_size": 20
}
```

**Output:**
```python
{
    "message_bounds": [
        {
            "message_id": "msg_5",
            "bounds": {
                "start_message_id": "msg_0",
                "end_message_id": "msg_5",
                "should_process": True
            }
        },
        {
            "message_id": "msg_12",
            "bounds": {
                "start_message_id": "msg_6",
                "end_message_id": "msg_12",
                "should_process": True
            }
        }
    ]
}
```

**Detection Criteria:**
- Topic changes
- Time gaps between messages
- Role transitions (multiple user messages)
- Explicit conversation markers ("Let's talk about...")

### 2. Atomic Sentence Parsing

**Agent:** `parser`

**Purpose:** Break conversation into atomic, semantically complete sentences

**Input:**
```python
{
    "text": "Jukka wants to build a daily summary generator. It should run every morning at 9 AM.",
    "original_message_timestamp": "2025-09-29T10:30:00"
}
```

**Output:**
```python
{
    "parsed_sentences": [
        {
            "sentence": "Jukka wants to build a daily summary generator",
            "sentence_type": "declarative",
            "entities_mentioned": ["Jukka", "daily summary generator"]
        },
        {
            "sentence": "The daily summary generator should run every morning at 9 AM",
            "sentence_type": "declarative",
            "entities_mentioned": ["daily summary generator"]
        }
    ]
}
```

**Why Atomic Sentences?**
- Each sentence represents one fact
- Easier for fact extraction
- Better provenance (sentence → node/edge mapping)

### 3. Fact Extraction

**Agent:** `fact_extractor`

**Purpose:** Extract entities (nodes) and relationships (edges) from sentences

**Input:**
```python
{
    "text": [
        "Jukka wants to build a daily summary generator",
        "The daily summary generator should run every morning at 9 AM"
    ],
    "original_message_timestamp": "2025-09-29T10:30:00"
}
```

**Output:**
```python
{
    "nodes": [
        {
            "temp_id": "temp_1",
            "label": "Jukka",
            "node_type": "Entity",
            "category": "Person",
            "sentence": "Jukka wants to build a daily summary generator"
        },
        {
            "temp_id": "temp_2",
            "label": "daily summary generator",
            "node_type": "Goal",
            "category": "Feature",
            "sentence": "Jukka wants to build a daily summary generator"
        }
    ],
    "edges": [
        {
            "source": "temp_1",
            "target": "temp_2",
            "label": "WantsToBuild",
            "relationship_descriptor": "wants to build",
            "sentence": "Jukka wants to build a daily summary generator"
        },
        {
            "source": "temp_2",
            "target": "temp_3",
            "label": "ScheduledFor",
            "relationship_descriptor": "should run",
            "sentence": "The daily summary generator should run every morning at 9 AM"
        }
    ]
}
```

**Chunking Strategy:**
If more than 5 sentences, process in chunks:
```python
if len(sentences) > 5:
    chunks = [sentences[i:i+5] for i in range(0, len(sentences), 5)]
    # Process each chunk separately
```

**Why Chunk?**
- Prevents LLM context overflow
- Better focus on smaller text units
- Maintains quality with long conversations

### 4. Metadata Enrichment

**Agent:** `meta_data_add`

**Purpose:** Add temporal metadata, confidence scores, importance ratings

**Input (per node):**
```python
{
    "nodes": [
        {
            "temp_id": "temp_1",
            "label": "daily summary feature",
            "node_type": "Event",
            # ... other fields
        }
    ],
    "resolved_sentence": "Jukka started working on the daily summary feature on September 29th",
    "message_timestamp": "2025-09-29T10:30:00"
}
```

**Output:**
```python
{
    "Nodes": [
        {
            "temp_id": "temp_1",
            "label": "daily summary feature",
            "node_type": "Event",
            "start_date": "2025-09-29T00:00:00",
            "start_date_confidence": 0.9,
            "end_date": null,
            "end_date_confidence": 0.0,
            "valid_during": "September 2025",
            "semantic_type": "software_feature",
            "confidence": 0.85,
            "importance": 0.7,
            "aliases": ["daily summary", "summary feature"],
            "category": "Feature Development",
            "hash_tags": ["#feature", "#development"]
        }
    ]
}
```

**Metadata Fields:**

**Temporal:**
- `start_date` - When entity/event began (for Event, State, Goal)
- `end_date` - When entity/event ended
- `start_date_confidence` - Confidence in start date (0-1)
- `end_date_confidence` - Confidence in end date (0-1)
- `valid_during` - Temporal qualifier ("September 2025", "during the sprint")

**Semantic:**
- `semantic_type` - Fine-grained type (for State, Property)
- `goal_status` - Status for Goal nodes ("planned", "in_progress", "completed")
- `category` - High-level categorization
- `hash_tags` - Relevant tags

**Quality:**
- `confidence` - Confidence in this node existing (0-1)
- `importance` - Importance score (0-1)

**One-Node-at-a-Time Processing:**
```python
for node in nodes:
    # Process each node individually
    meta_data_input = {
        "nodes": json.dumps([node]),  # Single node
        "resolved_sentence": node.get("sentence", ""),
        "message_timestamp": timestamp
    }
    # Call agent for this node
    result = meta_data_agent.action_handler(Message(agent_input=meta_data_input))
```

**Why Individual Processing?**
- Better focus on each node's context
- More accurate temporal extraction
- Uses node's specific sentence (not full conversation)

### 5. Smart Merging

The pipeline uses multiple agents to decide whether to create new nodes/edges or merge with existing ones.

#### Node Merging

**Step 1: Find Similar Nodes**
```python
similar_nodes = kg_utils.find_similar_nodes(
    label=new_label,
    node_type=new_type,
    k=5  # Top 5 most similar
)
```

Uses embedding similarity and label matching.

**Step 2: Ask Merge Agent**

**Agent:** `node_merger`

**Input:**
```python
{
    "new_node_data": {
        "label": "daily summary feature",
        "node_type": "Goal",
        "category": "Feature Development"
    },
    "existing_node_candidates": [
        {
            "candidate_id": 1,
            "node_id": "uuid-123",
            "label": "daily summary generator",
            "node_type": "Goal",
            "category": "Feature",
            "similarity_score": 0.92
        },
        # ... more candidates
    ]
}
```

**Output:**
```python
{
    "merge_nodes": True,
    "merged_node_id": 1,  # Candidate ID to merge with
    "reasoning": "Both refer to the same feature. 'generator' and 'feature' are synonymous in this context.",
    "confidence": 0.95
}
```

**Step 3: Merge Node Data**

If merge is decided, use `node_data_merger` agent.

**Agent:** `node_data_merger`

**Input:**
```python
{
    "existing_node_data": {
        "label": "daily summary generator",
        "aliases": [],
        "start_date": "2025-09-28",
        "start_date_confidence": 0.8,
        "category": "Feature",
        # ... more fields
    },
    "new_node_data": {
        "label": "daily summary feature",
        "aliases": ["summary feature"],
        "start_date": "2025-09-29",
        "start_date_confidence": 0.9,
        "category": "Feature Development",
        # ... more fields
    }
}
```

**Output:**
```python
{
    "merged_aliases": ["daily summary feature", "summary feature"],
    "merged_hash_tags": ["#feature", "#development", "#summary"],
    "unified_semantic_type": "software_feature",
    "unified_start_date": "2025-09-28T00:00:00",  # Earlier date
    "unified_start_date_confidence": 0.8,  # Lower confidence (more conservative)
    "unified_category": "Feature Development",  # More specific
    "reasoning": "Combined aliases from both. Chose earlier start date. Used more specific category.",
    "merge_confidence": 0.92
}
```

**Merge Logic:**
- **Aliases:** Union of both + new label if different
- **Hash Tags:** Union of both
- **Category:** More specific one
- **Dates:** Earlier start date, later end date
- **Confidence/Importance:** Higher value (take max)
- **Valid During:** Merge temporal qualifiers
- **Semantic Type:** More specific one

**Enhanced Logging:**
```
🧠 NODE DATA MERGER AGENT OUTPUT
================================================================================
📊 Merging nodes: 'daily summary generator' + 'daily summary feature'
🎯 Agent Reasoning: Both refer to the same feature...
📈 Confidence Score: 0.92
================================================================================
📝 ALIASES:
   Before: []
   After:  ['daily summary feature', 'summary feature']
   Change: Added
✅ MERGE COMPLETED: Updated 3 field(s): aliases, category, start_date
🕒 Timestamp updated: 2025-09-29 10:35:42
📂 Source preserved: chat (original source)
================================================================================
```

#### Edge Merging

**Agent:** `edge_merger`

**Input:**
```python
{
    "new_edge_data": {
        "relationship_type": "WantsToBuild",
        "source_node_label": "Jukka",
        "target_node_label": "daily summary feature",
        "sentence": "Jukka wants to build the daily summary feature"
    },
    "existing_edge_candidates": [
        {
            "candidate_id": 1,
            "edge_id": "uuid-456",
            "relationship_type": "WantsToBuild",
            "source_label": "Jukka",
            "target_label": "daily summary generator",
            "sentence": "Jukka wants to create a daily summary generator",
            "created_at": "2025-09-28T14:20:00"
        }
    ]
}
```

**Output:**
```python
{
    "merge_edges": True,
    "merged_edge_id": 1,
    "reasoning": "Same relationship between same entities. Sentences convey identical intent.",
    "confidence": 0.88
}
```

**Edge Creation:**
If no merge, create new edge with:
- `source_id`, `target_id` - Node database IDs
- `relationship_type` - Normalized relationship name
- `relationship_descriptor` - Natural language description
- `sentence` - Source sentence
- `original_message_timestamp` - When relationship was mentioned
- `original_message_id` - Provenance
- `sentence_id` - Which sentence this came from
- `confidence`, `importance` - Quality metrics
- `source` - Data source (chat/email/slack)

### 6. Database Commit

After processing each conversation:

```python
# 1. Create/merge nodes
for node in nodes:
    node_obj, status = kg_utils.add_node(...)
    # status is "created" or "merged"

# 2. Create/merge edges
for edge in edges:
    edge_obj, status = kg_utils.safe_add_relationship_by_id(...)
    # status is "created" or "merged"

# 3. Commit transaction
kg_utils.session.commit()

# 4. Mark messages as processed
mark_logs_as_processed(block_ids)
```

**Detailed Logging:**
```
================================================================================
💾 SAVING NEW NODE TO DATABASE
================================================================================
🏷️  LABEL: daily summary feature
🔖 NODE_TYPE: Goal
📝 DESCRIPTION: 
🏷️  ALIASES: ['summary feature']
📂 CATEGORY: Feature Development
📋 ATTRIBUTES: {}
📅 START_DATE: 2025-09-29 00:00:00
📅 END_DATE: None
📊 START_DATE_CONFIDENCE: 0.9
📊 END_DATE_CONFIDENCE: 0.0
⏰ VALID_DURING: September 2025
🏷️  HASH_TAGS: ['#feature', '#development']
🔍 SEMANTIC_TYPE: software_feature
🎯 GOAL_STATUS: planned
📊 CONFIDENCE: 0.85
⭐ IMPORTANCE: 0.7
📂 SOURCE: processed_entity_log
================================================================================
✅ NODE DEBUG: CREATED node 'daily summary feature' (ID: uuid-789)
```

## Processing Flow Summary

```
FOR each window in log:
    1. Get 20 messages
    2. Find conversation boundaries
    3. Determine optimal window split
    
    FOR each conversation in window:
        4. Parse into atomic sentences
        
        IF sentences > 5:
            FOR each chunk of 5 sentences:
                5. Extract facts (nodes + edges)
                6. Enrich with metadata
                7. Process nodes (create/merge)
                8. Process edges (create/merge)
                9. Commit this chunk
        ELSE:
            5. Extract facts (nodes + edges)
            6. Enrich with metadata
            7. Process nodes (create/merge)
            8. Process edges (create/merge)
            9. Commit this conversation
        
        10. Mark messages as processed
    
    11. Advance window
    12. Commit processed message IDs
```

## Conversation Boundary Handling

### Overlap Merging

If boundaries overlap, merge them:

```python
# Input boundaries
Conv 1: msg_0 → msg_5
Conv 2: msg_3 → msg_8  # Overlaps with Conv 1

# Merged
Conv 1: msg_0 → msg_8  # Take min start, max end
```

### Fallback Strategy

If no conversations found:
```python
# Create conservative fallback chunks (10 messages each)
for start in range(0, boundary, 10):
    end = min(start + 9, boundary - 1)
    conversations.append({
        "start_id": f"msg_{start}",
        "end_id": f"msg_{end}",
        "target_message_id": f"msg_{end}"
    })
```

Prevents data loss when boundary detection fails.

### Filtered Messages

Messages marked as `should_process: False` by boundary agent:
- HTML content
- System messages
- Non-conversational content

These are immediately marked as processed without knowledge extraction.

## Data Integrity

### Orphaned Node Detection

After edge processing:
```python
for temp_id, node in node_map.items():
    has_edges = any(e.source == temp_id or e.target == temp_id for e in edges)
    if not has_edges:
        raise RuntimeError(f"Node {node.label} has no edges!")
```

**Why?**
- Every node should be connected to something
- Orphaned nodes indicate extraction errors
- Better to fail than pollute graph with disconnected nodes

### Transaction Safety

```python
try:
    # Process nodes
    # Process edges
    kg_utils.session.commit()
    print("SUCCESS: Transaction committed")
except Exception as e:
    kg_utils.session.rollback()
    print(f"ERROR: Rollback due to {e}")
    raise
```

All-or-nothing commits prevent partial state.

## Performance Optimizations

### Batching Strategy
- Process 100-200 messages per batch
- Commit after each window (not each conversation)
- Mark processed messages incrementally

### Chunking Strategy
- Split long conversations into 5-sentence chunks
- Prevents LLM context overflow
- Maintains extraction quality

### Caching
- Node embeddings cached in database
- Edge embeddings calculated once
- Similarity search uses vector indexes

## Monitoring

### Progress Tracking
```python
print(f"🎯 TOTAL FACT EXTRACTOR CALLS: {fact_extractor_call_count}")
print(f"📊 TOTAL WINDOWS PROCESSED: {windows_processed}")
print(f"📊 TOTAL CONVERSATIONS: {conversations_processed}")
```

### Per-Conversation Summary
```
📊 CONVERSATION PROCESSING SUMMARY
================================================================================
🏷️  NODES CREATED/MERGED: 3
   • Jukka (ID: uuid-123, Type: Entity)
   • daily summary feature (ID: uuid-456, Type: Goal)
   • morning schedule (ID: uuid-789, Type: State)
🔗 EDGES CREATED/MERGED: 2
   • Jukka -> WantsToBuild -> daily summary feature
   • daily summary feature -> ScheduledFor -> morning schedule
================================================================================
```

## Error Handling

### Common Errors

**1. No Sentences Parsed**
```python
if not parsed_items:
    print("--- No sentences parsed from conversation block")
    processed_log_ids.extend(block_ids)  # Mark as processed anyway
    continue
```

**2. Node Creation Failed**
```python
try:
    new_node, status = kg_utils.add_node(...)
except Exception as e:
    logger.exception(f"Failed to create node: {label}")
    raise  # Re-raise to trigger rollback
```

**3. Edge Missing Nodes**
```python
if not source_node or not target_node:
    edges_skipped_missing_nodes += 1
    logger.warning(f"Skipping edge: missing nodes")
    continue  # Skip this edge, continue with others
```

## Configuration

### Window Configuration
```python
WINDOW_SIZE = 20           # Adjust for conversation length
THRESHOLD_POSITION = 15    # Adjust for break detection sensitivity
```

### Chunking Configuration
```python
MAX_SENTENCES_PER_CHUNK = 5  # Adjust for LLM context limits
```

### Similarity Search
```python
TOP_K_SIMILAR = 5  # Number of candidates to consider for merging
```

## Best Practices

1. **Process in Batches:** Don't try to process everything at once
2. **Monitor Logs:** Watch for merge decisions and extraction quality
3. **Review Periodically:** Check graph structure for anomalies
4. **Tune Configuration:** Adjust window size based on data patterns
5. **Validate Provenance:** Ensure source tracking is accurate

## Related Documentation

- [Main Architecture](./KG_ARCHITECTURE.md)
- [Entity Resolution](./KG_ENTITY_RESOLUTION.md)
- [Agent Details](./KG_AGENTS.md)
- [Database Schema](./KG_DATABASE_SCHEMA.md)
