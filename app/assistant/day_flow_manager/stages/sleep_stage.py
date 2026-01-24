# stages/sleep_stage.py
"""
Sleep Stage

Flow:
1. Prepare inputs: Read AFK events, user sleep/wake segments from DB
2. Execute: Compute sleep data via compute_sleep_data()
3. Determine if user is up (active after 5 AM boundary = day started)
4. Output: Write resource_sleep_output.json
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from app.assistant.utils.logging_config import get_logger
from app.assistant.utils.time_utils import get_local_timezone, local_to_utc
from app.assistant.day_flow_manager.manager import BaseStage, StageContext, StageResult

logger = get_logger(__name__)

class SleepStage(BaseStage):
    """
    Pipeline stage for sleep tracking.
    
    Also determines if user is "up" for the day:
    - User is up if active after the 5 AM daily boundary
    - If up after boundary, sleep has ended
    """

    stage_id: str = "sleep"

    def _output_filename(self) -> str:
        return f"resource_{self.stage_id}_output.json"

    def _check_user_is_up(self, ctx: StageContext) -> tuple[bool, datetime | None]:
        """
        Day can start in two ways:
        1) User is active after the ambiguous wake divider (ex: 5:30 AM) -> day started at that activity.
        2) No activity after divider and current time is past sleep window end -> day started at normal wake time.
        
        Returns:
            Tuple of (user_is_up, day_start_time_utc)
            - user_is_up: True if active after boundary
            - day_start_time_utc: First "returned" event after boundary (UTC), or None
        """
        from app.assistant.afk_manager.afk_db import get_recent_active_segments
        from app.assistant.day_flow_manager.sleep.sleep_config import get_sleep_config
        
        # Compute ambiguous wake divider boundary in local time
        tz = get_local_timezone()
        cfg = get_sleep_config()
        divider = cfg.sleep_awake_divider
        boundary_local = ctx.now_local.replace(
            hour=divider.hour,
            minute=divider.minute,
            second=0,
            microsecond=0,
        )
        
        from datetime import timedelta

        # If now is before divider, use yesterday's boundary
        if ctx.now_local.timetz().replace(tzinfo=None) < divider:
            boundary_local = boundary_local - timedelta(days=1)
        
        boundary_utc = local_to_utc(boundary_local)

        # Check for any active segment start after boundary (start of activity)
        # Find the FIRST one (earliest day start time)
        segments = get_recent_active_segments(hours=24) or []
        
        first_active_after_boundary: datetime | None = None
        
        for seg in segments:
            ts_str = seg.get("start_time")  # Active segment START = when user became active
            if not ts_str:
                continue

            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                
                if ts >= boundary_utc:
                    if first_active_after_boundary is None or ts < first_active_after_boundary:
                        first_active_after_boundary = ts
            except Exception:
                continue
        
        # If there is activity after the divider, day starts at that activity.
        if first_active_after_boundary:
            return True, first_active_after_boundary

        # No activity after divider: if we're past sleep window end, default to normal wake time.
        if ctx.now_local.timetz().replace(tzinfo=None) < divider:
            day_date = ctx.now_local.date() - timedelta(days=1)
        else:
            day_date = ctx.now_local.date()

        sleep_window_end = cfg.sleep_window_end
        sleep_window_end_local = datetime(
            day_date.year, day_date.month, day_date.day,
            sleep_window_end.hour, sleep_window_end.minute, 0,
            tzinfo=tz,
        )
        if ctx.now_local >= sleep_window_end_local:
            typical_wake_hhmm = str(cfg.get("normal_sleep", "end", default=cfg.sleep_window_end_hhmm()))
            try:
                th, tm = cfg.parse_hhmm(typical_wake_hhmm)
            except Exception:
                th, tm = cfg.parse_hhmm(cfg.sleep_window_end_hhmm())

            typical_wake_local = datetime(
                day_date.year, day_date.month, day_date.day,
                th, tm, 0,
                tzinfo=tz,
            )
            return True, local_to_utc(typical_wake_local)

        return False, None

    def run(self, ctx: StageContext) -> StageResult:
        """
        1. Prepare inputs: (handled by compute_sleep_data - reads from DB)
        2. Execute: Compute sleep data
        3. Determine if user is up and when
        4. Output: Write resource file
        """
        from app.assistant.day_flow_manager.sleep.sleep_resource_generator import (
            compute_sleep_data,
        )
        from app.assistant.utils.time_utils import utc_to_local

        # Step 2: Execute computation
        data = compute_sleep_data(now_utc=ctx.now_utc)

        # Step 3: Determine if user is up (active after ambiguous wake end)
        user_is_up, day_start_utc = self._check_user_is_up(ctx)
        data["user_is_up"] = user_is_up
        data["day_started"] = user_is_up  # Alias for clarity
        
        # Record day start time (when user first became active after boundary)
        if day_start_utc:
            day_start_local = utc_to_local(day_start_utc)
            data["day_start_time"] = day_start_local.strftime("%Y-%m-%d %I:%M %p %Z")
            data["day_start_time_utc"] = day_start_utc.astimezone(timezone.utc).isoformat()
            # Align wake_time fields with day_start when user is up
            data["wake_time"] = day_start_local.strftime("%H:%M")
            data["wake_time_today"] = day_start_local.strftime("%Y-%m-%d %H:%M")
            data["wake_time_today_local"] = day_start_local.strftime("%Y-%m-%d %I:%M %p %Z")
        else:
            data["day_start_time"] = None
            data["day_start_time_utc"] = None

        # Step 4: Output - write resource file
        ctx.write_resource(self._output_filename(), data)

        # Also write sleep segments to a dedicated resource file
        segments_output: Dict[str, Any] = {
            "date": ctx.now_local.strftime("%Y-%m-%d"),
            "timezone": str(get_local_timezone().key),
            "last_updated": ctx.now_local.strftime("%Y-%m-%d %I:%M %p %Z"),
            "sleep_periods": data.get("sleep_periods", []) or [],
        }
        ctx.write_resource("resource_sleep_segments_output.json", segments_output)

        # Extract wake time for downstream stages
        wake_time_str = data.get("wake_time_today")

        logger.info(
            f"SleepStage: {data.get('total_sleep_minutes', 0):.0f} min sleep, "
            f"quality={data.get('sleep_quality', 'unknown')}, "
            f"user_is_up={user_is_up}, day_start={data.get('day_start_time')}"
        )

        return StageResult(
            output=data,
            state_updates={
                "wake_time_today": wake_time_str,
                "user_is_up": user_is_up,
                "day_started": user_is_up,
                "day_start_time": data.get("day_start_time"),
                "day_start_time_utc": data.get("day_start_time_utc"),
            },
            debug={
                "total_sleep_minutes": data.get("total_sleep_minutes"),
                "segment_count": data.get("segment_count"),
                "wake_time": data.get("wake_time"),
                "user_is_up": user_is_up,
                "day_start_time": data.get("day_start_time"),
            },
        )

    def reset_daily(self, ctx: StageContext) -> None:
        """
        Reset sleep data at 5AM boundary using defaults from config.
        Assumes user had a good night's sleep until real data is computed.
        
        Note: wake_time_today format is "YYYY-MM-DD HH:MM" (local time string)
        for downstream stages to parse and convert to UTC as needed.
        """
        stage_config = self.get_stage_config(ctx)
        daily_reset = stage_config.get("daily_reset", {})
        defaults = daily_reset.get("output_resource_defaults", {})

        tz = get_local_timezone()
        now_local = ctx.now_local
        today_str = now_local.strftime("%Y-%m-%d")

        from datetime import timedelta

        # Config stores just "07:00" (local time), prepend today's date
        # This is a string for storage - downstream stages convert to UTC when computing
        wake_time_hhmm = defaults.get("wake_time_today", "07:00")
        wake_time_today_str = f"{today_str} {wake_time_hhmm}"

        bedtime_hhmm = defaults.get("bedtime_previous", "22:30")
        try:
            bed_hour, bed_min = map(int, bedtime_hhmm.split(":"))
        except Exception:
            bed_hour, bed_min = 22, 30

        try:
            wake_hour, wake_min = map(int, wake_time_hhmm.split(":"))
        except Exception:
            wake_hour, wake_min = 7, 0

        bedtime_local = now_local.replace(hour=bed_hour, minute=bed_min, second=0, microsecond=0) - timedelta(days=1)
        wake_local = now_local.replace(hour=wake_hour, minute=wake_min, second=0, microsecond=0)

        bedtime_local_str = bedtime_local.strftime("%Y-%m-%d %I:%M %p %Z")
        wake_local_str = wake_local.strftime("%Y-%m-%d %I:%M %p %Z")

        bedtime_utc = local_to_utc(bedtime_local)
        wake_utc = local_to_utc(wake_local)

        sleep_periods = [
            {
                "start": bedtime_utc.replace(tzinfo=None).isoformat(),
                "end": wake_utc.replace(tzinfo=None).isoformat(),
                "duration_minutes": float(defaults.get("total_sleep_minutes", 510)),
                "type": "main_sleep",
                "source": "reset_default",
                "start_local": bedtime_local_str,
                "end_local": wake_local_str,
            }
        ]

        default_data: Dict[str, Any] = {
            "timezone": str(tz.key) if hasattr(tz, 'key') else str(tz),
            "date": today_str,
            "total_sleep_minutes": defaults.get("total_sleep_minutes", 510),
            "last_night_sleep_minutes": defaults.get("last_night_sleep_minutes", 510),
            "main_sleep_minutes": defaults.get("main_sleep_minutes", 510),
            "sleep_quality": defaults.get("sleep_quality", "good"),
            "fragmented": defaults.get("fragmented", False),
            "segment_count": defaults.get("segment_count", 1),
            "total_wake_minutes": defaults.get("total_wake_minutes", 0),
            "time_in_bed_minutes": defaults.get("time_in_bed_minutes", 510),
            "sleep_periods": sleep_periods,
            "wake_time": wake_time_hhmm,
            "wake_time_today": wake_time_today_str,  # Local time string: YYYY-MM-DD HH:MM
            "wake_time_today_local": wake_local_str,
            "bedtime_previous": bedtime_local.strftime("%Y-%m-%d %H:%M"),
            "bedtime_previous_local": bedtime_local_str,
            "user_is_up": False,  # At 5 AM reset, user is not yet confirmed up
            "day_started": False,
            "day_start_time": wake_local_str,  # Expected wake time
            "day_start_time_utc": wake_utc.astimezone(timezone.utc).isoformat(),
            "last_updated": now_local.strftime("%Y-%m-%d %I:%M %p"),
            "source_breakdown_minutes": defaults.get("source_breakdown_minutes", {}),
            "_reset_reason": "daily_boundary",
        }

        ctx.write_resource(self._output_filename(), default_data)
        logger.info(f"SleepStage: Daily reset complete")
