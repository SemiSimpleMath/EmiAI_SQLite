# Temporal Knowledge Graph (TKG) Schema Specification

## 1. Core Philosophy

This document specifies the schema for a temporal knowledge graph designed to model a user's life. The architecture is built on three foundational principles to ensure data is structured, queryable, and contextually rich.

### Event-Centric Modeling is Standard
Nearly all facts and relationships are temporal. Therefore, the standard modeling pattern is to connect entities through an intermediary "State" or "Event" node that holds the temporal and contextual metadata. Direct entity-to-entity links are an exception reserved for truly timeless, immutable facts.

### Simplify Node Labels
Node labels follow a two-tier system:
- **Label**: Descriptive type labels (e.g., "Birthday Party", "Employment", "Wedding Ceremony") - these are specific but reusable categories
- **Semantic Label**: Descriptive labels with specific names in parentheses (e.g., "Birthday Party (Jukka)", "Employment (Google)", "Wedding Ceremony (Jukka & Katy)") - these provide context and specificity

### Enrich Edge Labels
Edge labels are descriptive, semantic verbs (e.g., is_employee_in, has_spouse_in). They explicitly define the role a node plays in a relationship, making the graph's structure inherently meaningful.

## 2. Node Schema

Nodes represent the entities, concepts, and occurrences within the graph.

### 2.1. Node Types

Each node must be assigned one of the following node_type values:

| Type | Description | Example |
|------|-------------|---------|
| **Entity** | A distinct person, place, organization, or object. | Person (Jukka), Organization (Google), Place (Irvine) |
| **State** (Primary Type) | A condition or relationship that exists over a time interval. | Marriage (Jukka & Katy), Employment (Google), Skill (Python) |
| **Event** | A discrete occurrence or action. Events often create, modify, or end States. | Birth (Jukka), Wedding (Jukka & Katy), Project Launch (EmiAI) |
| **Goal** | A future intention or desire. | Learn Spanish, Master Python, Travel to Japan |
| **Concept** | A reusable, abstract idea or field of knowledge. | Mathematics, Stoicism, Computer Science |
| **Property** (Rare) | An immutable attribute that has existed for an entity's entire existence. | Date of Birth (Jukka) |

### 2.2. Node Labeling Principle

All nodes follow a two-tier labeling system:

**Label (Descriptive Type):**
- **Descriptive**: Specific type labels (e.g., "Birthday Party", "Employment", "Wedding Ceremony")
- **Reusable**: These define the specific category/type, not the generic class
- **Title Case**: Use proper capitalization (e.g., "Birthday Party", "Wedding Ceremony", "Employment")
- **Specific**: More descriptive than generic "Event", "State", "Person"

**Semantic Label (Descriptive with Names):**
- **Descriptive**: Specific context with names in parentheses (e.g., "Birthday Party (Jukka)", "Wedding Ceremony (Jukka & Katy)")
- **Names in Parentheses**: All specific names go in parentheses for consistency
- **Contextual**: Provides the specific instance information
- **Format**: "Label (Specific Names)" (e.g., "Employment (Google)", "Marriage (Jukka & Katy)")

### 2.3. Labeling Examples

**Entity Nodes:**
- Label: "Person" → Semantic Label: "Person (Jukka)"
- Label: "Organization" → Semantic Label: "Organization (Google)"
- Label: "Place" → Semantic Label: "Place (Irvine)"

**Event Nodes:**
- Label: "Birthday Party" → Semantic Label: "Birthday Party (Jukka)"
- Label: "Wedding Ceremony" → Semantic Label: "Wedding Ceremony (Jukka & Katy)"
- Label: "Project Launch" → Semantic Label: "Project Launch (EmiAI)"

**State Nodes:**
- Label: "Employment" → Semantic Label: "Employment (Google)"
- Label: "Marriage" → Semantic Label: "Marriage (Jukka & Katy)"
- Label: "Skill" → Semantic Label: "Skill (Python)"

### 2.4. Node Metadata Fields

Every node in the graph must be enriched with the following fields. Use null for any unknown or inapplicable value.

| Field | Type | Description |
|-------|------|-------------|
| **label** | String | The descriptive type label (e.g., "Birthday Party", "Employment", "Wedding Ceremony"). |
| **semantic_label** | String | The descriptive label with names in parentheses (e.g., "Birthday Party (Jukka)", "Employment (Google)"). |
| **node_type** | String | One of the types defined in section 2.1. |
| **category** | String | A lower_snake_case keyword that specifies the node's role (e.g., family_relationship, career_milestone). |
| **start_date** | String / Null | The start of the node's validity in ISO 8601 format (YYYY-MM-DD). |
| **end_date** | String / Null | The end of the node's validity in ISO 8601 format (YYYY-MM-DD). |
| **start_date_confidence** | String / Null | actual, inferred, estimated. See Appendix A. |
| **end_date_confidence** | String / Null | actual, inferred, estimated. See Appendix A. |
| **valid_during** | String / Null | A qualitative description of the timeframe (e.g., "currently ongoing"). |
| **source_text** | String | The original, self-contained sentence from which the node was generated. Used for attribution. |
| **importance** | Float | A score from 0.0 to 1.0 representing the node's significance to the user. See Appendix B. |
| **confidence** | Float | A score from 0.0 to 1.0 representing the factual accuracy of the node's data. |
| **hash_tags** | List[String] | 1-3 lower_snake_case keywords for search and discovery. |
| **aliases** | List[String] | A list of alternative names for the node, if any. |
| **goal_status** | String / Null | active, completed, abandoned (for Goal nodes only). |
| **other properties** | Varies | Other specific data can be stored as properties (e.g., name: "Jukka", degree: "PhD"). |

