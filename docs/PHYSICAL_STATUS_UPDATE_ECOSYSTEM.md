# Who Updates resource_user_physical_status.json?

## Overview
Multiple components contribute to the physical status file. Here's the complete ecosystem:

---

## 1. Physical_Status_Inference Agent (LLM)

**File:** `app/assistant/agents/physical_status_inference/`

### What it computes:
Analyzes all available data and **infers** the user's current state.

### Input (what it reads):
- Sleep summary (last 24 hours)
- Activity timers (time since last hydration, meal, etc.)
- Recent tickets (accepted/dismissed)
- Calendar (meetings, schedule load)
- Chat history (mood, mentions of pain/tiredness)
- Health profile (chronic conditions from user_health.json)

### Output (what it writes):
```python
{
  "health_status": {
    "overall_wellness": "Good | Fair | Poor",
    "acute_conditions_detected": ["Headache"],  # From chat
    "chronic_conditions_flaring": ["Back Pain"]  # From overdue timers
  },
  "physiology": {
    "energy_level": "High | Normal | Waning | Depleted",
    "hunger_probability": "Low | Medium | High",
    "hydration_need": "Low | Medium | High",
    "caffeine_state": "Under-caffeinated | Optimal | Over-caffeinated | Cutoff-Reached"
  },
  "cognitive_state": {
    "load": "Low | Medium | High",
    "interruption_tolerance": "High | Medium | Low | Zero",
    "focus_depth": "Scattered | Normal | Deep_Work"
  },
  "emotional_state": {
    "mood": "Positive | Neutral | Stressed | Frustrated",
    "social_battery": "Available | Drained"
  },
  "schedule_pressure": {
    "meeting_density": "Open | Moderate | Packed",
    "next_free_block_minutes": 45,
    "imminent_deadline": false
  }
}
```

### When it runs:
- Every `refresh()` cycle (triggered by background_task_manager)
- Currently every 2-5 minutes

### What it's GOOD at:
- ✅ Energy level (from sleep + time-of-day)
- ✅ Cognitive load (from calendar meetings)
- ✅ Schedule pressure (from calendar)
- ✅ Detecting acute pain from chat ("my head hurts")

