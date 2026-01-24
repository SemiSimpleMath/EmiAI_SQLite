# Sleep Segment Management - Missing Features

## Current Limitations

### 1. No "Going Back to Sleep" Support
**Problem:**
- Wake up at 3 AM, go back to sleep until 7 AM
- System records: Sleep segment ends at 3 AM
- No way to say "actually, I went back to sleep"

**Current behavior:**
```
Sleep: 11 PM → 3 AM (4 hours)
[User returns from AFK at 3 AM]
System: "Good morning! Day started at 3 AM"
User: "No, I'm going back to sleep"
System: Cancels day start, but sleep segment already ended at 3 AM
```

**What should happen:**
```
Sleep: 11 PM → 3 AM → 7 AM (8 hours total, with brief interruption)
```

### 2. No Sleep Segment Editing
**Problem:**
- Sleep segments in database can't be edited/merged/deleted
- Mistakes are permanent
- Brief wake-ups fragment sleep incorrectly

**Examples of needed edits:**
- Merge two segments (3 AM false wake)
- Delete a segment (system detected wrong activity as sleep)
- Adjust times (woke at 7:05, not 7:00)
- Change source (was user_chat, should be afk_detection)

### 3. Brief Wake-ups vs Real Wake-ups
**Problem:**
- No distinction between:
  - **Brief wake**: 5 min bathroom trip at 3 AM
  - **Real wake**: Getting up for the day at 7 AM

**Current logic:**
- ANY AFK return during sleep window triggers potential day start
- No grace period for brief wake-ups

## Proposed Solutions

### Solution 1: "Continuation" Segments
When user says "going back to sleep":
1. Keep previous segment open-ended (no end_time yet)
2. When they wake up again, set the end_time
3. Or create a new segment with `continuation_of=previous_segment_id`

**Database change:**
```python
class SleepSegment(Base):
    # ... existing fields ...
    continuation_of = Column(Integer, ForeignKey('sleep_segments.id'), nullable=True)
    is_interruption = Column(Boolean, default=False)  # Brief wake, not real wake
```

**UI/Chat:**
- Agent detects: "I'm going back to sleep"
- System: Marks segment as interrupted, waits for next AFK return
- Next wake: Agent asks "Are you up now or going back to sleep?"

### Solution 2: Grace Period for Brief Wake-ups
Don't trigger day start immediately on AFK return:

```python
# Config
early_wake_grace_period_minutes: 15  # Wait 15 min before assuming real wake

# Logic
if afk_return_during_sleep_window:
    if now < ambiguous_hour:
        # Before 5 AM: wait for grace period
        # If user goes AFK again within 15 min → part of same sleep
        # If user stays active > 15 min → real wake, trigger day start query
```

### Solution 3: Manual Sleep Segment Editor (UI)
Add a simple web UI for managing sleep segments:

**Route:** `/wellness/sleep-segments`

**Features:**
- View all sleep segments (last 7 days)
- Merge two segments
- Delete segment
- Edit start/end times
- Mark segment as "invalid" (exclude from calculations)

**API endpoints:**
```python
POST /api/sleep-segments/merge
POST /api/sleep-segments/delete/{id}
PUT  /api/sleep-segments/{id}
```

### Solution 4: Chat-Based Editing
Let user fix sleep via chat:

**User:** "Actually, I slept from 11 PM to 7 AM continuously"

**Agent response:**
1. Parse sleep times
2. Check existing segments in that window
3. Propose merge/replacement
4. User confirms
5. Update database

**Implementation:**
- New `sleep_editor` agent
- Schema: `{action: 'merge'|'replace'|'delete', segments: [...], new_segment: {...}}`
- Confirmation step before DB modification

## Recommended Approach

**Phase 1: Quick fixes (now)**
1. Add `is_interruption` flag to sleep segments
2. When user says "going back to sleep", mark latest segment as interruption
3. Sleep resource generator: Merge interrupted segments when calculating totals

**Phase 2: Better wake detection (next)**
1. Add grace period for brief wake-ups (15 min)
2. Don't trigger day start until grace period expires
3. If user goes AFK again within grace → merge segments

**Phase 3: Manual editing (later)**
1. Simple web UI for viewing/editing segments
2. Chat-based segment correction
3. Audit log for manual edits

## Code Impact

### Files to modify:
1. `app/models/afk_sleep_tracking.py` - Add `is_interruption`, `continuation_of` fields
2. `app/assistant/physical_status_manager/afk_sleep_db.py` - Add merge/edit functions
3. `app/assistant/physical_status_manager/day_start_manager.py` - Add grace period logic
4. `app/assistant/physical_status_manager/sleep_data_generator.py` - Merge interrupted segments
5. `app/agents/activity_tracker/` - Better "going back to sleep" detection

### Migration script:
```python
# Add new columns to sleep_segments table
ALTER TABLE sleep_segments ADD COLUMN is_interruption BOOLEAN DEFAULT FALSE;
ALTER TABLE sleep_segments ADD COLUMN continuation_of INTEGER REFERENCES sleep_segments(id);
```

## Example Flow (After Fix)

**Scenario: Wake at 3 AM, back to sleep, up at 7 AM**

```
11:00 PM: Go AFK
3:00 AM: Return from AFK
  → System: "You're up early (3 AM). Going back to sleep?"
  → User: "Yes, back to sleep"
  → System: Marks segment as interrupted, doesn't trigger day start

3:15 AM: Go AFK again (back to sleep)
7:00 AM: Return from AFK
  → System: "Good morning! How did you sleep?"
  → Triggers day start
  → Database: 2 segments, but marked as continuous sleep
  → Resource file: Shows 8 hours total sleep (11 PM → 7 AM)
```

## Priority

**HIGH:** 
- Grace period for brief wake-ups (prevents false day starts)
- `is_interruption` flag (fixes sleep calculations)

**MEDIUM:**
- Chat-based "I went back to sleep" support
- Segment merging in calculations

**LOW:**
- Web UI for manual editing (nice to have, not critical)
