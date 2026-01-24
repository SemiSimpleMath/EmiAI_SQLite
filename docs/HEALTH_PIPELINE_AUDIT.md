# Health Pipeline Audit Report

**Date**: 2025-12-29  
**Auditor**: AI Assistant  
**Scope**: Complete health/wellness pipeline codebase review

---

## Executive Summary

The health pipeline is **functionally working** but suffers from:
1. **God Object anti-pattern** (`PhysicalStatusManager`: 2068 lines, 65 methods)
2. **Code duplication** across managers (chat retrieval, ticket fetching)
3. **Hard-coded values** scattered throughout
4. **Dead/deprecated code** not removed
5. **Lack of constants** for magic numbers

**Overall Grade**: C+ (Functional but needs refactoring)

---

## Component-by-Component Findings

### 1. `background_task_manager.py` ✅ **GOOD**

**Lines**: 481  
**Status**: Minor issues

#### Issues:
- 🗑️ **Dead Code**: Lines 289-332 (`_run_physical_status`, `_run_proactive_orchestrator`) marked DEPRECATED but still present
- 🔢 **Hard-coded intervals**: `3 * 60`, `60`, `5 * 60` should be constants
- 🔴 **Stale comments**: "TEMPORARILY RE-ENABLED FOR TESTING" (line 136)
- 💬 **Commented code**: Location tracking disabled (lines 148-154) - remove or document

#### Recommendations:
```python
# Add at top
WELLNESS_CYCLE_INTERVAL_MINUTES = 3
SWITCHBOARD_INTERVAL_MINUTES = 1
MEMORY_RUNNER_INTERVAL_MINUTES = 5
```

---

### 2. `physical_status_manager.py` 🔴 **CRITICAL REFACTOR NEEDED**

**Lines**: 2068  
**Methods**: 65  
**Status**: God Object anti-pattern

#### Major Issues:

1. **🔴 Massive Class** - Violates Single Responsibility Principle
   - Should be split into:
     - `SleepTracker` (sleep segment recording, config)
     - `AFKMonitor` (idle detection, AFK state machine)
     - `ActivityRecorder` (wellness activity timestamps)
     - `StatusOrchestrator` (coordinates LLM agents)
     - `DayBoundaryManager` (5 AM resets, day start logic)

2. **🔁 Code Duplication**:
   - `_get_recent_chat_messages()` (lines 1569-1599) - duplicated in `proactive_orchestrator_manager.py`
   - `_get_recent_accepted_tickets()` (lines 1714-1766) - duplicated
   - `_calculate_time_deltas()` (lines 1600-1633) - duplicated

3. **🔢 Hard-coded Values**:
   - Line 94: `if age_minutes < 5` (cache timeout)
   - Line 160: `timedelta(hours=48)` (cleanup threshold)
   - Line 1874: `hours_back=2` (lookback window)
   - Countless `print()` statements (should be `logger.debug`)

4. **⚠️ Silent Failures**:
   - Line 1983: Falls back to `_simple_status_inference()` on error - might hide LLM problems
   - Line 205: Swallows exception when sending chat message

5. **🗑️ Unused/Legacy Code**:
   - `_simple_status_inference()` (lines 1985-2052) - fallback that's never tested
   - Probably several other methods not called in production

#### Recommendations:
- **Immediate**: Extract utility methods to shared module (`health_utils.py`)
- **Short-term**: Split into 3-4 smaller classes
- **Long-term**: Event-driven architecture for activity tracking

---

### 3. `activity_tracker` Agent ✅ **GOOD**

**Prompt**: 128 lines  
**Status**: Minor issues

#### Issues:
- 🔴 **Prompt length**: 128 lines might overwhelm LLM (consider splitting examples to separate file)
- 🔢 **Magic temperature**: `0.2` in config (should be constant with explanation)
- ⚠️ **No validation**: LLM could return invalid field names - no Python validation

#### Recommendations:
- Add validation in `physical_status_manager._run_activity_tracker()`:
```python
valid_fields = self._get_all_tracked_fields()
activities_to_reset = [a for a in activities_to_reset if a in valid_fields]
```

---

### 4. `physical_status_inference` Agent ✅ **ACCEPTABLE**

**Status**: No major issues found

- Prompt is clear and focused
- Output schema is well-defined
- Config matches prompt requirements

---

### 5. `proactive_orchestrator_manager.py` ⚠️ **NEEDS CLEANUP**

**Lines**: ~400  
**Status**: Duplication issues

#### Issues:
- 🔁 **Duplicated methods** from `physical_status_manager.py`:
  - `_get_recent_chat_messages()`
  - `_calculate_time_deltas()` (similar logic)
