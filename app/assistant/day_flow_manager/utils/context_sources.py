from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.assistant.utils.logging_config import get_logger
from app.assistant.utils.path_utils import get_resources_dir
from app.assistant.utils.time_utils import parse_time_string, utc_to_local

logger = get_logger(__name__)


def _parse_utc(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _load_calendar_events() -> List[Dict[str, Any]]:
    try:
        from app.assistant.event_repository.event_repository import EventRepositoryManager

        repo = EventRepositoryManager()
        events_json = repo.search_events(data_type="calendar")
        events_list = json.loads(events_json) if events_json else []

        parsed: List[Dict[str, Any]] = []
        for event in events_list:
            data = event.get("data", {})
            if isinstance(data, str):
                try:
                    data = json.loads(data)
                except Exception:
                    continue

            start_iso = data.get("start", "")
            end_iso = data.get("end", "")
            start = _parse_utc(start_iso)
            end = _parse_utc(end_iso) if end_iso else None

            if not start:
                continue

            parsed.append({
                "summary": data.get("summary", "Untitled"),
                "start_utc": start,
                "end_utc": end,
                "attendees": data.get("attendees", []) or [],
            })

        return parsed
    except Exception as e:
        logger.warning(f"Could not load calendar events: {e}")
        return []


def _load_sleep_output() -> Dict[str, Any]:
    try:
        resources_dir = get_resources_dir()
        sleep_path = resources_dir / "resource_sleep_output.json"
        if not sleep_path.exists():
            return {}
        with sleep_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.warning(f"Could not load sleep output: {e}")
        return {}


def _format_local_time(dt: Optional[datetime]) -> str:
    if not dt:
        return ""
    return utc_to_local(dt).strftime("%I:%M %p")


def _is_meeting_event(summary: str, attendees: List[Any]) -> bool:
    label = (summary or "").lower()
    return bool(attendees) or "meeting" in label or "call" in label


def get_calendar_events_upcoming_for_daily_context(hours: int = 12) -> List[Dict[str, Any]]:
    now = datetime.now(timezone.utc)
    window_end = now + timedelta(hours=hours)
    result: List[Dict[str, Any]] = []

    for event in _load_calendar_events():
        start = event.get("start_utc")
        end = event.get("end_utc")
        if not start:
            continue
        if start > now and start < window_end:
            result.append({
                "summary": event.get("summary", "Untitled"),
                "start": _format_local_time(start),
                "end": _format_local_time(end),
            })

    return result


def get_calendar_events_completed(hours: int = 4) -> List[Dict[str, Any]]:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=hours)
    result: List[Dict[str, Any]] = []

    for event in _load_calendar_events():
        end = event.get("end_utc")
        if not end:
            continue
        if cutoff <= end <= now:
            result.append({
                "event_name": event.get("summary", "Untitled"),
                "end_time": _format_local_time(end),
            })

    return result


def get_calendar_events_for_orchestrator(hours: int = 4) -> List[Dict[str, Any]]:
    now = datetime.now(timezone.utc)
    window_end = now + timedelta(hours=hours)
    result: List[Dict[str, Any]] = []

    for event in _load_calendar_events():
        start = event.get("start_utc")
        end = event.get("end_utc")
        if not start:
            continue
        if start > now and start < window_end:
            result.append({
                "event_name": event.get("summary", "Untitled"),
                "start_time": _format_local_time(start),
                "end_time": _format_local_time(end),
            })

    return result


def get_calendar_events_for_health_inference(hours: int = 8) -> List[Dict[str, Any]]:
    now = datetime.now(timezone.utc)
    window_end = now + timedelta(hours=hours)
    result: List[Dict[str, Any]] = []

    for event in _load_calendar_events():
        start = event.get("start_utc")
        end = event.get("end_utc")
        if not start or not end:
            continue
        if end > now and start < window_end:
            result.append({
                "event_name": event.get("summary", "Untitled"),
                "start_time": _format_local_time(start),
                "end_time": _format_local_time(end),
                "is_meeting": _is_meeting_event(event.get("summary", ""), event.get("attendees", [])),
            })

    return result


#
# NOTE:
# We intentionally do NOT define "recent chat" wrapper functions here anymore.
# Callers should compute cutoff_utc and call:
#   DI.global_blackboard.get_recent_chat_since_utc(...)
#
# Post-processing (formatting excerpts/strings) should live in utilities that do
# not fetch from the blackboard, keeping the fetch API uniform.


