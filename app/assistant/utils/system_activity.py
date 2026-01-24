"""
System Activity Tracker
=======================
Detects user activity (keyboard/mouse) at the OS level.
Works on Windows using GetLastInputInfo API.
"""

import ctypes
import platform
from datetime import datetime, timezone
from typing import Dict, Any

def get_idle_seconds() -> float | None:
    """
    Returns seconds since last keyboard/mouse input (system-wide).
    Works on Windows only. Returns None if unavailable.
    
    Note: GetTickCount() can overflow after ~49.7 days of uptime, but since
    both values are 32-bit unsigned, the subtraction handles this correctly
    due to unsigned arithmetic wrapping.
    """
    if platform.system() != 'Windows':
        return None
    
    try:
        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [('cbSize', ctypes.c_uint), ('dwTime', ctypes.c_uint)]
        
        lii = LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
        
        # Get last input time
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
            return None
        
        # Calculate idle time in milliseconds
        current_tick = ctypes.windll.kernel32.GetTickCount()
        millis = (current_tick - lii.dwTime) & 0xFFFFFFFF  # Handle overflow correctly
        
        # Sanity check: if idle time is negative or impossibly large (>30 days), 
        # something is wrong - assume user is active
        max_reasonable_idle_ms = 30 * 24 * 60 * 60 * 1000  # 30 days in ms
        if millis < 0 or millis > max_reasonable_idle_ms:
            return None
        
        return millis / 1000.0
    except Exception:
        return None


def get_activity_status() -> Dict[str, Any]:
    """
    Returns a dict with user activity information.
    
    Note: The actual AFK threshold is configured in config_sleep_tracking.yaml
    under afk_thresholds.confirmed_afk_minutes. The 'status' field here is
    just informational - the AFKMonitor uses the configured threshold directly.
    """
    idle_seconds = get_idle_seconds()
    if idle_seconds is None:
        return {
            "idle_seconds": None,
            "idle_minutes": None,
            "status": "unknown",
            "last_checked": datetime.now(timezone.utc).isoformat(),
        }

    idle_minutes = idle_seconds / 60.0
    
    # Informational status (not used for AFK detection - that uses config)
    if idle_minutes < 1:
        status = "active"
    elif idle_minutes < 5:
        status = "recent"
    elif idle_minutes < 15:
        status = "idle"
    else:
        status = "away"
    
    return {
        "idle_seconds": round(idle_seconds, 1),
        "idle_minutes": round(idle_minutes, 1),
        "status": status,  # informational only
        "last_checked": datetime.now(timezone.utc).isoformat()
    }

