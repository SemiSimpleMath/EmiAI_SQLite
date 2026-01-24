import pytest
from datetime import datetime, timezone

from app.assistant.test.sleep_module_copy.sleep_resource_generator_copy import (
    compute_sleep_data_copy,
    SleepConfigCopy,
)


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def _run(now_utc: str, active_segments, user_sleep_segments=None, user_wake_segments=None, cfg=None):
    cfg = cfg or SleepConfigCopy()
    return compute_sleep_data_copy(
        now_utc=_dt(now_utc),
        active_segments=active_segments,
        user_sleep_segments=user_sleep_segments or [],
        user_wake_segments=user_wake_segments or [],
        cfg=cfg,
    )


def test_a1_return_before_window_start_no_sleep():
    # Active across window; no AFK gaps inside window
    result = _run(
        "2026-01-22T11:15:00",
        active_segments=[
            {"start_time": _dt("2026-01-21T22:00:00"), "end_time": _dt("2026-01-22T10:00:00")},
        ],
    )
    assert result["sleep_periods"] == []
    assert result["wake_time_activity"] is None


def test_a2_return_before_divider_sleep_from_window_start():
    result = _run(
        "2026-01-22T09:30:00",
        active_segments=[
            {"start_time": _dt("2026-01-21T21:00:00"), "end_time": _dt("2026-01-21T21:15:00")},
            {"start_time": _dt("2026-01-22T05:00:00"), "end_time": _dt("2026-01-22T05:15:00")},
        ],
    )
    assert len(result["sleep_periods"]) == 2
    assert result["sleep_periods"][0]["start"].startswith("2026-01-21T22:30:00")
    assert result["sleep_periods"][0]["end"].startswith("2026-01-22T05:00:00")
    assert result["sleep_periods"][1]["start"].startswith("2026-01-22T05:15:00")
    assert result["sleep_periods"][1]["end"].startswith("2026-01-22T07:30:00")
    assert result["wake_time_activity"] is None


def test_a3_return_after_divider_before_window_end_sleep_until_return():
    result = _run(
        "2026-01-22T10:15:00",
        active_segments=[
            {"start_time": _dt("2026-01-21T21:00:00"), "end_time": _dt("2026-01-21T21:15:00")},
            {"start_time": _dt("2026-01-22T07:00:00"), "end_time": _dt("2026-01-22T07:15:00")},
        ],
    )
    assert result["sleep_periods"][0]["start"].startswith("2026-01-21T22:30:00")
    assert result["sleep_periods"][0]["end"].startswith("2026-01-22T07:00:00")
    assert result["wake_time_activity"].startswith("2026-01-22T07:00:00")


def test_a4_return_after_window_end_defaults_sleep():
    result = _run(
        "2026-01-22T12:30:00",
        active_segments=[],
    )
    sleep_periods = result["sleep_periods"]
    assert len(sleep_periods) == 1
    assert sleep_periods[0]["source"] == "default_sleep"


def test_b5_afk_starts_in_window_return_before_divider():
    result = _run(
        "2026-01-22T11:45:00",
        active_segments=[
            {"start_time": _dt("2026-01-21T23:00:00"), "end_time": _dt("2026-01-21T23:15:00")},
            {"start_time": _dt("2026-01-22T04:30:00"), "end_time": _dt("2026-01-22T04:45:00")},
        ],
    )
    assert len(result["sleep_periods"]) == 2
    assert result["sleep_periods"][0]["start"].startswith("2026-01-21T23:15:00")
    assert result["sleep_periods"][0]["end"].startswith("2026-01-22T04:30:00")
    assert result["sleep_periods"][1]["start"].startswith("2026-01-22T04:45:00")
    assert result["sleep_periods"][1]["end"].startswith("2026-01-22T07:30:00")
    assert result["wake_time_activity"] is None


