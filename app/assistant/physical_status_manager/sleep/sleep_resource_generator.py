# app/assistant/physical_status_manager/sleep/sleep_resource_generator.py
"""
Sleep Computation Module

Pure computation - no file I/O.
Reads from DB tables, computes sleep data, returns dict.
The stage handles output.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, date, time, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, or_

from app.assistant.utils.logging_config import get_logger
from app.assistant.utils.time_utils import (
    get_local_timezone,
    local_to_utc,
    utc_to_local,
)
from app.assistant.physical_status_manager.sleep.sleep_config import get_sleep_config, SleepConfig
from app.assistant.physical_status_manager.sleep.sleep_reconciliation import reconcile_sleep
from app.models.base import get_session
from app.models.afk_sleep_tracking import ActiveSegment, SleepSegment
from app.models.wake_segments import WakeSegment

logger = get_logger(__name__)


# -------------------------------------------------------------------------
# Local "day" and window helpers
# -------------------------------------------------------------------------


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _combine_local(d: date, t: time) -> datetime:
    tz = get_local_timezone()
    return datetime(d.year, d.month, d.day, t.hour, t.minute, 0, tzinfo=tz)


def _day_date_local(now_local: datetime, divider: time) -> date:
    """
    "Day date" is keyed by the divider.
    If local time is before divider, treat as previous day.
    """
    if now_local.timetz().replace(tzinfo=None) < divider:
        return now_local.date() - timedelta(days=1)
    return now_local.date()


def _sleep_window_start_local(day_date: date, cfg: SleepConfig) -> datetime:
    # "Last night" start is on previous day
    return _combine_local(day_date - timedelta(days=1), cfg.sleep_window_start)


def _sleep_window_end_local(day_date: date, cfg: SleepConfig) -> datetime:
    end_local = _combine_local(day_date, cfg.sleep_window_end)
    start_local = _sleep_window_start_local(day_date, cfg)
    if end_local <= start_local:
        end_local = end_local + timedelta(days=1)
    return end_local


def _divider_cutoff_local(day_date: date, cfg: SleepConfig) -> datetime:
    return _combine_local(day_date, cfg.sleep_awake_divider)


# -------------------------------------------------------------------------
# DB reads
# -------------------------------------------------------------------------


def _fetch_active_segments(session, since_utc: datetime, until_utc: datetime) -> List[ActiveSegment]:
    """Fetch active segments that overlap with the given time window."""
    return (
        session.query(ActiveSegment)
            .filter(
            and_(
                ActiveSegment.start_time <= until_utc,
                ActiveSegment.end_time >= since_utc,
                )
        )
            .order_by(ActiveSegment.start_time.asc())
            .all()
    )


def _fetch_user_sleep_segments(session, since_utc: datetime, until_utc: datetime) -> List[SleepSegment]:
    return (
        session.query(SleepSegment)
            .filter(
            and_(
                SleepSegment.start_time <= until_utc,
                or_(SleepSegment.end_time.is_(None), SleepSegment.end_time >= since_utc),
                SleepSegment.source.in_(["user_chat", "manual"]),
                )
        )
            .order_by(SleepSegment.start_time.asc())
            .all()
    )


def _fetch_user_wake_segments(session, since_utc: datetime, until_utc: datetime) -> List[WakeSegment]:
    return (
        session.query(WakeSegment)
            .filter(
            and_(
                WakeSegment.start_time <= until_utc,
                or_(WakeSegment.end_time.is_(None), WakeSegment.end_time >= since_utc),
                WakeSegment.source.in_(["user_chat", "manual", "activity_tracker"]),
                )
        )
            .order_by(WakeSegment.start_time.asc())
            .all()
    )


# -------------------------------------------------------------------------
# Active segments -> AFK intervals (gaps) -> inferred sleep
# -------------------------------------------------------------------------


@dataclass(frozen=True)
class _Interval:
    start_utc: datetime
    end_utc: datetime


def _active_segments_to_afk_intervals(
    segments: List[ActiveSegment], 
    window_start_utc: datetime,
    window_end_utc: datetime,
) -> List[_Interval]:
    """
    Derive AFK intervals from gaps between active segments.
    
    With Active-First model:
    - Active segments = when user was at keyboard
    - Gaps between them = when user was AFK
    """
    if not segments:
        # No active segments = entire window is AFK
        return [_Interval(window_start_utc, window_end_utc)]
    
    out: List[_Interval] = []
    
    # Sort by start time
    sorted_segs = sorted(segments, key=lambda s: s.start_time)
    
    # Gap before first segment
    first_start = _ensure_utc(sorted_segs[0].start_time)
    if first_start > window_start_utc:
        out.append(_Interval(window_start_utc, first_start))
    
    # Gaps between segments
    for i in range(len(sorted_segs) - 1):
        try:
            prev_end = _ensure_utc(sorted_segs[i].end_time)
            next_start = _ensure_utc(sorted_segs[i + 1].start_time)
        except Exception:
            continue
        
        if next_start > prev_end:
            # Clip to window
            gap_start = max(prev_end, window_start_utc)
            gap_end = min(next_start, window_end_utc)
            if gap_end > gap_start:
                out.append(_Interval(gap_start, gap_end))
    
    # Gap after last segment (up to window end)
    last_end = _ensure_utc(sorted_segs[-1].end_time)
    if last_end < window_end_utc:
        out.append(_Interval(last_end, window_end_utc))
    
    return out


def _intersect_interval(a: _Interval, b_start: datetime, b_end: datetime) -> Optional[_Interval]:
    s = max(a.start_utc, b_start)
    e = min(a.end_utc, b_end)
    if e <= s:
        return None
    return _Interval(s, e)


def _filter_inferred_that_overlaps_user(
        inferred: List[Dict[str, Any]],
        user_sleep: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Rule you specified:
    If an inferred AFK-derived segment overlaps any user sleep segment,
    drop that inferred segment (for sleep consideration).
    """
    if not inferred or not user_sleep:
        return inferred

    def _parse(s: str) -> datetime:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return _ensure_utc(dt)

    user_ranges: List[Tuple[datetime, datetime]] = []
    for u in user_sleep:
        try:
            st = _parse(u["start"])
            en = _parse(u["end"])
            if en > st:
                user_ranges.append((st, en))
        except Exception:
            continue

    if not user_ranges:
        return inferred

    kept: List[Dict[str, Any]] = []
    for inf in inferred:
        try:
            st = _parse(inf["start"])
            en = _parse(inf["end"])
        except Exception:
            kept.append(inf)
            continue

        overlaps = False
        for ust, uen in user_ranges:
            if st < uen and ust < en:
                overlaps = True
                break

        if not overlaps:
            kept.append(inf)

    return kept


