# Knowledge Graph: Agent Details

## Overview

The KG system uses 8 specialized AI agents, each with a specific role in the knowledge extraction and management pipeline. This document details each agent's purpose, inputs, outputs, and behavior.

## Agent Registry Location

All agents are registered in: `app/assistant/agent_registry/`

Agent configurations typically include:
- Prompt templates (`.j2` files)
- Schema definitions (`.yaml` files)
- Output validation

## Stage 1 Agents

### 1. Entity Resolver Agent

**Registry Name:** `knowledge_graph_add::entity_resolver`

**Purpose:** Resolve pronouns, references, and ambiguous terms in conversational text

**Input Schema:**
```python
{
    "text": str,                        # Text to resolve (required)
    "previous_context": str,            # Context from previous chunks (optional)
    "original_message_timestamp": str   # ISO timestamp (required)
}
```

**Output Schema:**
```python
{
    "resolved_sentences": [
        {
            "original_sentence": str,    # Original text
            "resolved_sentence": str,    # Entity-resolved text
            "reasoning": str             # Why entities were resolved this way
        }
    ]
}
```

**Resolution Examples:**

1. **Pronoun Resolution:**
```
Input:  "I want to work on the UI"
Output: "Jukka wants to work on the Emi UI"
Reasoning: "Resolved 'I' to 'Jukka' (user context). Resolved 'the UI' to 'Emi UI' (project context)."
```

2. **Reference Resolution:**
```
Input:  "Let's add it to the task list"
Output: "Let's add the daily summary feature to the Emi task list"
Reasoning: "Resolved 'it' to 'daily summary feature' from previous context. Resolved 'task list' to 'Emi task list'."
```

3. **Implicit Subject Addition:**
```
Input:  "Sounds good!"
Output: "Emi AI assistant thinks the daily summary feature idea sounds good"
Reasoning: "Added explicit subject 'Emi AI assistant'. Expanded implicit reference to 'daily summary feature idea'."
```

**Key Behaviors:**
- Maintains entity chains across messages
- Uses previous_context for multi-chunk resolution
- Preserves original meaning while adding clarity
- Always provides reasoning for decisions

**Prompt Strategy:**
- Provides user name (Jukka) and assistant name (Emi AI)
- Includes previous resolved sentences as context
- Instructs to maintain natural language flow
- Emphasizes preserving original intent

---

## Stage 2 Agents

### 2. Conversation Boundary Agent

**Registry Name:** `knowledge_graph_add::conversation_boundary`

**Purpose:** Identify where conversations start and end in message sequences

**Input Schema:**
```python
{
    "messages": [
        {
            "id": str,         # Message ID (e.g., "msg_0")
            "role": str,       # "user" or "assistant"
            "message": str,    # Message text
            "timestamp": str   # ISO timestamp
        }
    ],
    "analysis_window_size": int  # Number of messages to analyze
}
```

**Output Schema:**
```python
{
    "message_bounds": [
        {
            "message_id": str,  # Target message (conversation end)
            "bounds": {
                "start_message_id": str,      # Conversation start
                "end_message_id": str,        # Conversation end
                "should_process": bool        # Whether to extract knowledge from this
            }
        }
    ]
}
```

**Detection Criteria:**

1. **Topic Changes:**
```
msg_0: "Let's build a new feature"
msg_5: "How's the weather today?"  ← Topic change detected
```

2. **Time Gaps:**
```
msg_0: timestamp 10:00 AM
msg_5: timestamp 2:00 PM  ← Large time gap
```

3. **Role Transitions:**
```
msg_0: user: "Hello"
msg_1: user: "Another question"  ← Multiple user messages without assistant response
```

4. **Explicit Markers:**
```
msg_5: "Let's move on to a different topic"  ← Explicit conversation marker
```

**Key Behaviors:**
- Can mark messages as `should_process: False` (HTML, system messages)
- Overlapping conversations are allowed (will be merged downstream)
- Provides analysis for every message in window
- Conservative approach: when uncertain, mark as new conversation

**Prompt Strategy:**
- Semantic analysis of content
- Temporal analysis of timestamps
- Conversational flow analysis
- Practical conversation units for knowledge extraction

---

### 3. Parser Agent

