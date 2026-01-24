# activity_recorder.py
"""
Activity Recorder

Rewrite goals:
- Single responsibility: maintain "tracked activities" state in memory and emit a single
  resource file suitable for proactive_orchestrator input.
- The orchestrator should not compute minutes-since. This module computes and outputs it.
- Source of truth for what to track: config_tracked_activities.json (stage config)

What this manages (in status_data):
status_data["tracked_activities_state"] = {
        "activities": {
     "<field_name>": {
        "last_utc": "ISO or None",
        "count_today": int,
        "count_date_local": "YYYY-MM-DD",  # the local date the counter applies to
        "last_reset_utc": "ISO",
        "last_reset_reason": "init|daily_boundary|afk_return"
     },
     ...
  },
  "last_updated_utc": "ISO",
}

What this writes (resource):
resources/resource_tracked_activities_output.json

This resource is designed to be direct input to proactive_orchestrator:
- includes thresholds (minutes) and computed minutes_since values
- includes counts_today
- includes gating-friendly fields like is_overdue, next_due_in_minutes
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from app.assistant.utils.logging_config import get_logger
from app.assistant.utils.path_utils import get_resources_dir
from app.assistant.utils.time_utils import utc_to_local

logger = get_logger(__name__)


# Path to config and resources folders
RESOURCES_DIR = get_resources_dir()
STAGES_DIR = Path(__file__).resolve().parent / "stages"
TRACKED_CONFIG_FILE = STAGES_DIR / "config_tracked_activities.json"
OUTPUT_RESOURCE_FILE = RESOURCES_DIR / "resource_tracked_activities_output.json"


def _load_existing_output() -> Dict[str, Any]:
    try:
        if not OUTPUT_RESOURCE_FILE.exists():
            return {}
        raw = json.loads(OUTPUT_RESOURCE_FILE.read_text(encoding="utf-8")) or {}
        return raw if isinstance(raw, dict) else {}
    except Exception as e:
        logger.warning(f"Failed to load existing tracked activities output: {e}")
        return {}


@dataclass(frozen=True)
class TrackedActivityDef:
    field_name: str
    display_name: str
    threshold_minutes: Optional[int]
    init_on_cold_start: bool
    reset_on_afk: bool
    guidance: Optional[str]


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_iso_utc(iso_str: str) -> Optional[datetime]:
    if not iso_str:
        return None
    try:
        return _ensure_utc(datetime.fromisoformat(iso_str.replace("Z", "+00:00")))
    except Exception:
        return None


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _local_date_str(dt_utc: datetime) -> str:
    return utc_to_local(dt_utc).strftime("%Y-%m-%d")


class ActivityRecorder:
    """
    Tracks the user's wellness activity timestamps and per-day counts.

    This is a pure state-and-resource writer. It does not interpret chat or tickets.
    Other stages/agents call:
      - record_occurrence(field_name, timestamp_utc=None)
      - set_count_today(field_name, count, date_local=None)
      - reset_for_new_day(boundary_date_local)
      - reset_on_afk_return(field_names, timestamp_utc=None)

    Then call write_output_resource() to emit the orchestrator-ready JSON file.
    """

    def __init__(self, status_data: Dict[str, Any]):
        self.status_data = status_data
        self._lock = threading.Lock()

        # Load config once; allow manual reload if needed.
        self._defs = self._load_tracked_defs()

        # Ensure in-memory structure exists
        with self._lock:
            self._ensure_state_initialized(_now_utc())

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------

    def _load_tracked_defs(self) -> Dict[str, TrackedActivityDef]:
        """
        Loads config_tracked_activities.json.

        Expected structure:
        {
          "activities": {
            "hydration": {
              "display_name": "...",
              "field_name": "hydration",
              "init_on_cold_start": true,
              "reset_on_afk": true,
              "threshold": { "minutes": 120, "label": "..." },
              "guidance": "..."
            },
            ...
          }
        }
        """
        defs: Dict[str, TrackedActivityDef] = {}
        if not TRACKED_CONFIG_FILE.exists():
            logger.warning(f"Tracked activities config missing: {TRACKED_CONFIG_FILE}")
            return defs

        try:
            raw = json.loads(TRACKED_CONFIG_FILE.read_text(encoding="utf-8")) or {}
            activities = raw.get("activities", {}) if isinstance(raw, dict) else {}
            if not isinstance(activities, dict):
                return defs

            for key, a in activities.items():
                if not isinstance(a, dict):
                    continue

                field_name = (a.get("field_name") or "").strip()
                if not field_name:
                    continue

                display_name = (a.get("display_name") or field_name).strip()
                init_on_cold_start = bool(a.get("init_on_cold_start", False))
                reset_on_afk = bool(a.get("reset_on_afk", False))
                guidance = a.get("guidance")
                guidance = str(guidance).strip() if isinstance(guidance, str) and guidance.strip() else None

                threshold_minutes = None
                threshold = a.get("threshold")
                if isinstance(threshold, dict):
                    m = threshold.get("minutes")
                    if isinstance(m, (int, float)) and m > 0:
                        threshold_minutes = int(m)

                defs[field_name] = TrackedActivityDef(
                    field_name=field_name,
                    display_name=display_name,
                    threshold_minutes=threshold_minutes,
                    init_on_cold_start=init_on_cold_start,
                    reset_on_afk=reset_on_afk,
                    guidance=guidance,
                )

            return defs

        except Exception as e:
            logger.error(f"Failed to load tracked activities config: {e}")
            return {}

    def reload_config(self) -> None:
        """Reload tracked activity definitions from config_tracked_activities.json."""
        with self._lock:
            self._defs = self._load_tracked_defs()
            self._ensure_state_initialized(_now_utc())

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------

    def _ensure_state_initialized(self, now_utc: datetime) -> None:
        """
        Creates tracked_activities_state if missing and ensures all configured
        field_names exist. If init_on_cold_start is true and last_utc is missing,
        initialize last_utc to now to prevent immediate nags on cold start.
        """
        if "tracked_activities_state" not in self.status_data or not isinstance(self.status_data["tracked_activities_state"], dict):
            self.status_data["tracked_activities_state"] = {}

        st = self.status_data["tracked_activities_state"]
        if "activities" not in st or not isinstance(st["activities"], dict):
            st["activities"] = {}

        activities_state: Dict[str, Any] = st["activities"]

        today_local = _local_date_str(now_utc)
        existing_output = _load_existing_output() if not activities_state else {}
        output_activities = existing_output.get("activities", {}) if isinstance(existing_output, dict) else {}

        for field_name, d in self._defs.items():
            if field_name not in activities_state or not isinstance(activities_state.get(field_name), dict):
                seed = output_activities.get(field_name, {}) if isinstance(output_activities, dict) else {}
                last_utc = seed.get("last_utc") if isinstance(seed, dict) else None
                count_today = seed.get("count_today", 0) if isinstance(seed, dict) else 0
                count_date_local = seed.get("count_date_local") if isinstance(seed, dict) else None

                activities_state[field_name] = {
                    "last_utc": last_utc if isinstance(last_utc, str) else None,
                    "count_today": int(count_today or 0),
                    "count_date_local": count_date_local or today_local,
                    "last_reset_utc": now_utc.isoformat(),
                    "last_reset_reason": "init",
                }

            astate = activities_state[field_name]
            if "count_today" not in astate:
                astate["count_today"] = 0
            if "count_date_local" not in astate:
                astate["count_date_local"] = today_local
            if "last_utc" not in astate:
                astate["last_utc"] = None
            if "last_reset_utc" not in astate:
                astate["last_reset_utc"] = now_utc.isoformat()
            if "last_reset_reason" not in astate:
                astate["last_reset_reason"] = "init"

            # Cold start behavior: suppress immediate nags for "init_on_cold_start"
            if d.init_on_cold_start and not astate.get("last_utc"):
                astate["last_utc"] = now_utc.isoformat()

        st["last_updated_utc"] = now_utc.isoformat()

    def _get_activity_state(self, field_name: str) -> Dict[str, Any]:
        st = self.status_data.get("tracked_activities_state", {})
        acts = st.get("activities", {}) if isinstance(st, dict) else {}
        return acts.get(field_name, {}) if isinstance(acts, dict) else {}

    def _set_activity_state(self, field_name: str, updates: Dict[str, Any]) -> None:
        st = self.status_data["tracked_activities_state"]
        acts = st["activities"]
        if field_name not in acts or not isinstance(acts.get(field_name), dict):
            acts[field_name] = {"last_utc": None, "count_today": 0, "count_date_local": _local_date_str(_now_utc())}
        acts[field_name].update(updates)

    # ------------------------------------------------------------------
    # Public API: updates
    # ------------------------------------------------------------------

    def record_occurrence(self, field_name: str, timestamp_utc: Optional[datetime] = None, increment_count: bool = True) -> None:
        """
        Record a single occurrence: sets last_utc and optionally increments count_today.

        This is the method you call when a ticket is accepted or when activity_tracker
        detected an activity in chat/calendar and you want to treat it as a real occurrence.
        """
        if field_name not in self._defs:
            logger.debug(f"record_occurrence ignored, unknown activity: {field_name}")
            return

        now_utc = _ensure_utc(timestamp_utc) if timestamp_utc else _now_utc()
        date_local = _local_date_str(now_utc)

        with self._lock:
            self._ensure_state_initialized(now_utc)
            astate = self._get_activity_state(field_name)

            # Reset counter if it belongs to a different local day
            if astate.get("count_date_local") != date_local:
                astate["count_today"] = 0
                astate["count_date_local"] = date_local

            if increment_count:
                astate["count_today"] = int(astate.get("count_today", 0) or 0) + 1

            astate["last_utc"] = now_utc.isoformat()
            self._set_activity_state(field_name, astate)

            self.status_data["tracked_activities_state"]["last_updated_utc"] = now_utc.isoformat()

    def set_count_today(self, field_name: str, count: int, date_local: Optional[str] = None) -> None:
        """
        Set the total count for today's occurrences (authoritative overwrite).

        This is what you call when activity_tracker agent produces a total count
        for the day (rather than a single occurrence).
        """
        if field_name not in self._defs:
            logger.debug(f"set_count_today ignored, unknown activity: {field_name}")
            return

        now_utc = _now_utc()
        if date_local is None:
            date_local = _local_date_str(now_utc)

        with self._lock:
            self._ensure_state_initialized(now_utc)
            astate = self._get_activity_state(field_name)

            astate["count_today"] = max(0, int(count))
            astate["count_date_local"] = str(date_local)

            self._set_activity_state(field_name, astate)
            self.status_data["tracked_activities_state"]["last_updated_utc"] = now_utc.isoformat()

    def reset_for_new_day(self, boundary_date_local: str) -> None:
        """
        Reset counts to 0 and last_utc to None at the daily boundary for all tracked activities.

        The manager decides boundary_date_local (the "day" starting at 5am local).
        """
        now_utc = _now_utc()
        with self._lock:
            self._ensure_state_initialized(now_utc)

            for field_name in list(self._defs.keys()):
                self._set_activity_state(
                    field_name,
                    {
                        "last_utc": None,
                        "count_today": 0,
                        "count_date_local": boundary_date_local,
                        "last_reset_utc": now_utc.isoformat(),
                        "last_reset_reason": "daily_boundary",
                    },
                )

            self.status_data["tracked_activities_state"]["last_updated_utc"] = now_utc.isoformat()

    def reset_on_afk_return(self, field_names: Optional[list] = None, timestamp_utc: Optional[datetime] = None) -> None:
        """
        Called when user returns from a meaningful AFK break.
        Sets last_utc to now for any activities configured with reset_on_afk=true
        unless field_names is explicitly provided.
        """
        now_utc = _ensure_utc(timestamp_utc) if timestamp_utc else _now_utc()

        if field_names is None:
            field_names = [f for f, d in self._defs.items() if d.reset_on_afk]

        with self._lock:
            self._ensure_state_initialized(now_utc)
            for field_name in field_names:
                if field_name not in self._defs:
                    continue
                self._set_activity_state(
                    field_name,
                    {
                        "last_utc": now_utc.isoformat(),
                        "last_reset_utc": now_utc.isoformat(),
                        "last_reset_reason": "afk_return",
                    },
                )

            self.status_data["tracked_activities_state"]["last_updated_utc"] = now_utc.isoformat()

    # ------------------------------------------------------------------
    # Public API: reads
    # ------------------------------------------------------------------

    def get_state(self) -> Dict[str, Any]:
        with self._lock:
            now_utc = _now_utc()
            self._ensure_state_initialized(now_utc)
            return json.loads(json.dumps(self.status_data.get("tracked_activities_state", {})))

    def compute_minutes_since(self, field_name: str, now_utc: Optional[datetime] = None) -> Optional[float]:
        """Returns minutes since last occurrence, or None if last_utc is missing."""
        if field_name not in self._defs:
            return None
        now = _ensure_utc(now_utc) if now_utc else _now_utc()
        with self._lock:
            last_iso = self._get_activity_state(field_name).get("last_utc")
        last_dt = _parse_iso_utc(last_iso) if isinstance(last_iso, str) else None
        if not last_dt:
            return None
        return max(0.0, (now - last_dt).total_seconds() / 60.0)

    # ------------------------------------------------------------------
    # Resource output
    # ------------------------------------------------------------------

    def build_output_payload(self, now_utc: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Build orchestrator-ready output payload.

        Shape:
        {
          "computed_at_utc": "...",
          "source": "tracked_activities_state",
          "activities": {
            "<field_name>": {
              "display_name": "...",
              "threshold_minutes": 120 or null,
              "minutes_since": 35.2 or null,
              "is_overdue": bool or null,
              "next_due_in_minutes": float or null,
              "count_today": int,
              "count_date_local": "YYYY-MM-DD",
              "last_utc": "ISO or null",
              "last_reset_utc": "ISO or null",
              "minutes_since_reset": float or null,
              "last_reset_reason": "init|daily_boundary|afk_return",
              "guidance": "..." or null
            },
            ...
          }
        }
        """
        now = _ensure_utc(now_utc) if now_utc else _now_utc()

        with self._lock:
            self._ensure_state_initialized(now)
            st = self.status_data.get("tracked_activities_state", {})
            acts_state = (st.get("activities", {}) if isinstance(st, dict) else {}) or {}

        out: Dict[str, Any] = {
            "computed_at_utc": now.isoformat(),
            "source": "tracked_activities_state",
            "activities": {},
        }

        for field_name, d in self._defs.items():
            s = acts_state.get(field_name, {}) if isinstance(acts_state, dict) else {}
            last_iso = s.get("last_utc")
            last_reset_iso = s.get("last_reset_utc")
            minutes_since = None
            if isinstance(last_iso, str) and last_iso:
                last_dt = _parse_iso_utc(last_iso)
                if last_dt:
                    minutes_since = max(0.0, (now - last_dt).total_seconds() / 60.0)
            minutes_since_reset = None
            if isinstance(last_reset_iso, str) and last_reset_iso:
                reset_dt = _parse_iso_utc(last_reset_iso)
                if reset_dt:
                    minutes_since_reset = max(0.0, (now - reset_dt).total_seconds() / 60.0)

            threshold = d.threshold_minutes
            is_overdue = None
            next_due = None
            if threshold is not None and minutes_since is not None:
                is_overdue = minutes_since >= float(threshold)
                next_due = max(0.0, float(threshold) - minutes_since)
            elif threshold is not None and minutes_since is None:
                # If no last timestamp, treat as overdue unless init_on_cold_start set it.
                is_overdue = True
                next_due = 0.0

            out["activities"][field_name] = {
                "display_name": d.display_name,
                "threshold_minutes": threshold,
                "minutes_since": round(minutes_since, 1) if isinstance(minutes_since, (int, float)) else None,
                "is_overdue": bool(is_overdue) if is_overdue is not None else None,
                "next_due_in_minutes": round(next_due, 1) if isinstance(next_due, (int, float)) else None,
                "count_today": int(s.get("count_today", 0) or 0),
                "count_date_local": s.get("count_date_local"),
                "last_utc": last_iso if isinstance(last_iso, str) else None,
                "last_reset_utc": last_reset_iso if isinstance(last_reset_iso, str) else None,
                "minutes_since_reset": round(minutes_since_reset, 1) if isinstance(minutes_since_reset, (int, float)) else None,
                "last_reset_reason": s.get("last_reset_reason"),
                "guidance": d.guidance,
            }

        return out

    def write_output_resource(self, now_utc: Optional[datetime] = None) -> None:
        payload = self.build_output_payload(now_utc=now_utc)
        try:
            RESOURCES_DIR.mkdir(parents=True, exist_ok=True)
            OUTPUT_RESOURCE_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
            try:
                from app.assistant.ServiceLocator.service_locator import DI
                resource_manager = getattr(DI, "resource_manager", None)
                if resource_manager:
                    resource_manager.update_resource("resource_tracked_activities_output", payload, persist=False)
            except Exception as e:
                logger.debug(f"Could not refresh tracked activities cache: {e}")
        except Exception as e:
            logger.error(f"Failed to write tracked activities output resource: {e}")