def test_b6_afk_starts_in_window_return_after_divider():
    result = _run(
        "2026-01-22T09:45:00",
        active_segments=[
            {"start_time": _dt("2026-01-21T23:00:00"), "end_time": _dt("2026-01-21T23:15:00")},
            {"start_time": _dt("2026-01-22T06:15:00"), "end_time": _dt("2026-01-22T06:30:00")},
        ],
    )
    assert len(result["sleep_periods"]) == 1
    assert result["sleep_periods"][0]["start"].startswith("2026-01-21T23:15:00")
    assert result["sleep_periods"][0]["end"].startswith("2026-01-22T06:15:00")
    assert result["wake_time_activity"].startswith("2026-01-22T06:15:00")


def test_c8_return_before_divider_then_afk_again_until_after_divider():
    result = _run(
        "2026-01-22T10:05:00",
        active_segments=[
            {"start_time": _dt("2026-01-21T21:00:00"), "end_time": _dt("2026-01-21T21:15:00")},
            {"start_time": _dt("2026-01-22T04:30:00"), "end_time": _dt("2026-01-22T04:45:00")},
            {"start_time": _dt("2026-01-22T07:30:00"), "end_time": _dt("2026-01-22T07:45:00")},
        ],
    )
    # Expect two sleep segments: [22:30-04:30] and [04:45-06:30]
    assert len(result["sleep_periods"]) == 2
    assert result["sleep_periods"][0]["end"].startswith("2026-01-22T04:30:00")
    assert result["sleep_periods"][1]["end"].startswith("2026-01-22T07:30:00")
    assert result["wake_time_activity"].startswith("2026-01-22T07:30:00")


def test_c9_return_before_divider_then_afk_again_before_divider():
    result = _run(
        "2026-01-22T06:20:00",
        active_segments=[
            {"start_time": _dt("2026-01-21T21:00:00"), "end_time": _dt("2026-01-21T21:15:00")},
            {"start_time": _dt("2026-01-22T02:00:00"), "end_time": _dt("2026-01-22T02:10:00")},
            {"start_time": _dt("2026-01-22T04:30:00"), "end_time": _dt("2026-01-22T04:40:00")},
        ],
    )
    assert len(result["sleep_periods"]) == 3
    assert result["wake_time_activity"] is None


def test_d1_evening_activity_then_midnight_then_morning():
    result = _run(
        "2026-01-22T12:10:00",
        active_segments=[
            {"start_time": _dt("2026-01-21T22:00:00"), "end_time": _dt("2026-01-21T22:30:00")},
            {"start_time": _dt("2026-01-21T23:00:00"), "end_time": _dt("2026-01-22T00:00:00")},
            {"start_time": _dt("2026-01-22T07:00:00"), "end_time": _dt("2026-01-22T10:00:00")},
        ],
    )
    assert len(result["sleep_periods"]) == 1
    assert result["sleep_periods"][0]["start"].startswith("2026-01-22T00:00:00")
    assert result["sleep_periods"][0]["end"].startswith("2026-01-22T07:00:00")
    assert result["wake_time_activity"].startswith("2026-01-22T07:00:00")


def test_d2_sleep_progresses_until_window_end_then_caps():
    before = _run(
        "2026-01-22T08:59:00",
        active_segments=[
            {"start_time": _dt("2026-01-21T23:00:00"), "end_time": _dt("2026-01-21T23:15:00")},
            {"start_time": _dt("2026-01-22T04:30:00"), "end_time": _dt("2026-01-22T04:45:00")},
        ],
    )
    assert before["sleep_periods"][-1]["end"].startswith("2026-01-22T08:59:00")

    after = _run(
        "2026-01-22T09:00:00",
        active_segments=[
            {"start_time": _dt("2026-01-21T23:00:00"), "end_time": _dt("2026-01-21T23:15:00")},
            {"start_time": _dt("2026-01-22T04:30:00"), "end_time": _dt("2026-01-22T04:45:00")},
        ],
    )
    assert after["sleep_periods"][-1]["end"].startswith("2026-01-22T07:30:00")


def test_e1_query_before_window_end_truncates_to_now():
    result = _run(
        "2026-01-22T08:05:00",
        active_segments=[
            {"start_time": _dt("2026-01-21T23:00:00"), "end_time": _dt("2026-01-21T23:15:00")},
        ],
    )
    assert result["sleep_periods"][-1]["end"].startswith("2026-01-22T08:05:00")


