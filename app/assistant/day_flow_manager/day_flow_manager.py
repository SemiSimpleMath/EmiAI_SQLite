# day_flow_manager.py
"""
Physical Pipeline Manager

Design goals:
1) Manager owns lifecycle and orchestration only:
   - 5AM local "daily boundary" reset
   - cursor bookkeeping (for gating stages like activity_tracker on new chat)
   - stage scheduling and run bookkeeping

2) Manager does NOT own semantic health fields (mental, cognitive, physiology, etc).
   Those are agent outputs written to resource files; other agents read those resources.

3) Manager does NOT hardcode tracked activities, agent schema fields, meeting logic, task logic, etc.
   Everything stage-related is defined in a pipeline config file.

4) Pythonic computations (AFK, sleep, elapsed time math, counters) are performed inside stages.
   The manager simply provides time context, state, and helper IO.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.assistant.utils.logging_config import get_logger
from app.assistant.utils.path_utils import get_resources_dir
from app.assistant.utils.time_utils import utc_to_local
from app.assistant.ServiceLocator.service_locator import DI

logger = get_logger(__name__)


# -------------------------------------------------------------------------
# Resource IO helpers
# -------------------------------------------------------------------------

def _resources_dir() -> Path:
    return get_resources_dir()


def _read_json_file(path: Path) -> Optional[Dict[str, Any]]:
    try:
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to read JSON file: {path} ({e})")
        return None


def _write_json_file(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _parse_iso_utc(dt_str: Optional[str]) -> Optional[datetime]:
    if not dt_str:
        return None
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# -------------------------------------------------------------------------
# Stage abstractions
# -------------------------------------------------------------------------

@dataclass
class StageResult:
    """
    Result returned by a stage's run() method.
    
    Stages write their own output files via ctx.write_resource().
    StageResult is for communicating state/cursor updates back to manager.
    """
    output: Optional[Dict[str, Any]] = None  # Stage output data (for debug/logging)
    state_updates: Dict[str, Any] = field(default_factory=dict)
    cursor_updates: Dict[str, Any] = field(default_factory=dict)
    debug: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StageContext:
    now_utc: datetime
    now_local: datetime
    state: Dict[str, Any]
    config: Dict[str, Any]
    stage_config: Dict[str, Any]
    resources_dir: Path
    new_chat_messages: List[Dict[str, Any]] = field(default_factory=list)

    def read_resource(self, filename: str) -> Optional[Dict[str, Any]]:
        return _read_json_file(self.resources_dir / filename)

    def write_resource(self, filename: str, data: Dict[str, Any]) -> None:
        """
        Write data to a resource file.
        
        Agents get resource files through their config subscriptions.
        The ResourceManager handles loading resources into the blackboard.
        """
        _write_json_file(self.resources_dir / filename, data)
        resource_manager = getattr(DI, "resource_manager", None)
        if resource_manager:
            resource_id = Path(filename).stem
            resource_manager.update_resource(resource_id, data, persist=False)


class BaseStage:
    """
    Base class for pipeline stages.
    
    Each stage should:
    - Implement run() for main logic
    - Implement reset_stage() for 5AM boundary reset behavior
    - Optionally implement should_run_stage() for gate logic
    - Use get_stage_config() to load stage-specific config
    """
    stage_id: str = ""

    def should_run_stage(self, ctx: StageContext) -> Tuple[bool, str]:
        """Default: always run. Override for custom gating logic."""
        return True, "ready"

    def run(self, ctx: StageContext) -> StageResult:
        """Execute the stage's main logic."""
        raise NotImplementedError

    def get_stage_config(self, ctx: StageContext) -> Dict[str, Any]:
        """
        Load this stage's dedicated config file if it exists.

        Looks for: stages/stage_configs/config_stage_<stage_id>.json
        Returns empty dict if not found.
        """
        stages_dir = Path(__file__).parent / "stages" / "stage_configs"
        config_path = stages_dir / f"config_stage_{self.stage_id}.json"
        return _read_json_file(config_path) or {}


    def reset_stage(self, ctx: StageContext) -> None:
        """
        Called when 5AM daily boundary is crossed (or on cold start after 5AM).
        
        Override to reset stage-specific data:
        - Clear daily counters
        - Reset resource files to defaults
        - Clear accumulated state
        
        Default implementation: no-op (stage has nothing to reset).
        """
        pass



def _load_stage_class(dotted: str):
    """
    dotted format: "some.module.path:ClassName"
    """
    if ":" not in dotted:
        raise ValueError(f"Invalid stage_class '{dotted}'. Expected 'module.path:ClassName'.")
    mod_path, cls_name = dotted.split(":", 1)
    mod = importlib.import_module(mod_path)
    cls = getattr(mod, cls_name)
    return cls


