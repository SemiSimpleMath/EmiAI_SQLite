from datetime import datetime, timezone, timedelta
import threading
from typing import Dict

from app.assistant.lib.tools.get_email.tool_forms.tool_forms import get_email_args, get_email_arguments
from app.assistant.lib.tools.get_news.tool_forms.tool_forms import get_news_args, get_news_arguments
from app.assistant.lib.tools.get_calendar_events.tool_forms.tool_forms import get_calendar_events_args, get_calendar_events_arguments
from app.assistant.lib.tools.get_todo_tasks.tool_forms.tool_forms import get_todo_tasks_args, get_todo_tasks_arguments
from app.assistant.lib.tools.get_scheduler_events.tool_forms.tool_forms import get_scheduler_events_args, get_scheduler_events_arguments
from app.assistant.lib.tools.get_weather.tool_forms.tool_forms import get_weather_args, get_weather_arguments
from app.assistant.utils.pydantic_classes import ToolMessage

from app.assistant.event_repository.event_repository import EventRepositoryManager
from app.assistant.ServiceLocator.service_locator import DI
from app.assistant.utils.logging_config import get_maintenance_logger
from app.assistant.utils.time_utils import get_local_time
from app.assistant.user_settings_manager.user_settings import can_run_feature

logger = get_maintenance_logger(__name__)

DEFAULT_MIN_INTERVALS = {
    'get_email': 5,       # Check email frequently
    'get_todo_tasks': 31, # Check todos less frequently
    'get_news': 23,       # Check news less frequently
    'get_weather': 11,    # Prime
    'get_scheduler_events': 3,  # Check scheduler frequently
    'get_calendar_events': 27,   # Check calendar less frequently
}


def fire_and_forget(func, *args, **kwargs):
    thread = threading.Thread(target=func, args=args, kwargs=kwargs)
    thread.daemon = True  # Daemon thread won't block process exit
    thread.start()