**Registry Name:** `knowledge_graph_add::parser`

**Purpose:** Break conversation text into atomic, semantically complete sentences

**Input Schema:**
```python
{
    "text": str,                        # Conversation text (required)
    "original_message_timestamp": str   # ISO timestamp (optional)
}
```

**Output Schema:**
```python
{
    "parsed_sentences": [
        {
            "sentence": str,              # Atomic sentence
            "sentence_type": str,         # "declarative", "question", "imperative"
            "entities_mentioned": [str]   # Entities in this sentence
        }
    ]
}
```

**Parsing Examples:**

1. **Complex Sentence Split:**
```
Input:  "Jukka wants to build a daily summary feature and it should run at 9 AM"
Output: 
  - "Jukka wants to build a daily summary feature"
  - "The daily summary feature should run at 9 AM"
```

2. **Preserving Context:**
```
Input:  "Jukka discussed the UI. He said it needs improvement. Emi agreed."
Output:
  - "Jukka discussed the Emi UI"
  - "Jukka said the Emi UI needs improvement"
  - "Emi AI assistant agreed that the Emi UI needs improvement"
```

3. **Question Handling:**
```
Input:  "Can you add the feature to the backlog?"
Output:
  - "Jukka asks Emi AI assistant to add the daily summary feature to the backlog"
```

**Key Behaviors:**
- Each sentence is self-contained (has subject + predicate)
- Maintains entity references throughout
- Converts questions to declarative statements
- Preserves temporal and causal relationships
- No information loss during splitting

**Prompt Strategy:**
- Atomic facts principle
- Entity resolution preservation
- Self-contained sentences
- Natural language flow

---

### 4. Fact Extractor Agent

**Registry Name:** `knowledge_graph_add::fact_extractor`

**Purpose:** Extract entities (nodes) and relationships (edges) from atomic sentences

**Input Schema:**
```python
{
    "text": [str],                      # List of atomic sentences (required)
    "original_message_timestamp": str   # ISO timestamp (optional)
}
```

**Output Schema:**
```python
{
    "nodes": [
        {
            "temp_id": str,        # Temporary ID (e.g., "temp_1")
            "label": str,          # Entity name
            "node_type": str,      # "Entity", "Event", "Goal", "State", "Property"
            "category": str,       # High-level category
            "sentence": str        # Source sentence
        }
    ],
    "edges": [
        {
            "source": str,                      # temp_id of source node
            "target": str,                      # temp_id of target node
            "label": str,                       # Relationship type (PascalCase)
            "relationship_descriptor": str,     # Natural language (e.g., "wants to build")
            "sentence": str                     # Source sentence
        }
    ]
}
```

**Node Types:**

1. **Entity** - Physical or abstract entities
   - People: "Jukka", "Emi AI assistant"
   - Organizations: "Development Team"
   - Concepts: "Machine Learning"

2. **Event** - Things that happened
   - "Jukka started working on the feature"
   - "Meeting scheduled for tomorrow"

3. **Goal** - Objectives or intentions
   - "Build a daily summary feature"
   - "Improve the UI"

4. **State** - Conditions or states of being
   - "The feature is in development"
   - "The system is operational"

5. **Property** - Attributes or characteristics
   - "The feature runs at 9 AM"
   - "The UI is user-friendly"

**Extraction Examples:**

```
Sentence: "Jukka wants to build a daily summary feature that runs every morning"

Nodes:
  1. temp_1: Jukka (Entity, Person)
  2. temp_2: daily summary feature (Goal, Feature)
  3. temp_3: every morning schedule (State, Schedule)

Edges:
  1. temp_1 --[WantsToBuild]--> temp_2
     Descriptor: "wants to build"
  2. temp_2 --[ScheduledFor]--> temp_3
     Descriptor: "runs"
```

**Key Behaviors:**
- Generates unique temp_ids for later merging
- Captures original sentence for provenance
- Extracts all entities mentioned
- Creates edges between related entities
- Normalizes relationship names (PascalCase)
- Preserves natural language descriptors

**Prompt Strategy:**
- Comprehensive entity extraction
- Relationship identification
- Node type classification
- Temporal awareness
- Provenance tracking

---

### 5. Metadata Enrichment Agent

