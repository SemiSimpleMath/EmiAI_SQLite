# AFK & Sleep Database Migration - Complete

## What Was Done

### 1. Database Models Created
**File:** `app/models/afk_sleep_tracking.py`

Two new SQLAlchemy models:

#### `AFKEvent` Table
- Tracks user computer activity state changes
- Fields:
  - `timestamp`: When the event occurred
  - `event_type`: 'went_afk', 'returned', 'potentially_afk'
  - `idle_seconds`: How long user was idle
  - `duration_minutes`: For 'returned' events, how long was AFK
- Indexed on `timestamp` and `event_type` for fast queries

#### `SleepSegment` Table
- Tracks continuous sleep periods
- Fields:
  - `start_time`: When sleep started (bedtime)
  - `end_time`: When sleep ended (wake time), NULL if ongoing
  - `duration_minutes`: Sleep duration
  - `source`: How detected ('afk_detection', 'user_chat', 'cold_start_assumed', 'manual')
  - `raw_mention`: User's original text (if from chat)
- Indexed on `start_time`, `end_time`, and `source` for fast queries

### 2. Database Access Layer Created
**File:** `app/assistant/physical_status_manager/afk_sleep_db.py`

High-level functions to abstract database operations:

#### AFK Event Operations
- `record_afk_event()`: Write new AFK events
- `get_recent_afk_events(hours)`: Get recent AFK history
- `get_last_afk_return()`: Get most recent return from AFK
- `cleanup_old_afk_events(days)`: Delete old AFK records

#### Sleep Segment Operations
- `record_sleep_segment()`: Write new sleep segments
- `update_sleep_segment_end()`: Mark sleep end time (wake up)
- `get_sleep_segments_last_24_hours()`: Get recent sleep history
- `get_ongoing_sleep_segment()`: Get current ongoing sleep (end_time=NULL)
- `calculate_last_night_sleep()`: Compute total sleep, quality, etc.
- `cleanup_old_sleep_segments(days)`: Delete old sleep records

#### Combined Utilities
- `get_afk_and_sleep_summary()`: Get everything in one call
- `cleanup_old_data()`: Clean up both tables

### 3. Migration Script Created
**File:** `migration_scripts/create_afk_sleep_tables.py`

Features:
- Creates the database tables
- Migrates existing sleep data from `resource_user_sleep_current.json`
- Backs up JSON files before migration
- Command-line flags:
  - `--migrate-json`: Migrate existing data
  - `--reset`: Drop and recreate tables

### 4. Migration Executed
- Tables created successfully in `emi.db`
- Existing sleep data migrated (1 segment)
- JSON files backed up to `resources/backups/afk_sleep_migration_20260106_173124/`

## Current Status

✅ **Database tables are ready to use**
- `afk_events` table: 0 records (no historical AFK data to migrate)
- `sleep_segments` table: 1 record (migrated from JSON)

## Next Steps

### Phase 1: Update AFKMonitor
**File:** `app/assistant/physical_status_manager/afk_monitor.py`

Current behavior: Tracks AFK state in memory only

Changes needed:
1. Import `record_afk_event` from `afk_sleep_db.py`
2. Call `record_afk_event()` whenever state changes:
   - When user goes AFK: `record_afk_event(now, 'went_afk', idle_seconds=...)`
   - When user returns: `record_afk_event(now, 'returned', duration_minutes=...)`
3. Keep in-memory state for real-time checks (don't change current logic)
4. Database writes are supplemental (historical record)

### Phase 2: Update SleepSegmentTracker
**File:** `app/assistant/physical_status_manager/sleep_segment_tracker.py`

Current behavior: Reads/writes `resource_user_sleep_current.json`

Changes needed:
1. Import functions from `afk_sleep_db.py`
2. Replace JSON file operations:
   - `load_sleep_data()` → `get_sleep_segments_last_24_hours()`
   - `write_sleep_data()` → `record_sleep_segment()`
   - `calculate_last_night_sleep()` → `calculate_last_night_sleep()` (already implemented in DB layer)
3. Remove JSON file I/O
4. Update `process_sleep_events()` to write to DB instead of JSON

### Phase 3: Update PhysicalStatusManager
**File:** `app/assistant/physical_status_manager/physical_status_manager.py`

Current behavior: Reads sleep data from `SleepSegmentTracker` methods

Changes needed:
1. Import `get_afk_and_sleep_summary` from `afk_sleep_db.py`
2. Update `_build_context_for_inference()`:
   - Replace `self.sleep_segment_tracker.get_sleep_segments_last_24_hours()` 
   - With `get_sleep_segments_last_24_hours()` from DB layer
3. Update `_run_daily_context_tracker()` similarly
4. No other changes needed (abstraction layer handles it)

### Phase 4: Cleanup & Testing
1. Test AFK detection writes to database
2. Test sleep segment recording
3. Test wake-up detection
4. Test day boundary logic
5. Verify agents receive correct sleep data
6. Once confirmed working, archive or delete:
   - `resources/resource_user_sleep_current.json`
7. Add periodic cleanup job:
   - Call `cleanup_old_data(days=7)` daily
   - Keep last 7 days of AFK/sleep history

## Benefits of This Architecture

### Clear Data Ownership
- **AFK Events** = raw computer activity data
- **Sleep Segments** = interpreted sleep periods (from AFK + user chat)
- **Physical Status** = computed summary for agents (from sleep segments)

### Better Queries
- "Show me all AFK periods > 30 minutes in the last week"
- "What nights did I sleep < 6 hours this month?"
- "How often do I take naps?"

### Easier Debugging
- Full history in database (can query with SQL)
- Clear source attribution (how was each sleep segment detected?)
- Timestamps for every event

### Clean Resets
- Delete all AFK events: `cleanup_old_afk_events(days=0)`
- Delete all sleep segments: `cleanup_old_sleep_segments(days=0)`
- Or just truncate tables

### Future Enhancements
- Add web UI to view/edit sleep history
- Generate sleep quality reports
- Detect sleep patterns and anomalies
- Export data for external analysis

## Files Changed/Created

### New Files
- `app/models/afk_sleep_tracking.py` (SQLAlchemy models)
- `app/assistant/physical_status_manager/afk_sleep_db.py` (database access layer)
- `migration_scripts/create_afk_sleep_tables.py` (migration script)

### Modified Files
- `app/models/__init__.py` (added exports)

### Backup Files Created
- `resources/backups/afk_sleep_migration_20260106_173124/resource_user_sleep_current.json`
- `resources/backups/afk_sleep_migration_20260106_173124/resource_user_physical_status.json`

## Migration Command Reference

```bash
# Create tables
python migration_scripts/create_afk_sleep_tables.py

# Create tables and migrate JSON data
python migration_scripts/create_afk_sleep_tables.py --migrate-json

# Reset tables (WARNING: deletes all data)
python migration_scripts/create_afk_sleep_tables.py --reset

# Reset tables and migrate fresh JSON data
python migration_scripts/create_afk_sleep_tables.py --reset --migrate-json
```
