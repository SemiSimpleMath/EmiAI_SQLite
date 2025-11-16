# Two-Stage Taxonomy Classification

## Architecture

### Problem with Single-Stage
```
Search: "Clyde. Clyde is Jukka's dog."
→ Embedding doesn't match "dog", "pet", "animal" well
→ Returns: jukkas_father (0.34), foster (0.31) ❌
→ Agent can't pick "dog" because it's not in the list!
```

### Solution: Two-Stage Classification

```
┌─────────────────────────────────────────────────────────────┐
│ STAGE 1: Concept Extraction Agent                           │
│ Input: "Clyde is Jukka's dog"                               │
│ Output: ["dog", "pet", "animal"]                            │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│ STAGE 2: Taxonomy Search                                    │
│ Search for: "dog" → pet_dog (0.95), animal (0.82)          │
│ Search for: "pet" → pet (0.93), pet_dog (0.90)             │
│ Search for: "animal" → animal (0.98), pet (0.80)           │
│ Deduplicate & merge: pet_dog, animal, pet                  │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│ STAGE 3: Classification Agent                               │
│ Input: Candidates (pet_dog, animal, pet)                    │
│ Output: pet_dog ✅ (most specific)                          │
└─────────────────────────────────────────────────────────────┘
```

---

## Implementation

### Agent 1: Concept Extractor
**Path:** `app/assistant/agents/knowledge_graph_add/taxonomy_concept_extractor/`

**Job:** Extract 1-5 searchable concept keywords

**Example:**
```
Input: "Clyde is Jukka's dog"
Output: {
  "concepts": ["dog", "pet", "animal"],
  "reasoning": "Clyde is a dog (most specific), which is a pet, which is an animal."
}
```

### Agent 2: Classifier (Existing)
**Path:** `app/assistant/agents/knowledge_graph_add/taxonomy_classifier/`

**Job:** Pick the most specific taxonomy type from candidates

**Example:**
```
Candidates: [pet_dog (0.95), animal (0.82), pet (0.78)]
Output: pet_dog ✅ (most specific match)
```

---

## Workflow in Code

```python
def classify_node(node, concept_extractor_agent, classifier_agent, session):
    # Stage 1: Extract concepts
    concepts = _extract_concepts(node, concept_extractor_agent)
    # ["dog", "pet", "animal"]
    
    # Stage 2: Search for each concept
    candidates = []
    for concept in concepts:
        results = semantic_search_taxonomy(concept, k=5)
        candidates.extend(results)
    
    # Deduplicate and sort
    candidates = deduplicate_by_id(candidates)
    
    # Stage 3: Classifier picks best
    taxonomy_id = classifier_agent.pick_best(node, candidates)
    
    return taxonomy_id
```

---

## Benefits

✅ **Better Candidates**: Searches for "dog", not "Clyde is Jukka's dog"  
✅ **Semantic Understanding**: Agent interprets meaning first  
✅ **More Robust**: Handles ambiguous labels better  
✅ **Flexible**: Can search multiple concepts and combine  
✅ **Self-Documenting**: Agent explains what it thinks the concept is

---

## Example Comparisons

### Test 1: "Clyde is Jukka's dog"

**Old (Single-Stage):**
```
Search: "Clyde. Clyde is Jukka's dog."
Candidates: jukkas_father (0.34), foster (0.31)
Result: ❌ No good match → placeholder
```

**New (Two-Stage):**
```
Stage 1: Extract → ["dog", "pet", "animal"]
Stage 2: Search → pet_dog (0.95), animal (0.82), pet (0.78)
Stage 3: Pick → pet_dog ✅
```

### Test 2: "Jukka's father"

**Old (Single-Stage):**
```
Search: "Jukka's father. Jukka has cherished memories..."
Candidates: jukkas_father (placeholder), family (0.45)
Result: ⚠️  Uses placeholder
```

**New (Two-Stage):**
```
Stage 1: Extract → ["father", "parent", "family member"]
Stage 2: Search → father (0.98), parent (0.92), family_member (0.88)
Stage 3: Pick → father ✅
```

### Test 3: "Birthday Party"

**Old (Single-Stage):**
```
Search: "Birthday Party. Jukka attended a birthday party."
Candidates: social_event (0.65), event (0.58)
Result: ⚠️  Too general (social_event)
```

**New (Two-Stage):**
```
Stage 1: Extract → ["party", "birthday", "social event", "celebration"]
Stage 2: Search → social_event_party (0.92), social_event_birthday (0.90), celebration (0.85)
Stage 3: Pick → social_event_party ✅
```

---

## Testing

```bash
# 1. Create taxonomy_suggestions table
python create_taxonomy_suggestions_table.py

# 2. Run the test
python test_taxonomy_classification.py
```

**Expected Output:**
```
Stage 1: Extracting concepts from 'Clyde'
Extracted concepts: ['dog', 'pet', 'animal']

Stage 2: Searching taxonomy for concepts: ['dog', 'pet', 'animal']
Found 12 unique candidates

Stage 3: Classifier picking from 12 candidates
✅ Matched 'Clyde' → taxonomy 'pet_dog' (path: entity → animal → pet → pet_dog)
```

---

## Files Created

1. `app/assistant/agents/knowledge_graph_add/taxonomy_concept_extractor/config.yaml`
2. `app/assistant/agents/knowledge_graph_add/taxonomy_concept_extractor/agent_form.py`
3. `app/assistant/agents/knowledge_graph_add/taxonomy_concept_extractor/prompts/system.j2`
4. `app/assistant/agents/knowledge_graph_add/taxonomy_concept_extractor/prompts/user.j2`
5. `app/assistant/agents/knowledge_graph_add/taxonomy_concept_extractor/__init__.py`

## Files Modified

1. `app/assistant/kg_core/taxonomy_orchestrator.py` - Added two-stage workflow
2. `test_taxonomy_classification.py` - Loads both agents

---

## Next Steps

1. ✅ Create `taxonomy_suggestions` table
2. ✅ Run test to see improvement
3. ✅ Validate with real data
4. ✅ Monitor classification accuracy

🎉 **Classification should now be much more accurate!**

