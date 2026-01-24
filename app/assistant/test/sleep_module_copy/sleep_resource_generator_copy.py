"""
Sleep Resource Generator (copy for tests).

Inline data only; no DB calls.
Uses a fixed UTC timezone for deterministic tests.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, date, time, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.assistant.test.sleep_module_copy.sleep_reconciliation_copy import reconcile_sleep

UTC = timezone.utc


@dataclass(frozen=True)
class SleepConfigCopy:
    sleep_window_start: str = "22:30"
    sleep_window_end: str = "09:00"
    sleep_awake_divider: str = "05:30"
    min_sleep_afk_minutes: int = 60
    normal_sleep_start: str = "22:30"
    normal_sleep_end: str = "07:30"

    def parse_hhmm(self, value: str) -> Tuple[int, int]:
        parts = (value or "").strip().split(":")
        if len(parts) != 2:
            raise ValueError(f"Invalid HH:MM: {value}")
        h = int(parts[0])
        m = int(parts[1])
        if h < 0 or h > 23 or m < 0 or m > 59:
            raise ValueError(f"Invalid HH:MM: {value}")
        return h, m


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _combine_local(d: date, t: time) -> datetime:
    return datetime(d.year, d.month, d.day, t.hour, t.minute, 0, tzinfo=UTC)


def _day_date_local(now_local: datetime, divider: time) -> date:
    if now_local.timetz().replace(tzinfo=None) < divider:
        return now_local.date() - timedelta(days=1)
    return now_local.date()


def _sleep_window_start_local(day_date: date, cfg: SleepConfigCopy) -> datetime:
    h, m = cfg.parse_hhmm(cfg.sleep_window_start)
    return _combine_local(day_date - timedelta(days=1), time(h, m))


def _sleep_window_end_local(day_date: date, cfg: SleepConfigCopy) -> datetime:
    h, m = cfg.parse_hhmm(cfg.sleep_window_end)
    end_local = _combine_local(day_date, time(h, m))
    start_local = _sleep_window_start_local(day_date, cfg)
    if end_local <= start_local:
        end_local = end_local + timedelta(days=1)
    return end_local


def _divider_cutoff_local(day_date: date, cfg: SleepConfigCopy) -> datetime:
    h, m = cfg.parse_hhmm(cfg.sleep_awake_divider)
    return _combine_local(day_date, time(h, m))


@dataclass(frozen=True)
class _Interval:
    start_utc: datetime
    end_utc: datetime


def _active_segments_to_afk_intervals_overlapping_range(
    segments: List[Dict[str, Any]],
    window_start_utc: datetime,
    window_end_utc: datetime,
) -> List[_Interval]:
    """
    Mirror get_afk_intervals_overlapping_range() without DB calls.

    Return AFK gaps that overlap the window, but do NOT clip them.
    Caller is responsible for trimming to any boundaries.
    """
    if window_end_utc <= window_start_utc:
        return []

    if not segments:
        return [_Interval(window_start_utc, window_end_utc)]

    out: List[_Interval] = []
    sorted_segs = sorted(segments, key=lambda s: s["start_time"])

    first_start = _ensure_utc(sorted_segs[0]["start_time"])
    gap_start = window_start_utc
    gap_end = first_start
    if gap_end > gap_start and gap_end > window_start_utc and gap_start < window_end_utc:
        out.append(_Interval(gap_start, gap_end))

    for i in range(len(sorted_segs) - 1):
        prev_end = _ensure_utc(sorted_segs[i]["end_time"])
        next_start = _ensure_utc(sorted_segs[i + 1]["start_time"])
        if next_start > prev_end:
            gap_start = prev_end
            gap_end = next_start
            if gap_end > gap_start and gap_end > window_start_utc and gap_start < window_end_utc:
                out.append(_Interval(gap_start, gap_end))

    last_end = _ensure_utc(sorted_segs[-1]["end_time"])
    gap_start = last_end
    gap_end = window_end_utc
    if gap_end > gap_start and gap_end > window_start_utc and gap_start < window_end_utc:
        out.append(_Interval(gap_start, gap_end))

    return out


def _intersect_interval(a: _Interval, b_start: datetime, b_end: datetime) -> Optional[_Interval]:
    s = max(a.start_utc, b_start)
    e = min(a.end_utc, b_end)
    if e <= s:
        return None
    return _Interval(s, e)


def compute_sleep_data_copy(
    *,
    now_utc: datetime,
    active_segments: List[Dict[str, Any]],
    user_sleep_segments: List[Dict[str, Any]],
    user_wake_segments: List[Dict[str, Any]],
    cfg: SleepConfigCopy,
) -> Dict[str, Any]:
    now_utc = _ensure_utc(now_utc)
    now_local = now_utc  # UTC as local for deterministic tests

    divider_local_time = cfg.parse_hhmm(cfg.sleep_awake_divider)
    day_date = _day_date_local(now_local, time(*divider_local_time))

    sleep_start_local = _sleep_window_start_local(day_date, cfg)
    sleep_end_local = _sleep_window_end_local(day_date, cfg)
    divider_local = _divider_cutoff_local(day_date, cfg)

    tracking_start_utc = sleep_start_local
    tracking_end_utc = now_local

    afk_intervals = _active_segments_to_afk_intervals_overlapping_range(
        active_segments,
        window_start_utc=tracking_start_utc,
        window_end_utc=tracking_end_utc,
    )

    divider_utc = divider_local
    first_active_after_divider_utc: Optional[datetime] = None
    has_activity_in_window = False
    for seg in active_segments:
        st = _ensure_utc(seg["start_time"])
        en = _ensure_utc(seg["end_time"])
        if st <= sleep_end_local and en >= sleep_start_local:
            has_activity_in_window = True
        if st >= divider_utc:
            if first_active_after_divider_utc is None or st < first_active_after_divider_utc:
                first_active_after_divider_utc = st

    # Sleep can extend past divider until the first active after divider.
    sleep_end_effective = sleep_end_local
    if first_active_after_divider_utc is not None:
        sleep_end_effective = min(sleep_end_local, first_active_after_divider_utc)

    # If there's no legitimate wake by the end of the sleep window, cap at
    # the configured normal wake end to avoid assuming sleep until 9 AM.
    if first_active_after_divider_utc is None and now_local >= sleep_end_local:
        eh, em = cfg.parse_hhmm(cfg.normal_sleep_end)
        normal_end_local = _combine_local(day_date, time(eh, em))
        if normal_end_local > sleep_start_local:
            sleep_end_effective = min(sleep_end_effective, normal_end_local)

    inference_start_utc = sleep_start_local
    inference_end_utc = min(now_local, sleep_end_effective)

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

    has_legit_wake = first_active_after_divider_utc is not None
    if (not has_legit_wake) and (not has_activity_in_window) and now_local >= sleep_end_local:
        sh, sm = cfg.parse_hhmm(cfg.normal_sleep_start)
        eh, em = cfg.parse_hhmm(cfg.normal_sleep_end)
        default_start_local = _combine_local(day_date, time(sh, sm)) - timedelta(days=1)
        default_end_local = _combine_local(day_date, time(eh, em))
        inferred_sleep_segments = [
            {
                "start": default_start_local.isoformat(),
                "end": default_end_local.isoformat(),
                "duration_minutes": (default_end_local - default_start_local).total_seconds() / 60.0,
                "source": "default_sleep",
            }
        ]

    # NOTE: Temporarily ignore user sleep/wake data to focus on AFK-only logic.
    reconciled = reconcile_sleep(
        inferred_sleep_segments=inferred_sleep_segments,
        user_sleep_segments=[],
        user_wake_segments=[],
        merge_gap_minutes=2,
    )

    night_start_local: Optional[datetime] = None
    night_start_utc: Optional[datetime] = None
    if reconciled.get("sleep_periods"):
        starts = [datetime.fromisoformat(p["start"]) for p in reconciled.get("sleep_periods", [])]
        if starts:
            earliest = min(starts)
            night_start_utc = _ensure_utc(earliest)
            night_start_local = night_start_utc

    wake_time_local_from_activity: Optional[datetime] = None
    if first_active_after_divider_utc is not None:
        wake_time_local_from_activity = first_active_after_divider_utc

    return {
        "sleep_periods": reconciled.get("sleep_periods", []),
        "total_sleep_minutes": reconciled.get("total_sleep_minutes", 0.0),
        "wake_time_activity": wake_time_local_from_activity.isoformat() if wake_time_local_from_activity else None,
        "night_start_time": night_start_local.isoformat() if night_start_local else None,
        "night_start_time_utc": night_start_utc.isoformat() if night_start_utc else None,
    }