class MaintenanceToolCaller:
    def __init__(self, min_intervals: Dict[str, int] = DEFAULT_MIN_INTERVALS):
        # Resolve tool_registry directly from DI
        self.tool_registry = DI.tool_registry
        self.min_intervals = min_intervals
        self.tool_timers: Dict[str, datetime] = {}
        self.tools_in_order = [
            'get_email',
            'get_news',
            'get_calendar_events',
            'get_todo_tasks',
            'get_scheduler_events',
            'get_weather',
        ]

        self.next_tool_index = 0
        self.first_run = True

    def call_next_tool_if_ready(self):
        now = datetime.now(timezone.utc)
        total_tools = len(self.tools_in_order)
        attempts = 0

        while attempts < total_tools:
            tool = self.tools_in_order[self.next_tool_index]
            is_eligible = self._is_tool_eligible(tool, now)
            
            # Log eligibility status for debugging
            if tool == 'get_email':
                last_called = self.tool_timers.get(tool)
                if last_called:
                    elapsed = (now - last_called).total_seconds() / 60.0
                    logger.info(f"📧 Email eligibility check: elapsed={elapsed:.1f} min, required=5 min, eligible={is_eligible}")
                else:
                    logger.info(f"📧 Email eligibility check: never called, eligible={is_eligible}")
            
            if is_eligible:
                # Dynamically get the trigger method (e.g., trigger_get_email)
                trigger_method = getattr(self, f"trigger_{tool}", None)
                if trigger_method:
                    trigger_method()
                    self.tool_timers[tool] = now
                    logger.info(f"Called tool: {tool}")
                    break
                else:
                    logger.error(f"No trigger method defined for tool: {tool}")
            else:
                logger.debug(f"Tool '{tool}' is not eligible yet.")
            self.next_tool_index = (self.next_tool_index + 1) % total_tools
            attempts += 1

        if self.first_run and self.next_tool_index == 0:
            self.first_run = False
            logger.debug("Completed first full round of tool execution.")

    def _is_tool_eligible(self, tool: str, current_time: datetime) -> bool:
        # Map tool names to feature names
        tool_feature_map = {
            'get_email': 'email',
            'get_calendar_events': 'calendar',
            'get_todo_tasks': 'tasks',
            'get_weather': 'weather',
            'get_news': 'news',
            'get_scheduler_events': 'scheduler'
        }
        
        # Check if feature is enabled and has required API keys
        feature_name = tool_feature_map.get(tool)
        if feature_name:
            if not can_run_feature(feature_name):
                logger.debug(f"⏸️ Tool '{tool}' skipped: feature '{feature_name}' disabled or missing required API key")
                return False
        
        if self.first_run:
            return True
        
        # Standard interval-based scheduling for all tools
        min_interval = self.min_intervals.get(tool, 10)
        last_called = self.tool_timers.get(tool)
        if last_called is None:
            return True
        elapsed = (current_time - last_called).total_seconds() / 60.0
        return elapsed >= min_interval

    def _run_tool_async(self, tool_func, *args, **kwargs):
        fire_and_forget(tool_func, *args, **kwargs)

    def trigger_get_email(self):
        logger.info("Triggering get_email tool.")
        repo = EventRepositoryManager()
        raw_last_checked = repo.get_last_altered_by_data_type().get("email")

        now_utc = datetime.now(timezone.utc)

        DEFAULT_LOOKBACK = timedelta(days=7)
        MAX_LOOKBACK = timedelta(days=7)
        FUTURE_SKEW_FALLBACK = timedelta(hours=1)

        # Normalize last_checked into an aware UTC datetime
        if not raw_last_checked:
            logger.info("📧 No last_checked found, defaulting to 7 days ago.")
            last_checked = now_utc - DEFAULT_LOOKBACK

        elif isinstance(raw_last_checked, str):
            try:
                iso_str = raw_last_checked.replace("Z", "+00:00")
                parsed = datetime.fromisoformat(iso_str)
                if parsed.tzinfo is None:
                    logger.warning("📧 last_checked string was naive. Treating as UTC.")
                    parsed = parsed.replace(tzinfo=timezone.utc)
                last_checked = parsed
            except Exception as e:
                logger.error(f"📧 Error parsing last_checked '{raw_last_checked}': {e}. Using default lookback.")
                last_checked = now_utc - DEFAULT_LOOKBACK

        elif isinstance(raw_last_checked, datetime):
            if raw_last_checked.tzinfo is None:
                logger.warning("📧 last_checked datetime was naive. Treating as UTC.")
                last_checked = raw_last_checked.replace(tzinfo=timezone.utc)
            else:
                last_checked = raw_last_checked

        else:
            logger.warning(f"📧 Unexpected last_checked type {type(raw_last_checked)}. Using default lookback.")
            last_checked = now_utc - DEFAULT_LOOKBACK

        # Guard against future timestamps
        if last_checked > now_utc:
            logger.warning(f"📧 last_checked ({last_checked}) is in the future. Adjusting to 1 hour ago.")
            last_checked = now_utc - FUTURE_SKEW_FALLBACK

        # Cap lookback window
        lookback = now_utc - last_checked
        if lookback > MAX_LOOKBACK:
            logger.warning(
                f"📧 last_checked ({last_checked}) is older than {MAX_LOOKBACK.days} days. "
                f"Capping start to {MAX_LOOKBACK.days} days ago."
            )
            last_checked = now_utc - MAX_LOOKBACK

        # Final window (UTC)
        start_date_str = last_checked.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%S")
        end_date_str = now_utc.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%S")

        logger.info(
            f"📧 Email search window (UTC): start_date={start_date_str}, "
            f"end_date={end_date_str}"
        )

        args_dict = get_email_args(
            start_date=start_date_str,
            end_date=end_date_str,
            unseen=True,
            repo_update=True,
        ).model_dump()

        email_args_model = get_email_arguments(
            tool_name="get_email",
            arguments=args_dict,
        )

        tool_message = ToolMessage(
            tool_name="get_email",
            tool_data=email_args_model.model_dump(),
        )

        def tool_call():
            tool_entry = self.tool_registry.get_tool('get_email')
            tool_class = tool_entry["tool_class"]
            tool_instance = tool_class()
            tool_instance.execute(tool_message)

        self._run_tool_async(tool_call)


    def trigger_get_news(self):
        logger.info("Triggering get_news tool.")
        args_dict = get_news_args(feed_urls=[]).model_dump()
        news_args_model = get_news_arguments(tool_name="get_news", arguments=args_dict)
        tool_message = ToolMessage(
            tool_name="get_news",
            tool_data=news_args_model.model_dump()
        )

        def tool_call():
            tool_entry = self.tool_registry.get_tool('get_news')
            tool_class = tool_entry["tool_class"]
            tool_instance = tool_class()
            tool_instance.execute(tool_message)

        self._run_tool_async(tool_call)

    def trigger_get_calendar_events(self):
        """
        Fetch calendar events with a stable 7 day window anchored to midnight.
        Window: Today 00:00:00 to (Today + 7 days) 23:59:59.
        """
        local_now = get_local_time()
        local_midnight = local_now.replace(hour=0, minute=0, second=0, microsecond=0)

        start_date = local_midnight.isoformat()
        end_date = (local_midnight + timedelta(days=7, seconds=-1)).isoformat()

        args_dict = get_calendar_events_args(
            start_date=start_date,
            end_date=end_date,
            calendar_names=[
                "primary",
                "birthday",
                "holidays in united states",
                "family",
                "work",
                "food",
            ],
            single_events=True,
            repo_update=True,  # only scheduler sets this
        ).model_dump()

        calendar_args_model = get_calendar_events_arguments(
            tool_name="get_calendar_events",
            arguments=args_dict,
        )

        tool_message = ToolMessage(
            tool_name="get_calendar_events",
            tool_data=calendar_args_model.model_dump(),
        )

        def tool_call():
            tool_entry = self.tool_registry.get_tool("get_calendar_events")
            tool_class = tool_entry["tool_class"]
            tool_instance = tool_class()
            tool_instance.execute(tool_message)

        self._run_tool_async(tool_call)




    def trigger_get_todo_tasks(self):
        logger.info("Triggering get_todo_tasks tool.")

        local_now = get_local_time()
        local_midnight = local_now.replace(hour=0, minute=0, second=0, microsecond=0)

        start_date = (local_midnight + timedelta(days=-30)).isoformat()
        end_date = (local_midnight + timedelta(days=30)).isoformat()


        args_dict = get_todo_tasks_args(
            start_date=start_date, 
            end_date=end_date,
            repo_update=True  # Maintenance tool writes to repo
        ).model_dump()
        todo_args_model = get_todo_tasks_arguments(tool_name='get_todo_tasks', arguments=args_dict)
        tool_message = ToolMessage(
            tool_name='get_todo_tasks',
            tool_data=todo_args_model.model_dump()
        )


        def tool_call():
            tool_entry = self.tool_registry.get_tool('get_todo_tasks')
            tool_class = tool_entry["tool_class"]
            tool_instance = tool_class()
            tool_instance.execute(tool_message)

        self._run_tool_async(tool_call)

    def trigger_get_scheduler_events(self):
        logger.info("Triggering get_scheduler_events tool.")

        args_model = get_scheduler_events_args(start_date="", end_date="")
        scheduler_args_model = get_scheduler_events_arguments(
            tool_name='get_scheduler_events',
            arguments=args_model
        )
        tool_message = ToolMessage(
            tool_name='get_scheduler_events',
            tool_data=scheduler_args_model.model_dump()
        )


        def tool_call():
            tool_entry = self.tool_registry.get_tool('get_scheduler_events')
            tool_class = tool_entry["tool_class"]
            tool_instance = tool_class()
            tool_instance.execute(tool_message)

        self._run_tool_async(tool_call)

    def trigger_get_weather(self):
        logger.info("Triggering get_weather tool.")
        args_dict = get_weather_args(city="Irvine", forecast_type="current").model_dump()
        weather_args_model = get_weather_arguments(tool_name="get_weather", arguments=args_dict)
        tool_message = ToolMessage(
            tool_name="get_weather",
            tool_data=weather_args_model.model_dump()
        )

        def tool_call():
            tool_entry = self.tool_registry.get_tool('get_weather')
            tool_class = tool_entry["tool_class"]
            tool_instance = tool_class()
            tool_instance.execute(tool_message)

        self._run_tool_async(tool_call)
