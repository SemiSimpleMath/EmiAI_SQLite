"""
JSON to Markdown Renderer for Agent Prompts

Renders JSON preference files as human-readable markdown for LLM agents.
"""

from typing import Any, Dict, List
import json


def render_json_to_markdown(data: Dict[str, Any], resource_id: str) -> str:
    """
    Convert JSON preference data to markdown for agent consumption.
    
    Args:
        data: JSON data with _metadata and content
        resource_id: The resource identifier
        
    Returns:
        Markdown-formatted string
    """
    if resource_id == 'resource_user_food_prefs':
        return _render_food_prefs(data)
    elif resource_id == 'resource_user_routine':
        return _render_routine(data)
    elif resource_id == 'resource_user_health':
        return _render_health(data)
    elif resource_id == 'resource_user_general_prefs':
        return _render_general_prefs(data)
    else:
        # Generic renderer
        return _render_generic(data, resource_id)


def _render_food_prefs(data: Dict) -> str:
    """Render food preferences JSON as markdown."""
    lines = ["# User Food & Drink Preferences\n"]
    
    food = data.get('food', {})
    
    # Food Likes
    likes = food.get('likes', [])
    if likes:
        lines.append("## Food Likes")
        for item in likes:
            display = item.get('display', item.get('item', ''))
            lines.append(f"- {display}")
        lines.append("")
    
    # Food Dislikes
    dislikes = food.get('dislikes', [])
    if dislikes:
        lines.append("## Food Dislikes")
        for item in dislikes:
            display = item.get('display', item.get('item', ''))
            lines.append(f"- {display}")
        lines.append("")
    
    # Food Preferences (text)
    prefs = food.get('preferences', [])
    if prefs:
        lines.append("## Food Preferences")
        for pref in prefs:
            text = pref.get('text', pref) if isinstance(pref, dict) else pref
            lines.append(f"- {text}")
        lines.append("")
    
    # Allergies
    allergies = food.get('allergies', [])
    if allergies:
        lines.append("## Allergies & Dietary Restrictions")
        for allergy in allergies:
            display = allergy.get('display', allergy.get('item', '')) if isinstance(allergy, dict) else allergy
            lines.append(f"- {display}")
    else:
        lines.append("## Allergies & Dietary Restrictions")
        lines.append("- None known")
    lines.append("")
    
    # Drinks
    drinks = data.get('drinks', {})
    if drinks:
        lines.append("## Drinks")
        
        # Coffee
        coffee = drinks.get('coffee', {})
        if coffee:
            lines.append("### Coffee")
            for key, value in coffee.items():
                if key not in ['added', 'expiry'] and value:
                    # Format key nicely
                    label = key.replace('_', ' ').title()
                    lines.append(f"- {label}: {value}")
            lines.append("")
        
        # Other drinks
        other = drinks.get('other', [])
        if other:
            lines.append("### Other Beverages")
            for drink in other:
                if isinstance(drink, dict):
                    pref = drink.get('preference', drink.get('display', ''))
                    lines.append(f"- {pref}")
                else:
                    lines.append(f"- {drink}")
            lines.append("")
    
    # Meal Timing
    timing = data.get('meal_timing', {})
    if timing:
        lines.append("## Meal Timing")
        for meal, time in timing.items():
            label = meal.title()
            lines.append(f"- **{label}**: {time}")
        lines.append("")
    
    return "\n".join(lines)


