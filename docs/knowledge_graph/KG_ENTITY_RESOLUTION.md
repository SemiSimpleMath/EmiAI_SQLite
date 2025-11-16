# Knowledge Graph: Entity Resolution (Stage 1)

## Overview

Entity Resolution is the first stage of the KG pipeline. It transforms raw conversational messages into clear, entity-resolved sentences where all pronouns, references, and ambiguous terms are replaced with explicit entity names.

## Purpose

Conversational data is full of ambiguity:
- "I want to work on it" - Who is "I"? What is "it"?
- "He said the meeting is tomorrow" - Who is "he"? Which meeting?
- "The UI needs improvement" - Which UI?

Entity resolution eliminates this ambiguity **before** knowledge extraction, making the downstream pipeline more accurate and reliable.

## Architecture

### File Location
`app/assistant/kg_core/log_preprocessing.py`

### Main Functions

#### `process_unified_log_chunks_with_entity_resolution()`
Main entry point for entity resolution processing.

**Parameters:**
- `chunk_size` (int): Number of messages per chunk (default: 8)
- `overlap_size` (int): Number of messages to overlap between chunks (default: 3)
- `source_filter` (str, optional): Filter by source (e.g., 'chat', 'slack')
- `role_filter` (list, optional): Filter by role (e.g., ['user', 'assistant'])
- `agent_version` (str): Version of entity_resolver agent (default: "1.0")

**Returns:**
```python
{
    'chunks_processed': int,      # Number of chunks processed
    'sentences_resolved': int,    # Total sentences resolved
    'records_created': int,       # Records saved to database
    'message': str                # Status message
}
```

#### `read_text_chunks_from_unified_log()`
Reads overlapping chunks from the unified log.

**Why Overlapping?**
- Prevents context loss at chunk boundaries
- Maintains entity reference chains
- Improves resolution quality

**Example:**
```
Chunk 1: [msg1, msg2, msg3, msg4, msg5, msg6, msg7, msg8]
                                    ↓ overlap (3 messages)
Chunk 2:                      [msg6, msg7, msg8, msg9, msg10, msg11, msg12, msg13]
```

#### `process_text_chunk_with_entity_resolver()`
Processes a single chunk with the entity_resolver agent.

**Smart Overlap Handling:**
- For overlapping chunks: Only processes NEW messages
- Uses previous resolved sentences as context
- Prevents duplicate processing

#### `save_resolved_sentences_to_processed_entity_log()`
Saves resolved sentences to the database with full provenance.

## Processing Flow

```
1. READ: Query unified_log for unprocessed messages
   ├─> Filter by source/role if specified
   ├─> Order by timestamp (oldest first)
   └─> Filter out HTML content

2. CHUNK: Create overlapping chunks
   ├─> Group messages into chunks of size N
   ├─> Overlap M messages between chunks
   └─> Track overlap metadata

3. RESOLVE: Process each chunk
   ├─> Combine messages into chunk text
   ├─> Add previous context from overlap
   ├─> Call entity_resolver agent
   └─> Extract resolved sentences

4. DEDUPLICATE: Remove duplicate sentences
   ├─> Track processed sentence keys
   ├─> Filter out sentences seen in overlap
   └─> Keep only new sentences

5. SAVE: Persist to database
   ├─> Match sentences to original messages
   ├─> Create ProcessedEntityLog records
   ├─> Mark original messages as processed
   └─> Commit transaction

6. REPEAT: Move to next chunk with overlap
```

## Entity Resolver Agent

### Agent Name
`knowledge_graph_add::entity_resolver`

### Input Format
```python
{
    "text": "user: I want to work on the UI today\nassistant: Great idea!",
    "previous_context": "Jukka discussed improving Emi's interface...",
    "original_message_timestamp": "2025-09-29T10:30:00"
}
```

### Output Format
```python
{
    "resolved_sentences": [
        {
            "original_sentence": "user: I want to work on the UI today",
            "resolved_sentence": "Jukka wants to work on the Emi UI today",
            "reasoning": "Resolved 'I' to 'Jukka' based on user context. Resolved 'the UI' to 'Emi UI' based on conversation context."
        },
        {
            "original_sentence": "assistant: Great idea!",
            "resolved_sentence": "Emi AI assistant agrees that working on the Emi UI is a great idea",
            "reasoning": "Added explicit subject 'Emi AI assistant' and expanded implicit reference to 'working on the Emi UI'."
        }
    ]
}
```

