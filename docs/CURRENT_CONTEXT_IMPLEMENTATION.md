# Current Context - Proper Implementation

## The Right Approach

You're absolutely correct - `current_context` (what user is currently doing) SHOULD be tracked, but it needs to be **computed from multiple reliable sources**, not guessed by an agent.

---

## Data Sources Available

### 1. Calendar (resource_daily_context.json)
```json
{
  "day_description": "focused on work schedule, with evening plans for family time",
  "milestones": [
    {"time": "09:00 AM", "description": "Work Hours"},
    {"time": "06:00 PM", "description": "Family time"}
  ]
}
```

### 2. Location (resource_user_location.json)
```json
{
  "current_location": {"label": "Home"},
  "location_timeline": [
    {
      "start": "17:00", 
      "end": "00:30",
      "label": "Home",
      "reasoning": "Work hours at home after meeting"
    }
  ]
}
```

### 3. Recent Chat
- User: "working on the database migration"
- User: "taking a break"
- User: "about to start cooking"

### 4. Accepted Tickets
- Just accepted "walk" ticket
- Just accepted "meal" ticket

### 5. Computer Activity
- `active_work_session_minutes: 120` → Deep in focus
- `is_afk: true` → Away from computer

---

## How to Compute `current_context`

```python
def compute_current_context(now):
    """
    Determine what user is currently doing based on multiple data sources.
    
    Returns one of:
    - "Working" (in work hours, active on computer)
    - "In Meeting" (calendar event now)
    - "Personal Time" (family time, evening)
    - "Sleeping" (during sleep hours, AFK)
    - "Away" (AFK during day, not sleeping)
    - "Break" (short AFK during work hours)
    - Specific activity from chat/tickets (e.g., "Cooking", "Walking dogs")
    """
    
    # 1. Check calendar - current event
    current_event = get_current_calendar_event(now)
    if current_event:
        if "meeting" in current_event.title.lower():
            return "In Meeting"
        if "family" in current_event.title.lower():
            return "Personal Time"
        # Return event title if specific
        return current_event.title
    
    # 2. Check recent accepted tickets (last 15 min)
    recent_ticket = get_last_accepted_ticket(minutes=15)
    if recent_ticket:
        # User just accepted "walk" → probably walking
        return recent_ticket.suggestion_type.title()  # "Walk", "Meal", etc.
    
    # 3. Check recent chat mentions (last 30 min)
    recent_activity = extract_current_activity_from_chat(minutes=30)
    if recent_activity:
        return recent_activity  # "Working on migration", "Cooking dinner"
    
    # 4. Check AFK status
    if is_afk and is_sleep_hours():
        return "Sleeping"
    if is_afk and afk_duration > 30:
        return "Away"
    if is_afk and afk_duration < 10:
        return "Break"
    
    # 5. Check daily context + location
    if is_work_hours() and location == "Home" and is_active:
        return "Working"
    if is_evening() and location == "Home":
        return "Personal Time"
    
    # 6. Default
    return "Active"
```

---

## Example Scenarios

| Time | Calendar | Location | Computer | Chat | Result |
|------|----------|----------|----------|------|--------|
| 10:00 AM | Work Hours | Home | Active (120 min) | "working on migration" | **"Working on migration"** |
| 10:30 AM | Analytics Meeting | Home | Active | - | **"In Meeting"** |
| 12:00 PM | - | Home | AFK (5 min) | - | **"Break"** |
| 12:30 PM | - | Home | Active | Just accepted "meal" | **"Eating"** |
| 6:00 PM | Family Time | Home | AFK | - | **"Personal Time"** |
| 8:00 PM | Walk dogs | Home | AFK | - | **"Walking dogs"** |
| 11:00 PM | - | Home | AFK | - | **"Sleeping"** |

---

## Implementation Location

**Option A: Compute in PhysicalStatusManager**
```python
# In physical_status_manager.py
def _compute_current_context(self) -> str:
    """Compute what user is currently doing."""
    # ... logic above ...
    return context

# Called during refresh()
self.status_data["cognitive_state"]["current_context"] = self._compute_current_context()
```

**Option B: Compute in status_inference agent**
- Agent reads calendar + location + chat
- Uses LLM to synthesize "what is user doing?"
- More flexible, can understand nuance

**Recommended: Option A (rule-based)** for now
- Faster, no LLM call
- More predictable
- Can switch to Option B later if needed

---

## How Proactive_Orchestrator Uses It

### 1. Respect Work Context
```python
if current_context in ["Working", "In Meeting", "Working on migration"]:
    # Only suggest quick breaks (finger stretch, hydration)
    # Don't suggest longer activities (walk, exercise)
```

### 2. Respect Personal Time
```python
if current_context in ["Personal Time", "Family time"]:
    # Reduce work-related suggestions
    # Focus on wellness (hydration, sleep prep)
```

### 3. Catch Specific Activities
```python
if current_context == "Walking dogs":
    # Don't suggest another walk!
    # Wait until they're back

if current_context == "Eating":
    # Don't suggest meals/snacks
    # Maybe suggest water after meal
```

### 4. Timing Suggestions
```python
if current_context == "Break":
    # Perfect time for stretch/hydration suggestions
    high_priority_suggestions()
```

---

## Benefits

✅ **Accurate** - Based on multiple reliable sources, not speculation  
✅ **Actionable** - Proactive_orchestrator can make smart decisions  
✅ **Understandable** - Clear what user is doing  
✅ **Maintainable** - Rule-based logic, not LLM guesswork  

---

## Decision

**KEEP `current_context`** but:
1. Compute it properly from calendar + location + chat + tickets
2. Make it rule-based (not LLM-inferred)
3. Use it for intelligent suggestion timing
4. Update it frequently (every refresh cycle)

This makes it one of the most valuable fields for proactive orchestration!
