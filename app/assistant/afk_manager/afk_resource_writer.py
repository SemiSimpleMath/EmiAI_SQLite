# afk_resource_writer.py
"""
AFK Resource Writer - Writes resource_afk_statistics_output.json

This module is called by AFKMonitor whenever AFK state changes.
It computes statistics and writes the resource file that agents consume.

This is NOT a pipeline stage - it's part of the AFK manager subsystem.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from app.assistant.utils.logging_config import get_logger
from app.assistant.utils.path_utils import get_resources_dir
from app.assistant.utils.time_utils import utc_to_local, local_to_utc, get_local_timezone

logger = get_logger(__name__)

# Resource file path
_RESOURCE_FILE = "resource_afk_statistics_output.json"


def _resources_dir() -> Path:
    """Get the resources directory path."""
    return get_resources_dir()


def _read_json_file(path: Path) -> Optional[Dict[str, Any]]:
    try:
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to read JSON file: {path} ({e})")
        return None


def _write_json_file(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _get_boundary_start_utc(boundary_hour: int = 5) -> datetime:
    """Get 5AM local boundary as UTC."""
    now_local = utc_to_local(datetime.now(timezone.utc))
    tz = get_local_timezone()
    
    # If before boundary hour, use yesterday's boundary
    if now_local.hour < boundary_hour:
        boundary_date = now_local.date() - timedelta(days=1)
    else:
        boundary_date = now_local.date()
    
    boundary_local = datetime(
        boundary_date.year, boundary_date.month, boundary_date.day,
        boundary_hour, 0, 0, tzinfo=tz
    )
    return local_to_utc(boundary_local)


def _parse_iso_utc(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _get_manager_state() -> Dict[str, Any]:
    """Read the pipeline manager state file for wake_time and reset info."""
    state_path = _resources_dir() / "resource_wellness_pipeline_status.json"
    return _read_json_file(state_path) or {}


def _parse_wake_time(wake_time_str: Optional[str]) -> Optional[datetime]:
    """Parse wake_time_today from state (format: YYYY-MM-DD HH:MM)."""
    if not wake_time_str:
        return None
    try:
        tz = get_local_timezone()
        dt_naive = datetime.strptime(wake_time_str, "%Y-%m-%d %H:%M")
        dt_local = dt_naive.replace(tzinfo=tz)
        return local_to_utc(dt_local)
    except Exception as e:
        logger.warning(f"Failed to parse wake_time: {wake_time_str} - {e}")
        return None


def write_afk_statistics(realtime_snapshot: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Compute AFK statistics and write to resource file.
    
    Called by AFKMonitor on every tick (to keep current session data fresh).
    
    Args:
        realtime_snapshot: Current snapshot from AFKMonitor (optional, will fetch if not provided)
    
    Returns:
        The data that was written
    """
    from app.assistant.afk_manager.afk_statistics import get_afk_statistics
    from app.assistant.ServiceLocator.service_locator import DI
    
    now_utc = datetime.now(timezone.utc)
    now_local = utc_to_local(now_utc)
    
    # Get real-time status from monitor if not provided
    realtime = realtime_snapshot or {}
    if not realtime:
        try:
            realtime = DI.afk_monitor.get_computer_activity()
        except Exception as e:
            logger.warning(f"Could not get real-time AFK status: {e}")
    
    # Extract current session state from realtime snapshot
    is_currently_active = not realtime.get("is_afk", True)
    active_start_utc = _parse_iso_utc(realtime.get("active_start_utc"))
    
    # Get state for wake_time and reset info
    state = _get_manager_state()
    boundary_utc = _get_boundary_start_utc()
    wake_time_str = state.get("wake_time_today")
    wake_time_utc = _parse_wake_time(wake_time_str)
    reset_utc = _parse_iso_utc(state.get("afk_reset_utc"))
    reset_offset = float(state.get("afk_reset_offset_minutes") or 0)
    
    # Use reset time as baseline when present
    baseline_utc = boundary_utc
    if reset_utc and reset_utc > boundary_utc:
        baseline_utc = reset_utc
    
    # Compute stats since baseline (using active-first model)
    stats_today = get_afk_statistics(
        since_utc=baseline_utc,
        current_active_start_utc=active_start_utc if is_currently_active else None,
        is_currently_active=is_currently_active,
    )
    
    # Stats since wake
    stats_since_wake: Dict[str, Any] = {}
    if wake_time_utc:
        since_wake_start = wake_time_utc
        if reset_utc and reset_utc > wake_time_utc:
            since_wake_start = reset_utc
        stats_since_wake = get_afk_statistics(
            since_utc=since_wake_start,
            current_active_start_utc=active_start_utc if is_currently_active else None,
            is_currently_active=is_currently_active,
        )
    
    # Build output (all times in LOCAL for agent consumption)
    def _to_local_str(dt_utc: Optional[datetime]) -> Optional[str]:
        if dt_utc is None:
            return None
        return utc_to_local(dt_utc).strftime("%Y-%m-%d %I:%M %p")
    
    boundary_local = utc_to_local(boundary_utc)
    wake_time_local = utc_to_local(wake_time_utc) if wake_time_utc else None
    
    # Apply reset offset to AFK time
    total_active_today = stats_today.get("total_active_time_minutes", 0)
    total_afk_today = stats_today.get("total_afk_time_minutes", 0) + reset_offset
    total_active_since_wake = stats_since_wake.get("total_active_time_minutes") if wake_time_utc else None
    total_afk_since_wake = (stats_since_wake.get("total_afk_time_minutes", 0) + reset_offset) if wake_time_utc else None
    afk_count_today = stats_today.get("afk_count", 0)
    if reset_offset > 0:
        afk_count_today = max(1, afk_count_today)
    
    # Active work session from stats (includes current session)
    active_work_session_minutes = stats_today.get("active_work_session_minutes", 0)
    
    # Current AFK minutes from stats
    current_afk_minutes = stats_today.get("current_afk_minutes", 0)
    if not is_currently_active:
        idle_minutes = realtime.get("idle_minutes")
        if isinstance(idle_minutes, (int, float)):
            current_afk_minutes = max(float(current_afk_minutes), float(idle_minutes))
    
    afk_start_local = None
    if realtime.get("last_afk_start"):
        afk_start_utc_parsed = _parse_iso_utc(realtime.get("last_afk_start"))
        afk_start_local = _to_local_str(afk_start_utc_parsed) if afk_start_utc_parsed else None
    
    data: Dict[str, Any] = {
        # Real-time status
        "is_afk": not is_currently_active,
        "idle_minutes": realtime.get("idle_minutes", 0),
        "active_start": realtime.get("active_start"),  # Already local from monitor
        "afk_start": afk_start_local,
        
        # Today stats (since 5AM boundary)
        "total_active_time_today": round(total_active_today, 1),
        "total_afk_time_today": round(total_afk_today, 1),
        "afk_count_today": afk_count_today,
        "active_segment_count_today": stats_today.get("active_segment_count", 0),
        
        # Since wake stats
        "total_active_time_since_wake": round(total_active_since_wake, 1) if total_active_since_wake is not None else None,
        "total_afk_time_since_wake": round(total_afk_since_wake, 1) if total_afk_since_wake is not None else None,
        
        # Current session info
        "active_work_session_minutes": round(active_work_session_minutes, 1),
        "current_afk_minutes": round(current_afk_minutes, 1),
        
        # Metadata (LOCAL time for agent/user display)
        "boundary_time": boundary_local.strftime("%Y-%m-%d %I:%M %p"),
        "wake_time": wake_time_local.strftime("%Y-%m-%d %I:%M %p") if wake_time_local else None,
        "wake_time_source": "sleep_stage" if wake_time_utc else None,
        "last_updated": now_local.strftime("%Y-%m-%d %I:%M %p"),
    }
    
    # Write to resource file
    output_path = _resources_dir() / _RESOURCE_FILE
    _write_json_file(output_path, data)

    # Refresh cached resource for agents
    try:
        resource_manager = getattr(DI, "resource_manager", None)
        if resource_manager:
            resource_manager.update_resource("resource_afk_statistics_output", data, persist=False)
    except Exception as e:
        logger.debug(f"Could not refresh AFK resource cache: {e}")

    # Silent update - no logging on every tick
    
    return data


