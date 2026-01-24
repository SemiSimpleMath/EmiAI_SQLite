# Switchboard Design: Sliding Window & Deduplication

## Overview

The SwitchboardRunner processes conversation windows to extract user preferences and feedback. This document explains how the sliding window works and how we prevent duplicate extractions.

## Sliding Window Strategy

### Overlapping Windows

The Switchboard uses **overlapping windows** to catch preferences that span multiple messages:

**Example:**
```
User: "you know what i like?"
Assistant: "what?"
User: "blueberries."
Assistant: "thats great."
User: "especially in smoothies."
```

This preference spans 5 messages. With overlapping windows:
- Window 1: messages 1-10 → might extract "user likes blueberries"
- Window 2: messages 8-17 (3 overlap) → sees full context, extracts "user likes blueberries especially in smoothies"

### Window Configuration

- **Window Size**: 10 messages per window
- **Overlap Size**: 3 messages overlap between windows
- **Rationale**: 
  - Large enough to capture context
  - Overlap ensures multi-turn preferences are caught
  - Small enough to process quickly
- **Configurable**: Can be adjusted in `SwitchboardRunner.__init__()`

## How We Slide the Window

```
Step 1: Get last_processed_message_id from SwitchboardState
        ↓
Step 2: Fetch window_size messages:
        - If first run: messages 1-10
        - If resuming: overlap_size messages before last_processed + window_size new messages
        ↓
Step 3: Check if window ending at message_id has been processed
        (via window_end_id in extracted_facts)
        ↓
Step 4: If not processed:
        - Run switchboard agent on full window (including overlap for context)
        - Filter out facts that reference already-extracted message IDs
        - Save new extracted facts with window_end_id
        - Update last_processed_message_id (advance by window_size - overlap_size)
        ↓
Step 5: Repeat from Step 2
```

### Example Flow with Overlap

```
Messages: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, ...]

Window 1: [1-10]        → window_end_id = 10, advance to 8
Window 2: [8-17]        → window_end_id = 17, advance to 15 (overlap: 8-10)
Window 3: [15-24]       → window_end_id = 24, advance to 22 (overlap: 15-17)
...
```

**Key**: We advance by `window_size - overlap_size = 7` messages each time, ensuring 3-message overlap.

## Preventing Duplicate Extractions

### Method 1: High Water Mark (`window_end_id`)

Each extracted fact stores `window_end_id` - the ID of the last message in the window that produced it.

**Before processing a window:**
```python
if self._check_window_already_processed(window_end_id):
    # Skip - this window was already processed
    return
```

**Why this works:**
- If we've processed window ending at message 17, we know that window has been analyzed
- We never reprocess the same window
- Even if the runner crashes and restarts, we resume from the last `window_end_id`

### Method 2: Message ID Deduplication

When saving facts from overlapping windows, we check if all message IDs referenced by a fact have already been extracted:

```python
# Get already-extracted message IDs
already_extracted_ids = self._get_already_extracted_message_ids()

# Filter facts that only reference already-extracted messages
if set(chunk_message_ids).issubset(already_extracted_ids):
    # Skip - this fact is a duplicate from overlap
    continue
```

**Why this works:**
- Overlapping windows will see the same messages
- If a fact only references messages we've already extracted, it's a duplicate
- We only save facts that reference new messages

### Method 3: Last Processed Message ID (`SwitchboardState`)

The `SwitchboardState` table (singleton row with `id=1`) tracks:
- `last_processed_message_id`: The last **new** message ID we've processed (not including overlap)
- `last_run_at`: Timestamp of last run

**How it works:**
```python
# Get where we left off
last_id = self._get_last_processed_message_id()  # e.g., "msg_10"

# Fetch window with overlap
messages = self._get_messages_for_window(start_after_message_id=last_id)
# Returns: [msg_8, msg_9, msg_10 (overlap), msg_11, msg_12, ... msg_17 (new)]

# After processing, advance by (window_size - overlap_size)
advance_to_id = new_messages[-1]['id']  # e.g., "msg_15"
self._update_last_processed_message_id(advance_to_id)
```

**Key**: We advance by `window_size - overlap_size` to ensure proper overlap in the next window.

## Handling Edge Cases

### What if a preference spans two windows?

**Example:**
```
Window 1: [1-10]
  User: "you know what i like?"
  Assistant: "what?"
  User: "blueberries."
  
Window 2: [8-17] (overlap: 8-10)
  User: "blueberries." (overlap)
  Assistant: "thats great." (overlap)
  User: "especially in smoothies." (new)
```

**Solution:**
- Window 1 might extract: "User likes blueberries" (partial, from messages 1-7)
- Window 2 sees full context (messages 8-17 including overlap) → extracts: "User likes blueberries especially in smoothies" (complete)
- Deduplication filters out Window 1's fact if it only references already-extracted messages
- Memory Manager processes the complete fact from Window 2

### What if the runner crashes mid-processing?

**Solution:**
- `window_end_id` check prevents reprocessing completed windows
- `last_processed_message_id` ensures we resume from the right place
- Even if a window was partially processed, the next run will skip it (via `window_end_id` check)

### What if messages are added out of order?

**Current assumption:** Messages are added to `unified_log` in timestamp order.

**If out-of-order messages occur:**
- The runner processes messages in timestamp order (`ORDER BY timestamp ASC`)
- Out-of-order messages will be processed when their timestamp is reached
- This could cause some windows to be processed out of order, but deduplication via `window_end_id` prevents issues

## Comparison with KG Pipeline

| Aspect | KG Pipeline | Switchboard |
|--------|-------------|-------------|
| **Window Size** | 20 messages | 10 messages |
| **Overlap** | Yes (3 messages) | Yes (3 messages) |
| **Why Overlap?** | Entity relationships can span boundaries | Preferences can span multiple messages |
| **Deduplication** | `processed` flag in `processed_entity_log` | `window_end_id` + message ID filtering |
| **Resumability** | `processed` flag | `last_processed_message_id` + `window_end_id` |
| **Boundary Detection** | Adaptive (finds conversation boundaries) | Fixed windows (no boundary detection needed) |

## Database Schema

### `extracted_facts` Table
```sql
CREATE TABLE extracted_facts (
    id TEXT PRIMARY KEY,
    category TEXT NOT NULL,              -- 'preference' or 'feedback'
    summary TEXT NOT NULL,               -- Extracted summary
    confidence REAL NOT NULL,            -- 0.0-1.0
    source_message_ids JSON NOT NULL,    -- All message IDs in window
    window_end_id TEXT NOT NULL,         -- High water mark
    processed BOOLEAN NOT NULL,          -- Processed by Memory Manager?
    created_at TIMESTAMP NOT NULL
);
```

### `switchboard_state` Table
```sql
CREATE TABLE switchboard_state (
    id INTEGER PRIMARY KEY DEFAULT 1,   -- Singleton row
    last_processed_message_id TEXT,     -- Last message ID processed
    last_run_at TIMESTAMP NOT NULL
);
```

## Summary

1. **Simple sliding window**: 10 messages at a time, no overlap
2. **High water mark**: `window_end_id` prevents reprocessing the same window
3. **State tracking**: `last_processed_message_id` enables resumable processing
4. **No explicit deduplication in agent**: The switchboard agent doesn't need to know what's been processed - deduplication happens at the database level
5. **Self-contained chunks**: Preferences are extracted as complete chunks, so overlap isn't needed

