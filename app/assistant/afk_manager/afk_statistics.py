"""
AFK Statistics Utility - Active-First Model

Computes presence metrics from ActiveSegment rows over a window [since_utc, now_utc]:
- total_active_time_minutes: sum of active session durations (bounded to window)
- total_afk_time_minutes: gaps between active sessions (bounded to window)
- active_work_session_minutes: current uninterrupted active session (if active now)
- current_afk_minutes: time since last active session ended (if AFK now)
- afk_count: number of AFK gaps (transitions from active to AFK)

Key correctness points:
- Active time is POSITIVE EVIDENCE: we only count time we KNOW user was active
- AFK time is DERIVED: gaps between proven active segments
- No data = unknown (not active), which is the conservative default
- Current session state comes from AFKMonitor's realtime snapshot

Usage:
- afk_resource_writer calls get_afk_statistics() with day boundary
- Receives realtime_snapshot from AFKMonitor for current session state
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List

from app.assistant.utils.logging_config import get_logger
from app.assistant.afk_manager.afk_db import get_active_segments_overlapping_range

logger = get_logger(__name__)


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _minutes_between(a: datetime, b: datetime) -> float:
    return max(0.0, (b - a).total_seconds() / 60.0)


def get_afk_intervals_overlapping_range(
    start_utc: datetime,
    end_utc: datetime,
    include_provisional: bool = True,
) -> List[Dict[str, Any]]:
    """
    Return AFK intervals (gaps between active segments) that overlap the range.

    NOTE: The returned intervals are NOT clipped to the range.
    Caller is responsible for trimming to any window boundaries.

    Args:
        start_utc: Range start (UTC)
        end_utc: Range end (UTC)
        include_provisional: Include open segments if True

    Returns:
        List of dicts with start_utc, end_utc, duration_minutes
    """
    start_utc = _ensure_utc(start_utc)
    end_utc = _ensure_utc(end_utc)

    if end_utc <= start_utc:
        return []

    segments = get_active_segments_overlapping_range(
        start_utc=start_utc,
        end_utc=end_utc,
        include_provisional=include_provisional,
    )

    if not segments:
        # No activity in range: return a single AFK interval that spans the range,
        # but keep it untrimmed (range is the caller-provided window).
        return [
            {
                "start_utc": start_utc.isoformat(),
                "end_utc": end_utc.isoformat(),
                "duration_minutes": round(_minutes_between(start_utc, end_utc), 2),
            }
        ]

    out: List[Dict[str, Any]] = []
    sorted_segs = sorted(segments, key=lambda s: s.start_time)

    first_start = _ensure_utc(sorted_segs[0].start_time)
    # Gap before first active segment
    gap_start = start_utc
    gap_end = first_start
    if gap_end > gap_start:
        if gap_end > start_utc and gap_start < end_utc:
            out.append(
                {
                    "start_utc": gap_start.isoformat(),
                    "end_utc": gap_end.isoformat(),
                    "duration_minutes": round(_minutes_between(gap_start, gap_end), 2),
                }
            )

    for i in range(len(sorted_segs) - 1):
        try:
            prev_end = _ensure_utc(sorted_segs[i].end_time)
            next_start = _ensure_utc(sorted_segs[i + 1].start_time)
        except Exception:
            continue

        if next_start > prev_end:
            gap_start = prev_end
            gap_end = next_start
            if gap_end > gap_start:
                if gap_end > start_utc and gap_start < end_utc:
                    out.append(
                        {
                            "start_utc": gap_start.isoformat(),
                            "end_utc": gap_end.isoformat(),
                            "duration_minutes": round(_minutes_between(gap_start, gap_end), 2),
                        }
                    )

    last_end = _ensure_utc(sorted_segs[-1].end_time)
    gap_start = last_end
    gap_end = end_utc
    if gap_end > gap_start:
        if gap_end > start_utc and gap_start < end_utc:
            out.append(
                {
                    "start_utc": gap_start.isoformat(),
                    "end_utc": gap_end.isoformat(),
                    "duration_minutes": round(_minutes_between(gap_start, gap_end), 2),
                }
            )

    return out


def _create_empty_stats(now_utc: datetime, since_utc: datetime) -> Dict[str, Any]:
    return {
        "total_active_time_minutes": 0.0,
        "total_afk_time_minutes": 0.0,

        "active_work_session_minutes": 0.0,
        "current_afk_minutes": 0.0,
        "is_currently_afk": True,  # Conservative: no data = assume AFK

        "afk_count": 0,
        "active_segment_count": 0,

        "last_active_end_utc": None,

        "computed_at_utc": now_utc.isoformat(),
        "since_utc": since_utc.isoformat(),
        "source": "database",
    }


def get_afk_statistics(
        since_utc: Optional[datetime] = None,
        current_active_start_utc: Optional[datetime] = None,
        is_currently_active: bool = False,
) -> Dict[str, Any]:
    """
    Compute presence statistics from active segments.
    
    Args:
        since_utc: Start of observation window (default: 24h ago)
        current_active_start_utc: If user is currently active, when did session start?
        is_currently_active: Is user active right now?
    
    Returns:
        Statistics dictionary
    """
    try:
        now_utc = _ensure_utc(datetime.now(timezone.utc))

        if since_utc is None:
            since_utc = now_utc - timedelta(hours=24)
        else:
            since_utc = _ensure_utc(since_utc)

        # Get completed active segments that overlap our window
        segments = get_active_segments_overlapping_range(
            start_utc=since_utc,
            end_utc=now_utc,
            include_provisional=False,
        )

        # Calculate active time from completed segments
        total_active = 0.0
        active_durations: List[float] = []
        last_active_end: Optional[datetime] = None

        for seg in segments:
            try:
                seg_start = _ensure_utc(seg.start_time)
                seg_end = _ensure_utc(seg.end_time)
            except Exception:
                continue

            if seg_end <= seg_start:
                continue

            # Clip to observation window
            overlap_start = max(seg_start, since_utc)
            overlap_end = min(seg_end, now_utc)
            
            if overlap_end > overlap_start:
                duration = _minutes_between(overlap_start, overlap_end)
                total_active += duration
                active_durations.append(duration)

            # Track the latest segment end
            if last_active_end is None or seg_end > last_active_end:
                last_active_end = seg_end

        # Handle current active session (not yet in DB)
        active_work_session_minutes = 0.0
        if is_currently_active and current_active_start_utc:
            current_start = _ensure_utc(current_active_start_utc)
            # Clip to observation window
            clipped_start = max(current_start, since_utc)
            if now_utc > clipped_start:
                active_work_session_minutes = _minutes_between(clipped_start, now_utc)
                total_active += active_work_session_minutes

        # Calculate AFK time from gap intervals (overlapping the window)
        total_afk = 0.0
        afk_count = 0
        current_afk_minutes = 0.0

        afk_window_end = now_utc
        if is_currently_active and current_active_start_utc:
            current_start = _ensure_utc(current_active_start_utc)
            if current_start < afk_window_end:
                afk_window_end = current_start

        afk_intervals = get_afk_intervals_overlapping_range(
            start_utc=since_utc,
            end_utc=afk_window_end,
            include_provisional=False,
        )

        for gap in afk_intervals:
            try:
                gap_start = _ensure_utc(datetime.fromisoformat(gap["start_utc"].replace("Z", "+00:00")))
                gap_end = _ensure_utc(datetime.fromisoformat(gap["end_utc"].replace("Z", "+00:00")))
            except Exception:
                continue

            overlap_start = max(gap_start, since_utc)
            overlap_end = min(gap_end, afk_window_end)
            if overlap_end > overlap_start:
                total_afk += _minutes_between(overlap_start, overlap_end)
                afk_count += 1

        if not is_currently_active:
            last_end = last_active_end or since_utc
            if now_utc > last_end:
                current_afk_minutes = _minutes_between(max(last_end, since_utc), now_utc)

        return {
            "total_active_time_minutes": round(total_active, 1),
            "total_afk_time_minutes": round(total_afk, 1),

            "active_work_session_minutes": round(active_work_session_minutes, 1),
            "current_afk_minutes": round(current_afk_minutes, 1),
            "is_currently_afk": not is_currently_active,

            "afk_count": afk_count,
            "active_segment_count": len(segments),

            "last_active_end_utc": last_active_end.isoformat() if last_active_end else None,

            "computed_at_utc": now_utc.isoformat(),
            "since_utc": since_utc.isoformat(),
            "source": "database",
        }

    except Exception as e:
        logger.error(f"Error computing AFK statistics: {e}")
        now_utc = _ensure_utc(datetime.now(timezone.utc))
        since_utc_safe = _ensure_utc(since_utc) if since_utc else (now_utc - timedelta(hours=24))
        return _create_empty_stats(now_utc, since_utc_safe)