def build_time_since() -> Dict[str, Any]:
    """
    Build time_since dict dynamically from config and output.
    
    Returns dict with:
    - minutes_since_{field_name}: float or None for each tracked activity
    - {field_name}_count_today: int for each tracked activity
    
    No hardcoded activity names - all derived from config.
    """
    try:
        stages_dir = Path(__file__).resolve().parents[1] / "stages" / "stage_configs"
        tracked_config_path = stages_dir / "config_tracked_activities.json"

        result: Dict[str, Any] = {}

        # Seed all keys from config with defaults
        if tracked_config_path.exists():
            try:
                tracked_config = json.loads(tracked_config_path.read_text(encoding="utf-8")) or {}
                activities_cfg = tracked_config.get("activities", {}) if isinstance(tracked_config, dict) else {}
                if isinstance(activities_cfg, dict):
                    for activity_cfg in activities_cfg.values():
                        if not isinstance(activity_cfg, dict):
                            continue
                        field_name = activity_cfg.get("field_name")
                        if isinstance(field_name, str) and field_name:
                            result[f"minutes_since_{field_name}"] = None
                            result[f"{field_name}_count_today"] = 0
            except Exception as e:
                logger.warning(f"Could not read tracked activities config: {e}")

        # Overlay actual values from output
        resources_dir = get_resources_dir()
        output_path = resources_dir / "resource_tracked_activities_output.json"
        output: Dict[str, Any] = {}
        if output_path.exists():
            output = json.loads(output_path.read_text(encoding="utf-8")) or {}

        activities = output.get("activities", {}) if isinstance(output, dict) else {}
        for field_name, data in activities.items():
            if not isinstance(data, dict):
                continue
            result[f"minutes_since_{field_name}"] = data.get("minutes_since")
            result[f"{field_name}_count_today"] = data.get("count_today", 0)

        return result
    except Exception as e:
        logger.warning(f"Could not build time_since: {e}")
        return {}


def get_recent_afk_intervals(
    hours: int = 8,
    limit: int = 20,
    min_duration_minutes: float = 10.0,
) -> List[Dict[str, Any]]:
    """
    Get recent AFK intervals derived from gaps between active segments.

    "Recent" means AFK gaps overlapping the window from wake -> now.
    If wake time is unavailable, fallback to the last `hours` window.
    """
    try:
        from app.assistant.afk_manager.afk_statistics import get_afk_intervals_overlapping_range

        now_utc = datetime.now(timezone.utc)
        is_currently_afk = False
        current_afk_minutes: Optional[float] = None
        try:
            afk_path = get_resources_dir() / "resource_afk_statistics_output.json"
            if afk_path.exists():
                afk_data = json.loads(afk_path.read_text(encoding="utf-8")) or {}
                if isinstance(afk_data, dict):
                    is_currently_afk = bool(afk_data.get("is_afk", False))
                    cur = afk_data.get("current_afk_minutes")
                    if isinstance(cur, (int, float)):
                        current_afk_minutes = float(cur)
        except Exception as e:
            logger.warning(f"Could not load AFK stats output: {e}")
        sleep_output = _load_sleep_output()
        wake_utc = _parse_utc(sleep_output.get("day_start_time_utc"))
        if not wake_utc:
            wake_local = sleep_output.get("wake_time_today")
            if wake_local:
                try:
                    wake_utc = parse_time_string(wake_local)
                except Exception:
                    wake_utc = None

        if not wake_utc or wake_utc >= now_utc:
            wake_utc = now_utc - timedelta(hours=hours)

        afk_intervals = get_afk_intervals_overlapping_range(
            start_utc=wake_utc,
            end_utc=now_utc,
            include_provisional=True,
        )

        if not afk_intervals:
            return []

        result: List[Dict[str, Any]] = []
        for interval in afk_intervals:
            start_utc = _parse_utc(interval.get("start_utc"))
            end_utc = _parse_utc(interval.get("end_utc"))
            if not start_utc or not end_utc or end_utc <= start_utc:
                continue

            # Trim to wake->now window for display and duration filtering.
            trimmed_start = max(start_utc, wake_utc)
            trimmed_end = min(end_utc, now_utc)
            if trimmed_end <= trimmed_start:
                continue

            duration = (trimmed_end - trimmed_start).total_seconds() / 60.0
            if duration < min_duration_minutes:
                continue

            is_ongoing = False
            if is_currently_afk:
                seconds_from_now = abs((now_utc - trimmed_end).total_seconds())
                if seconds_from_now <= 120:
                    is_ongoing = True
                    if current_afk_minutes is not None:
                        duration = current_afk_minutes

            start_local = utc_to_local(trimmed_start)
            end_local = "ongoing" if is_ongoing else utc_to_local(trimmed_end).strftime("%I:%M %p")
            result.append({
                "start_local": start_local.strftime("%I:%M %p"),
                "end_local": end_local,
                "duration_minutes": round(duration, 1),
                "end_utc": trimmed_end.isoformat(),
            })

        # Sort by most recent end time and limit.
        result.sort(key=lambda x: x["end_utc"], reverse=True)
        for item in result:
            item.pop("end_utc", None)
        return result[:limit]
    except Exception as e:
        logger.warning(f"Could not get AFK intervals: {e}")
        return []