def _render_routine(data: Dict) -> str:
    """Render routine preferences JSON as markdown."""
    lines = ["# User Daily Routine\n"]
    
    # Morning
    morning = data.get('morning', {})
    if morning:
        lines.append("## Morning Routine\n")
        
        wake_up = morning.get('wake_up', {})
        if wake_up:
            lines.append("### Wake Up")
            if 'usual_time' in wake_up:
                lines.append(f"- Usually wakes around {wake_up['usual_time']}")
            for note in wake_up.get('notes', []):
                lines.append(f"- {note}")
            lines.append("")
        
        pre_work = morning.get('pre_work', [])
        if pre_work:
            lines.append("### Pre-Work")
            for item in pre_work:
                if isinstance(item, dict):
                    time = item.get('time', '')
                    activity = item.get('activity', '')
                    pref = item.get('preference', '')
                    if time and activity:
                        lines.append(f"- {time}: {activity}")
                    elif activity:
                        lines.append(f"- {activity}")
                    elif pref:
                        lines.append(f"- {pref}")
                else:
                    lines.append(f"- {item}")
            lines.append("")
    
    # Work
    work = data.get('work', {})
    if work:
        lines.append("## Work Routine\n")
        
        focus = work.get('focus_time', {})
        if focus:
            lines.append("### Focus Time")
            if 'best_hours' in focus:
                lines.append(f"- Best hours: {focus['best_hours']}")
            for note in focus.get('notes', []):
                lines.append(f"- {note}")
            lines.append("")
        
        meetings = work.get('meetings', {})
        if meetings:
            lines.append("### Meetings")
            for pref in meetings.get('preferences', []):
                lines.append(f"- {pref}")
            lines.append("")
        
        breaks = work.get('breaks', [])
        if breaks:
            lines.append("### Breaks")
            for item in breaks:
                lines.append(f"- {item}")
            lines.append("")
    
    # Evening
    evening = data.get('evening', {})
    if evening:
        lines.append("## Evening Routine\n")
        
        after_work = evening.get('after_work', {})
        if after_work:
            lines.append("### After Work")
            if 'family_time_start' in after_work:
                lines.append(f"- Family time starts: {after_work['family_time_start']}")
            for note in after_work.get('notes', []):
                lines.append(f"- {note}")
            lines.append("")
        
        wind_down = evening.get('wind_down', [])
        if wind_down:
            lines.append("### Wind Down")
            for item in wind_down:
                if isinstance(item, dict):
                    time = item.get('time', '')
                    activity = item.get('activity', '')
                    pref = item.get('preference', '')
                    goal = item.get('goal', '')
                    if time and activity:
                        lines.append(f"- {time}: {activity}")
                    elif pref:
                        lines.append(f"- {pref}")
                    elif goal:
                        lines.append(f"- Goal: {goal}")
                else:
                    lines.append(f"- {item}")
            lines.append("")
    
    return "\n".join(lines)


def _render_health(data: Dict) -> str:
    """Render health preferences JSON as markdown."""
    lines = ["# User Health & Accommodations\n"]
    
    # Chronic conditions
    conditions = data.get('chronic_conditions', [])
    if conditions:
        lines.append("## Chronic Conditions\n")
        for cond in conditions:
            display = cond.get('display', cond.get('condition', ''))
            lines.append(f"### {display}")
            if 'severity' in cond:
                lines.append(f"- Severity: {cond['severity']}")
            if 'accommodation' in cond:
                lines.append(f"- Accommodation: {cond['accommodation']}")
            if 'suggested_interval_minutes' in cond:
                lines.append(f"- Suggested interval: Every {cond['suggested_interval_minutes']} minutes")
            lines.append("")
    
    # Sleep
    sleep = data.get('sleep', {})
    if sleep:
        lines.append("## Sleep")
        for key, value in sleep.items():
            if value:
                label = key.replace('_', ' ').title()
                lines.append(f"- {label}: {value}")
        lines.append("")
    
    # Exercise
    exercise = data.get('exercise', {})
    if exercise:
        lines.append("## Exercise")
        for pref in exercise.get('preferences', []):
            lines.append(f"- {pref}")
        lines.append("")
    
    # Pet care
    pet_care = data.get('pet_care', [])
    if pet_care:
        lines.append("## Pet Care")
        for item in pet_care:
            if isinstance(item, dict):
                activity = item.get('activity', '')
                timing = item.get('timing', '')
                lines.append(f"- {activity}: {timing}")
            else:
                lines.append(f"- {item}")
        lines.append("")
    
    return "\n".join(lines)


def _render_general_prefs(data: Dict) -> str:
    """Render general preferences JSON as markdown."""
    lines = ["# User General Preferences\n"]
    
    # Communication
    comm = data.get('communication', {})
    if comm:
        lines.append("## Communication")
        if 'style' in comm:
            lines.append("### Style")
            for item in comm['style']:
                lines.append(f"- {item}")
            lines.append("")
        if 'notifications' in comm:
            lines.append("### Notifications")
            for item in comm['notifications']:
                lines.append(f"- {item}")
            lines.append("")
    
    # Language
    lang = data.get('language', {})
    if lang:
        lines.append("## Language")
        if 'primary' in lang:
            lines.append(f"- Primary: {lang['primary']}")
        lines.append("")
    
    # Entertainment
    ent = data.get('entertainment', {})
    if ent:
        interests = ent.get('interests', [])
        if interests:
            lines.append("## Interests & Entertainment")
            for item in interests:
                if isinstance(item, dict):
                    display = item.get('display', item.get('item', ''))
                    note = item.get('note', '')
                    if note:
                        lines.append(f"- {display}: {note}")
                    else:
                        lines.append(f"- {display}")
                else:
                    lines.append(f"- {item}")
            lines.append("")
    
    return "\n".join(lines)


def _render_generic(data: Dict, resource_id: str) -> str:
    """Generic JSON to markdown renderer."""
    lines = [f"# {resource_id}\n"]
    
    for key, value in data.items():
        if key == '_metadata':
            continue
        
        lines.append(f"## {key.replace('_', ' ').title()}")
        lines.append(f"```json\n{json.dumps(value, indent=2)}\n```")
        lines.append("")
    
    return "\n".join(lines)

