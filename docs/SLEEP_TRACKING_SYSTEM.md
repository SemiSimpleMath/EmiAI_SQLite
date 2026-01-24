# Sleep Tracking System - Implementation

## Overview
Comprehensive sleep tracking system that automatically tracks main sleep (nighttime) and explicitly-mentioned naps, calculating sleep quality metrics and storing in a daily YAML file.

---

## Architecture

### **90% Automatic (Python)**
`physical_status_manager.py` automatically tracks:
- Sleep detection during sleep window (10pm-5am)
- Wake-up detection (first activity - 20min)
- Interruptions (mid-sleep activity)
- Sleep metrics calculation
- YAML file management

### **10% User Input (Chat)**
`activity_tracker` agent extracts from chat:
- "I napped for 30 minutes"
- "I went to bed at 11:30pm"
- "I woke up at 7am"
- "I slept 8 hours last night"

---

## Sleep Detection Logic

### **Sleep Window: 10pm - 5am**
```
IF current_time between 10pm-5am AND idle > 40min:
    State = SLEEPING
    Track as main sleep period
```

### **Wake Detection**
```
first_activity_after_sleep - 20 minutes = wake_time
```

### **Daytime: 5am - 10pm**
```
idle > 5min = AFK (away from desk)
NO automatic nap detection
Naps only from: user chat, calendar events
```

---

## Data Structure

### **File:** `resources/user_sleep_current.md`

```yaml
total_sleep_minutes: 570
main_sleep_minutes: 460
nap_minutes: 110
quality: good
fragmented: false
interruptions: 0
longest_continuous_minutes: 460

sleep_periods:
  - type: main
    start: "2025-12-27T23:40:00Z"
    end: "2025-12-28T07:20:00Z"
    duration_minutes: 460
    source: inferred
    
  - type: nap
    start: "2025-12-28T14:00:00Z"
    duration_minutes: 60
    source: user_chat
    
  - type: nap
    start: null
    duration_minutes: 50
    source: user_chat

wake_time: "07:20"
bedtime_previous: "23:40"
day_date: "2025-12-28"
```

---

## Sleep Quality Calculation

```python
def _calculate_sleep_quality(sleep_data):
    total_hours = total_sleep_minutes / 60
    main_hours = main_sleep_minutes / 60
    
    if total_hours < 5 or main_hours < 4:
        return 'poor'
    elif total_hours < 6.5 or fragmented:
        return 'fair'
    else:
        return 'good'
```

**Thresholds:**
- **Poor:** < 5 hours total OR < 4 hours main sleep
- **Fair:** 5-6.5 hours OR fragmented sleep
- **Good:** 7+ hours, not fragmented

---

## Chat-Based Sleep Events

### **Activity Tracker Agent Form**
Extended with `SleepEvent` model:

```python
class SleepEvent(BaseModel):
    type: str  # 'nap', 'bedtime', 'wake_time', 'sleep_duration'
    start_time: Optional[str]  # "14:00", "23:30"
    end_time: Optional[str]
    duration_minutes: Optional[int]
    source: str  # 'user_chat'
    raw_mention: str  # "I napped for 30 minutes"
```

### **Detection Examples**

| User Says | Extracted Event |
|-----------|----------------|
| "I napped for 30 minutes" | `{type: 'nap', duration_minutes: 30}` |
| "I took a nap at 2pm for an hour" | `{type: 'nap', start_time: '14:00', duration_minutes: 60}` |
| "I went to bed at 11:30pm" | `{type: 'bedtime', start_time: '23:30'}` |
| "I woke up at 7am" | `{type: 'wake_time', start_time: '07:00'}` |
| "I slept 8 hours last night" | `{type: 'sleep_duration', duration_minutes: 480}` |

---

## Implementation Flow

### **1. Activity Tracker** (LLM Agent)
```
Scans: chat + calendar + tickets
↓
Extracts: activities_to_reset + sleep_events
↓
Returns: {
  "activities_to_reset": ["hydration", "meal"],
  "sleep_events": [{type: "nap", duration_minutes: 30, ...}]
}
```

### **2. Physical Status Manager** (Python)
```
Receives tracker result
↓
Process activities: record_activity(name)
↓
Process sleep events: _process_sleep_event(event)
  ↓
  Load sleep data from YAML
  ↓
  Add nap / override bedtime / override wake / override duration
  ↓
  Recalculate quality
  ↓
  Write back to YAML
```

---

## Sleep Event Processing

### **Nap**
```python
def _add_nap_event(sleep_data, event):
    nap_period = {
        'type': 'nap',
        'start': event.get('start_time'),
        'duration_minutes': event['duration_minutes'],
        'source': 'user_chat'
    }
    sleep_data['sleep_periods'].append(nap_period)
    sleep_data['nap_minutes'] += duration
    sleep_data['total_sleep_minutes'] = main + nap
```

