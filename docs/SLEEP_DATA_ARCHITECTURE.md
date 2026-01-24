# Sleep Data Architecture - CLARIFIED

## Core Principle

**Database = Permanent Record, Resource File = Last 24 Hours**

- ✅ **Database (`sleep_segments` table)**: Keeps ALL sleep history FOREVER
- ✅ **Resource File (`resource_user_sleep_current.json`)**: Last 24 hours ONLY

## Why This Architecture?

### 1. Agents Need Current State
- Agents (activity_tracker, physical_status_inference) only care about recent sleep
- "How well did you sleep last night?" → last 24 hours
- "Are you tired?" → look at last night's sleep
- Resource file provides exactly what agents need

### 2. Long-Term Analysis Needs History
- "How has my sleep improved over 3 months?"
- "What's my average sleep on weekends vs. weekdays?"
- "Did I sleep better after changing my routine?"
- Database provides permanent record for analysis

### 3. Memory Efficiency
- Don't load years of sleep data into RAM
- Resource file is small, fast to read
- Database handles large datasets efficiently

## Data Flow

```
User sleeps (AFK or reported)
    ↓
SleepSegmentTracker.record_sleep_segment()
    ↓
Database INSERT (permanent record)
    ↓
generate_sleep_resource_file()
    ↓
Query last 24 hours from database
    ↓
Compute metrics
    ↓
Write to resource_user_sleep_current.json
    ↓
Agents read resource file
```

## Database Retention Policy

### Sleep Segments
- **Retention**: **PERMANENT** (never deleted)
- **Reason**: Historical sleep patterns are valuable
- **Use cases**: 
  - Long-term trend analysis
  - Sleep quality reports
  - Correlation with other metrics
  - Personal health tracking

### AFK Events
- **Retention**: 30 days
- **Reason**: Raw AFK data is only useful short-term
- **Use cases**:
  - Debugging sleep detection
  - Validating AFK → sleep conversion
  - Recent activity patterns

## Querying Historical Sleep

### Use the Sleep History Tool

```bash
# Last 7 days (default)
python -m app.assistant.physical_status_manager.sleep_history

# Last 30 days
python -m app.assistant.physical_status_manager.sleep_history --days 30

# Specific date range
python -m app.assistant.physical_status_manager.sleep_history \
    --start 2026-01-01 --end 2026-01-31

# Export to CSV
python -m app.assistant.physical_status_manager.sleep_history \
    --days 90 --export my_sleep_q1_2026.csv

# Detailed view
python -m app.assistant.physical_status_manager.sleep_history \
    --days 7 --detailed
```

### Example Output

```
Sleep History Query
============================================================
Date Range: 2025-12-30 to 2026-01-06

[*] Querying database...
[+] Found 8 sleep segments

Sleep Statistics
============================================================
Total Segments: 8
Total Sleep: 52.5 hours
Nights with Data: 7
Average per Night: 7.5 hours
Range: 6.2 - 8.5 hours

[i] All sleep data is stored permanently in the database
```

## Resource File Updates

The resource file is automatically regenerated:

1. **After recording sleep** (from AFK detection or user chat)
2. **After creating synthetic sleep** (cold start)
3. **On manual request** (CLI tool)

It is **NOT** regenerated periodically - only when sleep data changes.

## Database Schema

### `sleep_segments` Table

| Column | Type | Description | Indexed |
|--------|------|-------------|---------|
| `id` | Integer | Primary key | Yes |
| `start_time` | DateTime(TZ) | Bedtime (UTC) | Yes |
| `end_time` | DateTime(TZ) | Wake time (UTC) | Yes |
| `duration_minutes` | Float | Sleep duration | No |
| `source` | String(50) | How detected | Yes |
| `raw_mention` | Text | User's original text | No |
| `created_at` | DateTime(TZ) | Record timestamp | No |

### Indexes

- `idx_sleep_start`: On `start_time` (for date range queries)
- `idx_sleep_end`: On `end_time` (for recent sleep queries)
- `idx_sleep_source`: On `source` (for filtering by detection method)

### Sources

- `afk_detection`: Detected from long AFK during sleep window
- `user_chat`: User explicitly reported (e.g., "I slept 8 hours")
- `cold_start_assumed`: Synthetic sleep on app startup
- `manual`: Manually entered

## Future Enhancements

### 1. Sleep Reports

```python
from app.assistant.day_flow_manager.archive.sleep_history import get_sleep_history
from datetime import datetime, timedelta

# Generate monthly report
end = datetime.now()
start = end - timedelta(days=30)
segments = get_sleep_history(start, end)

# Analyze patterns
# - Best/worst nights
# - Weekday vs weekend
# - Correlation with activities
```

### 2. Sleep Goals
```python
# Track progress toward sleep goals
target_hours = 8.0
recent_avg = calculate_avg_sleep(days=7)
progress = (recent_avg / target_hours) * 100
```

### 3. Web UI
- Calendar view of sleep history
- Interactive charts
- Trend analysis
- Export to PDF

### 4. Health Correlations
- Compare sleep with mood ratings
- Sleep vs. productivity
- Sleep vs. exercise
- Identify patterns

## Key Files

| File | Purpose |
|------|---------|
| `app/models/afk_sleep_tracking.py` | Database models |
| `app/assistant/physical_status_manager/afk_sleep_db.py` | Database access layer |
| `app/assistant/physical_status_manager/sleep_data_generator.py` | Generate resource file (24h) |
| `app/assistant/physical_status_manager/sleep_history.py` | Query historical data |
| `resources/resource_user_sleep_current.json` | Current sleep (agents read) |

## Cleanup Schedule

### Daily (BackgroundTaskManager)
- **AFK Events**: Delete older than 30 days
- **Sleep Segments**: **NEVER DELETED**

### Manual Cleanup (if needed)

```python
from app.assistant.day_flow_manager.archive.afk_sleep_db import cleanup_old_afk_events

# Clean up AFK events older than 90 days
cleanup_old_afk_events(days=90)

# Sleep segments are never automatically deleted
# Manual deletion only if absolutely necessary:
from app.models.base import get_session
from app.models.afk_sleep_tracking import SleepSegment
from datetime import datetime, timedelta

session = get_session()
cutoff = datetime.now() - timedelta(days=365)  # 1 year ago
deleted = session.query(SleepSegment).filter(
  SleepSegment.start_time < cutoff
).delete()
session.commit()
session.close()
```

## Summary

✅ **Sleep segments stored permanently** in database
✅ **Resource file shows last 24 hours** for agents
✅ **Query tool** for historical analysis
✅ **Export to CSV** for external tools
✅ **Automatic cleanup** of AFK events (30 days)
✅ **No automatic cleanup** of sleep segments (permanent)

Your sleep history is now a permanent, queryable record! 💤