**Registry Name:** `knowledge_graph_add::meta_data_add`

**Purpose:** Enrich nodes with temporal metadata, confidence scores, and semantic information

**Input Schema:**
```python
{
    "nodes": str,                       # JSON string of single node
    "resolved_sentence": str,           # Node's source sentence
    "message_timestamp": str            # Original message timestamp (CRITICAL for dates)
}
```

**Output Schema:**
```python
{
    "Nodes": [
        {
            "temp_id": str,
            
            # Temporal metadata (for Event, State, Goal)
            "start_date": str,                    # ISO date
            "end_date": str,                      # ISO date
            "start_date_confidence": float,       # 0-1
            "end_date_confidence": float,         # 0-1
            "valid_during": str,                  # Temporal qualifier
            
            # Semantic metadata (for State, Property)
            "semantic_type": str,                 # Fine-grained type
            
            # Goal metadata (for Goal)
            "goal_status": str,                   # "planned", "in_progress", "completed"
            
            # Quality metadata (for all)
            "confidence": float,                  # 0-1
            "importance": float,                  # 0-1
            
            # Organizational metadata
            "aliases": [str],                     # Alternative names
            "category": str,                      # High-level category
            "hash_tags": [str]                    # Relevant tags
        }
    ]
}
```

**Temporal Metadata Examples:**

1. **Explicit Date:**
```
Sentence: "Jukka started working on the feature on September 29th"
message_timestamp: "2025-09-29T10:30:00"

Output:
  start_date: "2025-09-29T00:00:00"
  start_date_confidence: 0.95
  end_date: null
  valid_during: "September 2025"
```

2. **Relative Date:**
```
Sentence: "The meeting is tomorrow"
message_timestamp: "2025-09-29T14:00:00"

Output:
  start_date: "2025-09-30T00:00:00"
  start_date_confidence: 0.85
  end_date: "2025-09-30T23:59:59"
  valid_during: "September 30, 2025"
```

3. **Ongoing State:**
```
Sentence: "The system is currently operational"
message_timestamp: "2025-09-29T10:00:00"

Output:
  start_date: null  (unknown when it started)
  end_date: null    (still ongoing)
  valid_during: "as of September 2025"
  start_date_confidence: 0.0
```

**Confidence & Importance Scoring:**

**Confidence (0-1):** How certain we are this entity/fact exists
- 0.9-1.0: Explicit statement ("Jukka is working on X")
- 0.7-0.9: Strong implication ("Jukka mentioned X")
- 0.5-0.7: Weak implication ("Jukka might work on X")
- 0.3-0.5: Speculation ("X could be useful")
- 0.0-0.3: Very uncertain

**Importance (0-1):** How significant this entity is
- 0.9-1.0: Core entities (people, main projects)
- 0.7-0.9: Important concepts (key features, goals)
- 0.5-0.7: Supporting entities (tools, methods)
- 0.3-0.5: Minor details (preferences, options)
- 0.0-0.3: Trivial mentions

**Semantic Type Examples:**

For State/Property nodes:
- "software_feature"
- "user_preference"
- "system_configuration"
- "temporal_schedule"
- "quality_attribute"

**Key Behaviors:**
- Processes ONE node at a time for focus
- Uses node's specific sentence (not full conversation)
- message_timestamp is CRITICAL for relative date resolution
- Conservative with date confidence
- Provides reasoning for all decisions
- Entity nodes don't get valid_during (reset to null)

**Prompt Strategy:**
- Temporal extraction guidelines
- Confidence calibration examples
- Importance criteria
- Semantic categorization
- Conservative date handling

---

### 6. Node Merger Agent

**Registry Name:** `knowledge_graph_add::node_merger`

**Purpose:** Decide whether a new node should merge with an existing node or be created as new

**Input Schema:**
```python
{
    "new_node_data": {
        "label": str,
        "node_type": str,
        "category": str,
        # ... other node fields
    },
    "existing_node_candidates": [
        {
            "candidate_id": int,          # 1-based ID for selection
            "node_id": str,               # Database UUID
            "label": str,
            "node_type": str,
            "category": str,
            "similarity_score": float,    # 0-1 from embedding similarity
            # ... other node fields
        }
    ]
}
```