### What it's BAD at:
- ❌ Social_battery (can't detect, no data)
- ❌ Accomplishment_boost (always "Unknown")
- ❌ Mental clarity (always "Unknown")

---

## 2. AFKMonitor (Python - Direct Updates)

**File:** `app/assistant/physical_status_manager/afk_monitor.py`

### What it updates:
```python
"computer_activity": {
  "idle_seconds": 0.1,
  "idle_minutes": 0.0,
  "is_afk": false,
  "is_potentially_afk": false,
  "last_checked": "...",
  "active_work_session_start": "...",
  "active_work_session_minutes": 19.7,
  "total_afk_time_today": 587.9,
  "total_active_time_today": 387.0
}
```

### When it runs:
- Every `refresh()` cycle
- Checks system idle time via `pywinctl` or OS APIs

### Purpose:
- Track if user is at computer or away
- Calculate work session duration
- Feed into cognitive load assessment

---

## 3. ActivityRecorder (Python - Direct Updates)

**File:** `app/assistant/physical_status_manager/activity_recorder.py`

### What it updates:
```python
"wellness_activities": {
  "last_hydration": "2026-01-07T22:59:59...",
  "last_coffee": "2026-01-07T19:14:47...",
  "last_finger_stretch": "2026-01-07T22:56:18...",
  "last_meal": "2026-01-07T19:49:50...",
  "coffees_today": 2,
  "coffees_today_date": "2026-01-07"
  // ... all other wellness activities
}
```

### When it updates:
1. **Activity_tracker agent** detects activity from chat → calls `record_activity()`
2. **Proactive ticket accepted** → `status_effect` triggers `record_activity()`
3. **Manual API calls** (via wellness UI)

### Purpose:
- Track when each wellness activity last occurred
- Count daily activities (coffee, hydration, etc.)
- Feed into "is user overdue for break?" logic

---

## 4. DayStartManager (Python - Direct Updates)

**File:** `app/assistant/physical_status_manager/day_start_manager.py`

### What it updates:
```python
"day_started": true,
"day_start_time": "2026-01-07T06:45:01...",
"morning_greeting_sent": false,
"last_night_sleep": {
  "total_hours": 8.5,
  "quality": "good",
  "segments": [...]
}
```

### When it updates:
1. User returns from sleep AFK
2. Activity_tracker detects "I'm up" in chat
3. Cold start / stale day detection

### Purpose:
- Mark when day officially started
- Capture last night's sleep summary
- Reset daily counters

---

## 5. SleepSegmentTracker (Python - Database → Resource File)

**File:** `app/assistant/physical_status_manager/sleep_segment_tracker.py`

### What it updates:
- Writes sleep segments to **database** (`sleep_segments` table)
- Generates `resource_user_sleep_current.json` from database

### When it updates:
1. AFK return during sleep window → records segment
2. Activity_tracker detects "I slept from 11 PM to 7 AM" → records segment
3. Cold start → creates synthetic segment

### Purpose:
- Permanent sleep history in database
- Current sleep context for agents (last 24h in resource file)

---

## 6. BackgroundTaskManager (Orchestration)

**File:** `app/assistant/background_task_manager/background_task_manager.py`

### What it does:
Doesn't update directly, but **triggers the refresh cycle**:

```python
physical_status_manager.refresh()
  → afk_monitor.update_computer_activity()  # Update AFK status
  → _run_activity_tracker()                 # Detect activities from chat
  → _run_status_inference()                 # LLM analyzes state
  → _update_status_from_result()            # Apply LLM output
  → _save_status()                          # Write to file
```

### Frequency:
- Every 2-5 minutes (configurable)

---

## DATA FLOW DIAGRAM

```
User Activity Sources:
├─ System idle time ──────────► AFKMonitor ──────────┐
├─ Chat messages ──────────────► Activity_Tracker ───┤
├─ Calendar events ────────────► Calendar Manager ───┤
├─ Proactive tickets ──────────► Ticket Manager ─────┤
└─ Sleep/AFK patterns ─────────► Sleep Tracker ──────┤
                                                      ▼
                                        PhysicalStatusManager
                                        (In-memory status_data)
                                                │
                                    ┌───────────┴───────────┐
                                    │                       │
                            Physical_Status_Inference    Direct Updates
                            (LLM analyzes)               (Python code)
                                    │                       │
                                    │                       │
                        ┌───────────┴──────────┐            │
                        │                      │            │
                    Physiology          Cognitive/      Wellness
                    Energy, hunger      Emotional       Activities
                    caffeine state      load, mood      Timestamps
                        │                      │            │
                        └──────────────────────┴────────────┘
                                         │
                                         ▼
                        resource_user_physical_status.json
                        (Written every refresh cycle)
```

---

## SUMMARY: WHO DOES WHAT

| Component | Updates | Method | Frequency |
|-----------|---------|--------|-----------|
| **physical_status_inference** | Physiology, Cognitive, Emotional, Schedule | LLM inference | Every refresh (2-5 min) |
| **AFKMonitor** | computer_activity | Direct (system APIs) | Every refresh (2-5 min) |
| **ActivityRecorder** | wellness_activities | Direct (from chat/tickets) | On activity detection |
| **DayStartManager** | day_started, last_night_sleep | Direct (on wake-up) | Once per day |
| **SleepSegmentTracker** | (writes to DB, generates sleep resource) | Direct (on AFK return) | When sleep detected |

---

## KEY INSIGHT

**Two types of updates:**

1. **Computed/Inferred (LLM):**
   - Energy level, mood, cognitive load
   - "What do I think the user's state is?"
   - Can be wrong, speculative

2. **Observed/Measured (Python):**
   - Last hydration time, AFK status, sleep duration
   - "What actually happened?"
   - Factual, reliable

**Best practice:** Rely on measured data where possible, use inferred data for suggestions only.