- 🔢 **Hard-coded values**:
  - `hours_back=2` for chat retrieval
  - Rate limit thresholds embedded in method

#### Recommendations:
- Extract shared utilities to `app/assistant/health_utils.py`:
  - `get_recent_chat_messages(hours_back: int)`
  - `get_recent_accepted_tickets(hours_back: int)`
  - `calculate_activity_deltas(wellness: Dict, now: datetime)`

---

### 6. `proactive_orchestrator` Agent ✅ **GOOD**

**Status**: Recently improved

- Wind-down schedule now included in prompt ✅
- Ticket TTL reduced from 5h to 2h ✅
- Good context injection

#### Minor Issues:
- Could benefit from more examples in prompt
- Rate limiting logic embedded in manager (should be in config)

---

### 7. `proactive_ticket_manager.py` ✅ **GOOD**

**Status**: Clean implementation

- Well-defined state machine
- Proper timezone handling
- Good database session management

#### Minor Issues:
- No ticket archival (old tickets just accumulate)
- Could add `ARCHIVED` state for completed tickets older than 30 days

---

### 8. Resource Files & Configuration ⚠️ **MIXED**

**Status**: Some consistency issues

#### Issues:
- **Mixed formats**: Some YAML, some JSON (standardize?)
- **No schema validation**: JSON files have no JSON Schema
- **Hard-coded paths**: `resource_user_physical_status.json` path built with `os.path.join` instead of `Path`

#### Recommendations:
- Add JSON Schema validation for all `.json` resource files
- Standardize on Pathlib (`Path`) for all file operations
- Consider JSON Schema for `resource_tracked_activities.json`

---

### 9. `system_activity.py` (AFK Detection) ⚠️ **PLATFORM DEPENDENT**

**Status**: Functional but fragile

#### Issues:
- Platform-specific idle detection (Windows/Mac/Linux)
- No tests for idle detection logic
- Hardcoded threshold check in caller (should be in this module)

#### Recommendations:
- Add configurable AFK thresholds to `system_activity.py`
- Mock idle detection for tests
- Add logging for idle time changes (debugging)

---

## Critical Findings Summary

| Component | Severity | Issue | Impact |
|-----------|----------|-------|--------|
| `physical_status_manager.py` | 🔴 **HIGH** | God Object (2068 lines) | Maintenance nightmare, hard to test |
| Duplication | 🟡 **MEDIUM** | 3 methods duplicated across managers | Code drift, bug inconsistency |
| Hard-coded values | 🟡 **MEDIUM** | 15+ magic numbers | Hard to tune, unclear intent |
| Dead code | 🟢 **LOW** | ~200 lines deprecated | Clutter, confusion |
| Silent failures | 🟡 **MEDIUM** | 2 exception swallows | Hidden bugs |

---

## Refactoring Recommendations (Priority Order)

### 1. **HIGH PRIORITY** - Extract Shared Utilities (1-2 hours)

Create `app/assistant/health_utils.py`:

```python
"""Shared utilities for health/wellness pipeline."""
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional

# Constants
CHAT_LOOKBACK_HOURS = 2
TICKET_LOOKBACK_HOURS = 2
ACTIVITY_CACHE_TTL_MINUTES = 5

def get_recent_chat_messages(hours_back: int = CHAT_LOOKBACK_HOURS) -> List[Dict]:
    """Get recent chat from global blackboard (filtered)."""
    # Move implementation from proactive_orchestrator_manager
    pass

def get_recent_accepted_tickets(hours_back: int = TICKET_LOOKBACK_HOURS) -> List[Dict]:
    """Get recently accepted wellness tickets."""
    # Move implementation from physical_status_manager
    pass

def calculate_activity_deltas(wellness: Dict, now: datetime) -> Dict[str, int]:
    """Calculate minutes_since for all tracked activities."""
    # Move implementation from physical_status_manager
    pass
```

Update both managers to import from `health_utils`.

---

### 2. **MEDIUM PRIORITY** - Clean Up Dead Code (30 min)

**Remove:**
- `background_task_manager._run_physical_status()` (deprecated)
- `background_task_manager._run_proactive_orchestrator()` (deprecated)
- Commented location tracking code (or document why disabled)

**Update:**
- Remove "TEMPORARILY" from comments
- Replace all `print()` with `logger.debug()` in `physical_status_manager.py`

---

### 3. **MEDIUM PRIORITY** - Add Constants File (1 hour)

Create `app/assistant/health_constants.py`:

```python
"""Configuration constants for health/wellness pipeline."""

# Timing
WELLNESS_CYCLE_INTERVAL_MINUTES = 3
SWITCHBOARD_INTERVAL_MINUTES = 1
MEMORY_RUNNER_INTERVAL_MINUTES = 5

# AFK Detection
POTENTIAL_AFK_THRESHOLD_MINUTES = 1
CONFIRMED_AFK_THRESHOLD_MINUTES = 3

# Lookback Windows
CHAT_LOOKBACK_HOURS = 2
TICKET_LOOKBACK_HOURS = 2
CALENDAR_LOOKBACK_HOURS = 2

# Ticket Lifecycle
TICKET_MAX_AGE_HOURS = 2
TICKET_ARCHIVE_AFTER_DAYS = 30

# Cache
CONFIG_CACHE_TTL_MINUTES = 5
SLEEP_SEGMENT_RETENTION_HOURS = 48

# Temperature Settings
ACTIVITY_TRACKER_TEMPERATURE = 0.2
STATUS_INFERENCE_TEMPERATURE = 0.3
ORCHESTRATOR_TEMPERATURE = 0.8
```

---

### 4. **LOW PRIORITY** - Split PhysicalStatusManager (4-8 hours)

**Phase 1**: Extract pure-function helpers to separate files:
- `sleep_tracking.py` (sleep segment logic)
- `day_boundary.py` (5 AM reset logic)
- `activity_recording.py` (timestamp recording)

**Phase 2**: Create smaller coordinator classes:
- Keep `PhysicalStatusManager` as thin orchestrator
- Delegate to specialized classes

**Example**:
```python
class PhysicalStatusManager:
    def __init__(self):
        self.sleep_tracker = SleepTracker()
        self.afk_monitor = AFKMonitor()
        self.activity_recorder = ActivityRecorder()
        self.day_manager = DayBoundaryManager()
    
    def refresh(self):
        # Orchestrate only, delegate work
        self.afk_monitor.update()
        if self.afk_monitor.is_afk:
            return
        
        tracker_result = self._run_activity_tracker()
        self.activity_recorder.record_activities(tracker_result)
        # etc...
```

---

## Testing Gaps

**Current State**: No unit tests for health pipeline found.

**Critical Test Needs**:
1. AFK state machine transitions (active → potentially_afk → confirmed_afk)
2. Day boundary detection (5 AM rollover)
3. Ticket expiry logic (2h TTL)
4. Activity deduplication (don't reset twice for same evidence)
5. Sleep segment recording (overnight vs nap)

**Recommendation**: Add `tests/health_pipeline/` with pytest fixtures for:
- Mock `system_activity` (idle time)
- Mock `global_blackboard` (chat messages)
- Mock `proactive_ticket_manager` (ticket state)

---

## Performance Concerns

### Current Bottlenecks:
1. **LLM calls every 3 minutes** (activity_tracker + status_inference + orchestrator)
   - Cost: ~3 LLM calls every 3 min = 1000+ calls/day
   - Mitigation: Already skips during AFK ✅

2. **File I/O every cycle**:
   - `resource_user_physical_status.json` written every 3 min
   - Consider: Only write on actual state changes

3. **Database queries**:
   - Calendar events, tasks, tickets queried fresh each cycle
   - Consider: Add caching layer (Redis?)

**Recommendation**: Profile with `cProfile` during active session to confirm.

---

## Security & Privacy

**No Critical Issues Found**

Minor notes:
- Chat messages stored in `unified_log` (intended)
- Physical status in JSON file (world-readable on Unix)
  - Consider: File permissions `chmod 600` for user status file

---

## Documentation Gaps

**Missing:**
1. Architecture diagram (data flow through pipeline)
2. State machine diagram (AFK transitions)
3. Agent prompt engineering guide (why temperature = 0.2 for tracker?)
4. Runbook for debugging (what logs to check when X happens)

**Next**: Create comprehensive pipeline documentation (see separate doc)

---

## Conclusion

The health pipeline is **functional and well-architected** at a high level, but suffers from:
- **Technical debt** in `physical_status_manager.py` (too large)
- **Code duplication** that will cause maintenance issues
- **Lack of tests** makes refactoring risky

**Immediate Actions** (next 1-2 days):
1. ✅ Extract shared utilities → `health_utils.py`
2. ✅ Create constants file → `health_constants.py`
3. ✅ Remove dead code (deprecated methods)
4. ✅ Add validation for activity field names

**Medium-term** (next 1-2 weeks):
1. Split `PhysicalStatusManager` into smaller classes
2. Add unit tests for critical paths
3. Profile and optimize file I/O

**Long-term** (next month):
1. Consider event-driven architecture
2. Add Redis caching layer
3. Implement ticket archival system