**Output Schema:**
```python
{
    "merge_nodes": bool,           # True to merge, False to create new
    "merged_node_id": int,         # candidate_id to merge with (if merge_nodes=True)
    "reasoning": str,              # Explanation
    "confidence": float            # 0-1
}
```

**Decision Criteria:**

1. **Same Entity:**
```
New: "daily summary feature"
Existing: "daily summary generator"
Decision: MERGE (same feature, different phrasing)
```

2. **Different Entities:**
```
New: "daily summary feature"
Existing: "weekly report feature"
Decision: CREATE NEW (different features)
```

3. **Ambiguous:**
```
New: "the UI" (generic)
Existing: "Emi UI" (specific)
Decision: MERGE if context confirms, else CREATE NEW
```

**Well-Known Entities:**

Special handling for:
- "jukka", "juka" → Always merge
- "emi", "emi_ai", "emi ai assistant" → Always merge
- Other common entities configurable

**Key Behaviors:**
- High threshold for merging (avoid false positives)
- Uses both label similarity and semantic similarity
- Considers node_type (only merge same types)
- Provides detailed reasoning
- Confidence score reflects certainty

**Prompt Strategy:**
- Entity identity criteria
- Common variations handling
- Context-dependent decisions
- Conservative merging approach

---

### 7. Node Data Merger Agent

**Registry Name:** `knowledge_graph_add::node_data_merger`

**Purpose:** Intelligently combine information from new node into existing node

**Input Schema:**
```python
{
    "existing_node_data": {
        "label": str,
        "aliases": [str],
        "hash_tags": [str],
        "semantic_type": str,
        "goal_status": str,
        "valid_during": str,
        "category": str,
        "start_date": str,              # ISO or null
        "end_date": str,                # ISO or null
        "start_date_confidence": float,
        "end_date_confidence": float,
        "confidence": float,
        "importance": float
    },
    "new_node_data": {
        # Same fields as existing_node_data
    }
}
```

**Output Schema:**
```python
{
    "merged_aliases": [str],                    # Union + new label if different
    "merged_hash_tags": [str],                  # Union of both
    "unified_semantic_type": str,               # More specific one
    "unified_goal_status": str,                 # Latest/most specific
    "unified_valid_during": str,                # Merged temporal qualifiers
    "unified_category": str,                    # More specific one
    "unified_start_date": str,                  # Earlier date (conservative)
    "unified_start_date_confidence": float,     # Corresponding confidence
    "unified_end_date": str,                    # Later date (conservative)
    "unified_end_date_confidence": float,       # Corresponding confidence
    "reasoning": str,                           # Explanation of choices
    "merge_confidence": float                   # 0-1
}
```

**Merge Strategies:**

1. **Aliases:** Union + new label
```
Existing: ["summary feature"]
New label: "daily summary generator"
Result: ["summary feature", "daily summary generator"]
```

2. **Dates:** Conservative approach
```
Existing: start_date="2025-09-28" (confidence 0.8)
New:      start_date="2025-09-29" (confidence 0.9)
Result:   start_date="2025-09-28" (earlier date, confidence 0.8)
```

3. **Category:** More specific
```
Existing: "Feature"
New:      "Feature Development"
Result:   "Feature Development" (more specific)
```

4. **Confidence/Importance:** Take maximum
```
Existing: confidence=0.7, importance=0.6
New:      confidence=0.85, importance=0.5
Result:   confidence=0.85, importance=0.6
```

**Special Handling:**