# -------------------------------------------------------------------------
# Manager
# -------------------------------------------------------------------------

class PhysicalPipelineManager:
    """
    Orchestrates the physical pipeline via config-driven stages.

    State is stored in a single resource state file (configured), containing only:
    - lifecycle flags and timestamps
    - stage run bookkeeping
    - cursors (chat cursor, etc.)
    - optional stage-generated signals that the manager uses (day_start_signal, etc.)
    """

    DEFAULT_CONFIG_FILE = "config_physical_pipeline.json"

    def __init__(self, config_filename: Optional[str] = None):
        self._resources_dir = _resources_dir()
        self._config_filename = config_filename or self.DEFAULT_CONFIG_FILE
        self._config_path = self._resources_dir / self._config_filename

        self._config: Dict[str, Any] = {}
        self._config_mtime: Optional[float] = None

        self.state: Dict[str, Any] = {}
        self._state_path: Optional[Path] = None

        self._stages: Dict[str, BaseStage] = {}
        self._state_dirty: bool = False

        self._load_config()
        self._load_state()
        self._init_stages()

        self._save_state(force=True)

    # ------------------------------------------------------------------
    # Config and state
    # ------------------------------------------------------------------

    def _load_config(self) -> None:
        cfg = _read_json_file(self._config_path) or {}
        self._config = cfg
        try:
            self._config_mtime = self._config_path.stat().st_mtime
        except Exception:
            self._config_mtime = None

        if not self._config.get("enabled", True):
            logger.info("PhysicalPipelineManager config enabled=false; manager will no-op on refresh.")

        state_file = self._config.get("state_resource_file") or "resource_wellness_pipeline_status.json"
        self._state_path = self._resources_dir / state_file

    def _reload_config_if_changed(self) -> bool:
        try:
            mtime = self._config_path.stat().st_mtime
        except Exception:
            return False

        if self._config_mtime is None or mtime != self._config_mtime:
            logger.info("Pipeline config changed; reloading.")
            self._load_config()
            self._init_stages()
            return True
        return False

    def _default_state(self) -> Dict[str, Any]:
        return {
            "schema_version": 2,
            "last_updated_utc": _utc_now().isoformat(),
            "boundary_date_local": None,  # YYYY-MM-DD (as defined by boundary hour)
            "last_daily_reset_utc": None,  # Full ISO datetime of when daily reset last ran
            "last_daily_reset_boundary": None,  # YYYY-MM-DD boundary date that was reset
            "day_started": False,
            "day_start_time_utc": None,
            "day_start_time": None,
            "wake_time_today": None,
            "user_is_up": None,
            "cursors": {
                "chat_last_seen_utc": None
            },
            "stage_runs": {
                # stage_id -> { "last_run_utc": ..., "last_reason": ..., "last_debug": ... }
            },
            "signals": {
                # arbitrary stage-set signals
            }
        }

    def _load_state(self) -> None:
        assert self._state_path is not None
        loaded = _read_json_file(self._state_path)
        if not loaded:
            self.state = self._default_state()
            return

        base = self._default_state()

        # Only load known schema v2 fields - ignore any legacy fields
        known_fields = {
            "schema_version",
            "last_updated_utc",
            "boundary_date_local",
            "last_daily_reset_utc",
            "last_daily_reset_boundary",
            "day_started",
            "day_start_time_utc",
            "day_start_time",
            "wake_time_today",
            "user_is_up",
        }

        for k, v in loaded.items():
            if k in known_fields:
                base[k] = v

        base["cursors"].update(loaded.get("cursors") or {})
        base["stage_runs"].update(loaded.get("stage_runs") or {})
        base["signals"].update(loaded.get("signals") or {})

        self.state = base

    def _mark_dirty(self) -> None:
        self._state_dirty = True

    def _save_state(self, force: bool = False) -> None:
        if not self._state_path:
            return
        if not force and not self._state_dirty:
            return
        self.state["last_updated_utc"] = _utc_now().isoformat()
        _write_json_file(self._state_path, self.state)
        self._state_dirty = False

    # ------------------------------------------------------------------
    # Stage initialization
    # ------------------------------------------------------------------

    def _init_stages(self) -> None:
        self._stages = {}
        stages_cfg = self._config.get("stages") or []
        for item in stages_cfg:
            try:
                stage_id = (item.get("id") or "").strip()
                if not stage_id:
                    continue
                if not item.get("enabled", True):
                    continue
                stage_class_path = item.get("stage_class")
                if not stage_class_path:
                    logger.warning(f"Stage '{stage_id}' missing stage_class; skipping.")
                    continue

                cls = _load_stage_class(stage_class_path)
                stage_obj = cls()  # constructor must not require args

                if not getattr(stage_obj, "stage_id", ""):
                    setattr(stage_obj, "stage_id", stage_id)

                self._stages[stage_id] = stage_obj
                logger.info(f"Initialized stage '{stage_id}' from {stage_class_path}")

            except Exception as e:
                logger.error(f"Failed to init stage from config item={item}: {e}")

    # ------------------------------------------------------------------
    # Boundary day logic (default 5AM local)
    # ------------------------------------------------------------------

    def _boundary_date_local_str(self, now_local: datetime) -> str:
        daily_reset = self._config.get("daily_reset") or {}
        boundary_hour = int(daily_reset.get("boundary_hour_local", 5))

        effective_day = now_local
        if now_local.hour < boundary_hour:
            effective_day = now_local - timedelta(days=1)

        return effective_day.strftime("%Y-%m-%d")

    def _handle_daily_boundary(self, now_utc: datetime, now_local: datetime) -> bool:
        """
        Returns True if boundary crossed and we performed reset actions.

        Manager-only reset actions:
        - reset boundary_date_local
        - reset day_started, day_start_time_utc
        - clear signals
        - call reset_stage() on each stage

        Reset is needed when:
        - Flask starts after 5AM boundary but no reset has happened for today's boundary
        - 5AM boundary is crossed during normal operation
        
        We track both the boundary date AND the full datetime of the last reset.
        """
        current_boundary_date = self._boundary_date_local_str(now_local)
        prev_boundary_date = self.state.get("boundary_date_local")
        last_reset_boundary = self.state.get("last_daily_reset_boundary")

        # Check if we need to run daily reset
        # This handles both boundary crossing AND cold start catch-up
        need_reset = last_reset_boundary != current_boundary_date

        if prev_boundary_date != current_boundary_date:
            logger.info(f"Daily boundary crossed: {prev_boundary_date} -> {current_boundary_date}")
            self.state["boundary_date_local"] = current_boundary_date
            self.state["day_started"] = False
            self.state["day_start_time_utc"] = None
            self.state["signals"] = {}
            self._mark_dirty()

        if need_reset:
            logger.info(f"🌅 Daily reset needed: last_reset_boundary={last_reset_boundary}, current={current_boundary_date}")
            self._run_stage_resets(now_utc, now_local)
            self.state["last_daily_reset_utc"] = now_utc.isoformat()
            self.state["last_daily_reset_boundary"] = current_boundary_date
            self._mark_dirty()
            return True

        return prev_boundary_date != current_boundary_date

    def _run_stage_resets(self, now_utc: datetime, now_local: datetime) -> None:
        logger.info("🌅 Running stage resets for all stages...")

        ctx = StageContext(
            now_utc=now_utc,
            now_local=now_local,
            state=self.state,        # optional; keep if stages need read-only orchestration context
            config=self._config,     # optional; pipeline-level config only
            stage_config={},         # unused when stages own their config
            resources_dir=self._resources_dir,
        )

        any_reset_succeeded = False

        for stage_id, stage in self._stages.items():
            try:
                stage.reset_stage(ctx)   # stage loads its own config internally
                logger.info("  ✓ %s reset complete", stage_id)
                any_reset_succeeded = True
            except Exception as e:
                logger.error("  ✗ %s reset failed: %s", stage_id, e)

        if any_reset_succeeded:
            self._mark_dirty()


    def force_stage_reset(self) -> Dict[str, Any]:
        """
        Force a boundary reset on all stages (debugging).

        Returns a dict with per-stage results.
        """
        now_utc = datetime.now(timezone.utc)
        now_local = utc_to_local(now_utc)

        logger.info("🔧 FORCED reset triggered via debug UI")

        results: Dict[str, Any] = {
            "timestamp_utc": now_utc.isoformat(),
            "timestamp_local": now_local.strftime("%Y-%m-%d %I:%M %p"),
            "stages": {},
        }

        ctx = StageContext(
            now_utc=now_utc,
            now_local=now_local,
            state=self.state,
            config=self._config,
            stage_config={},  # unused; stages manage their own config
            resources_dir=self._resources_dir,
        )

        for stage_id, stage in self._stages.items():
            try:
                stage.reset_stage(ctx)
                results["stages"][stage_id] = {"status": "success"}
                logger.info("  ✓ %s forced reset complete", stage_id)
            except Exception as e:
                results["stages"][stage_id] = {"status": "error", "error": str(e)}
                logger.error("  ✗ %s forced reset failed: %s", stage_id, e)

        # Record forced reset in manager state
        self.state["last_daily_reset_utc"] = now_utc.isoformat()
        self.state["last_daily_reset_boundary"] = self._boundary_date_local_str(now_local)
        self.state["_last_reset_source"] = "forced_debug"
        self._mark_dirty()
        self._save_state()

        results["state_updated"] = True
        return results


    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """
        Main refresh entrypoint (called by maintenance_manager).

        Steps:
        1) reload config if changed
        2) compute now_utc and now_local
        3) daily boundary check (boundary hour local)
        4) run enabled stages according to run_policy
        5) persist state
        """
        self._reload_config_if_changed()

        if not self._config.get("enabled", True):
            return

        now_utc = _utc_now()
        now_local = utc_to_local(now_utc)

        # Reset dirty state for this cycle
        self._state_dirty = False

        # Daily boundary reset (also handles cold start catch-up)
        boundary_crossed = self._handle_daily_boundary(now_utc, now_local)
        self.state["_transient_boundary_crossed"] = boundary_crossed

        stages_cfg_list = self._config.get("stages") or []
        stages_cfg = {s.get("id"): s for s in stages_cfg_list if s.get("id")}

        # Create context once, reuse for all stages
        ctx = StageContext(
            now_utc=now_utc,
            now_local=now_local,
            state=self.state,
            config=self._config,
            stage_config={},  # Stages load their own config
            resources_dir=self._resources_dir,
        )

        for stage_id, stage in self._stages.items():
            should_run, reason = stage.should_run_stage(ctx)

            if not should_run:
                # Don't update last_run_utc when skipped - just log
                # (updating it would break min_interval_seconds logic)
                continue

            try:
                result = stage.run(ctx)
            except Exception as e:
                logger.error(f"Stage '{stage_id}' failed: {e}")
                self._record_stage_run(stage_id, now_utc, f"{reason}; error", debug={"error": str(e)})
                raise

            if result.state_updates:
                if self._merge_into(self.state, result.state_updates):
                    self._mark_dirty()

            # Stages write their own output files via ctx.write_resource()
            # Manager only records the run

            self._record_stage_run(stage_id, now_utc, reason, debug=result.debug)

        # Clear transient flags
        if "_transient_boundary_crossed" in self.state:
            del self.state["_transient_boundary_crossed"]

        self._save_state()

    # ------------------------------------------------------------------
    # State merge and stage run bookkeeping
    # ------------------------------------------------------------------

    @staticmethod
    def _merge_into(dst: Dict[str, Any], src: Dict[str, Any]) -> bool:
        """
        Shallow merge only. This is intentional.
        Manager state should remain small and predictable.
        """
        changed = False
        for k, v in (src or {}).items():
            if dst.get(k) != v:
                dst[k] = v
                changed = True
        return changed

    def _record_stage_run(
            self,
            stage_id: str,
            now_utc: datetime,
            reason: str,
            debug: Optional[Dict[str, Any]],
    ) -> None:
        runs = self.state.setdefault("stage_runs", {})
        runs[stage_id] = {
            "last_run_utc": now_utc.isoformat(),
            "last_reason": reason,
            "last_debug": debug,
        }
        self._mark_dirty()

    def run_stage(self, stage_id: str, reason: str = "on_demand") -> Optional[StageResult]:
        """
        Run a specific stage on-demand.

        Returns StageResult or None if stage not found.
        """
        stage = self._stages.get(stage_id)
        if stage is None:
            logger.warning("Stage '%s' not found for on-demand run", stage_id)
            return None

        now_utc = _utc_now()
        now_local = utc_to_local(now_utc)

        ctx = StageContext(
            now_utc=now_utc,
            now_local=now_local,
            state=self.state,
            config=self._config,
            stage_config={},  # stages own their config
            resources_dir=self._resources_dir,
        )

        try:
            result = stage.run(ctx)

            if result.cursor_updates:
                if self._merge_into(self.state.setdefault("cursors", {}), result.cursor_updates):
                    self._mark_dirty()
            if result.state_updates:
                if self._merge_into(self.state, result.state_updates):
                    self._mark_dirty()

            self._record_stage_run(stage_id, now_utc, reason, debug=result.debug)
            self._save_state()

            logger.info("Stage '%s' run on-demand: %s", stage_id, reason)
            return result

        except Exception as e:
            logger.error("Stage '%s' on-demand run failed: %s", stage_id, e)
            self._record_stage_run(stage_id, now_utc, f"{reason}; error", debug={"error": str(e)})
            self._save_state()
            raise


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

_pipeline_manager: Optional[PhysicalPipelineManager] = None


def get_physical_pipeline_manager() -> PhysicalPipelineManager:
    global _pipeline_manager
    if _pipeline_manager is None:
        _pipeline_manager = PhysicalPipelineManager()
    return _pipeline_manager