### Resolution Strategies

1. **Pronoun Resolution**
   - I/me/my → User's name (Jukka)
   - You/your → Target entity (Emi, other person)
   - He/she/they → Previously mentioned entities

2. **Reference Resolution**
   - "the UI" → "Emi UI"
   - "the meeting" → Specific meeting mentioned earlier
   - "it" → Most relevant entity from context

3. **Implicit Subject Addition**
   - "Great idea!" → "Emi AI assistant thinks it's a great idea"
   - "Working on it" → "Jukka is working on the Emi UI"

4. **Context Integration**
   - Uses previous_context to understand references
   - Maintains entity chains across chunks
   - Leverages temporal information

## Database Tables

### Input: unified_log

```sql
CREATE TABLE unified_log (
    id VARCHAR PRIMARY KEY,
    message TEXT NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    role VARCHAR NOT NULL,
    source VARCHAR NOT NULL,
    processed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### Output: processed_entity_log

```sql
CREATE TABLE processed_entity_log (
    id VARCHAR PRIMARY KEY,
    original_message_id VARCHAR NOT NULL,
    original_message_timestamp TIMESTAMP NOT NULL,
    role VARCHAR NOT NULL,
    original_sentence TEXT NOT NULL,
    resolved_sentence TEXT NOT NULL,
    reasoning TEXT,
    agent_version VARCHAR NOT NULL,
    processed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    FOREIGN KEY (original_message_id) REFERENCES unified_log(id)
);
```

## HTML Filtering

### Why Filter HTML?
Assistant responses sometimes include formatted content:
- Search results with `<div>` tags
- Lists with `<ul>` and `<li>` tags
- Formatted output with `<span>` tags

This content is not conversational and should not be added to the KG.

### Detection Logic
```python
def is_html_message(message: str) -> bool:
    if '<div' in message and 'class=' in message:
        return True
    if '<ul>' in message or '<li>' in message:
        return True
    if message.count('<div') > 2:
        return True
    return False
```

### Handling
- Filtered messages are marked as `processed = True`
- They skip entity resolution entirely
- Prevents noise in the knowledge graph

## Example Processing Session

### Input Messages (unified_log)
```
1. user: "I want to build a new feature"
2. assistant: "What feature do you have in mind?"
3. user: "A daily summary generator"
4. assistant: "Great! Let me help you plan it out"
5. user: "Can you add it to the task list?"
```

### Chunk 1 (messages 1-3)
**Combined Text:**
```
user: I want to build a new feature
assistant: What feature do you have in mind?
user: A daily summary generator
```

**Entity Resolver Output:**
```
1. "Jukka wants to build a new feature"
2. "Emi AI assistant asks Jukka what feature he has in mind"
3. "Jukka wants to build a daily summary generator"
```

### Chunk 2 (messages 2-5, with overlap)
**New Messages Only:** 4-5
**Previous Context:** Resolved sentences from Chunk 1

**Combined Text (new only):**
```
assistant: Great! Let me help you plan it out
user: Can you add it to the task list?
```

**Entity Resolver Output:**
```
4. "Emi AI assistant offers to help Jukka plan the daily summary generator"
5. "Jukka asks Emi AI assistant to add the daily summary generator to the task list"
```

### Saved to processed_entity_log
All 5 resolved sentences with:
- Original sentence
- Resolved sentence
- Reasoning
- Link to original message
- Role and timestamp

## Configuration

### Recommended Settings

**For Most Use Cases:**
```python
chunk_size = 8
overlap_size = 3
```

**For Long-Running Conversations:**
```python
chunk_size = 10
overlap_size = 4
```

**For Short Exchanges:**
```python
chunk_size = 5
overlap_size = 2
```

### Trade-offs

**Larger Chunks:**
- ✅ Better context for resolution
- ✅ Fewer API calls
- ❌ Higher token usage per call
- ❌ Slower per-chunk processing

**Smaller Chunks:**
- ✅ Faster processing
- ✅ Lower token usage per call
- ❌ Less context available
- ❌ More API calls total

**Larger Overlap:**
- ✅ Better context preservation
- ✅ Higher quality resolution
- ❌ More duplicate processing (filtered out)
- ❌ Slower overall

## Performance Metrics

### Typical Throughput
- **Messages/second:** ~5-10 (depends on LLM API speed)
- **Chunk processing time:** 2-5 seconds
- **API calls per chunk:** 1

### Bottlenecks
1. **LLM API calls** (main bottleneck)
2. Database writes (minimal impact)
3. Text processing (negligible)

### Optimization Tips
1. Use batch processing (multiple chunks in parallel) - future enhancement
2. Optimize chunk_size to balance quality and speed
3. Cache common entity resolutions - future enhancement
4. Use faster LLM models for non-critical cases

## Error Handling

### Common Errors

**1. No Sentences Resolved**
```python
if not resolved_sentences:
    print("⚠️  No sentences resolved for this chunk")
    # Chunk is skipped but messages are not marked as processed