## 3. Edge Schema

Edges represent the relationships between nodes.

### 3.1. Core Principle: No Direct Entity-to-Entity Connections

All relationships between two Entity nodes are temporal and must be mediated by a State or Event node. This is the fundamental rule of the temporal model.

**Incorrect Model:**
```
Person (Jukka) -[:married_to]-> Person (Katy)
```

**Correct Model:**
```
Person (Jukka) -[:has_spouse_in]-> Marriage (Jukka & Katy) <-[:has_spouse_in]- Person (Katy)
```

### 3.2. Edge Labeling Principle

Edge labels are the semantic glue of the graph and follow strict conventions:

- **Descriptive**: They are clear, semantic verbs.
- **lower_snake_case**: All edge labels use this format (e.g., is_employee_in).
- **Directional**: The direction of the edge is meaningful and should be consistent.

### 3.3. Standard Edge Labels

The following is a non-exhaustive list of recommended edge labels:

| Label | Source Node | Target Node | Description |
|-------|-------------|-------------|-------------|
| **is_employee_in** | Person (Jukka) | Employment (Google) | Connects a person to their employment state. |
| **occurred_at** | Employment (Google) | Organization (Google) | Connects an employment state to the company. |
| **has_spouse_in** | Person (Jukka) | Marriage (Jukka & Katy) | Connects a person to their marriage state. |
| **is_parent_in** | Person (Jukka) | Parenthood (Jukka & Child) | Connects a parent to a parenthood state. |
| **is_child_in** | Person (Child) | Parenthood (Jukka & Child) | Connects a child to a parenthood state. |
| **has_achievement** | Person (Jukka) | Educational Achievement (PhD) | Connects a person to an achievement. |
| **in_field** | Educational Achievement (PhD) | Concept (Computer Science) | Connects an achievement to its field. |
| **results_in** | Wedding (Jukka & Katy) | Marriage (Jukka & Katy) | Connects an event to the state it creates. |
| **is_birth_of** | Birth (Jukka) | Person (Jukka) | Connects a birth event to the person born. |

## 4. Preferred Labeling Standards

### 4.1. Preference Labels

For nodes that express personal preferences, likes, or dislikes, use the standardized format:

**Format:** `[Category] Preference`

**Examples:**
- **Food Preference** (not "Jukka likes pizza")
- **Music Preference** (not "Jukka loves jazz")
- **Travel Preference** (not "Jukka prefers beaches")
- **Entertainment Preference** (not "Jukka enjoys sci-fi movies")

**Semantic Labels:**
- Label: "Food Preference" → Semantic Label: "Food Preference (Jukka)"
- Label: "Music Preference" → Semantic Label: "Music Preference (Jukka)"
- Label: "Travel Preference" → Semantic Label: "Travel Preference (Jukka)"

**Usage Guidelines:**
- Use this format for any personal preference, taste, or liking
- The category should be broad enough to encompass related preferences
- Avoid specific items in the label (e.g., "Pizza Preference" is too specific)
- Store specific preferences in the node's description or attributes

## 5. Appendices

### Appendix A: Temporal Confidence Levels

- **actual**: Used for explicitly stated, precise dates (e.g., "on July 4, 2020").
- **estimated**: Used for approximations or vague timeframes (e.g., "around 2010," "last summer"). For a period like "in 2023," set start_date to 2023-01-01 and end_date to 2023-12-31.
- **inferred**: Used when a date is logically deduced, often from the message timestamp for a present-tense action ("I am watching TV").

### Appendix B: Importance Score Guidelines

- **1.0**: The user themselves (e.g., Jukka).
- **0.98**: Core Family (e.g., spouses, children, parents).
- **0.95**: Major Life Events & States (e.g., Marriage, Birth of a child).
- **0.90**: Close Social Circle.
- **0.70-0.89**: Significant Hobbies, Interests, Work.
- **0.60-0.69**: Secondary Events & Relationships (e.g., a vacation, a work project).
- **0.40-0.59**: Contextual Information (e.g., a restaurant where an event occurred).
- **< 0.40**: Transitory or Trivial Information (e.g., watching TV).