- **Entity nodes:** Reset valid_during to null (entities don't have temporal bounds)
- **Valid_during:** Truncate if > 100 chars (should be simple temporal qualifier)
- **Semantic_type:** More specific type wins
- **Goal_status:** Latest status (more recent information)

**Key Behaviors:**
- Never loses information (additive approach)
- Conservative with temporal data
- Detailed before/after logging
- Tracks which fields changed
- Preserves provenance (source field NOT updated)

**Prompt Strategy:**
- Information preservation
- Conflict resolution rules
- Specificity preference
- Conservative temporal handling

---

### 8. Edge Merger Agent

**Registry Name:** `knowledge_graph_add::edge_merger`

**Purpose:** Decide whether a new edge should merge with an existing edge or be created as new

**Input Schema:**
```python
{
    "new_edge_data": {
        "relationship_type": str,
        "source_node_label": str,
        "target_node_label": str,
        "sentence": str
    },
    "existing_edge_candidates": [
        {
            "candidate_id": int,              # 1-based ID for selection
            "edge_id": str,                   # Database UUID
            "relationship_type": str,
            "source_label": str,
            "target_label": str,
            "sentence": str,
            "created_at": str                 # ISO timestamp
        }
    ]
}
```

**Output Schema:**
```python
{
    "merge_edges": bool,           # True to merge, False to create new
    "merged_edge_id": int,         # candidate_id to merge with (if merge_edges=True)
    "reasoning": str,              # Explanation
    "confidence": float            # 0-1
}
```

**Decision Criteria:**

1. **Same Relationship:**
```
New: Jukka --[WantsToBuild]--> daily summary feature
Existing: Jukka --[WantsToBuild]--> daily summary generator
Decision: MERGE (same intent, nodes will be merged)
```

2. **Different Relationships:**
```
New: Jukka --[WantsToBuild]--> daily summary feature
Existing: Jukka --[IsWorkingOn]--> daily summary feature
Decision: CREATE NEW (different relationship types)
```

3. **Temporal Changes:**
```
New: "Jukka completed the feature" (Sept 30)
Existing: "Jukka is working on the feature" (Sept 28)
Decision: CREATE NEW (relationship evolved over time)
```

**Key Behaviors:**
- Considers relationship_type, source, target, and semantic meaning
- Higher threshold than node merging (edges are cheaper to store)
- Temporal context matters (relationships evolve)
- Provides detailed reasoning

**Prompt Strategy:**
- Relationship identity criteria
- Temporal evolution handling
- Semantic equivalence detection
- Conservative merging for safety

---

## Agent Interaction Patterns

### Sequential Processing
```
entity_resolver → parser → fact_extractor → meta_data_add → mergers
```

### Parallel Opportunities
- Metadata enrichment (one node at a time, but could parallelize nodes)
- Similarity search (independent lookups)
- Edge processing (independent of other edges)

### Feedback Loops
- Merger agents update nodes, affecting future similarity searches
- Entity resolution improves with more data in graph
- Boundary detection learns from conversation patterns

## Agent Prompt Engineering

### Common Patterns

1. **Few-Shot Examples:** All agents use examples in prompts
2. **Structured Output:** JSON schemas enforce consistency
3. **Reasoning Required:** Agents must explain decisions
4. **Conservative Defaults:** When uncertain, choose safer option
5. **Context Awareness:** Use previous context and timestamps

### Prompt Templates

Located in agent registry directories:
- `*.j2` files contain Jinja2 templates
- `*.yaml` files define schemas and examples
- Prompts are dynamically rendered with context

## Agent Performance

### Typical Response Times
- Entity Resolver: 2-4 seconds
- Conversation Boundary: 1-2 seconds
- Parser: 1-2 seconds
- Fact Extractor: 2-5 seconds
- Metadata Add: 1-3 seconds per node
- Merger Agents: 1-2 seconds

### Token Usage
- Entity Resolver: 500-1500 tokens
- Fact Extractor: 800-2000 tokens
- Metadata Add: 600-1200 tokens per node
- Merger Agents: 400-800 tokens

## Debugging Agents

### Enable Verbose Logging
```python
import logging
logging.getLogger('app.assistant').setLevel(logging.DEBUG)
```

### Inspect Agent Input/Output
```python
print(f"Agent input: {agent_input}")
result = agent.action_handler(Message(agent_input=agent_input))
print(f"Agent output: {result.data}")
```

### Test Individual Agents
```python
from app.assistant.ServiceLocator.service_locator import DI

agent = DI.agent_factory.create_agent("knowledge_graph_add::fact_extractor")
result = agent.action_handler(Message(agent_input={
    "text": ["Jukka wants to build a feature"]
}))
print(result.data)
```

## Related Documentation

- [Main Architecture](./KG_ARCHITECTURE.md)
- [Entity Resolution](./KG_ENTITY_RESOLUTION.md)
- [Pipeline Details](./KG_PIPELINE_DETAILS.md)
- [Configuration Guide](./KG_CONFIGURATION.md)