def reset_afk_statistics(
    now_utc: datetime,
    boundary_hour: int = 5,
    state_updates: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Reset AFK statistics at 5AM boundary (or late catch-up reset).
    
    Called by pipeline manager during daily reset.
    
    Two paths:
    1. On-time reset (within 30min of boundary): Everything = 0, fresh start
    2. Late catch-up reset: AFK time = elapsed since boundary, active = 0
    
    Args:
        now_utc: Current UTC time
        boundary_hour: Hour for daily boundary (default 5)
        state_updates: Dict to populate with state changes (afk_reset_utc, afk_reset_offset_minutes)
    
    Returns:
        The reset data that was written
    """
    from app.assistant.ServiceLocator.service_locator import DI
    
    now_local = utc_to_local(now_utc)
    boundary_utc = _get_boundary_start_utc(boundary_hour)
    boundary_local_str = utc_to_local(boundary_utc).strftime("%Y-%m-%d %I:%M %p")
    
    # Get actual AFK status from monitor (don't assume)
    try:
        realtime = DI.afk_monitor.get_computer_activity()
        is_afk = realtime.get("is_afk", True)
        idle_minutes = realtime.get("idle_minutes", 0)
        active_start = realtime.get("active_start")  # Already local from monitor
    except Exception as e:
        logger.warning(f"Could not get AFK status during reset: {e}")
        is_afk = True  # Default to AFK if we can't check
        idle_minutes = 0
        active_start = None
    
    # Determine if this is a late catch-up reset
    minutes_since_boundary = (now_utc - boundary_utc).total_seconds() / 60
    is_late_reset = minutes_since_boundary > 30
    
    if is_late_reset:
        # Late catch-up: computer was off since boundary = AFK time
        afk_minutes_elapsed = round(minutes_since_boundary, 1)
        
        # Reset counters, preserve actual AFK status from monitor
        data: Dict[str, Any] = {
            "is_afk": is_afk,  # Actual status from monitor
            "idle_minutes": idle_minutes,  # Actual idle from monitor
            "active_start": active_start if not is_afk else None,
            "afk_start": boundary_local_str if is_afk else None,
            "total_active_time_today": 0,
            "total_afk_time_today": afk_minutes_elapsed,
            "afk_count_today": 1,
            "total_active_time_since_wake": None,
            "total_afk_time_since_wake": None,
            "active_work_session_minutes": 0,
            "current_afk_minutes": afk_minutes_elapsed if is_afk else 0,
            "last_completed_afk_duration": 0,
            "boundary_time": boundary_local_str,
            "wake_time": None,
            "wake_time_source": None,
            "last_updated": now_local.strftime("%Y-%m-%d %I:%M %p"),
            "_reset_reason": "late_catchup",
            "_afk_since_boundary_minutes": afk_minutes_elapsed,
        }
        
        logger.info(f"AFK reset (late): {afk_minutes_elapsed:.0f}min since boundary, is_afk={is_afk}")
        
        if state_updates is not None:
            state_updates["afk_reset_offset_minutes"] = afk_minutes_elapsed
    else:
        # On-time reset (at 5 AM): preserve actual AFK status from monitor
        data = {
            "is_afk": is_afk,  # Actual status from monitor
            "idle_minutes": idle_minutes,  # Actual idle from monitor
            "active_start": active_start if not is_afk else None,
            "afk_start": boundary_local_str if is_afk else None,
            "total_active_time_today": 0,
            "total_afk_time_today": 0,
            "afk_count_today": 0,
            "total_active_time_since_wake": None,
            "total_afk_time_since_wake": None,
            "active_work_session_minutes": 0,
            "current_afk_minutes": 0,
            "last_completed_afk_duration": 0,
            "boundary_time": boundary_local_str,
            "wake_time": None,
            "wake_time_source": None,
            "last_updated": now_local.strftime("%Y-%m-%d %I:%M %p"),
            "_reset_reason": "daily_boundary",
        }
        
        logger.info(f"AFK reset (on-time): counters zeroed, is_afk={is_afk}")
        
        if state_updates is not None:
            state_updates["afk_reset_offset_minutes"] = 0
    
    if state_updates is not None:
        state_updates["afk_reset_utc"] = now_utc.isoformat()
    
    # Write to resource file
    output_path = _resources_dir() / _RESOURCE_FILE
    _write_json_file(output_path, data)

    # Refresh cached resource for agents
    try:
        resource_manager = getattr(DI, "resource_manager", None)
        if resource_manager:
            resource_manager.update_resource("resource_afk_statistics_output", data, persist=False)
    except Exception as e:
        logger.debug(f"Could not refresh AFK resource cache (reset): {e}")

    return data