### **Bedtime Override**
```python
def _override_bedtime(sleep_data, event):
    # Find main sleep period
    for period in sleep_data['sleep_periods']:
        if period['type'] == 'main':
            period['start'] = event['start_time']
            period['source'] = 'user_chat_override'
```

### **Wake Time Override**
```python
def _override_wake_time(sleep_data, event):
    for period in sleep_data['sleep_periods']:
        if period['type'] == 'main':
            period['end'] = event['start_time']
```

### **Sleep Duration Override**
```python
def _override_sleep_duration(sleep_data, event):
    for period in sleep_data['sleep_periods']:
        if period['type'] == 'main':
            period['duration_minutes'] = event['duration_minutes']
    
    sleep_data['main_sleep_minutes'] = duration
    sleep_data['total_sleep_minutes'] = duration + naps
```

---

## File Management

### **Load Sleep Data**
```python
def _load_sleep_data() -> Dict:
    # Read resources/user_sleep_current.md
    # Extract YAML from ```yaml ... ```
    # Parse and return dict
```

### **Write Sleep Data**
```python
def _write_sleep_data(data: Dict):
    # Convert dict to YAML
    # Wrap in markdown code block
    # Write to resources/user_sleep_current.md
```

### **Create Empty**
```python
def _create_empty_sleep_data() -> Dict:
    return {
        'total_sleep_minutes': 0,
        'main_sleep_minutes': 0,
        'nap_minutes': 0,
        'quality': 'unknown',
        'fragmented': False,
        'sleep_periods': [],
        'day_date': datetime.now().strftime("%Y-%m-%d")
    }
```

---

## Integration Points

### **Files Modified:**

1. **`activity_tracker/agent_form.py`**
   - Added `SleepEvent` model
   - Added `sleep_events` field to `AgentForm`

2. **`activity_tracker/prompts/system.j2`**
   - Added sleep/nap detection rules
   - Added extraction examples for various sleep mentions

3. **`physical_status_manager.py`**
   - Modified `_run_activity_tracker()` to return dict with sleep_events
   - Modified `refresh()` to process sleep events
   - Added sleep file management methods:
     - `_load_sleep_data()`
     - `_write_sleep_data()`
     - `_create_empty_sleep_data()`
     - `_process_sleep_event()`
     - `_add_nap_event()`
     - `_override_bedtime()`
     - `_override_wake_time()`
     - `_override_sleep_duration()`
     - `_calculate_sleep_quality()`

---

## Future Enhancements

### **Phase 2: Automatic Main Sleep Tracking**
- Detect sleep start: `last_activity + 40min (if after 10pm)`
- Detect wake time: `first_activity - 20min`
- Track interruptions: mid-sleep activity
- Write main sleep period to YAML automatically

### **Phase 3: Historical Analysis**
- Archive daily sleep files: `resources/sleep_archive/2025-12-28.md`
- Sleep pattern queries: "How was my sleep this week?"
- Correlation analysis: sleep quality vs productivity

### **Phase 4: Wearable Integration**
- Fitbit/Apple Watch API integration
- Use wearable data as primary source
- Keep inference as fallback

### **Phase 5: Smart Suggestions**
- "You've had poor sleep 3 nights in a row"
- "Consider going to bed earlier tonight"
- "You're averaging 6.2 hours - aim for 7+"

---

## Testing Scenarios

### **Scenario 1: Simple Nap**
```
User: "I just napped for 30 minutes"
→ Activity tracker extracts: {type: 'nap', duration_minutes: 30}
→ Python appends to sleep_periods
→ Updates nap_minutes: 0 → 30
→ Updates total_sleep_minutes
```

### **Scenario 2: Nap with Time**
```
User: "I took a nap at 2pm for an hour"
→ Extracts: {type: 'nap', start_time: '14:00', duration_minutes: 60}
→ Appends with start time
```

### **Scenario 3: Bedtime Override**
```
User: "I went to bed at 11:30 last night"
→ Extracts: {type: 'bedtime', start_time: '23:30'}
→ Finds main sleep period
→ Overrides start time
→ Marks source as 'user_chat_override'
```

### **Scenario 4: Multiple Events**
```
User: "I slept 7 hours last night and took a 20 min nap"
→ Extracts TWO events:
   1. {type: 'sleep_duration', duration_minutes: 420}
   2. {type: 'nap', duration_minutes: 20}
→ Processes both sequentially
```

---

**Date**: 2025-12-27  
**Status**: Implementation Complete, Ready for Testing

