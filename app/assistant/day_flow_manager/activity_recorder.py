# activity_recorder.py
"""
Activity Recorder

Responsibilities:
- Maintain "tracked activities" state in memory (backed by status_data)
- Emit a single resource file suitable for day_flow_orchestrator input
- Compute minutes_since, overdue flags, and due-in values for each activity

Non-responsibilities:
- Interpreting chat, tickets, or calendar (other stages do that)
- Policy decisions beyond simple, local consistency rules

State shape (in status_data):
status_data["tracked_activities_state"] = {
  "activities": {
    "<field_name>": {
      "last_occurrence_utc": "ISO or None",
      "count_today": int,
      "count_date_local": "YYYY-MM-DD",
      "last_reset_utc": "ISO",
      "last_reset_reason": "init|daily_boundary|afk_return",
      "suppress_overdue_until_utc": "ISO or None"
    },
    ...
  },
  "last_updated_utc": "ISO",
  "schema_version": 2
}

Output resource:
resources/resource_tracked_activities_output.json
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

from app.assistant.utils.logging_config import get_logger
from app.assistant.utils.path_utils import get_resources_dir
from app.assistant.utils.time_utils import utc_to_local

logger = get_logger(__name__)

RESOURCES_DIR = get_resources_dir()
STAGES_DIR = Path(__file__).resolve().parent / "stages"
TRACKED_CONFIG_FILE = STAGES_DIR / "stage_configs" / "config_tracked_activities.json"
OUTPUT_RESOURCE_FILE = RESOURCES_DIR / "resource_tracked_activities_output.json"

_SCHEMA_VERSION = 2

# Prevent immediate nags on cold start without overwriting history.
# Keep small and boring.
_DEFAULT_COLD_START_GRACE_MINUTES = 15

# Only seed from output if it is recent enough to be trustworthy.
_SEED_MAX_AGE_HOURS = 12


@dataclass(frozen=True)
class TrackedActivityDef:
    field_name: str
    display_name: str
    threshold_minutes: Optional[int]
    init_on_cold_start: bool
    reset_on_afk: bool
    guidance: Optional[str]
    show_daily_count: bool


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_iso_utc(iso_str: Optional[str]) -> Optional[datetime]:
    if not iso_str or not isinstance(iso_str, str):
        return None
    try:
        return _ensure_utc(datetime.fromisoformat(iso_str.replace("Z", "+00:00")))
    except Exception:
        return None


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _local_date_str(dt_utc: datetime) -> str:
    return utc_to_local(dt_utc).strftime("%Y-%m-%d")


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _load_existing_output_if_fresh(now_utc: datetime) -> Dict[str, Any]:
    try:
        if not OUTPUT_RESOURCE_FILE.exists():
            return {}
        raw = json.loads(OUTPUT_RESOURCE_FILE.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            return {}

        computed_at = _parse_iso_utc(raw.get("computed_at_utc"))
        if not computed_at:
            return {}

        age_hours = (now_utc - computed_at).total_seconds() / 3600.0
        if age_hours > float(_SEED_MAX_AGE_HOURS):
            return {}

        return raw
    except Exception as e:
        logger.debug(f"Failed to load existing tracked activities output: {e}")
        return {}


class ActivityRecorder:
    """
    Tracks activity timestamps and per-day counts, and writes an orchestrator-ready resource.
    """

    def __init__(self, status_data: Dict[str, Any]):
        self.status_data = status_data
        self._lock = threading.Lock()
        self._defs = self._load_tracked_defs()

        with self._lock:
            self._ensure_state_initialized(_now_utc())

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------

    def _load_tracked_defs(self) -> Dict[str, TrackedActivityDef]:
        defs: Dict[str, TrackedActivityDef] = {}
        if not TRACKED_CONFIG_FILE.exists():
            logger.error(f"CRITICAL: Tracked activities config NOT FOUND at {TRACKED_CONFIG_FILE} - activity tracking DISABLED")
            return defs

        try:
            raw = json.loads(TRACKED_CONFIG_FILE.read_text(encoding="utf-8")) or {}
            activities = raw.get("activities", {}) if isinstance(raw, dict) else {}
            if not isinstance(activities, dict):
                return defs

            for _, a in activities.items():
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
                show_daily_count = bool(a.get("show_daily_count", False))

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
                    show_daily_count=show_daily_count,
                )

            return defs
        except Exception as e:
            logger.error(f"Failed to load tracked activities config: {e}")
            return {}

    def reload_config(self) -> None:
        with self._lock:
            self._defs = self._load_tracked_defs()
            self._ensure_state_initialized(_now_utc())

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------

    def _ensure_state_initialized(self, now_utc: datetime) -> None:
        if "tracked_activities_state" not in self.status_data or not isinstance(self.status_data["tracked_activities_state"], dict):
            self.status_data["tracked_activities_state"] = {}

        st = self.status_data["tracked_activities_state"]
        if "activities" not in st or not isinstance(st["activities"], dict):
            st["activities"] = {}

        st["schema_version"] = _SCHEMA_VERSION
        activities_state: Dict[str, Any] = st["activities"]

        today_local = _local_date_str(now_utc)

        existing_output = _load_existing_output_if_fresh(now_utc) if not activities_state else {}
        output_activities = existing_output.get("activities", {}) if isinstance(existing_output, dict) else {}

        for field_name, d in self._defs.items():
            if field_name not in activities_state or not isinstance(activities_state.get(field_name), dict):
                seed = output_activities.get(field_name, {}) if isinstance(output_activities, dict) else {}

                last_occurrence_utc = seed.get("last_occurrence_utc") or seed.get("last_utc")
                count_today = seed.get("count_today", 0)
                count_date_local = seed.get("count_date_local")

                activities_state[field_name] = {
                    "last_occurrence_utc": last_occurrence_utc if isinstance(last_occurrence_utc, str) else None,
                    "count_today": _safe_int(count_today, 0),
                    "count_date_local": count_date_local if isinstance(count_date_local, str) and count_date_local else today_local,
                    "last_reset_utc": now_utc.isoformat(),
                    "last_reset_reason": "init",
                    "suppress_overdue_until_utc": None,
                }

            astate = activities_state[field_name]

            if "last_occurrence_utc" not in astate:
                astate["last_occurrence_utc"] = None
            if "count_today" not in astate:
                astate["count_today"] = 0
            if "count_date_local" not in astate:
                astate["count_date_local"] = today_local
            if "last_reset_utc" not in astate:
                astate["last_reset_utc"] = now_utc.isoformat()
            if "last_reset_reason" not in astate:
                astate["last_reset_reason"] = "init"
            if "suppress_overdue_until_utc" not in astate:
                astate["suppress_overdue_until_utc"] = None

            # Cold start behavior: do not overwrite last_occurrence_utc.
            # Instead, add a short suppression window if configured and last is missing.
            if d.init_on_cold_start and not astate.get("last_occurrence_utc"):
                suppress_until = _ensure_utc(now_utc + timedelta(minutes=_DEFAULT_COLD_START_GRACE_MINUTES))
                astate["suppress_overdue_until_utc"] = suppress_until.isoformat()

        st["last_updated_utc"] = now_utc.isoformat()

    def _get_activity_state(self, field_name: str) -> Dict[str, Any]:
        st = self.status_data.get("tracked_activities_state", {})
        acts = st.get("activities", {}) if isinstance(st, dict) else {}
        return acts.get(field_name, {}) if isinstance(acts, dict) else {}

    def _set_activity_state(self, field_name: str, updates: Dict[str, Any]) -> None:
        st = self.status_data["tracked_activities_state"]
        acts = st["activities"]
        if field_name not in acts or not isinstance(acts.get(field_name), dict):
            acts[field_name] = {
                "last_occurrence_utc": None,
                "count_today": 0,
                "count_date_local": _local_date_str(_now_utc()),
                "last_reset_utc": _now_utc().isoformat(),
                "last_reset_reason": "init",
                "suppress_overdue_until_utc": None,
            }
        acts[field_name].update(updates)

    def _touch_updated(self, now_utc: datetime) -> None:
        self.status_data["tracked_activities_state"]["last_updated_utc"] = now_utc.isoformat()

    # ------------------------------------------------------------------
    # Public API: updates
    # ------------------------------------------------------------------

    def record_occurrence(self, field_name: str, timestamp_utc: Optional[datetime] = None, increment_count: bool = True) -> None:
        if field_name not in self._defs:
            logger.debug(f"record_occurrence ignored, unknown activity: {field_name}")
            return

        now_utc = _ensure_utc(timestamp_utc) if timestamp_utc else _now_utc()
        date_local = _local_date_str(now_utc)

        with self._lock:
            self._ensure_state_initialized(now_utc)
            astate = self._get_activity_state(field_name)

            if astate.get("count_date_local") != date_local:
                astate["count_today"] = 0
                astate["count_date_local"] = date_local

            if increment_count:
                astate["count_today"] = _safe_int(astate.get("count_today", 0), 0) + 1

            astate["last_occurrence_utc"] = now_utc.isoformat()

            # If an occurrence happened, overdue suppression is no longer needed.
            astate["suppress_overdue_until_utc"] = None

            self._set_activity_state(field_name, astate)
            self._touch_updated(now_utc)

    def set_count_today(
            self,
            field_name: str,
            count: int,
            date_local: Optional[str] = None,
            update_last_occurrence_if_increasing: bool = True,
    ) -> None:
        if field_name not in self._defs:
            logger.debug(f"set_count_today ignored, unknown activity: {field_name}")
            return

        now_utc = _now_utc()
        if date_local is None:
            date_local = _local_date_str(now_utc)

        with self._lock:
            self._ensure_state_initialized(now_utc)
            astate = self._get_activity_state(field_name)

            prev = _safe_int(astate.get("count_today", 0), 0)
            new_val = max(0, int(count))

            astate["count_today"] = new_val
            astate["count_date_local"] = str(date_local)

            if update_last_occurrence_if_increasing and new_val > prev:
                astate["last_occurrence_utc"] = now_utc.isoformat()
                astate["suppress_overdue_until_utc"] = None

            self._set_activity_state(field_name, astate)
            self._touch_updated(now_utc)

    def reset_for_new_day(self, boundary_date_local: str, boundary_utc: Optional[datetime] = None) -> None:
        """
        Daily boundary reset.
        - count_today -> 0
        - count_date_local -> boundary_date_local
        - last_occurrence_utc:
            - for threshold-based activities, set to boundary time so they become due after threshold
            - for non-threshold activities, keep None
        """
        now_utc = _now_utc()
        boundary_dt = _ensure_utc(boundary_utc) if boundary_utc else now_utc

        with self._lock:
            self._ensure_state_initialized(now_utc)

            for field_name, d in self._defs.items():
                last_occ = boundary_dt.isoformat() if d.threshold_minutes is not None else None
                self._set_activity_state(
                    field_name,
                    {
                        "last_occurrence_utc": last_occ,
                        "count_today": 0,
                        "count_date_local": boundary_date_local,
                        "last_reset_utc": boundary_dt.isoformat(),
                        "last_reset_reason": "daily_boundary",
                        "suppress_overdue_until_utc": None,
                    },
                )

            self._touch_updated(now_utc)

    def reset_on_afk_return(self, field_names: Optional[list] = None, timestamp_utc: Optional[datetime] = None) -> None:
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
                        "last_occurrence_utc": now_utc.isoformat(),
                        "last_reset_utc": now_utc.isoformat(),
                        "last_reset_reason": "afk_return",
                        "suppress_overdue_until_utc": None,
                    },
                )
            self._touch_updated(now_utc)

    # ------------------------------------------------------------------
    # Public API: reads
    # ------------------------------------------------------------------

    def get_state(self) -> Dict[str, Any]:
        with self._lock:
            now_utc = _now_utc()
            self._ensure_state_initialized(now_utc)
            return json.loads(json.dumps(self.status_data.get("tracked_activities_state", {})))

    def has_activity(self, field_name: str) -> bool:
        return field_name in self._defs

    def compute_minutes_since(self, field_name: str, now_utc: Optional[datetime] = None) -> Optional[float]:
        if field_name not in self._defs:
            return None

        now = _ensure_utc(now_utc) if now_utc else _now_utc()
        with self._lock:
            last_iso = self._get_activity_state(field_name).get("last_occurrence_utc")

        last_dt = _parse_iso_utc(last_iso)
        if not last_dt:
            return None
        return max(0.0, (now - last_dt).total_seconds() / 60.0)

    # ------------------------------------------------------------------
    # Resource output
    # ------------------------------------------------------------------

    def build_output_payload(self, now_utc: Optional[datetime] = None) -> Dict[str, Any]:
        now = _ensure_utc(now_utc) if now_utc else _now_utc()

        with self._lock:
            self._ensure_state_initialized(now)
            st = self.status_data.get("tracked_activities_state", {})
            acts_state = (st.get("activities", {}) if isinstance(st, dict) else {}) or {}

        out: Dict[str, Any] = {
            "computed_at_utc": now.isoformat(),
            "source": "tracked_activities_state",
            "schema_version": _SCHEMA_VERSION,
            "activities": {},
        }

        for field_name, d in self._defs.items():
            s = acts_state.get(field_name, {}) if isinstance(acts_state, dict) else {}

            last_iso = s.get("last_occurrence_utc")
            last_reset_iso = s.get("last_reset_utc")
            suppress_until_iso = s.get("suppress_overdue_until_utc")

            last_dt = _parse_iso_utc(last_iso)
            reset_dt = _parse_iso_utc(last_reset_iso)
            suppress_until_dt = _parse_iso_utc(suppress_until_iso)

            minutes_since = None
            if last_dt:
                minutes_since = max(0.0, (now - last_dt).total_seconds() / 60.0)

            minutes_since_reset = None
            if reset_dt:
                minutes_since_reset = max(0.0, (now - reset_dt).total_seconds() / 60.0)

            threshold = d.threshold_minutes

            is_overdue = None
            next_due = None

            # Suppression window: force not-overdue while suppression is active.
            suppression_active = bool(suppress_until_dt and now < suppress_until_dt)

            if threshold is not None:
                if suppression_active:
                    is_overdue = False
                    next_due = max(0.0, float(threshold))
                elif minutes_since is None:
                    # Unknown last occurrence, treat as due now but not "overdue"
                    # so the orchestrator can choose a gentle first prompt.
                    is_overdue = False
                    next_due = 0.0
                else:
                    is_overdue = minutes_since >= float(threshold)
                    next_due = max(0.0, float(threshold) - minutes_since)

            out["activities"][field_name] = {
                "display_name": d.display_name,
                "threshold_minutes": threshold,
                "minutes_since": round(minutes_since, 1) if isinstance(minutes_since, (int, float)) else None,
                "is_overdue": bool(is_overdue) if is_overdue is not None else None,
                "next_due_in_minutes": round(next_due, 1) if isinstance(next_due, (int, float)) else None,
                "count_today": _safe_int(s.get("count_today", 0), 0),
                "count_date_local": s.get("count_date_local"),
                "last_occurrence_utc": last_iso if isinstance(last_iso, str) else None,
                "last_reset_utc": last_reset_iso if isinstance(last_reset_iso, str) else None,
                "minutes_since_reset": round(minutes_since_reset, 1) if isinstance(minutes_since_reset, (int, float)) else None,
                "last_reset_reason": s.get("last_reset_reason"),
                "suppress_overdue_until_utc": suppress_until_iso if isinstance(suppress_until_iso, str) else None,
                "guidance": d.guidance,
                "show_daily_count": d.show_daily_count,
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
