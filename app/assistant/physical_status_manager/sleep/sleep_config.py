# sleep_config.py
"""
Sleep Config

Single responsibility:
- Load sleep tracking parameters from resources/config_sleep_tracking.yaml
- Provide small, safe helpers for interpreting HH:MM config fields

Notes:
- This module does NOT do any sleep math.
- Timezone handling is delegated to app.assistant.utils.time_utils.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta, date, time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from app.assistant.utils.logging_config import get_logger
from app.assistant.utils.time_utils import get_local_timezone, local_to_utc

logger = get_logger(__name__)


@dataclass(frozen=True)
class SleepQualityThresholds:
    """
    Simple grading thresholds (minutes).

    These are defaults only. If you add a section like this to YAML, they will be used:

    sleep_quality_thresholds:
      good_minutes: 420
      fair_minutes: 360
    """
    good_minutes: int = 420  # 7h
    fair_minutes: int = 360  # 6h


class SleepConfig:
    def __init__(self, config_path: Optional[Path] = None):
        self._config_cache: Optional[Dict[str, Any]] = None
        self._loaded_at_utc: Optional[datetime] = None

        if config_path is None:
            # parents[4] = project root (file is in app/assistant/physical_status_manager/sleep/)
            self._config_path = Path(__file__).resolve().parents[4] / "resources" / "config_sleep_tracking.yaml"
        else:
            self._config_path = config_path

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load(self, force_reload: bool = False) -> Dict[str, Any]:
        """
        Loads YAML into a dict. Cached for 5 minutes by default.
        """
        now_utc = datetime.now(timezone.utc)

        if not force_reload and self._config_cache and self._loaded_at_utc:
            age_min = (now_utc - self._loaded_at_utc).total_seconds() / 60.0
            if age_min < 5:
                return self._config_cache

        if not self._config_path.exists():
            raise FileNotFoundError(f"Sleep config file not found: {self._config_path}")

        try:
            import yaml
            with open(self._config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            if not isinstance(cfg, dict):
                cfg = {}

            self._config_cache = cfg
            self._loaded_at_utc = now_utc
            return cfg

        except Exception as e:
            raise RuntimeError(f"Failed to load sleep config: {e}") from e

    def get(self, *keys: str, default: Any = None) -> Any:
        cfg = self.load()
        cur: Any = cfg
        for k in keys:
            if not isinstance(cur, dict) or k not in cur:
                return default
            cur = cur[k]
        return cur

    # ------------------------------------------------------------------
    # Core parameters we actually use
    # ------------------------------------------------------------------

    def sleep_window_start_hhmm(self) -> str:
        return str(self.get("sleep_window", "start", default="22:30"))

    def sleep_window_end_hhmm(self) -> str:
        return str(self.get("sleep_window", "end", default="09:00"))

    @property
    def min_sleep_afk_minutes(self) -> int:
        v = self.get("min_sleep_afk_minutes", default=120)
        try:
            return max(0, int(v))
        except Exception:
            return 120

    def daily_reset_hour_local(self) -> int:
        v = self.get("daily_reset", "hour", default=5)
        try:
            return max(0, min(23, int(v)))
        except Exception:
            return 5

    def sleep_awake_divider_hhmm(self) -> str:
        """
        Divider between "AFK can count as sleep" vs "AFK counts as awake".

        Preference order:
        1) sleep_awake_divider (new recommended key)
        2) ambiguous_wake.divider (if you want to keep it under ambiguous_wake)
        3) ambiguous_wake.window_end (legacy fallback)
        4) daily_reset.hour (converted to HH:00)

        You can add to YAML:
          sleep_awake_divider: "05:30"
        """
        v = self.get("sleep_awake_divider", default=None)
        if v:
            return str(v)

        v2 = self.get("ambiguous_wake", "divider", default=None)
        if v2:
            return str(v2)

        v3 = self.get("ambiguous_wake", "window_end", default=None)
        if v3:
            return str(v3)

        return f"{self.daily_reset_hour_local():02d}:00"

    def quality_thresholds(self) -> SleepQualityThresholds:
        cfg = self.get("sleep_quality_thresholds", default={}) or {}
        if not isinstance(cfg, dict):
            return SleepQualityThresholds()

        def _int(name: str, default: int) -> int:
            try:
                return int(cfg.get(name, default))
            except Exception:
                return default

        good = _int("good_minutes", 420)
        fair = _int("fair_minutes", 360)
        return SleepQualityThresholds(good_minutes=good, fair_minutes=fair)

    # ------------------------------------------------------------------
    # Property accessors for time objects (used by sleep_resource_generator)
    # ------------------------------------------------------------------

    @property
    def sleep_window_start(self) -> time:
        """Returns sleep window start as a time object."""
        h, m = self.parse_hhmm(self.sleep_window_start_hhmm())
        return time(h, m)

    @property
    def sleep_window_end(self) -> time:
        """Returns sleep window end as a time object."""
        h, m = self.parse_hhmm(self.sleep_window_end_hhmm())
        return time(h, m)

    @property
    def sleep_awake_divider(self) -> time:
        """Returns sleep/awake divider as a time object."""
        h, m = self.parse_hhmm(self.sleep_awake_divider_hhmm())
        return time(h, m)

    @property
    def good_min_minutes(self) -> int:
        """Minutes threshold for 'good' sleep quality."""
        return self.quality_thresholds().good_minutes

    @property
    def fair_min_minutes(self) -> int:
        """Minutes threshold for 'fair' sleep quality."""
        return self.quality_thresholds().fair_minutes

    # ------------------------------------------------------------------
    # Tiny time helpers
    # ------------------------------------------------------------------

    @staticmethod
    def parse_hhmm(value: str) -> Tuple[int, int]:
        """
        Returns (hour, minute). Raises ValueError if invalid.
        """
        text = (value or "").strip()
        parts = text.split(":")
        if len(parts) != 2:
            raise ValueError(f"Invalid HH:MM: {value}")
        h = int(parts[0])
        m = int(parts[1])
        if h < 0 or h > 23 or m < 0 or m > 59:
            raise ValueError(f"Invalid HH:MM: {value}")
        return h, m

    def local_night_window_utc(self, anchor_local_date: date) -> Tuple[datetime, datetime]:
        """
        Returns the UTC bounds for the "night sleep inference window":
        [sleep_window.start -> sleep_awake_divider] in local time.

        Example with divider 05:30:
        anchor_local_date = 2026-01-19 (local day of wake)
        start_local = 2026-01-18 22:30
        end_local   = 2026-01-19 05:30

        This is the window you intersect AFK intervals with to infer sleep.
        """
        tz = get_local_timezone()

        sh, sm = self.parse_hhmm(self.sleep_window_start_hhmm())
        dh, dm = self.parse_hhmm(self.sleep_awake_divider_hhmm())

        # Start is previous local day at sleep_window.start
        start_local = datetime(
            year=anchor_local_date.year,
            month=anchor_local_date.month,
            day=anchor_local_date.day,
            hour=sh,
            minute=sm,
            tzinfo=tz,
        ) - timedelta(days=1)

        # End is anchor local day at divider
        end_local = datetime(
            year=anchor_local_date.year,
            month=anchor_local_date.month,
            day=anchor_local_date.day,
            hour=dh,
            minute=dm,
            tzinfo=tz,
        )

        start_utc = start_local.astimezone(timezone.utc)
        end_utc = end_local.astimezone(timezone.utc)
        return start_utc, end_utc


# Singleton accessor (optional)
_sleep_config: Optional[SleepConfig] = None


def get_sleep_config() -> SleepConfig:
    global _sleep_config
    if _sleep_config is None:
        _sleep_config = SleepConfig()
    return _sleep_config
