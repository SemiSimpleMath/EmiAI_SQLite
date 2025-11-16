# Progressive Taxonomy Classification with Counting

## 🎯 Concept

Instead of having a **single taxonomy classification** per node, track **multiple classifications with occurrence counts**. This enables:

1. **Emergence of Truth**: Most common classification rises to the top
2. **Multi-Dimensional Tagging**: Nodes can have multiple valid types
3. **Contextual Awareness**: Different contexts emphasize different aspects
4. **Temporal Evolution**: Track how classifications change over time
5. **Confidence Accumulation**: High-confidence classifications gain weight

---

## 📊 Example

### Before (Single Classification)
```
Node: "Jukka" (UUID: abc-123)
Taxonomy: entity > person > friend
```

### After (Multi-Dimensional with Counts)
```
Node: "Jukka" (UUID: abc-123)
Taxonomy Links:
  1. entity > person                      (count: 42, conf: 0.92, last: 2025-01-10) ← PRIMARY
  2. entity > person > friend             (count: 18, conf: 0.85, last: 2025-01-09)
  3. entity > person > software_developer (count: 12, conf: 0.90, last: 2025-01-08)
  4. entity > person > family_member      (count:  3, conf: 0.70, last: 2025-01-05)
```

**Interpretation:**
- Most commonly classified as "person" (generic, appears in many contexts)
- Also classified as "friend" in social contexts
- Also classified as "software_developer" in professional contexts
- Occasionally classified as "family_member" (might be confusion, low count)

---

## 🗄️ Schema

### `node_taxonomy_links` Table

```sql
CREATE TABLE node_taxonomy_links (
    node_id UUID NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    taxonomy_id INTEGER NOT NULL REFERENCES taxonomy(id) ON DELETE RESTRICT,
    
    -- Classification metadata
    confidence FLOAT DEFAULT 1.0 NOT NULL,
    source VARCHAR(100),
    
    -- NEW: Counting and temporal tracking
    count INTEGER DEFAULT 1 NOT NULL,              -- How many times classified
    last_seen TIMESTAMP WITH TIME ZONE,            -- Most recent classification
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    PRIMARY KEY (node_id, taxonomy_id)
);

CREATE INDEX ix_node_taxonomy_links_count ON node_taxonomy_links(count DESC);
CREATE INDEX ix_node_taxonomy_links_last_seen ON node_taxonomy_links(last_seen DESC);
```

---

## 🔄 Behavior

### First Classification
```python
# Sentence: "Jukka is a software developer"
classify_node("Jukka", "Entity", "Jukka is a software developer")
→ Creates link: (node_id=abc, taxonomy_id=123, count=1, conf=0.90)
```

### Second Classification (Same Type)
```python
# Sentence: "Jukka works as a software developer at Microsoft"
classify_node("Jukka", "Entity", "Jukka works as a software developer...")
→ Increments count: count=2, updates last_seen, adjusts confidence
```

### Third Classification (Different Type)
```python
# Sentence: "Jukka is a good friend"
classify_node("Jukka", "Entity", "Jukka is a good friend")
→ Creates new link: (node_id=abc, taxonomy_id=456, count=1, conf=0.85)
```

---

## 📈 Weighted Scoring

The `get_primary_taxonomy()` method uses a weighted score to determine the "best" taxonomy:

```python
score = (
    0.6 * count_score +      # 60%: Frequency (normalized by max count)
    0.3 * confidence_score + # 30%: Agent confidence
    0.1 * recency_score      # 10%: Days since last seen (decays over 30 days)
)
```

**Example:**
```
Taxonomy A: count=42, conf=0.80, last_seen=5 days ago  → score = 0.85
Taxonomy B: count=18, conf=0.95, last_seen=1 day ago   → score = 0.70
Taxonomy C: count= 3, conf=0.70, last_seen=60 days ago → score = 0.15

PRIMARY = Taxonomy A (highest score)
```

---

## 🛠️ API Methods

### `link_node_to_taxonomy(node_id, taxonomy_id, confidence, source)`
- **First call**: Creates link with `count=1`
- **Subsequent calls**: Increments `count`, updates `last_seen`, adjusts `confidence`

### `get_node_taxonomies(node_id, order_by="count")`
Returns all taxonomies for a node, ordered by:
- `"count"`: Most common first (default)
- `"confidence"`: Highest confidence first
- `"last_seen"`: Most recent first

### `get_primary_taxonomy(node_id)`
Returns the single "best" taxonomy using weighted scoring.

---

## 🎬 Migration Steps

1. **Run migration**:
   ```bash
   python add_count_and_last_seen_to_taxonomy_links.py
   ```

2. **Existing data**: All existing links will have `count=1` and `last_seen=NOW()`

3. **Future classifications**: New classifications will increment counts automatically

---

## 🌟 Use Cases

### 1. **Entity Evolution**
```
Week 1: "Martin" classified as "person" (count=5)
Week 2: "Martin is a software engineer" → adds "software_developer" (count=1)
Week 3: More work context → "software_developer" (count=8) overtakes "person" (count=5)
Week 4: PRIMARY taxonomy changes from "person" to "software_developer"
```

### 2. **Ambiguity Detection**
```
"Zoom" classified as:
  - platform (count=15)
  - meeting (count=12)
  - company (count=8)

→ Indicates the node label is ambiguous across contexts
```

### 3. **Context-Aware Labeling**
```
Query: "Get Jukka's profession"
→ Filter taxonomies to occupation branch
→ Return: "software_developer" (count=12, most common occupation)
```

---

## 💡 Future Enhancements

1. **Confidence Decay**: Lower confidence for old, unseen classifications
2. **Context Filtering**: Get taxonomy for specific context (e.g., "professional" vs "social")
3. **Taxonomy Migration**: Automatically merge similar taxonomies if counts converge
4. **Dashboard**: Visualize taxonomy distributions per node
5. **Anomaly Detection**: Flag nodes with conflicting taxonomies

---

## ✅ Summary

**Before**: One taxonomy per node → rigid, context-blind
**After**: Multiple taxonomies per node with counts → flexible, context-aware, self-improving

**Key Insight**: The graph "learns" the true nature of entities over time as evidence accumulates. 🧠✨