```

**2. Sentence Matching Failed**
```python
if not original_message:
    print(f"⚠️  Skipping sentence that couldn't be matched: {original_sentence[:100]}...")
    continue  # Skip this sentence but continue processing
```

**3. Database Commit Failed**
```python
try:
    session.commit()
except Exception as e:
    session.rollback()
    print(f"❌ Error committing: {e}")
    raise
```

### Recovery Strategies

1. **Partial Success:** If some sentences are saved, mark messages as processed
2. **Total Failure:** Rollback transaction, leave messages unprocessed
3. **Retry Logic:** Can re-run the same function safely (idempotent)

## Monitoring

### Key Metrics to Track

```python
# Check processing progress
session = get_session()
total = session.query(UnifiedLog).count()
processed = session.query(UnifiedLog).filter_by(processed=True).count()
remaining = total - processed

print(f"Progress: {processed}/{total} ({processed/total*100:.1f}%)")
print(f"Remaining: {remaining}")
```

### Output Logs

```
🔄 Processing chunk 1/5 with 8 messages...
   📝 Processing full content (no overlap)
🔍 DEBUG: Sending to agent:
  Text to process: user: I want to build a new feature...
  Previous context: 
🔍 DEBUG: Agent returned 3 sentences:
  1. Original: user: I want to build a new feature...
     Resolved: Jukka wants to build a new feature...
✅ Resolved 3 new sentences, created 3 records
📝 Marked 8 messages as processed
```

## Best Practices

### 1. Choose Appropriate Chunk Size
- Start with default (8 messages, 3 overlap)
- Adjust based on conversation patterns
- Monitor resolution quality

### 2. Filter Appropriately
- Always filter HTML content
- Use role_filter to focus on relevant messages
- Use source_filter for specific channels

### 3. Monitor Quality
- Review resolved sentences periodically
- Check reasoning field for agent decisions
- Validate entity resolution accuracy

### 4. Handle Failures Gracefully
- Use try-except blocks
- Log errors for debugging
- Allow resumption after failures

### 5. Batch Processing
- Process in reasonable batches
- Don't try to process entire log at once
- Use incremental approach

## Testing

### Unit Tests
```python
# Test chunk reading
chunks = read_text_chunks_from_unified_log(chunk_size=3, overlap_size=1)
assert len(chunks) > 0
assert chunks[0]['chunk_size'] <= 3

# Test HTML filtering
assert is_html_message('<div class="result">test</div>') == True
assert is_html_message('normal message') == False
```

### Integration Tests
```python
# Test full processing
result = process_unified_log_chunks_with_entity_resolution(
    chunk_size=5,
    overlap_size=2,
    role_filter=['user', 'assistant']
)
assert result['chunks_processed'] > 0
assert result['records_created'] > 0
```

## Troubleshooting

### Issue: No chunks found
**Cause:** All messages are already processed
**Solution:** Check `processed` flag in unified_log

### Issue: All sentences filtered as duplicates
**Cause:** Overlap is too large, all sentences already seen
**Solution:** Reduce overlap_size or check deduplication logic

### Issue: Sentences don't match original messages
**Cause:** Role prefix stripping issue or text mismatch
**Solution:** Review sentence matching logic and role prefixes

### Issue: Agent returns empty results
**Cause:** Input text is too short/unclear or agent prompt issue
**Solution:** Review agent configuration and input text quality

## Related Documentation

- [Main Architecture](./KG_ARCHITECTURE.md)
- [Knowledge Graph Pipeline](./KG_PIPELINE_DETAILS.md)
- [Agent Details](./KG_AGENTS.md)
- [Database Schema](./KG_DATABASE_SCHEMA.md)
