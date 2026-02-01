# background_task_manager.py
"""
Background Task Manager
=======================

Runs periodic tasks independently of the browser/UI.
These tasks do not require user interaction and should run even when no browser tab is open.

Tasks managed (current defaults):
- Day flow cycle (3 min): day flow pipeline refresh
- Save chat (30s): persist in-memory global blackboard to unified_log
- Switchboard runner (60s): extract preferences from unified_log windows
- Memory runner (5 min): process extracted facts and update resource files
- Database cleanup (24h): delete old AFK events
- Watchdog (60s): restart any tasks that stop unexpectedly
- Ticket maintenance (5 min): expire old tickets (>2h), wake snoozed tickets
"""

import threading
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

from app.assistant.utils.logging_config import get_logger
from app.assistant.utils.error_logging import log_critical_error

logger = get_logger(__name__)


TaskFn = Callable[[], None]


class BackgroundTask:
    """
    A single background task with its own thread.

    Key behavior:
    - Uses a stop Event for interruptible waiting (fast shutdown).
    - Maintains thread and counters under a lock for safe status reads.
    - Does not drop the thread handle unless the thread is actually dead.
    - Logs exceptions with tracebacks via logger.exception.
    """

    def __init__(
            self,
            name: str,
            func: TaskFn,
            interval_seconds: int,
            run_immediately: bool = False,
            initial_delay_seconds: int = 0,
    ):
        self.name = name
        self.func = func
        self.interval_seconds = int(interval_seconds)
        self.run_immediately = bool(run_immediately)
        self.initial_delay_seconds = int(initial_delay_seconds)

        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        self._last_run: Optional[datetime] = None
        self._run_count = 0
        self._error_count = 0
        self._running_intent = False  # "Should be running" signal, not thread liveness

    def start(self) -> None:
        with self._lock:
            if self._running_intent and self._thread and self._thread.is_alive():
                logger.debug("Task '%s' already running", self.name)
                return

            # If intent was true but thread died, we are restarting cleanly.
            self._running_intent = True
            self._stop_event.clear()

            self._thread = threading.Thread(
                target=self._loop,
                daemon=True,
                name=f"bg-{self.name}",
            )
            self._thread.start()

        logger.info(
            "Background task '%s' started (interval=%ss, run_immediately=%s, initial_delay=%ss)",
            self.name,
            self.interval_seconds,
            self.run_immediately,
            self.initial_delay_seconds,
        )

    def stop(self, join_timeout_seconds: float = 2.0) -> None:
        # Signal stop first (interrupts waiting)
        with self._lock:
            self._running_intent = False
            self._stop_event.set()
            thread = self._thread

        if thread is None:
            logger.info("Background task '%s' stopped (was not running)", self.name)
            return

        thread.join(timeout=join_timeout_seconds)

        # Only clear the thread handle if it actually exited
        with self._lock:
            if self._thread and not self._thread.is_alive():
                self._thread = None

        logger.info(
            "Background task '%s' stop requested (joined=%s)",
            self.name,
            (thread is not None and not thread.is_alive()),
        )

    def restart(self) -> None:
        self.stop()
        self.start()

    def is_alive(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    def should_be_running(self) -> bool:
        with self._lock:
            return self._running_intent

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            thread_alive = self._thread.is_alive() if self._thread else False
            last_run = self._last_run.isoformat() if self._last_run else None
            return {
                "name": self.name,
                "should_be_running": self._running_intent,
                "thread_alive": thread_alive,
                "interval_seconds": self.interval_seconds,
                "run_immediately": self.run_immediately,
                "initial_delay_seconds": self.initial_delay_seconds,
                "last_run": last_run,
                "run_count": self._run_count,
                "error_count": self._error_count,
            }

    def _loop(self) -> None:
        # Optional initial delay
        if self.initial_delay_seconds > 0:
            if self._stop_event.wait(timeout=self.initial_delay_seconds):
                return

        # Optional immediate run on start
        if self.run_immediately and not self._stop_event.is_set():
            self._execute()

        # Fixed-rate loop, using Event.wait for interruptible sleep
        while not self._stop_event.is_set():
            if self._stop_event.wait(timeout=self.interval_seconds):
                break
            self._execute()

    def _execute(self) -> None:
        try:
            self.func()
            now = datetime.now(timezone.utc)
            with self._lock:
                self._last_run = now
                self._run_count += 1
        except Exception:
            with self._lock:
                self._error_count += 1
            logger.exception("Background task '%s' failed during execution", self.name)


class BackgroundTaskManager:
    """
    Manages all background tasks that run independently of the UI.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self.tasks: Dict[str, BackgroundTask] = {}
        self._started = False

        self._register_default_tasks()

    def _register_default_tasks(self) -> None:
        # 1. Day flow cycle (3 minutes)
        self.register_task(
            name="day_flow_cycle",
            func=self._run_day_flow_cycle,
            interval_seconds=3 * 60,
            run_immediately=False,
        )

        # 2. Save chat (30 seconds)
        # Run this quickly so switchboard has fresh unified_log to read from.
        self.register_task(
            name="save_chat",
            func=self._run_save_chat,
            interval_seconds=30,
            run_immediately=True,
            initial_delay_seconds=5,
        )

        # 3. Switchboard runner (1 minute)
        # Small initial delay so "save_chat" has a chance to ingest the first batch.
        self.register_task(
            name="switchboard_runner",
            func=self._run_switchboard_runner,
            interval_seconds=60,
            run_immediately=False,
            initial_delay_seconds=20,
        )

        # 4. Memory runner (5 minutes)
        self.register_task(
            name="memory_runner",
            func=self._run_memory_runner,
            interval_seconds=5 * 60,
            run_immediately=False,
            initial_delay_seconds=60,
        )

        # 5. Database cleanup (24 hours)
        self.register_task(
            name="db_cleanup",
            func=self._run_db_cleanup,
            interval_seconds=24 * 60 * 60,
            run_immediately=False,
            initial_delay_seconds=60,
        )

        # 6. Watchdog (1 minute)
        self.register_task(
            name="watchdog",
            func=self._run_watchdog,
            interval_seconds=60,
            run_immediately=False,
            initial_delay_seconds=60,
        )

        # 7. Ticket maintenance (5 minutes)
        # Expire tickets older than 2 hours
        self.register_task(
            name="ticket_maintenance",
            func=self._run_ticket_maintenance,
            interval_seconds=5 * 60,
            run_immediately=False,
            initial_delay_seconds=30,
        )

    def register_task(
            self,
            name: str,
            func: TaskFn,
            interval_seconds: int,
            run_immediately: bool = False,
            initial_delay_seconds: int = 0,
    ) -> None:
        with self._lock:
            if name in self.tasks:
                logger.warning("Task '%s' already registered, replacing", name)
                self.tasks[name].stop()

            self.tasks[name] = BackgroundTask(
                name=name,
                func=func,
                interval_seconds=interval_seconds,
                run_immediately=run_immediately,
                initial_delay_seconds=initial_delay_seconds,
            )

    def start_all(self) -> None:
        with self._lock:
            if self._started:
                logger.warning("BackgroundTaskManager already started")
                return
            self._started = True

        logger.info("Starting background tasks (count=%s)", len(self.tasks))
        for task in self.tasks.values():
            task.start()

    def stop_all(self) -> None:
        logger.info("Stopping all background tasks...")
        for task in self.tasks.values():
            task.stop()

        with self._lock:
            self._started = False

        logger.info("All background tasks stopped")

    def start_task(self, name: str) -> None:
        task = self.tasks.get(name)
        if not task:
            logger.error("Task '%s' not registered", name)
            return
        task.start()

    def stop_task(self, name: str) -> None:
        task = self.tasks.get(name)
        if not task:
            logger.error("Task '%s' not registered", name)
            return
        task.stop()

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            started = self._started
        return {
            "started": started,
            "task_count": len(self.tasks),
            "tasks": {name: task.get_status() for name, task in self.tasks.items()},
        }

    # =========================================================================
    # Task Implementations
    # =========================================================================

    def _run_day_flow_cycle(self) -> None:
        """
        Trigger the day flow pipeline refresh.
        """
        try:
            from app.assistant.day_flow_manager import get_physical_pipeline_manager
            manager = get_physical_pipeline_manager()
            manager.refresh()
            logger.debug("Day flow cycle complete")

        except Exception as e:
            log_critical_error(
                message="Day flow cycle failed",
                exception=e,
                context="BackgroundTaskManager._run_day_flow_cycle",
                include_traceback=True,
            )

    def _run_switchboard_runner(self) -> None:
        try:
            from app.assistant.switchboard import SwitchboardRunner
            from app.models.base import get_session
            from app.assistant.database.db_handler import UnifiedLog, SwitchboardState
            from sqlalchemy import func

            session = get_session()
            try:
                state = (
                    session.query(SwitchboardState)
                        .filter(SwitchboardState.id == 1)
                        .first()
                )
                last_id = state.last_processed_message_id if state else None

                q = session.query(func.count(UnifiedLog.id)).filter(
                    UnifiedLog.role.in_(["user", "assistant"])
                )

                # Prefer the monotonic ID cursor rather than timestamp comparisons
                if last_id is not None:
                    q = q.filter(UnifiedLog.id > last_id)

                new_count = q.scalar() or 0
                if new_count == 0:
                    logger.debug("Switchboard: no new messages (skipping)")
                    return

            finally:
                session.close()

            runner = SwitchboardRunner()
            result = runner.run()

            processed = result.get("processed", 0)
            facts_extracted = result.get("facts_extracted", 0)

            if processed > 0:
                logger.debug(
                    "Switchboard processed %s messages, extracted %s facts",
                    processed,
                    facts_extracted,
                )
            else:
                logger.debug("Switchboard: %s", result.get("message", "No new messages"))

        except Exception as e:
            log_critical_error(
                message="Switchboard runner failed to process chat history",
                exception=e,
                context="BackgroundTaskManager._run_switchboard_runner",
                include_traceback=True,
            )

    def _run_save_chat(self) -> None:
        """
        Persist chat messages from the in-memory global blackboard into unified_log.
        Provides ingestion independent of UI idle events.
        """
        try:
            from app.assistant.ServiceLocator.service_locator import ServiceLocator

            maintenance_manager = ServiceLocator.get("maintenance_manager")
            if maintenance_manager is None:
                # initialize_system() registers this later in startup
                return

            maintenance_manager.save_chat_history()

        except Exception as e:
            log_critical_error(
                message="Chat persistence task failed",
                exception=e,
                context="BackgroundTaskManager._run_save_chat",
                include_traceback=True,
            )

    def _run_memory_runner(self) -> None:
        try:
            from app.models.base import get_session
            from app.assistant.database.db_handler import ExtractedFact

            session = get_session()
            try:
                unprocessed_count = (
                    session.query(ExtractedFact)
                        .filter(
                        ExtractedFact.processed.is_(False),
                        ExtractedFact.category.in_(["preference", "feedback"]),
                    )
                        .count()
                )
                if unprocessed_count == 0:
                    logger.debug("Memory runner: no unprocessed facts (skipping)")
                    return
            finally:
                session.close()

            from app.assistant.memory.memory_runner import MemoryRunner
            runner = MemoryRunner()
            result = runner.run(max_facts=3)

            processed = result.get("processed", 0)
            success = result.get("success", 0)
            failed = result.get("failed", 0)

            if processed > 0:
                logger.info(
                    "Memory runner processed %s facts (success=%s, failed=%s)",
                    processed,
                    success,
                    failed,
                )
            else:
                logger.debug("Memory runner: %s", result.get("message", "No facts"))

        except Exception as e:
            log_critical_error(
                message="Memory runner failed to process extracted facts",
                exception=e,
                context="BackgroundTaskManager._run_memory_runner",
                include_traceback=True,
            )

    def _run_watchdog(self) -> None:
        # Restart any task that is intended to be running but is not alive.
        dead = []
        for name, task in self.tasks.items():
            if name == "watchdog":
                continue

            if task.should_be_running() and not task.is_alive():
                dead.append(name)

        if not dead:
            return

        logger.error("Watchdog detected dead tasks: %s", dead)
        for name in dead:
            try:
                logger.warning("Watchdog restarting task: %s", name)
                self.tasks[name].start()
            except Exception:
                logger.exception("Watchdog failed to restart task: %s", name)

    def _run_db_cleanup(self) -> None:
        try:
            pass

        except Exception as e:
            log_critical_error(
                message="Database cleanup failed",
                exception=e,
                context="BackgroundTaskManager._run_db_cleanup",
                include_traceback=True,
            )

    def _run_ticket_maintenance(self) -> None:
        """
        Expire tickets older than 2 hours.
        Also wakes up snoozed tickets whose snooze time has passed.
        """
        try:
            from app.assistant.ticket_manager import get_ticket_manager
            
            ticket_manager = get_ticket_manager()
            
            # Expire old tickets (2 hour max age)
            expired = ticket_manager.expire_old_tickets()
            if expired > 0:
                logger.info(f"Ticket maintenance: expired {expired} old tickets")
            
            # Handle snoozed tickets whose snooze time has passed
            # Policy: expire them so orchestrator can create fresh tickets with current context
            snoozed_ready = ticket_manager.get_snoozed_tickets_ready()
            for ticket in snoozed_ready:
                ticket_manager.mark_expired(
                    ticket.ticket_id,
                    reason=f"Snooze expired after {ticket.snooze_count} snooze(s) - orchestrator will re-evaluate"
                )
            if snoozed_ready:
                logger.info(f"Ticket maintenance: expired {len(snoozed_ready)} snoozed tickets")

        except Exception as e:
            log_critical_error(
                message="Ticket maintenance failed",
                exception=e,
                context="BackgroundTaskManager._run_ticket_maintenance",
                include_traceback=True,
            )


# Singleton instance
_background_task_manager: Optional[BackgroundTaskManager] = None


def get_background_task_manager() -> BackgroundTaskManager:
    global _background_task_manager
    if _background_task_manager is None:
        _background_task_manager = BackgroundTaskManager()
    return _background_task_manager


def start_background_tasks() -> BackgroundTaskManager:
    manager = get_background_task_manager()
    manager.start_all()
    return manager


def stop_background_tasks() -> None:
    global _background_task_manager
    if _background_task_manager:
        _background_task_manager.stop_all()
