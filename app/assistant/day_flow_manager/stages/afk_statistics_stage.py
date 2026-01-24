# stages/afk_statistics_stage.py
"""
AFK Statistics Stage

Flow:
1. Prepare inputs: Get wake_time from state, compute boundary times
2. Execute: Compute AFK stats for _today and _since_wake windows
3. Output: Write resource_afk_statistics_output.json
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from app.assistant.utils.logging_config import get_logger
from app.assistant.utils.time_utils import utc_to_local, local_to_utc, get_local_timezone
from app.assistant.day_flow_manager.manager import BaseStage, StageContext, StageResult

logger = get_logger(__name__)


class AFKStatisticsStage(BaseStage):
    """
    Pipeline stage for AFK statistics.
    
    Combines:
    - Real-time AFK status from DI.afk_monitor
    - Daily aggregates (_today: since 5AM boundary)
    - Since-wake aggregates (_since_wake: since wake time from sleep stage)
    """

    stage_id: str = "afk_statistics"

    def _output_filename(self) -> str:
        return f"resource_{self.stage_id}_output.json"

    def _get_boundary_start_utc(self, ctx: StageContext) -> datetime:
        """
        Get 5AM local boundary as UTC.
        """
        daily_reset = ctx.config.get("daily_reset", {})
        boundary_hour = int(daily_reset.get("boundary_hour_local", 5))
        
        now_local = ctx.now_local
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

    def _parse_wake_time(self, wake_time_str: Optional[str]) -> Optional[datetime]:
        """
        Parse wake_time_today from state (format: YYYY-MM-DD HH:MM).
        """
        if not wake_time_str:
            return None
        try:
            # wake_time_today is local time string
            tz = get_local_timezone()
            dt_naive = datetime.strptime(wake_time_str, "%Y-%m-%d %H:%M")
            dt_local = dt_naive.replace(tzinfo=tz)
            return local_to_utc(dt_local)
        except Exception as e:
            logger.warning(f"Failed to parse wake_time: {wake_time_str} - {e}")
            return None

    def _parse_iso_utc(self, value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            return None

    def run(self, ctx: StageContext) -> StageResult:
        """
        1. Prepare inputs: boundary time, wake time
        2. Execute: compute AFK stats
        3. Output: write resource file
        """
        from app.assistant.afk_manager.afk_statistics import get_afk_statistics
        from app.assistant.ServiceLocator.service_locator import DI
        now_utc = datetime.now(timezone.utc)

        # Step 1: Prepare inputs
        boundary_utc = self._get_boundary_start_utc(ctx)
        wake_time_str = ctx.state.get("wake_time_today")
        wake_time_utc = self._parse_wake_time(wake_time_str)
        reset_utc = self._parse_iso_utc(ctx.state.get("afk_reset_utc"))
        reset_offset = float(ctx.state.get("afk_reset_offset_minutes") or 0)

        # Use reset time as baseline when present to avoid counting pre-reset events
        baseline_utc = boundary_utc
        if reset_utc and reset_utc > boundary_utc:
            baseline_utc = reset_utc

        # Step 2: Execute computations
        
        # Real-time status from monitor
        realtime = {}
        try:
            realtime = DI.afk_monitor.get_computer_activity()
        except Exception as e:
            logger.warning(f"Could not get real-time AFK status: {e}")

        # Stats since baseline (boundary or last reset)
        stats_today = get_afk_statistics(
            since_utc=baseline_utc,
            ignore_prior_state=bool(reset_utc),
        )

        # Stats since wake (_since_wake)
        stats_since_wake = {}
        if wake_time_utc:
            # Since wake should also respect reset baseline
            since_wake_start = wake_time_utc
            if reset_utc and reset_utc > wake_time_utc:
                since_wake_start = reset_utc
            stats_since_wake = get_afk_statistics(
                since_utc=since_wake_start,
                ignore_prior_state=bool(reset_utc),
            )

        # Step 3: Build output (all times in LOCAL for agent consumption)
        def _to_local_str(dt_utc: Optional[datetime]) -> Optional[str]:
            if dt_utc is None:
                return None
            return utc_to_local(dt_utc).strftime("%Y-%m-%d %I:%M %p")

        boundary_local = utc_to_local(boundary_utc)
        wake_time_local = utc_to_local(wake_time_utc) if wake_time_utc else None
        now_local = ctx.now_local

        # Apply reset offset (late reset: assume AFK since boundary)
        total_active_today = stats_today.get("total_active_time_minutes", 0)
        total_afk_today = stats_today.get("total_afk_time_minutes", 0) + reset_offset
        total_active_since_wake = stats_since_wake.get("total_active_time_minutes") if wake_time_utc else None
        total_afk_since_wake = (stats_since_wake.get("total_afk_time_minutes", 0) + reset_offset) if wake_time_utc else None
        afk_count_today = stats_today.get("afk_count", 0)
        if reset_offset > 0:
            afk_count_today = max(1, afk_count_today)

        last_completed_afk_duration = stats_today.get("last_completed_afk_duration_minutes", 0)
        if last_completed_afk_duration == 0 and reset_offset > 0:
            last_completed_afk_duration = reset_offset

        last_segment_end_utc = self._parse_iso_utc(stats_today.get("last_segment_end_utc"))
        active_work_session_minutes = stats_today.get("active_work_session_minutes", 0)
        active_start_utc = self._parse_iso_utc(realtime.get("active_start_utc"))
        if not realtime.get("is_afk"):
            if active_start_utc:
                active_work_session_minutes = max(
                    0.0, (now_utc - active_start_utc).total_seconds() / 60.0
                )
            elif last_segment_end_utc:
                active_work_session_minutes = max(
                    0.0, (now_utc - last_segment_end_utc).total_seconds() / 60.0
                )

        current_afk_minutes = stats_today.get("current_afk_minutes", 0)
        if realtime.get("is_afk"):
            afk_start_utc = self._parse_iso_utc(realtime.get("last_afk_start"))
            if afk_start_utc:
                current_afk_minutes = max(
                    0.0, (now_utc - afk_start_utc).total_seconds() / 60.0
                )

        afk_start_local = None
        if realtime.get("last_afk_start"):
            afk_start_utc = self._parse_iso_utc(realtime.get("last_afk_start"))
            afk_start_local = _to_local_str(afk_start_utc) if afk_start_utc else None

        data: Dict[str, Any] = {
            # Real-time status
            "is_afk": realtime.get("is_afk", False),
            "idle_minutes": realtime.get("idle_minutes", 0),
            "active_start": realtime.get("active_start"),  # Already local from monitor
            "afk_start": afk_start_local,
            
            # Today stats (since 5AM boundary)
            "total_active_time_today": total_active_today,
            "total_afk_time_today": total_afk_today,
            "afk_count_today": afk_count_today,
            
            # Since wake stats (falls back to _today if no wake time)
            "total_active_time_since_wake": total_active_since_wake,
            "total_afk_time_since_wake": total_afk_since_wake,
            
            # Current session info
            "active_work_session_minutes": round(active_work_session_minutes, 1),
            "current_afk_minutes": round(current_afk_minutes, 1),
            "last_completed_afk_duration": last_completed_afk_duration,
            
            # Metadata (LOCAL time for agent/user display)
            "boundary_time": boundary_local.strftime("%Y-%m-%d %I:%M %p"),
            "wake_time": wake_time_local.strftime("%Y-%m-%d %I:%M %p") if wake_time_local else None,
            "wake_time_source": "sleep_stage" if wake_time_utc else None,
            "last_updated": now_local.strftime("%Y-%m-%d %I:%M %p"),
        }

        # Write output
        ctx.write_resource(self._output_filename(), data)

        logger.info(
            f"AFKStatisticsStage: is_afk={data['is_afk']}, "
            f"active_today={data['total_active_time_today']:.0f}min, "
            f"afk_today={data['total_afk_time_today']:.0f}min"
        )

        return StageResult(
            output=data,
            debug={
                "boundary_time": boundary_local.strftime("%H:%M"),
                "wake_time_available": wake_time_utc is not None,
            },
        )

    def reset_daily(self, ctx: StageContext) -> None:
        """
        Reset AFK statistics at 5AM boundary (or late catch-up reset).
        
        Two paths:
        1. On-time reset (within 30min of boundary): Everything = 0, fresh start
        2. Late catch-up reset: AFK time = elapsed since boundary, active = 0
           (computer was off, so user was AFK by definition)
        """
        now_utc = ctx.now_utc
        now_local = ctx.now_local
        boundary_utc = self._get_boundary_start_utc(ctx)
        boundary_local_str = utc_to_local(boundary_utc).strftime("%Y-%m-%d %I:%M %p")
        
        # Determine if this is a late catch-up reset
        minutes_since_boundary = (now_utc - boundary_utc).total_seconds() / 60
        is_late_reset = minutes_since_boundary > 30  # More than 30 min after boundary
        
        if is_late_reset:
            # Late catch-up: computer was off since boundary = AFK time
            afk_minutes_elapsed = round(minutes_since_boundary, 1)
            
            default_data: Dict[str, Any] = {
                # User just returned - they're active now
                "is_afk": False,
                "idle_minutes": 0,
                "active_start": now_local.strftime("%Y-%m-%d %I:%M %p"),
                "afk_start": None,
                
                # AFK time = elapsed since boundary, active = 0
                "total_active_time_today": 0,
                "total_afk_time_today": afk_minutes_elapsed,
                "afk_count_today": 1,  # One AFK period: boundary to now
                "total_active_time_since_wake": 0,
                "total_afk_time_since_wake": afk_minutes_elapsed,
                "active_work_session_minutes": 0,
                "current_afk_minutes": 0,  # Just returned, not currently AFK
                "last_completed_afk_duration": afk_minutes_elapsed,
                
                # Metadata
                "boundary_time": boundary_local_str,
                "wake_time": now_local.strftime("%Y-%m-%d %I:%M %p"),
                "wake_time_source": "late_reset",
                "last_updated": now_local.strftime("%Y-%m-%d %I:%M %p"),
                "_reset_reason": "late_catchup",
                "_afk_since_boundary_minutes": afk_minutes_elapsed,
            }
            
            logger.info(f"AFKStatisticsStage: Late reset - {afk_minutes_elapsed:.0f}min AFK since boundary, user now active")
            ctx.state["afk_reset_offset_minutes"] = afk_minutes_elapsed
        else:
            # On-time reset: everything to 0
            default_data: Dict[str, Any] = {
                # User just returned - they're active now
                "is_afk": False,
                "idle_minutes": 0,
                "active_start": now_local.strftime("%Y-%m-%d %I:%M %p"),
                "afk_start": None,
                
                # All counters start at 0
                "total_active_time_today": 0,
                "total_afk_time_today": 0,
                "afk_count_today": 0,
                "total_active_time_since_wake": 0,
                "total_afk_time_since_wake": 0,
                "active_work_session_minutes": 0,
                "current_afk_minutes": 0,
                "last_completed_afk_duration": 0,
                
                # Metadata
                "boundary_time": boundary_local_str,
                "wake_time": now_local.strftime("%Y-%m-%d %I:%M %p"),
                "wake_time_source": "daily_reset",
                "last_updated": now_local.strftime("%Y-%m-%d %I:%M %p"),
                "_reset_reason": "daily_boundary",
            }
            
            logger.info("AFKStatisticsStage: On-time reset - all counters zeroed, user marked active")
            ctx.state["afk_reset_offset_minutes"] = 0

        ctx.state["afk_reset_utc"] = now_utc.isoformat()
        ctx.write_resource(self._output_filename(), default_data)
