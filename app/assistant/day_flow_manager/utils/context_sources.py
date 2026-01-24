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


def get_recent_chat_excerpts(hours: int = 4, limit: int = 30, content_limit: int = 300) -> List[Dict[str, Any]]:
    try:
        from app.assistant.ServiceLocator.service_locator import DI

        all_messages = DI.global_blackboard.get_all_messages()
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=hours)

        result = []
        for msg in all_messages:
            ts = getattr(msg, "timestamp", None)
            if ts and ts > cutoff:
                content = getattr(msg, "content", "")
                sender = getattr(msg, "sender", "")
                if content and sender in ("user", "assistant"):
                    ts_local = utc_to_local(ts)
                    result.append({
                        "time_local": ts_local.strftime("%I:%M %p"),
                        "sender": sender,
                        "content": content[:content_limit],
                    })

        return result[-limit:]
    except Exception as e:
        logger.warning(f"Could not get chat excerpts: {e}")
        return []


def get_recent_chat_history(hours: int = 2, limit: int = 20, content_limit: int = 200) -> str:
    excerpts = get_recent_chat_excerpts(hours=hours, limit=limit, content_limit=content_limit)
    lines = [
        f"[{msg['time_local']}] {msg['sender']}: {msg['content']}"
        for msg in excerpts
    ]
    return "\n".join(lines)


def build_time_since(include_water: bool = False) -> Dict[str, Any]:
    try:
        stages_dir = Path(__file__).resolve().parents[1] / "stages"
        tracked_config_path = stages_dir / "config_tracked_activities.json"

        result: Dict[str, Any] = {
            "coffees_today": 0,
        }
        if include_water:
            result["water_count"] = 0

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
            except Exception as e:
                logger.warning(f"Could not read tracked activities config: {e}")

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

            if field_name == "coffee":
                result["coffees_today"] = data.get("count_today", 0)
            if include_water and field_name == "hydration":
                result["water_count"] = data.get("count_today", 0)

        return result
    except Exception as e:
        logger.warning(f"Could not build time_since: {e}")
        base = {"coffees_today": 0}
        if include_water:
            base["water_count"] = 0
        return base


def _format_ticket(t: Any, include_message: bool = False, accepted_label: str = "accepted_at_local") -> Dict[str, Any]:
    created_at = getattr(t, "created_at", None)
    responded_at = getattr(t, "responded_at", None)
    updated_at = getattr(t, "updated_at", None)

    created_local = utc_to_local(created_at) if created_at else None
    responded_local = utc_to_local(responded_at) if responded_at else None
    updated_local = utc_to_local(updated_at) if updated_at else None

    payload: Dict[str, Any] = {
        "title": getattr(t, "title", "") or "",
        "suggestion_type": getattr(t, "suggestion_type", "") or "",
        "state": str(getattr(t, "state", "")).lower().replace("ticketstate.", ""),
        "created_at_local": created_local.strftime("%I:%M %p") if created_local else "",
        "updated_at_local": updated_local.strftime("%I:%M %p") if updated_local else "",
        accepted_label: responded_local.strftime("%I:%M %p") if responded_local else "",
        "user_response_raw": getattr(t, "user_response_raw", "") or "",
        "user_text": getattr(t, "user_response_raw", "") or "",
    }

    if include_message:
        payload["message"] = getattr(t, "message", "") or ""

    return payload


def get_active_tickets_for_orchestrator() -> List[Dict[str, Any]]:
    try:
        from app.assistant.ticket_manager import get_ticket_manager, TicketState

        manager = get_ticket_manager()
        active = (
            manager.get_tickets_by_state(TicketState.PENDING) +
            manager.get_tickets_by_state(TicketState.PROPOSED) +
            manager.get_tickets_by_state(TicketState.SNOOZED)
        )
        return [_format_ticket(t, include_message=True) for t in active]
    except Exception as e:
        logger.warning(f"Could not get active tickets: {e}")
        return []


def get_recently_accepted_tickets_for_orchestrator(hours: int = 2, limit: int = 20) -> List[Dict[str, Any]]:
    try:
        from app.assistant.ticket_manager import get_ticket_manager

        manager = get_ticket_manager()
        tickets = manager.get_recently_accepted_tickets(hours=hours, limit=limit)
        return [
            _format_ticket(t, include_message=True, accepted_label="responded_at_local")
            for t in tickets
        ]
    except Exception as e:
        logger.warning(f"Could not get accepted tickets: {e}")
        return []


def get_recently_accepted_tickets(hours: int = 4, limit: int = 20) -> List[Dict[str, Any]]:
    try:
        from app.assistant.ticket_manager import get_ticket_manager

        manager = get_ticket_manager()
        tickets = manager.get_recently_accepted_tickets(hours=hours, limit=limit)
        return [
            {
                "title": getattr(t, "title", "") or "",
                "suggestion_type": getattr(t, "suggestion_type", "") or "",
                "accepted_at_local": _format_ticket(t).get("accepted_at_local", ""),
                "user_action": getattr(t, "user_response_raw", "") or "",
                "user_text": getattr(t, "user_response_raw", "") or "",
            }
            for t in tickets
        ]
    except Exception as e:
        logger.warning(f"Could not get accepted tickets: {e}")
        return []


def get_recent_tickets_for_health_inference(hours: int = 4, limit: int = 20) -> List[Dict[str, Any]]:
    try:
        from app.assistant.ticket_manager import get_ticket_manager

        manager = get_ticket_manager()
        tickets = manager.get_recent_tickets(hours=hours)
        return [
            {
                "title": getattr(t, "title", "") or "",
                "suggestion_type": getattr(t, "suggestion_type", "") or "",
                "state": str(getattr(t, "state", "")).lower(),
                "updated_at_local": _format_ticket(t).get("updated_at_local", ""),
            }
            for t in tickets[:limit]
        ]
    except Exception as e:
        logger.warning(f"Could not get recent tickets: {e}")
        return []


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