def _sleep_quality(total_sleep_minutes: float, cfg: SleepConfig) -> str:
    if total_sleep_minutes <= 0:
        return "unknown"
    if total_sleep_minutes >= float(cfg.good_min_minutes):
        return "good"
    if total_sleep_minutes >= float(cfg.fair_min_minutes):
        return "fair"
    return "poor"


# -------------------------------------------------------------------------
# Main computation
# -------------------------------------------------------------------------


def compute_sleep_data(now_utc: Optional[datetime] = None) -> Dict[str, Any]:
    """
    Computes sleep for the current "day" as:
      tracking window = [sleep_window_start (last night), now]

    Rules:
    - AFK-derived sleep is inferred only inside the sleep window AND only before the divider.
      (AFK after divider is treated as awake for inference.)
    - Sleep outside the sleep window (naps) is only counted if the user reported it
      (SleepSegment source user_chat/manual).
    - Wake segments are subtracted (set subtraction), splitting sleep into fragments.
    - If an inferred AFK-derived sleep segment overlaps any user sleep segment,
      drop that inferred segment (do not partially keep it).
    """
    cfg = get_sleep_config()

    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    now_utc = _ensure_utc(now_utc)
    now_local = utc_to_local(now_utc)

    day_date = _day_date_local(now_local, cfg.sleep_awake_divider)

    sleep_start_local = _sleep_window_start_local(day_date, cfg)
    sleep_end_local = _sleep_window_end_local(day_date, cfg)
    divider_local = _divider_cutoff_local(day_date, cfg)

    tracking_start_local = sleep_start_local
    tracking_end_local = now_local

    tracking_start_utc = local_to_utc(tracking_start_local)
    tracking_end_utc = _ensure_utc(local_to_utc(tracking_end_local))

    # Inference is only within last night's window, and only before divider, and never after now.
    inference_end_local = min(tracking_end_local, sleep_end_local, divider_local)
    inference_start_utc = local_to_utc(sleep_start_local)
    inference_end_utc = local_to_utc(inference_end_local)

    # DB query padding to avoid boundary misses
    pad = timedelta(hours=12)
    query_start_utc = _ensure_utc(tracking_start_utc - pad)
    query_end_utc = _ensure_utc(tracking_end_utc + pad)

    session = get_session()
    try:
        active_segments = _fetch_active_segments(session, query_start_utc, query_end_utc)
        user_sleep_rows = _fetch_user_sleep_segments(session, query_start_utc, query_end_utc)
        user_wake_rows = _fetch_user_wake_segments(session, query_start_utc, query_end_utc)

        # User sleep segments clipped to tracking window
        user_sleep_segments: List[Dict[str, Any]] = []
        for s in user_sleep_rows:
            try:
                st = _ensure_utc(s.start_time)
                en = _ensure_utc(s.end_time) if s.end_time else None
                if not en or en <= st:
                    continue
                st = max(st, tracking_start_utc)
                en = min(en, tracking_end_utc)
                if en > st:
                    user_sleep_segments.append(
                        {
                            "id": getattr(s, "id", None),
                            "start": st.isoformat(),
                            "end": en.isoformat(),
                            "duration_minutes": (en - st).total_seconds() / 60.0,
                            "source": "user_sleep",
                        }
                    )
            except Exception:
                continue

        # User wake segments clipped to tracking window
        user_wake_segments: List[Dict[str, Any]] = []
        for w in user_wake_rows:
            try:
                st = _ensure_utc(w.start_time)
                en = _ensure_utc(w.end_time) if w.end_time else None
                if not en or en <= st:
                    continue
                st = max(st, tracking_start_utc)
                en = min(en, tracking_end_utc)
                if en > st:
                    user_wake_segments.append(
                        {
                            "id": getattr(w, "id", None),
                            "start_time": st.isoformat(),
                            "end_time": en.isoformat(),
                            "duration_minutes": (en - st).total_seconds() / 60.0,
                            "notes": getattr(w, "notes", "") or "",
                            "source": getattr(w, "source", None) or "user_chat",
                        }
                    )
            except Exception:
                continue

        # Derive AFK intervals from gaps between active segments
        afk_intervals = _active_segments_to_afk_intervals(
            active_segments, 
            window_start_utc=tracking_start_utc,
            window_end_utc=tracking_end_utc,
        )

        inferred_sleep_segments: List[Dict[str, Any]] = []
        if inference_end_utc > inference_start_utc:
            for seg in afk_intervals:
                clipped = _intersect_interval(seg, inference_start_utc, inference_end_utc)
                if not clipped:
                    continue

                dur_min = (clipped.end_utc - clipped.start_utc).total_seconds() / 60.0
                if dur_min < float(cfg.min_sleep_afk_minutes):
                    continue

                inferred_sleep_segments.append(
                    {
                        "start": clipped.start_utc.isoformat(),
                        "end": clipped.end_utc.isoformat(),
                        "duration_minutes": dur_min,
                        "source": "inferred_sleep",
                    }
                )

        # Your rule: if inferred overlaps user sleep, drop inferred segment entirely
        inferred_sleep_segments = _filter_inferred_that_overlaps_user(inferred_sleep_segments, user_sleep_segments)

        reconciled = reconcile_sleep(
            inferred_sleep_segments=inferred_sleep_segments,
            user_sleep_segments=user_sleep_segments,
            user_wake_segments=user_wake_segments,
            merge_gap_minutes=2,  # Default merge gap
        )

        # Build resource payload
        sleep_periods_out: List[Dict[str, Any]] = []
        for p in reconciled.get("sleep_periods", []) or []:
            try:
                st = _ensure_utc(datetime.fromisoformat(p["start"].replace("Z", "+00:00")))
                en = _ensure_utc(datetime.fromisoformat(p["end"].replace("Z", "+00:00")))
                st_local = utc_to_local(st)
                en_local = utc_to_local(en)

                # Store UTC timestamps as naive strings (matches your existing resource style)
                sleep_periods_out.append(
                    {
                        "start": st.replace(tzinfo=None).isoformat(),
                        "end": en.replace(tzinfo=None).isoformat(),
                        "duration_minutes": float(p.get("duration_minutes", 0.0) or 0.0),
                        "type": p.get("type", "sleep"),
                        "source": p.get("source", "unknown"),
                        "start_local": st_local.strftime("%Y-%m-%d %I:%M %p %Z"),
                        "end_local": en_local.strftime("%Y-%m-%d %I:%M %p %Z"),
                    }
                )
            except Exception:
                continue

        total_sleep_minutes = float(reconciled.get("total_sleep_minutes", 0.0) or 0.0)
        primary_sleep_minutes = float(reconciled.get("primary_sleep_minutes", 0.0) or 0.0)
        total_wake_minutes = float(reconciled.get("total_wake_minutes", 0.0) or 0.0)
        time_in_bed_minutes = float(reconciled.get("time_in_bed_minutes", 0.0) or 0.0)
        fragmented = bool(reconciled.get("fragmented", False))

        # Bedtime and wake time are based on the combined sleep envelope after reconciliation.
        bedtime_previous_local: Optional[datetime] = None
        wake_time_local: Optional[datetime] = None
        if sleep_periods_out:
            starts = [datetime.fromisoformat(x["start"]) for x in sleep_periods_out]
            ends = [datetime.fromisoformat(x["end"]) for x in sleep_periods_out]
            if starts and ends:
                # these are naive UTC; make them aware UTC for formatting
                earliest_utc = _ensure_utc(starts[0].replace(tzinfo=timezone.utc))
                latest_utc = _ensure_utc(ends[0].replace(tzinfo=timezone.utc))
                for sdt in starts[1:]:
                    dt_utc = _ensure_utc(sdt.replace(tzinfo=timezone.utc))
                    if dt_utc < earliest_utc:
                        earliest_utc = dt_utc
                for edt in ends[1:]:
                    dt_utc = _ensure_utc(edt.replace(tzinfo=timezone.utc))
                    if dt_utc > latest_utc:
                        latest_utc = dt_utc

                bedtime_previous_local = utc_to_local(earliest_utc)
                wake_time_local = utc_to_local(latest_utc)

        data: Dict[str, Any] = {
            "timezone": str(get_local_timezone().key),
            "date": day_date.isoformat(),
            "total_sleep_minutes": round(total_sleep_minutes, 1),
            "last_night_sleep_minutes": round(total_sleep_minutes, 1),
            "main_sleep_minutes": round(primary_sleep_minutes, 1),
            "sleep_quality": _sleep_quality(total_sleep_minutes, cfg),
            "fragmented": fragmented,
            "segment_count": int(len(sleep_periods_out)),
            "total_wake_minutes": round(total_wake_minutes, 1),
            "time_in_bed_minutes": round(time_in_bed_minutes, 1),
            "sleep_periods": sleep_periods_out,
            "wake_time": wake_time_local.strftime("%H:%M") if wake_time_local else None,
            "wake_time_today": wake_time_local.strftime("%Y-%m-%d %H:%M") if wake_time_local else None,
            "wake_time_today_local": wake_time_local.strftime("%Y-%m-%d %I:%M %p %Z") if wake_time_local else None,
            "bedtime_previous": bedtime_previous_local.strftime("%Y-%m-%d %H:%M") if bedtime_previous_local else None,
            "bedtime_previous_local": bedtime_previous_local.strftime("%Y-%m-%d %I:%M %p %Z") if bedtime_previous_local else None,
            "last_updated": now_utc.isoformat(),
            "source_breakdown_minutes": reconciled.get("source_breakdown_minutes", {}),
        }

        return data

    finally:
        session.close()