def get_current_presence_status() -> Dict[str, Any]:
    """
    Get current user presence status for daily_context_generator.
    
    Returns dict with:
    - is_afk: bool
    - status_label: "AT_KEYBOARD" or "AWAY"
    - duration_minutes: float (current session or away duration)
    - start_time_local: str (when current state started)
    - most_recent_afk: dict or None (most recent completed AFK interval)
    """
    try:
        from app.assistant.ServiceLocator.service_locator import DI
        
        now_utc = datetime.now(timezone.utc)
        result: Dict[str, Any] = {
            "is_afk": False,
            "status_label": "AT_KEYBOARD",
            "duration_minutes": 0.0,
            "start_time_local": "",
            "most_recent_afk": None,
        }
        
        # Try to get live data from AFKMonitor
        monitor = getattr(DI, "afk_monitor", None)
        if monitor:
            snapshot = monitor.get_computer_activity()
            if isinstance(snapshot, dict):
                is_afk = bool(snapshot.get("is_afk", False))
                result["is_afk"] = is_afk
                result["status_label"] = "AWAY" if is_afk else "AT_KEYBOARD"
                
                if is_afk:
                    # AFK duration from idle_minutes
                    idle_mins = snapshot.get("idle_minutes") or snapshot.get("current_afk_minutes") or 0
                    result["duration_minutes"] = round(float(idle_mins), 1)
                    if idle_mins > 0:
                        start_utc = now_utc - timedelta(minutes=float(idle_mins))
                        result["start_time_local"] = utc_to_local(start_utc).strftime("%I:%M %p")
                else:
                    # Active session duration - compute from active_start_utc
                    active_start_iso = snapshot.get("active_start_utc")
                    if active_start_iso:
                        try:
                            active_start = _parse_utc(active_start_iso)
                            if active_start and active_start < now_utc:
                                active_mins = (now_utc - active_start).total_seconds() / 60.0
                                result["duration_minutes"] = round(active_mins, 1)
                                result["start_time_local"] = utc_to_local(active_start).strftime("%I:%M %p")
                        except Exception:
                            logger.debug("Could not parse active_start_utc from AFK snapshot", exc_info=True)
        
        # Get most recent completed AFK interval (not ongoing)
        try:
            from app.assistant.afk_manager.afk_statistics import get_afk_intervals_overlapping_range
            
            # Look back 8 hours for recent AFK
            start_window = now_utc - timedelta(hours=8)
            afk_intervals = get_afk_intervals_overlapping_range(
                start_utc=start_window,
                end_utc=now_utc,
                include_provisional=False,  # Only completed intervals
            )
            
            if afk_intervals:
                # Sort by end time, get most recent
                sorted_intervals = sorted(
                    afk_intervals,
                    key=lambda x: x.get("end_utc", ""),
                    reverse=True
                )
                for interval in sorted_intervals:
                    start_utc = _parse_utc(interval.get("start_utc"))
                    end_utc = _parse_utc(interval.get("end_utc"))
                    if start_utc and end_utc and end_utc > start_utc:
                        duration = (end_utc - start_utc).total_seconds() / 60.0
                        if duration >= 5:  # At least 5 min to be meaningful
                            result["most_recent_afk"] = {
                                "start_local": utc_to_local(start_utc).strftime("%I:%M %p"),
                                "end_local": utc_to_local(end_utc).strftime("%I:%M %p"),
                                "duration_minutes": round(duration, 0),
                            }
                            break
        except Exception as e:
            logger.debug(f"Could not get recent AFK intervals: {e}")
        
        return result
    except Exception as e:
        logger.warning(f"Could not get presence status: {e}")
        return {
            "is_afk": False,
            "status_label": "UNKNOWN",
            "duration_minutes": 0.0,
            "start_time_local": "",
            "most_recent_afk": None,
        }


