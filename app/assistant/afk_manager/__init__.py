"""
AFK Manager - System idle detection and presence tracking.

This is a standalone service registered in DI, used by multiple consumers.

Model: Active-First (positive evidence)
- Records ACTIVE segments: when user IS at keyboard
- Active time = sum of recorded sessions (bounded, conservative)
- AFK time = gaps between active sessions
- No data = unknown (not active) - the safe default

Components:
- AFKMonitor: Real-time idle detection, writes active segments to DB, updates statistics resource
- get_afk_statistics(): Computes aggregate stats over a time window from active segments
- write_afk_statistics(): Writes resource_afk_statistics_output.json
- reset_afk_statistics(): Resets AFK stats at daily boundary

Database:
- active_segments: Records (start, end) pairs for when user was active
"""
from app.assistant.afk_manager.afk_monitor import AFKMonitor, AFKThresholds
from app.assistant.afk_manager.afk_statistics import get_afk_statistics
from app.assistant.afk_manager.afk_resource_writer import write_afk_statistics, reset_afk_statistics

__all__ = [
    'AFKMonitor',
    'AFKThresholds',
    'get_afk_statistics',
    'write_afk_statistics',
    'reset_afk_statistics',
]
