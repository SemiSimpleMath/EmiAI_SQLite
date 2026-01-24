# Debug UI - Wellness Activities Display - Complete ✅

## What Was Added

Added the `resource_user_wellness_activities.json` content to the debug UI at `/debug/status`.

---

## Changes Made

### 1. Backend (debug_status.py)

**Line 207:** Load the resource file
```python
wellness_activities_raw = load_resource("resource_user_wellness_activities.json")
```

**Line 214:** Convert timestamps to local time
```python
wellness_activities_local = _convert_timestamps_to_local(wellness_activities_raw)
```

**Line 237:** Include in JSON response
```python
"wellness_activities": wellness_activities_local,  # NEW - Tracking data
```

---

### 2. Frontend (debug_status.html)

**Lines 249-257:** New card displaying wellness activities

```javascript
html += '<div class="card"><h2>✅ Wellness Activities (Tracking Data)</h2>';
html += '<h3>resource_user_wellness_activities.json</h3>';
html += '<p style="font-size: 12px; color: #7ee787; margin-bottom: 10px;">';
html += '📊 Actual timestamps & counts (auto-updates after each activity)';
html += '</p>';
const wellnessActivities = data.wellness_activities || {};
html += `<pre class="raw-json">${syntaxHighlight(wellnessActivities)}</pre>`;
html += '</div>';
```

**Position:** Placed right after "Tracked Activities (Config)" card for logical grouping:
- Config (what to track)
- Data (actual tracking values)

---

## What You'll See

After restart, visit `http://localhost:5000/debug/status` and you'll see a new card:

```
┌─────────────────────────────────────────────┐
│ ✅ Wellness Activities (Tracking Data)     │
│ resource_user_wellness_activities.json      │
│ 📊 Actual timestamps & counts               │
│ (auto-updates after each activity)          │
├─────────────────────────────────────────────┤
│ {                                           │
│   "_metadata": {                            │
│     "resource_id": "resource_user_...",     │
│     "last_updated": "2026-01-08 12:34 PM"   │
│   },                                        │
│   "activities": {                           │
│     "last_hydration": "2026-01-08 11:30 AM",│
│     "last_coffee": "2026-01-08 09:00 AM",   │
│     "last_meal": "2026-01-08 12:00 PM",     │
│     ...                                     │
│   },                                        │
│   "counters": {                             │
│     "coffees_today": 2,                     │
│     "coffees_today_date": "2026-01-08"      │
│   }                                         │
│ }                                           │
└─────────────────────────────────────────────┘
```

---

## Features

### 1. **Timestamps in Local Time** 🕐
All timestamps are automatically converted to your local timezone:
- `"2026-01-08T11:30:00Z"` → `"2026-01-08 11:30:00 AM PST"`

### 2. **Syntax Highlighting** 🎨
- Keys: Green
- Strings: Blue
- Numbers: Light blue
- Nulls: Gray

### 3. **Auto-Refresh** 🔄
Click "🔄 Refresh Data" button to reload the page and see latest values.

### 4. **Real-Time Updates** ⚡
After recording an activity (e.g., "drank water"), refresh the page to see:
- Updated `last_hydration` timestamp
- Updated `last_updated` in metadata

---

## Card Ordering

The wellness activities card appears in the logical flow:

1. LLM Agent Outputs (activity_tracker, health_status_inference)
2. Health Status (orchestrator input)
3. User Health (traits)
4. Sleep Data
5. **Tracked Activities (Config)** ← What to track
6. **✅ Wellness Activities (Data)** ← NEW - Actual values
7. Location
8. Daily Context
9. User Routine
10. Sleep Segments Log (DB)
11. AFK Events Log (DB)
12. Wake Segments Log (DB)
13. Physical Status (legacy)

---

## Testing

### 1. View Initial State
```
Visit: http://localhost:5000/debug/status
See: All activities with null timestamps, counters at 0
```

### 2. Record an Activity
```
In chat: "drank water"
Click: 🔄 Refresh Data
See: last_hydration now has a timestamp
```

### 3. Trigger Day Start
```
Trigger day start (wake up)
Click: 🔄 Refresh Data
See: All activities reset to null, counters to 0
```

---

## Summary

✅ **Backend:** Loads `resource_user_wellness_activities.json` and converts timestamps  
✅ **Frontend:** Displays in new card with syntax highlighting  
✅ **Positioning:** Right after config file for easy comparison  
✅ **Real-time:** Updates automatically on every activity record/reset

**The wellness activities tracking data is now visible in the debug UI!** 🎉