def get_significant_activity_segments(
    since_utc: datetime,
    noise_threshold_minutes: float = 5.0,
    merge_gap_minutes: float = 10.0,
) -> List[str]:
    """
    Get significant ACTIVE and AFK segments since a given time.
    
    Computes AFK from gaps between active segments to ensure consistency (no overlaps).
    
    Args:
        since_utc: Start time (UTC)
        noise_threshold_minutes: Filter out segments shorter than this (default 5 min)
        merge_gap_minutes: Merge active segments if gap between them is < this (default 10 min)
    
    Returns:
        List of formatted strings describing significant segments
    """
    from app.assistant.afk_manager.afk_db import get_active_segments_overlapping_range
    
    now_utc = datetime.now(timezone.utc)
    since_utc = _parse_utc(since_utc.isoformat()) if isinstance(since_utc, datetime) else _parse_utc(since_utc)
    
    if not since_utc or since_utc >= now_utc:
        return []
    
    try:
        # Get active segments and sort by start time
        active_segments = get_active_segments_overlapping_range(
            start_utc=since_utc,
            end_utc=now_utc,
            include_provisional=True,
        )
        
        # Parse and clip active segments to window, filter noise
        parsed_active: List[Dict[str, Any]] = []
        for seg in active_segments:
            start = _parse_utc(seg.start_time.isoformat()) if seg.start_time else None
            end = _parse_utc(seg.end_time.isoformat()) if seg.end_time else None
            if start and end and end > start:
                # Clip to window
                start = max(start, since_utc)
                end = min(end, now_utc)
                duration = (end - start).total_seconds() / 60.0
                # Filter out noise (very short segments)
                if end > start and duration >= noise_threshold_minutes:
                    parsed_active.append({"start": start, "end": end})
        
        # Sort by start time
        parsed_active.sort(key=lambda x: x["start"])
        
        # Step 1: Merge active segments separated by small gaps (< merge_gap_minutes)
        # This absorbs insignificant AFK into continuous active blocks
        merged_active: List[Dict[str, Any]] = []
        for seg in parsed_active:
            if merged_active:
                gap = (seg["start"] - merged_active[-1]["end"]).total_seconds() / 60.0
                if gap < merge_gap_minutes:
                    # Small gap - extend previous active block
                    merged_active[-1]["end"] = max(merged_active[-1]["end"], seg["end"])
                else:
                    # Significant gap - this is a new active block
                    merged_active.append(seg.copy())
            else:
                merged_active.append(seg.copy())
        
        # Step 2: Build timeline from merged active blocks
        # AFK = gaps between active blocks (all gaps are now >= merge_gap_minutes)
        merged: List[Dict[str, Any]] = []
        cursor = since_utc
        
        for seg in merged_active:
            # Gap before this active block = AFK (only if >= merge threshold)
            if seg["start"] > cursor:
                gap_duration = (seg["start"] - cursor).total_seconds() / 60.0
                if gap_duration >= merge_gap_minutes:
                    merged.append({
                        "start_utc": cursor,
                        "end_utc": seg["start"],
                        "type": "AFK",
                    })
            
            # This active block (already filtered for noise, just add it)
            merged.append({
                "start_utc": seg["start"],
                "end_utc": seg["end"],
                "type": "Active",
            })
            
            cursor = max(cursor, seg["end"])
        
        # Gap after last active segment to now = AFK (if >= merge threshold)
        if cursor < now_utc:
            gap_duration = (now_utc - cursor).total_seconds() / 60.0
            if gap_duration >= merge_gap_minutes:
                merged.append({
                    "start_utc": cursor,
                    "end_utc": now_utc,
                    "type": "AFK",
                })
        
        # Add current state if not already covered (for < 20 min current state)
        if merged:
            last_end = merged[-1]["end_utc"]
            seconds_since_last = (now_utc - last_end).total_seconds()
        else:
            seconds_since_last = (now_utc - since_utc).total_seconds()
        
        if seconds_since_last > 120:  # Gap of more than 2 min
            # Get current state from AFKMonitor
            try:
                from app.assistant.ServiceLocator.service_locator import DI
                monitor = getattr(DI, "afk_monitor", None)
                if monitor:
                    snapshot = monitor.get_computer_activity()
                    if isinstance(snapshot, dict):
                        is_afk = bool(snapshot.get("is_afk", False))
                        current_type = "AFK" if is_afk else "Active"
                        
                        if is_afk:
                            mins = float(snapshot.get("idle_minutes") or snapshot.get("current_afk_minutes") or 0)
                        else:
                            mins = float(snapshot.get("active_work_session_minutes") or 0)
                        
                        if mins > 0:
                            current_start = now_utc - timedelta(minutes=mins)
                            merged.append({
                                "start_utc": current_start,
                                "end_utc": now_utc,
                                "type": current_type,
                                "is_current": True,
                            })
            except Exception as e:
                logger.debug(f"Could not append current AFKMonitor state to merged segments: {e}", exc_info=True)
        
        if not merged:
            return []
        
        # Format as strings
        result: List[str] = []
        for i, seg in enumerate(merged):
            start_local = utc_to_local(seg["start_utc"]).strftime("%I:%M %p").lstrip("0")
            
            is_last = (i == len(merged) - 1)
            is_current = seg.get("is_current", False)
            seconds_from_now = abs((now_utc - seg["end_utc"]).total_seconds())
            is_ongoing = is_last and (is_current or seconds_from_now < 120)
            
            if is_ongoing:
                duration_mins = int((now_utc - seg["start_utc"]).total_seconds() / 60)
                result.append(f"{start_local} {seg['type']} ({duration_mins} min, ongoing)")
            else:
                end_local = utc_to_local(seg["end_utc"]).strftime("%I:%M %p").lstrip("0")
                result.append(f"{start_local} - {end_local} {seg['type']}")
        
        return result
        
    except Exception as e:
        logger.warning(f"Could not get significant activity segments: {e}")
        return []


