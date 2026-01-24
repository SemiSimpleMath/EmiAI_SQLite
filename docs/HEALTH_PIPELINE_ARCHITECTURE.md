# Health Pipeline Architecture

**Date**: 2025-12-29  
**Version**: 2.0  
**Status**: Production

---

## Table of Contents

1. [Overview](#overview)
2. [Data Flow](#data-flow)
3. [Components](#components)
4. [State Machines](#state-machines)
5. [Timing & Intervals](#timing--intervals)
6. [Agent Prompts](#agent-prompts)
7. [Resource Files](#resource-files)
8. [Debugging Guide](#debugging-guide)

---

## Overview

The **Health Pipeline** is a coordinated system that:
1. Monitors user's physical activity and cognitive state
2. Detects wellness activities from multiple sources (chat, calendar, accepted tickets)
3. Generates proactive wellness suggestions (hydration, stretches, breaks)
4. Tracks AFK (away from keyboard) status to avoid interrupting absent users

### Design Principles

- **LLMs for semantic understanding** (detect "grabbed water" → reset hydration timer)
- **Python for mechanical execution** (timestamp recording, state updates)
- **Graceful degradation** (skip LLM calls when user is AFK)
- **Data flow guarantees** (activity tracker runs before status inference)

---

## Data Flow

### High-Level Pipeline (Every 3 Minutes)

```
┌─────────────────────────────────────────────────────────────────┐
│  BackgroundTaskManager (wellness_cycle, every 3 min)            │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
        ┌────────────────────────────────────────┐
        │  PhysicalStatusManager.refresh()       │
        └─────┬──────────────────────────────────┘
              │
              ├─► Phase 0: update_computer_activity() [Python]
              │   ├─► Check idle time via system_activity.py
              │   ├─► Determine: active / potentially_afk / confirmed_afk
              │   ├─► Handle state transitions (active↔afk)
              │   ├─► Check for day boundary (5 AM reset)
              │   └─► Save status to JSON
              │
              ├─► [SKIP IF AFK or POTENTIALLY_AFK]
              │
              ├─► Phase 1: activity_tracker Agent [LLM]
              │   ├─► Inputs: recent_chat, calendar_events, accepted_tickets
              │   ├─► Outputs: activities_to_reset, sleep_events, day_start_signal
              │   └─► Python records timestamps for detected activities
              │
              ├─► Phase 2: build_context_for_inference() [Python]
              │   ├─► Calculate minutes_since for all activities
              │   ├─► Fetch calendar events, tasks
              │   └─► Assemble context dict
              │
              └─► Phase 3: physical_status_inference Agent [LLM]
                  ├─► Inputs: context (time_since, calendar, tasks, sleep)
                  ├─► Outputs: cognitive_load, energy_level, interruption_tolerance
                  └─► Update status_data and save

┌─────────────────────────────────────────────────────────────────┐
│  ProactiveOrchestratorManager.run() [Triggered after refresh]   │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ├─► Check: is_afk or potentially_afk → SKIP
                         │
                         ├─► Maintenance: wake_snoozed_tickets, expire_old_tickets
                         │
                         ├─► Gather context:
                         │   ├─► time_since (from physical_status)
                         │   ├─► calendar_events
                         │   ├─► active_tickets (duplicate check)
                         │   ├─► recent_chat_messages
                         │   ├─► recent_accepted_tickets (avoid re-suggesting)
                         │   └─► resource files (routine, health)
                         │
                         ├─► Call proactive_orchestrator Agent [LLM]
                         │   ├─► Inputs: full context
                         │   ├─► Outputs: list of wellness suggestions
                         │   └─► Each suggestion: type, title, message, urgency
                         │
                         └─► Create tickets via ProactiveTicketManager
                             ├─► Check rate limits (max per cycle, per day)
                             └─► Create PENDING tickets in database
```

---

## Components

### 1. `BackgroundTaskManager`

**File**: `app/assistant/background_task_manager/background_task_manager.py`  
**Responsibility**: Registers and runs all background tasks in separate threads

**Registered Tasks**:
- `wellness_cycle`: Every 3 minutes (coordinates all health pipeline)
- `switchboard_runner`: Every 1 minute (extract preferences from chat)
- `memory_runner`: Every 5 minutes (process extracted facts)

**Key Methods**:
- `start_all()`: Start all registered background tasks
- `_run_wellness_cycle()`: Coordinate refresh + orchestrator

---

### 2. `PhysicalStatusManager`

**File**: `app/assistant/physical_status_manager/physical_status_manager.py`  
**Responsibility**: Orchestrates activity tracking, AFK monitoring, and status inference

**Key Methods**:

#### Core Loop
- `refresh()`: Main entry point (called by wellness_cycle)
  - Phase 0: Python updates (computer activity, day boundary)
  - Phase 1: Activity tracker LLM (detect activities)
  - Phase 2: Build context (calculate time_since)
  - Phase 3: Status inference LLM (assess cognitive load)

#### AFK Monitoring
- `update_computer_activity()`: Check idle time, update AFK state
  - Active (0-1 min idle)
  - Potentially AFK (1-3 min idle) - grace period
  - Confirmed AFK (3+ min idle) - skip LLM agents

#### Activity Recording
- `record_activity(activity_type, timestamp)`: Record wellness activity timestamp
- `minutes_since_activity(activity_type)`: Calculate time delta

#### Sleep Tracking
- `_record_sleep_segment(start, end)`: Record AFK period during sleep window
- `_trigger_day_start(wake_time)`: Calculate last night's sleep, reset daily metrics
- `_check_daily_resets()`: 5 AM boundary check for coffee counter, etc.

#### Status Queries
- `get_current_status()`: Full status dict
- `get_wellness_activities()`: Activity timestamps
- `get_cognitive_load()`: "Low", "Medium", "High", "Overloaded"
- `get_energy_level()`: "Fresh", "Normal", "Waning", "Depleted"

**Data Storage**:
- `resources/resource_user_physical_status.json` (written every cycle)

---

### 3. `activity_tracker` Agent (LLM)

**Files**:
- `app/assistant/agents/activity_tracker/prompts/system.j2`
- `app/assistant/agents/activity_tracker/agent_form.py`
- `app/assistant/agents/activity_tracker/config.yaml`

**Responsibility**: Detect wellness activities from user evidence

**Inputs**:
- `recent_chat_excerpts`: User chat messages (last 2 hours)
- `calendar_events_completed`: Calendar events that ended recently
- `recent_accepted_tickets`: Wellness tickets user accepted

**Outputs** (JSON):
```json
{
  "activities_to_reset": ["hydration", "finger_stretch"],
  "sleep_events": [
    {
      "type": "nap",
      "duration_minutes": 120,
      "raw_mention": "I just napped for 2 hours"
    }
  ],
  "day_start_signal": {
    "signal_type": "confirmed_awake",
    "reasoning": "User mentioned making coffee"
  },
  "reasoning": "User accepted 'Finger stretch' ticket and said 'grabbed water'"
}
```

**Detection Sources (Priority)**:
1. **Accepted Tickets** (highest confidence) - User explicitly accepted suggestion
2. **Chat Messages** - Parse for past-tense actions ("just drank", "ate lunch")
3. **Calendar Events** - Match event title to activity hints ("Lunch" → meal)

**Tracked Activities** (from `resource_tracked_activities.json`):
- `hydration` - Drinking water
- `coffee` - Coffee consumption
- `meal` - Main meal
- `snack` - Light eating
- `walk` - Walking/movement
- `exercise` - Exercise session
- `finger_stretch` - Finger stretches
- `standing_break` - Standing break
- `back_stretch` - Back stretch

---

### 4. `physical_status_inference` Agent (LLM)

**Files**:
- `app/assistant/agents/physical_status_inference/prompts/system.j2`
- `app/assistant/agents/physical_status_inference/prompts/user.j2`
- `app/assistant/agents/physical_status_inference/agent_form.py`

**Responsibility**: Assess user's physical, cognitive, and emotional state

**Inputs**:
- `date_time`: Current time
- `calendar_events`: Upcoming meetings/events
- `tasks`: Pending tasks
- `time_since`: Minutes since last hydration, meal, walk, etc.
- `sleep_summary`: Last night's sleep quality and duration
- `resource_user_health`: Chronic conditions (back pain, carpal tunnel)
- `resource_user_routine`: Daily routine preferences

**Outputs** (JSON):
```json
{
  "cognitive_state": {
    "load": "Medium",
    "focus_capacity": "Good",
    "context_switch_tolerance": "Low",
    "reasoning": "2 meetings today, in focus hours"
  },
  "physical_state": {
    "energy_level": "Normal",
    "pain_indicators": ["back_pain"],
    "hydration_concern": true,
    "reasoning": "45 min since water, sitting for 2h"
  },
  "emotional_state": {
    "stress_level": "Low",
    "mood": "Neutral",
    "reasoning": "No urgent deadlines"
  },
  "interruption_tolerance": "Medium",
  "overall_assessment": "User is in good working state but needs hydration"
}
```

---

### 5. `ProactiveOrchestratorManager`

**File**: `app/assistant/proactive_orchestrator/proactive_orchestrator_manager.py`  
**Responsibility**: Generate wellness suggestions based on rules and context

**Key Methods**:
- `run()`: Main entry point (called after physical_status refresh)
  - Check AFK status → skip if AFK or potentially_afk
  - Maintenance (wake snoozed, expire old tickets)
  - Gather context
  - Call orchestrator LLM
  - Create tickets via ProactiveTicketManager

- `_gather_context()`: Assemble all relevant data
  - Time deltas (from physical_status)
  - Calendar events (next 4 hours)
  - Active tickets (duplicate check)
  - Recent chat messages (mood, acute needs)
  - Recent accepted tickets (avoid re-suggesting)
  - Resource files (routine, health rules)

**Rate Limiting**:
- Max 3 suggestions per cycle
- Max 10 suggestions per day

---

### 6. `proactive_orchestrator` Agent (LLM)

**Files**:
- `app/assistant/agents/proactive_orchestrator/prompts/system.j2`
- `app/assistant/agents/proactive_orchestrator/prompts/user.j2`
- `app/assistant/agents/proactive_orchestrator/agent_form.py`

**Responsibility**: Generate wellness suggestions using rules and context

**Inputs**:
- `date_time`: Current time
- `day_of_week`: Monday, Tuesday, etc.
- `computer_activity`: Idle time, AFK status
- `time_since`: Minutes since each activity
- `location_summary`: Current location (Home, Office, etc.)
- `weather_summary`: Weather conditions
- `recent_chat_messages`: Last 2 hours of chat
- `calendar_events`: Upcoming events (next 4 hours)
- `active_tickets`: Current pending suggestions (don't duplicate)
- `recent_accepted_tickets`: Recently completed activities (don't re-suggest)
- `recent_tickets`: Recently dismissed suggestions (don't nag)
- `resource_tracked_activities`: Activity rules (intervals, conditions)
- `resource_user_routine`: User's daily routine and preferences
- `resource_user_health`: Chronic conditions and accommodations

**Outputs** (JSON):
```json
{
  "suggestions": [
    {
      "suggestion_type": "hydration_break",
      "title": "Time for water",
      "message": "It's been 45 minutes since your last drink. Grab some water?",
      "urgency": "medium",
      "valid_until": "2025-12-29T16:30:00Z",
      "reasoning": "User hasn't had water in 45 min, recommended interval is 30 min"
    }
  ],
  "reasoning": "User overdue for hydration (45 min), also approaching back stretch interval"
}
```

**Suggestion Types**:
- `hydration_break` - Drink water
- `coffee_break` - Coffee (respects cutoff time)
- `meal_reminder` - Lunch/dinner
- `snack_reminder` - Light snack
- `walk_break` - Take a walk
- `exercise_reminder` - Exercise session
- `finger_stretch` - Finger stretches (carpal tunnel)
- `standing_break` - Stand up break (back pain)
- `back_stretch` - Back stretch (back pain)
- `wind_down` - Prepare for sleep

**Context-Aware Rules**:
1. **Time-of-day**: No coffee after caffeine cutoff (4pm default)
2. **Routine**: Wind-down only near bedtime (not at 1 AM!)
3. **Duplicates**: Don't suggest if active ticket exists for same type
4. **Recent accepts**: Don't re-suggest recently completed activities (2h window)
5. **Dismissals**: Don't nag about recently dismissed suggestions (1h window)
6. **Health conditions**: Suggest stretches more frequently for chronic pain

---

### 7. `ProactiveTicketManager`

**File**: `app/assistant/proactive_orchestrator/proactive_ticket_manager.py`  
**Responsibility**: Manage ticket lifecycle in database

**Ticket States**:
```
PENDING → PROPOSED → ACTIVE → [ACCEPTED | DISMISSED | EXPIRED]
                           ↓
                      SNOOZED (temp)
```

**Key Methods**:
- `create_ticket(type, title, message, urgency, valid_until)`: Create new ticket
- `mark_proposed(ticket_id)`: Mark as shown to user
- `mark_active(ticket_id)`: User is viewing ticket
- `mark_accepted(ticket_id)`: User accepted suggestion
- `mark_dismissed(ticket_id, reason)`: User rejected suggestion
- `mark_snoozed(ticket_id, duration_minutes)`: User snoozed for X minutes
- `expire_old_tickets()`: Expire tickets older than 2 hours (safety net)
- `wake_snoozed_tickets()`: Check for snoozed tickets ready to re-appear
- `get_recently_accepted_tickets(hours)`: Get accepted tickets (for activity tracker)

**Database**: `proactive_tickets` table in SQLite

---

## State Machines

### AFK State Machine

```
┌─────────┐
│ ACTIVE  │  (0-1 min idle)
│         │  - Wellness cycle runs normally
│         │  - LLM agents fire
└────┬────┘
     │ idle ≥ 1 min
     ▼
┌──────────────────┐
│ POTENTIALLY_AFK  │  (1-3 min idle)
│                  │  - Grace period
│ potentially_afk_since: timestamp
│                  │  - Wellness cycle SKIPS LLM
└────┬─────────────┘
     │ idle ≥ 3 min
     ▼
┌──────────────────┐
│ CONFIRMED_AFK    │  (3+ min idle)
│                  │  - last_afk_start: backdated to potentially_afk_since
│ is_afk: true     │  - Wellness cycle SKIPS entirely
│                  │  - Stretch timers reset continuously
└──────────────────┘
     │ idle < 1 min
     ▼
┌─────────┐
│ ACTIVE  │  (returned from AFK)
│         │  - Log AFK duration
│         │  - Check if sleep (>sleep_threshold during sleep_window)
│         │  - Trigger day start if morning wake-up
└─────────┘
```

**Key Thresholds**:
- `POTENTIAL_AFK_THRESHOLD = 1 minute` (grace period)
- `CONFIRMED_AFK_THRESHOLD = 3 minutes` (official AFK)
- `SLEEP_AFK_THRESHOLD = 60 minutes` (configurable in `config_sleep_tracking.yaml`)

**Backdating Logic**:
- When user hits 3-minute threshold, `last_afk_start` is backdated to `potentially_afk_since`
- This ensures accurate AFK duration tracking even with grace period

---

### Ticket State Machine

```
┌─────────┐
│ PENDING │  - Created by orchestrator
│         │  - Not yet shown to user
└────┬────┘
     │ shown to user
     ▼
┌──────────┐
│ PROPOSED │  - Displayed in UI
│          │  - Awaiting user response
└─────┬────┘
      │ user clicks ticket
      ▼
┌────────┐
│ ACTIVE │  - Ticket detail view shown
│        │  - User can: Accept, Dismiss, Snooze
└───┬────┘
    │
    ├─► ACCEPTED ✅ (terminal state)
    │   - Activity tracker will detect this
    │   - Reset wellness timer
    │
    ├─► DISMISSED ❌ (terminal state)
    │   - Don't re-suggest same type for 1 hour
    │   - Reason logged (not_now, not_interested, already_did, other)
    │
    ├─► SNOOZED 💤 (temporary state)
    │   - Hidden for X minutes (15/30/60)
    │   - Returns to PENDING when snooze expires
    │
    └─► EXPIRED ⏰ (terminal state)
        - Ticket older than valid_until
        - Or older than 2 hours (safety net)
```

---

## Timing & Intervals

### Background Tasks

| Task | Interval | Trigger | Skips If |
|------|----------|---------|----------|
| `wellness_cycle` | 3 min | Timer | Never (but internal phases skip if AFK) |
| `switchboard_runner` | 1 min | Timer | No new chat messages |
| `memory_runner` | 5 min | Timer | No unprocessed facts |

### Wellness Cycle Phases

| Phase | Type | Duration | Skips If |
|-------|------|----------|----------|
| Phase 0: Computer Activity | Python | ~10ms | Never |
| Phase 1: Activity Tracker | LLM | ~2-5s | AFK or potentially_afk |
| Phase 2: Build Context | Python | ~50ms | AFK or potentially_afk |
| Phase 3: Status Inference | LLM | ~2-5s | AFK or potentially_afk |
| Orchestrator | LLM | ~2-5s | AFK or potentially_afk |

**Total Time (Active)**: ~6-15 seconds (3 LLM calls)  
**Total Time (AFK)**: ~10ms (Python only)

### Activity Intervals (from `resource_tracked_activities.json`)

| Activity | Interval | Condition | Priority |
|----------|----------|-----------|----------|
| Hydration | 30 min | Always | High |
| Meal | 4-6 hours | Time of day | High |
| Snack | 2-3 hours | Optional | Low |
| Coffee | 2-3 hours | Before cutoff (4pm) | Medium |
| Walk | 60-90 min | Sedentary work | Medium |
| Exercise | Daily | Once per day | Low |
| Finger Stretch | 30 min | Carpal tunnel | High |
| Standing Break | 45 min | Back pain | High |
| Back Stretch | 60 min | Back pain | High |

### Ticket Lifecycle Times

- **Creation → Proposed**: Immediate (next UI poll)
- **Proposed → Active**: User click (immediate)
- **Active → Accepted/Dismissed**: User action (immediate)
- **Snooze Duration**: 15, 30, or 60 minutes (user choice)
- **Expiry**: 2 hours max (from creation)
- **Recently Accepted Window**: 2 hours (don't re-suggest)
- **Recently Dismissed Window**: 1 hour (don't nag)

---

## Agent Prompts

### Activity Tracker

**Model**: `gpt-4.1-mini`  
**Temperature**: `0.2` (low for consistent parsing)  
**Max Tokens**: Not specified (default)

**Prompt Strategy**:
- **System prompt**: Defines role, rules, and output schema
- **User prompt**: Provides evidence (chat, calendar, tickets)
- **Output**: Structured JSON with Pydantic validation

**Key Instructions**:
1. Parse chat for past-tense actions ("grabbed water", "just ate")
2. Match calendar event titles to activity hints ("Lunch" → meal)
3. Parse accepted tickets for activity types ("Finger stretch break" → finger_stretch)
4. Detect sleep events and day-start signals
5. Return exact field names from `resource_tracked_activities`

---

### Physical Status Inference

**Model**: `gpt-4.1-mini`  
**Temperature**: `0.3` (slightly higher for nuanced assessment)

**Prompt Strategy**:
- **System prompt**: Defines assessment framework and output schema
- **User prompt**: Provides full context (time_since, calendar, health, routine)
- **Output**: Structured JSON with cognitive, physical, emotional state

**Key Instructions**:
1. Assess cognitive load based on meetings, tasks, time of day
2. Assess energy level based on sleep, time since meal, circadian rhythm
3. Assess physical needs based on time_since activities and chronic conditions
4. Determine interruption tolerance (can we suggest wellness activities now?)
5. Provide reasoning for each assessment

---

### Proactive Orchestrator

**Model**: `gemini-3-flash-preview`  
**Temperature**: `0.8` (higher for creative, personalized suggestions)

**Prompt Strategy**:
- **System prompt**: Defines role as wellness coach and output schema
- **User prompt**: Provides full context + rules from resource files
- **Output**: List of wellness suggestions with reasoning

**Key Instructions**:
1. Review activity intervals and determine which are overdue
2. Check active tickets (don't duplicate)
3. Check recent accepted tickets (don't re-suggest completed activities)
4. Check recent dismissed tickets (don't nag)
5. Apply time-of-day rules (no coffee after 4pm, wind-down only near bedtime)
6. Respect user's routine (no meetings before 10am, family time at 6pm)
7. Accommodate health conditions (more frequent stretches for pain)
8. Generate 0-3 suggestions (prioritize by urgency and health impact)

---

## Resource Files

### Configuration Files

| File | Format | Purpose | Reload |
|------|--------|---------|--------|
| `config_sleep_tracking.yaml` | YAML | Sleep window, wake time, greetings | Cached (5 min) |
| `resource_tracked_activities.json` | JSON | Activity definitions and intervals | Loaded at startup |

### User Data Files

| File | Format | Purpose | Update Frequency |
|------|--------|---------|------------------|
| `resource_user_physical_status.json` | JSON | Current status, activity timestamps | Every 3 min |
| `resource_user_routine.json` | JSON | Daily routine preferences | Manual (via memory pipeline) |
| `resource_user_health.json` | JSON | Chronic conditions, accommodations | Manual (via memory pipeline) |
| `resource_user_food_prefs.json` | JSON | Food likes/dislikes | Manual (via memory pipeline) |
| `user_sleep_current.md` | Markdown | Last night's sleep summary | Daily (at wake-up) |

### Schema: `resource_tracked_activities.json`

```json
{
  "_metadata": {
    "resource_id": "resource_tracked_activities",
    "version": "1.0",
    "last_updated": "2025-12-28"
  },
  "activities": {
    "hydration": {
      "display_name": "Hydration",
      "field_name": "hydration",
      "suggested_interval_minutes": 30,
      "detection_hints": ["water", "drink", "hydration", "Gatorade"],
      "urgency": "high",
      "health_condition": null,
      "time_of_day_constraint": null,
      "reset_on_afk": false
    },
    "finger_stretch": {
      "display_name": "Finger Stretch",
      "field_name": "finger_stretch",
      "suggested_interval_minutes": 30,
      "detection_hints": ["finger", "hand stretch", "typing break"],
      "urgency": "high",
      "health_condition": "carpal_tunnel",
      "time_of_day_constraint": null,
      "reset_on_afk": true
    }
  }
}
```

### Schema: `resource_user_physical_status.json`

```json
{
  "wellness_activities": {
    "last_hydration": "2025-12-29T14:30:00+00:00",
    "last_meal": "2025-12-29T12:00:00+00:00",
    "last_coffee": "2025-12-29T09:00:00+00:00",
    "last_walk": "2025-12-29T13:00:00+00:00",
    "last_finger_stretch": "2025-12-29T14:00:00+00:00",
    "coffees_today": 2,
    "coffees_today_date": "2025-12-29"
  },
  "cognitive_state": {
    "load": "Medium",
    "focus_capacity": "Good",
    "context_switch_tolerance": "Low"
  },
  "physical_state": {
    "energy_level": "Normal",
    "pain_indicators": ["back_pain"],
    "hydration_concern": true
  },
  "computer_activity": {
    "is_afk": false,
    "potentially_afk": false,
    "idle_minutes": 0.5,
    "last_afk_start": null,
    "last_afk_duration_minutes": 0,
    "active_work_session_minutes": 45.2,
    "total_afk_time_today": 120.5,
    "total_active_time_today": 420.3
  },
  "day_started": true,
  "day_start_time": "2025-12-29T15:00:00+00:00",
  "morning_greeting_sent": true
}
```

---

## Debugging Guide

### Common Issues

#### 1. **Wellness suggestions not appearing**

**Symptoms**: No tickets created even though intervals are overdue

**Check**:
1. Is user AFK? → Check `computer_activity.is_afk` in `resource_user_physical_status.json`
2. Is orchestrator running? → Check logs for `🔄 Starting wellness cycle...`
3. Are suggestions rate-limited? → Check `ProactiveTicketManager.get_stats()`
4. Is there a duplicate active ticket? → Check `proactive_tickets` table for PENDING/ACTIVE tickets of same type

**Logs to Check**:
```
🔄 Starting wellness cycle...
✅ Physical status refreshed: Load=Medium, Energy=Normal
⏭️  User is AFK (idle 5.2min) - skipping orchestrator
✅ Proactive orchestrator created 2 suggestion(s)
```

---

#### 2. **Activities not resetting from accepted tickets**

**Symptoms**: User accepted "Hydration break" but minutes_since still increasing

**Check**:
1. Is ticket state correct? → Should transition PENDING → PROPOSED → ACTIVE → ACCEPTED
2. Is activity_tracker seeing the accepted ticket? → Check `recent_accepted_tickets` in logs
3. Is field name correct? → Ticket type must match activity field name exactly

**Debug Steps**:
1. Check `proactive_tickets` table: `SELECT * FROM proactive_tickets WHERE state = 'ACCEPTED' ORDER BY responded_at DESC LIMIT 5;`
2. Check `physical_status_manager` logs for: `Activity tracker: reset ['hydration']`
3. Check `resource_user_physical_status.json` for updated timestamp: `"last_hydration": "2025-12-29T..."`

---

#### 3. **Day not starting (stuck at morning)**

**Symptoms**: It's 9 AM but `day_started = False`, no daily reset happened

**Check**:
1. Cold start detection: `physical_status_manager` should force day start if hour >= `normal_sleep.end`
2. Sleep config loaded? → Check for `config_sleep_tracking.yaml` file
3. Activity tracker day-start signal? → Look for `day_start_signal` in logs

**Forced Day Start**:
- Automatically triggered if:
  - Current hour >= normal wake hour (e.g., 7 AM)
  - `day_started = False`
  - AFK monitor detects user active

**Manual Override** (in Python console):

```python
from app.assistant.day_flow_manager import get_physical_status_manager

manager = get_physical_status_manager()
manager.confirm_day_start()
```

---

#### 4. **AFK detection not working**

**Symptoms**: System thinks user is AFK when they're active (or vice versa)

**Check**:
1. System idle detection: `app.assistant.utils.system_activity.get_activity_status()`
2. Thresholds: `POTENTIAL_AFK_THRESHOLD = 1 min`, `CONFIRMED_AFK_THRESHOLD = 3 min`
3. Platform-specific issues: Windows vs Mac vs Linux idle detection

**Test Idle Detection**:
```python
from app.assistant.utils.system_activity import get_activity_status
status = get_activity_status()
print(f"Idle: {status['idle_minutes']:.1f} min, AFK: {status['idle_minutes'] >= 3}")
```

**Platform Checks**:
- **Windows**: Uses `ctypes.windll.user32.GetLastInputInfo()`
- **Mac**: Uses `IOKit` framework (requires `pyobjc`)
- **Linux**: Uses `python-xlib` (X11 idle time)

---

#### 5. **LLM agents returning empty/invalid results**

**Symptoms**: `Agent returned no data` in logs

**Check**:
1. LLM API key configured? → Check environment variables
2. LLM quota exceeded? → Check OpenAI/Gemini dashboard
3. Prompt rendering error? → Check for Jinja2 errors in logs
4. Schema validation failing? → Check for Pydantic validation errors

**Debug LLM Calls**:
- Enable debug logging: `logger.setLevel(logging.DEBUG)`
- Check `app/assistant/services/llm_client.py` for API errors
- Inspect agent's blackboard: `agent.blackboard.get_state_value('result')`

---

### Log Levels

**INFO** (default):
- Wellness cycle start/complete
- Activity tracker results
- Status inference results
- Orchestrator suggestions created
- Day start/reset events

**DEBUG** (for troubleshooting):
- AFK state transitions (active → potentially_afk → confirmed_afk)
- Activity timer resets
- Context building details
- Ticket state transitions

**ERROR** (critical issues):
- LLM API failures
- Database errors
- File I/O errors
- Missing configuration files

---

### Performance Profiling

**Monitor LLM Call Times**:
- Each LLM call is logged with duration
- Look for: `🔍 Using model: gpt-4.1-mini for structured output, with temperature 0.2, timeout 240s.`

**Monitor File I/O**:
- Status file written every 3 min (even if no changes)
- Consider: Only write on actual state changes

**Monitor Database Queries**:
- Calendar events queried every cycle
- Tasks queried every cycle
- Tickets queried every cycle
- Consider: Add caching layer

**Baseline Costs** (per day, active user):
- 3 LLM calls every 3 minutes (activity_tracker + status_inference + orchestrator)
- 8 hours active = 160 cycles
- 160 cycles × 3 calls = 480 LLM calls/day
- Cost: ~$0.50-$1.00/day (at GPT-4.1-mini pricing)

---

## Future Enhancements

### Short-term (1-2 weeks)
1. Extract shared utilities to `health_utils.py`
2. Add constants file (`health_constants.py`)
3. Remove deprecated methods
4. Add unit tests for critical paths

### Medium-term (1-2 months)
1. Split `PhysicalStatusManager` into smaller classes
2. Add Redis caching for calendar/tasks queries
3. Implement ticket archival (move old tickets to archive table)
4. Add performance profiling dashboard

### Long-term (3-6 months)
1. Event-driven architecture (pub/sub for state changes)
2. Machine learning for personalized intervals
3. Multi-user support (per-user status files)
4. Mobile app integration (push notifications for wellness)

---

## Appendix: File Structure

```
app/assistant/
├── background_task_manager/
│   └── background_task_manager.py
├── physical_status_manager/
│   └── physical_status_manager.py
├── proactive_orchestrator/
│   ├── proactive_orchestrator_manager.py
│   └── proactive_ticket_manager.py
├── agents/
│   ├── activity_tracker/
│   │   ├── config.yaml
│   │   ├── agent_form.py
│   │   └── prompts/
│   │       └── system.j2
│   ├── physical_status_inference/
│   │   ├── config.yaml
│   │   ├── agent_form.py
│   │   └── prompts/
│   │       ├── system.j2
│   │       └── user.j2
│   └── proactive_orchestrator/
│       ├── config.yaml
│       ├── agent_form.py
│       └── prompts/
│           ├── system.j2
│           └── user.j2
└── utils/
    └── system_activity.py

resources/
├── config_sleep_tracking.yaml
├── resource_tracked_activities.json
├── resource_user_physical_status.json
├── resource_user_routine.json
├── resource_user_health.json
├── resource_user_food_prefs.json
└── user_sleep_current.md

docs/
├── HEALTH_PIPELINE_AUDIT.md
└── HEALTH_PIPELINE_ARCHITECTURE.md
```

---

**End of Documentation**  
For questions or updates, contact the development team.