def test_e2_query_at_window_end_caps_to_normal_end():
    result = _run(
        "2026-01-22T09:05:00",
        active_segments=[
            {"start_time": _dt("2026-01-21T23:00:00"), "end_time": _dt("2026-01-21T23:15:00")},
        ],
    )
    assert result["sleep_periods"][-1]["end"].startswith("2026-01-22T07:30:00")


def test_e3_active_after_divider_shortens_sleep_to_activity():
    result = _run(
        "2026-01-22T08:10:00",
        active_segments=[
            {"start_time": _dt("2026-01-21T23:30:00"), "end_time": _dt("2026-01-21T23:45:00")},
            {"start_time": _dt("2026-01-22T06:00:00"), "end_time": _dt("2026-01-22T06:30:00")},
        ],
    )
    assert len(result["sleep_periods"]) == 2
    assert result["sleep_periods"][1]["end"].startswith("2026-01-22T06:00:00")
    assert result["wake_time_activity"].startswith("2026-01-22T06:00:00")


def test_e4_activity_before_divider_no_legit_wake_caps():
    result = _run(
        "2026-01-22T09:45:00",
        active_segments=[
            {"start_time": _dt("2026-01-22T04:00:00"), "end_time": _dt("2026-01-22T04:10:00")},
        ],
    )
    assert result["sleep_periods"][-1]["end"].startswith("2026-01-22T07:30:00")
    assert result["wake_time_activity"] is None


def test_e5_midnight_activity_splits_sleep():
    result = _run(
        "2026-01-22T08:35:00",
        active_segments=[
            {"start_time": _dt("2026-01-21T23:50:00"), "end_time": _dt("2026-01-22T00:10:00")},
        ],
    )
    assert len(result["sleep_periods"]) == 2
    assert result["sleep_periods"][1]["start"].startswith("2026-01-22T00:10:00")


def test_e6_multiple_short_gaps_filtered_out():
    result = _run(
        "2026-01-22T08:15:00",
        active_segments=[
            {"start_time": _dt("2026-01-21T23:00:00"), "end_time": _dt("2026-01-21T23:30:00")},
            {"start_time": _dt("2026-01-21T23:50:00"), "end_time": _dt("2026-01-22T00:10:00")},
            {"start_time": _dt("2026-01-22T00:40:00"), "end_time": _dt("2026-01-22T01:00:00")},
        ],
    )
    assert len(result["sleep_periods"]) == 1
    assert result["sleep_periods"][0]["start"].startswith("2026-01-22T01:00:00")


def test_e7_activity_crosses_sleep_window_start():
    result = _run(
        "2026-01-22T08:20:00",
        active_segments=[
            {"start_time": _dt("2026-01-21T22:15:00"), "end_time": _dt("2026-01-21T22:45:00")},
        ],
    )
    assert len(result["sleep_periods"]) == 1
    assert result["sleep_periods"][0]["start"].startswith("2026-01-21T22:45:00")


def test_e8_activity_after_window_end_only():
    result = _run(
        "2026-01-22T09:35:00",
        active_segments=[
            {"start_time": _dt("2026-01-22T10:00:00"), "end_time": _dt("2026-01-22T11:00:00")},
        ],
    )
    assert result["sleep_periods"][-1]["end"].startswith("2026-01-22T09:00:00")
    assert result["wake_time_activity"].startswith("2026-01-22T10:00:00")


def test_e9_long_sleep_without_activity_until_now_before_end():
    result = _run(
        "2026-01-22T06:05:00",
        active_segments=[],
    )
    assert result["sleep_periods"][-1]["end"].startswith("2026-01-22T06:05:00")


def test_e10_no_activity_after_window_end_defaults():
    result = _run(
        "2026-01-22T12:05:00",
        active_segments=[],
    )
    assert result["sleep_periods"][0]["source"] == "default_sleep"


if __name__ == "__main__":
    pytest.main([__file__])