# -----------------------------------------------------------------------------
# Ticket context helpers
# -----------------------------------------------------------------------------

def _format_ticket_for_context(ticket) -> Dict[str, Any]:
    """
    Format a Ticket object into a dict for agent context.
    
    Includes: title, message, suggestion_type, responded_at_local, 
    snooze_until_local, user_comment
    """
    responded_at = getattr(ticket, "responded_at", None)
    snooze_until = getattr(ticket, "snooze_until", None)
    
    responded_local = utc_to_local(responded_at) if responded_at else None
    snooze_until_local = utc_to_local(snooze_until) if snooze_until else None
    
    return {
        "title": ticket.title or "",
        "message": ticket.message or "",
        "suggestion_type": ticket.suggestion_type or "",
        "responded_at_local": responded_local.strftime("%I:%M %p") if responded_local else "",
        "snooze_until_local": snooze_until_local.strftime("%I:%M %p") if snooze_until_local else "",
        "user_comment": ticket.user_text or "",
    }


def get_responded_tickets_categorized(since_utc: datetime) -> Dict[str, List[Dict[str, Any]]]:
    """
    Get tickets user responded to since given time, categorized by response type.
    
    Categories (based on user_action):
    - accepted: done/willdo - user is doing this now or shortly
    - acknowledged: acknowledge - user received, may or may not act
    - declined: skip/no - user not interested, don't resuggest unless urgent
    - snoozed: later - user wants reminder later, wait until eligible time
    
    Returns dict with lists of formatted ticket dicts for each category.
    Raises ValueError if unknown user_action encountered.
    """
    try:
        from app.assistant.ticket_manager import get_ticket_manager, TicketState
        
        tickets = get_ticket_manager().get_tickets(
            since_responded_utc=since_utc,
            states=[TicketState.ACCEPTED, TicketState.DISMISSED, TicketState.SNOOZED],
            order_by="responded_at",
            limit=50,
        )
        
        result: Dict[str, List[Dict[str, Any]]] = {
            "accepted": [],      # done, willdo
            "acknowledged": [],  # acknowledge
            "declined": [],      # skip, no
            "snoozed": [],       # later
        }
        
        for t in tickets:
            formatted = _format_ticket_for_context(t)
            action = (t.user_action or "").lower()
            
            if action in ("done", "willdo"):
                result["accepted"].append(formatted)
            elif action == "acknowledge":
                result["acknowledged"].append(formatted)
            elif action in ("skip", "no"):
                result["declined"].append(formatted)
            elif action == "later":
                result["snoozed"].append(formatted)
            else:
                raise ValueError(f"Unknown user_action '{action}' for ticket '{t.title}'")
        
        return result
        
    except ValueError:
        # Re-raise ValueError (unknown user_action) - fail loudly
        raise
    except Exception as e:
        logger.warning(f"Could not get responded tickets: {e}")
        return {"accepted": [], "acknowledged": [], "declined": [], "snoozed": []}
