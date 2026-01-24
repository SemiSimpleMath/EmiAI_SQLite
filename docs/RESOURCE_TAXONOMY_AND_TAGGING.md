# Resource File Taxonomy and Tag-Based Routing

## Overview

Resource files self-organize by declaring **tag subscriptions** in their YAML front-matter. When the Memory Manager processes a new fact, it tags the fact, and the tag router automatically finds all files subscribing to those tags.

## Tag Taxonomy (10 Broad Categories)

| Tag | Description | Example Facts |
|-----|-------------|---------------|
| `food` | Food preferences, likes/dislikes, dietary restrictions | "User loves Thai food", "Allergic to peanuts" |
| `drink` | Beverage preferences (coffee, tea, alcohol) | "Prefers coffee in morning", "No caffeine after 4pm" |
| `routine` | Daily routines, schedules, timing preferences | "Wakes at 7am", "Prefers meetings after 10am" |
| `health` | Chronic conditions, pain, physical accommodations | "Has back pain", "Needs standing breaks" |
| `wellness` | Exercise, sleep, breaks, self-care | "Likes morning walks", "Needs 8h sleep" |
| `communication` | Communication style, language, notification prefs | "Prefers concise responses", "Keep messages brief" |
| `entertainment` | Movies, games, TV shows, hobbies | "Likes The Walking Dead", "Enjoys Disco Elysium" |
| `family` | Family logistics, visits, travel | "Dad visiting this week", "Katy in Sacramento" |
| `schedule` | Calendar preferences, meeting habits | "Needs buffer between meetings", "Video calls drain energy" |
| `general` | Miscellaneous preferences that don't fit elsewhere | Any other preference |

## Tagging Rules

1. **Assign 1-2 tags maximum** per fact (focus on primary topic)
2. **Most specific tag wins** (e.g., `food` over `general`)
3. **Multiple files can subscribe to same tag** (fan-out routing)
4. **Files declare their own subscriptions** (self-organizing)

## File Subscription Examples

### Long-term Preference Files

```yaml
---
resource_id: resource_user_food_prefs
subscriptions:
  - food
  - drink
---
```

```yaml
---
resource_id: resource_user_health
subscriptions:
  - health
  - wellness
  - pain
---
```

```yaml
---
resource_id: resource_user_routine
subscriptions:
  - routine
  - schedule
  - timing
---
```

```yaml
---
resource_id: resource_user_general_prefs
subscriptions:
  - communication
  - entertainment
  - hobbies
  - general
---
```

### Short-term Operational Files

```yaml
---
resource_id: resource_context_ephemeral
subscriptions:
  - ephemeral
  - temporary
---
```

```yaml
---
resource_id: resource_family_logistics
subscriptions:
  - family
  - travel
---
```

## Routing Flow

```
1. Switchboard extracts fact from chat
   ↓
2. Memory Planner reviews and assigns tags
   Example: "User likes Thai food" → tags: ['food']
   ↓
3. Tag Router finds subscribing files
   → resource_user_food_prefs.md (subscribes to 'food')
   ↓
4. Memory Manager updates matched file(s)
```

## Temporal Scope (Lifecycle Management)

- **`active`**: Current, actionable facts (route to files)
- **`chronic`**: Long-term facts (route to files)
- **`historical`**: Old, non-actionable (skip routing)

## Benefits

1. **Self-organizing**: Files declare what they want, no central config
2. **Flexible**: Easy to add new files or tags
3. **Fan-out**: One fact can update multiple files
4. **Discoverable**: Can inspect subscriptions by reading YAML front-matter

