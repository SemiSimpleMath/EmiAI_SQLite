# calendar_tools.py
from datetime import datetime, timezone

from app.assistant.lib.core_tools.base_tool.base_tool import BaseTool
from app.assistant.utils.pydantic_classes import ToolMessage, ToolResult, Message
from app.assistant.utils.time_utils import parse_time_string, normalize_google_event_times, get_local_timezone
from app.assistant.lib.core_tools.calendar_tool.utils.google_calendar import (
    authenticate_google_api,
    create_event,
    create_repeating_event,
    get_events,
    search_event_by_name,
    edit_event,
    delete_event,
)

from app.assistant.ServiceLocator.service_locator import DI

from app.assistant.utils.time_utils import local_to_utc, utc_to_local
from typing import Any, Dict, Optional
from pathlib import Path

# Import the repository manager class
from app.assistant.event_repository.event_repository import EventRepositoryManager

# Setup Logging
from app.assistant.utils.logging_config import get_logger

logger = get_logger(__name__)

# Define Valid RRULE Parameters
VALID_FREQ = {"DAILY", "WEEKLY", "MONTHLY", "YEARLY"}
VALID_BYDAY = {"MO", "TU", "WE", "TH", "FR", "SA", "SU"}


def format_rrule(freq: str, start: str, byday: Optional[str] = None, until: Optional[str] = None) -> str:
    """
    Formats an RRULE string using UTC for the UNTIL parameter and ensures DTSTART is included.
    """
    freq = freq.upper()
    if freq not in VALID_FREQ:
        raise ValueError(f"Invalid FREQ value: {freq}. Must be one of {VALID_FREQ}.")

    rrule = f"RRULE:FREQ={freq}"

    if byday:
        days = [day.strip().upper() for day in byday.split(',')]
        invalid_days = [day for day in days if day not in VALID_BYDAY]
        if invalid_days:
            raise ValueError(f"Invalid BYDAY value(s): {', '.join(invalid_days)}. Must be among {VALID_BYDAY}.")
        rrule += f";BYDAY={','.join(days)}"

    if until:
        # Parse using the existing helper and then force UTC conversion
        parsed_until = parse_time_string(until)
        if not parsed_until:
            raise ValueError(f"Invalid UNTIL date format: {until}")
        from datetime import timezone as dt_timezone
        until_utc = parsed_until.astimezone(dt_timezone.utc)
        formatted_until = until_utc.strftime('%Y%m%dT%H%M%SZ')
        rrule += f";UNTIL={formatted_until}"
        logger.debug(f"Formatted UNTIL: {formatted_until}")

    logger.debug(f"Final RRULE: {rrule}")
    return rrule


class CalendarTool(BaseTool):
    """
    Tool to interact with Google Calendar for creating, fetching, updating, and deleting events.
    Also synchronizes events with the local repository.
    """

    def __init__(self):
        super().__init__('calendar_tool')
        self.service = None
        # Initialize the repository manager
        self.repo_manager = EventRepositoryManager()

    def init_credentials(self):
        if self.service is None:  # Only authenticate if not already initialized

            PROJECT_ROOT = Path(__file__).resolve().parents[2]

            credentials_path = PROJECT_ROOT / "credentials" / "credentials.json"
            token_path = PROJECT_ROOT / "credentials" / "token.pickle"

            self.service = authenticate_google_api(str(token_path), str(credentials_path))

    def execute(self, tool_message: 'ToolMessage') -> ToolMessage:
        """
        Initializes credentials, converts incoming time fields to UTC,
        and then dispatches the tool message to the appropriate handler.
        """

        self.init_credentials()
        request_id = tool_message.request_id

        logger.debug(f"Received tool_message: {tool_message}")
        try:
            logger.info("Starting CalendarTool execution.")
            arguments = tool_message.tool_data.get('arguments', {})
            tool_name = tool_message.tool_data.get('tool_name')

            if not tool_name:
                raise ValueError("No tool_name specified.")

            # Convert time fields from local to UTC using the global local timezone.
            # Keys that likely represent time values.
            for key in ['start', 'end', 'start_date', 'end_date']:
                if key in arguments and arguments[key]:
                    # local_to_utc uses the global config for local timezone.
                    original = arguments[key]
                    # Convert to UTC and format as RFC3339 with 'Z' suffix
                    utc_dt = local_to_utc(arguments[key])
                    arguments[key] = utc_dt.isoformat().replace('+00:00', 'Z')
                    logger.debug(f"Converted {key}: {original} -> {arguments[key]}")

            handler_method = getattr(self, f"handle_{tool_name}", None)
            if not handler_method:
                raise ValueError(f"Unsupported tool_name '{tool_name}'.")

            tool_result = handler_method(arguments)
            if request_id:
                self.publish_result(tool_message, tool_result, request_id)
            else:
                return tool_result

        except Exception as e:
            logger.exception(f"Error in CalendarTool: {e}")
            return self.publish_error(tool_message, str(e), request_id)

    def publish_result(self, tool_message: 'ToolMessage', tool_result: Any, request_id: str) -> ToolMessage:
        tool_name = tool_message.tool_data.get('tool_name')
        result_msg = ToolMessage(
            data_type='tool_result',
            sender='CalendarTool',
            receiver=tool_message.sender,
            task=tool_message.task,
            tool_name=tool_name,
            tool_data=tool_message.tool_data,
            tool_result=tool_result,
            group_id=tool_message.group_id,
            request_id=request_id
        )

        return result_msg

    def publish_error(self, tool_message: 'ToolMessage', error_message: str, request_id: str) -> ToolMessage:
        tool_name = tool_message.tool_data.get('tool_name')
        error_result = ToolResult(result_type="error", content=error_message)
        result_msg = ToolMessage(
            data_type='tool_result',
            sender='CalendarTool',
            receiver=tool_message.sender,
            task=tool_message.task,
            tool_name=tool_name,
            tool_data=tool_message.tool_data,
            tool_result=error_result,
            group_id=tool_message.group_id,
            request_id=request_id
        )

        return result_msg

    def handle_create_calendar_event(self, arguments: Dict[str, Any]) -> ToolResult:
        """
        Creates a single calendar event and writes it to the repository.
        Expects 'start' and 'end' in local time; they are already converted to UTC.
        """
        try:
            event_name = arguments.get('event_name')
            start = arguments.get('start')
            end = arguments.get('end')
            description = arguments.get('description')
            location = arguments.get('location')
            link = arguments.get('link')
            participants = arguments.get('participants')

            time_zone = "UTC"
            calendar_name = arguments.get('calendar_name', 'primary')

            # Build attendees list from participants
            attendees = []
            if isinstance(participants, list):
                for p in participants:
                    email = p.get('email')
                    name = p.get('name') or p.get('displayName') or ""
                    if email:
                        attendee = {'email': email}
                        if name:
                            attendee['displayName'] = name
                        attendees.append(attendee)

            event = create_event(self.service, {
                'event_name': event_name,
                'start': start,
                'end': end,
                'time_zone': time_zone,
                'description': description,
                'location': location,
                'link': link,
                'participants': attendees,
            })
            event_id = event.get('id')
            if not event:
                return ToolResult(result_type="error", content="Error, event not created.")

            self.repo_manager.store_event(event_id, event_data=event, data_type="calendar")

            repo_msg = Message(
                data_type="repo_update",
                sender="CalenderTool",
                receiver=None,
                data={
                    "data_type": "calendar_task",
                    "action": "create",
                    "entity_id": event_id
                }
            )
            event_hub = DI.event_hub
            repo_msg.event_topic = 'repo_update'
            event_hub.publish(repo_msg)

            return ToolResult(result_type="success", content="Event created successfully")
        except Exception as e:
            logger.error(f"Failed to handle_create_calendar_event: {e}")
            return ToolResult(result_type="error", content=f"Error, event not created. {e}")

    def handle_create_repeating_calendar_event(self, arguments: Dict[str, Any]) -> ToolResult:
        """
        Creates a repeating calendar event and writes it to the repository.
        Expects 'start' and 'end' in local time; they are already converted to UTC.
        """
        try:
            logger.debug(f"Input Arguments: {arguments}")
            event_name = arguments.get('event_name')
            start = arguments.get('start')
            end = arguments.get('end')
            calendar_name = arguments.get('calendar_name', 'primary')
            recurrence_rule_input = arguments.get('recurrence_rule')
            time_zone = "UTC"
            description = arguments.get('description')
            location = arguments.get('location')
            link = arguments.get('link')
            participants = arguments.get('participants')

            if not all([event_name, start, end, recurrence_rule_input]):
                raise ValueError("Missing required fields for creating a repeating event.")

            # strip leading "RRULE:" if present
            if recurrence_rule_input.upper().startswith("RRULE:"):
                recurrence_rule_input = recurrence_rule_input[6:]

            # parse and re‑format RRULE
            parts = dict(item.split('=') for item in recurrence_rule_input.split(';'))
            freq = parts.get('FREQ')
            if not freq:
                raise ValueError("RRULE must include a 'FREQ' parameter.")
            formatted_rrule = format_rrule(
                freq=freq,
                start=start,
                byday=parts.get('BYDAY'),
                until=parts.get('UNTIL')
            )

            # build attendees list from your list of dicts
            attendees = []
            if isinstance(participants, list):
                for p in participants:
                    email = p.get('email')
                    name = p.get('name') or ""
                    if email:
                        attendees.append({
                            "email": email,
                            "displayName": name
                        })

            event_dict = {
                "event_name": event_name,
                "start": start,
                "end": end,
                "time_zone": time_zone,
                "recurrence_rule": formatted_rrule,
                "description": description,
                "location": location,
                "link": link,
                "participants": attendees,
            }
            logger.debug(f"Prepared Event Dictionary: {event_dict}")

            event = create_repeating_event(self.service, event_dict)
            if not event:
                raise ValueError("Failed to create the repeating event.")

            event_id = event.get('id')
            self.repo_manager.store_event(event_id, event_data=event, data_type="calendar")

            repo_msg = Message(
                data_type="repo_update",
                sender="CalendarTool",
                receiver=None,
                data={
                    "data_type": "calendar_task",
                    "action": "create_repeating",
                    "entity_id": event_id
                }
            )
            repo_msg.event_topic = 'repo_update'
            DI.event_hub.publish(repo_msg)

            return ToolResult(result_type="success", content="Repeating event created successfully")

        except Exception as e:
            logger.error(f"Failed to handle_create_repeating_calendar_event: {e}")
            return ToolResult(
                result_type="error",
                content=f"Error, event not created. {e}"
            )

    def handle_get_calendar_events(self, arguments: Dict[str, Any]) -> ToolResult:
        """
        Fetches events and optionally syncs them into the repository.

        Expects:
          - start_date, end_date: already converted to UTC ISO by execute()
          - calendar_names: optional list of calendar names
          - single_events: whether to expand recurring instances
          - repo_update: if True, update EventRepository (used by scheduler)
                         if False, read only (used by agents)
        """
        max_results = arguments.get("max_results", 100)
        start_iso = arguments.get("start_date")
        end_iso = arguments.get("end_date")
        calendar_names = arguments.get("calendar_names")
        single_events = arguments.get("single_events", True)

        # New unified flag; keep backward compatibility with old sync_to_repo
        repo_update = arguments.get("repo_update", arguments.get("sync_to_repo", False))

        if not start_iso or not end_iso:
            raise ValueError("Both 'start_date' and 'end_date' are required for fetching events.")

        logger.info(
            f"Fetching calendar events from {start_iso} to {end_iso} "
            f"max_results={max_results}, repo_update={repo_update}"
        )

        # If no specific calendar_names, resolve all calendars
        calendar_ids = None
        if not calendar_names:
            all_calendar_ids = []
            page_token = None
            while True:
                resp = self.service.calendarList().list(pageToken=page_token).execute()
                all_calendar_ids += [cal["id"] for cal in resp.get("items", [])]
                page_token = resp.get("nextPageToken")
                if not page_token:
                    break
            calendar_ids = all_calendar_ids

        events = get_events(
            service=self.service,
            start_str=start_iso,
            end_str=end_iso,
            calendar_names=calendar_names,
            calendar_ids=calendar_ids,
            max_results=max_results,
            single_events=single_events,
        )

        if events is None:
            logger.info("No events found in the specified time range.")
            events = []

        server_ids = set()
        result_events = []

        for event in events:
            event_id = event.get("id")
            is_recurring = "recurringEventId" in event
            recurring_event_id = event.get("recurringEventId")
            recurrence_rule = event.get("recurrence")

            # For recurring instances, try to pull recurrence from parent
            if is_recurring and recurring_event_id and not recurrence_rule:
                try:
                    parent_event = self.service.events().get(
                        calendarId="primary", eventId=recurring_event_id
                    ).execute()
                    recurrence_rule = parent_event.get("recurrence")
                except Exception as e:
                    logger.warning(
                        f"Failed to retrieve parent event {recurring_event_id}: {e}"
                    )

            start_utc, end_utc = normalize_start_end(event)

            parsed_event = {
                "id": event_id,
                "summary": event.get("summary", "No Title"),
                "description": event.get("description", ""),
                "start": start_utc,
                "end": end_utc,
                "link": event.get("htmlLink"),
                "is_recurring": is_recurring,
                "recurring_event_id": recurring_event_id,
                "recurrence_rule": recurrence_rule,
                "participants": [
                    {
                        "email": attendee.get("email"),
                        "response_status": attendee.get("responseStatus"),
                    }
                    for attendee in event.get("attendees", [])
                ],
                "data_type": "calendar",
            }

            result_events.append(parsed_event)
            server_ids.add(event_id)

            if repo_update:
                self.repo_manager.store_event(
                    event_id,
                    event_data=parsed_event,
                    data_type="calendar",
                )

        if repo_update:
            # Enforce stable 7 day window: repo will match current fetch set
            self.repo_manager.sync_events_with_server(list(server_ids), "calendar")

        return ToolResult(
            result_type="calendar_events",
            content="",
            data_list=result_events,
        )


    def handle_search_event(self, arguments: Dict[str, Any]) -> ToolResult:
        try:
            query = arguments.get('query')
            if not query:
                raise ValueError("Missing 'query' parameter for searching events.")

            events = search_event_by_name(self.service, query)
            result_events = []
            for event in events:
                event.update({'data_type': 'calendar'})
                result_events.append(event)
            return ToolResult(result_type="calendar", data_list=result_events)
        except Exception as e:
            logger.error(f"Failed to handle_search_event: {e}")
            return ToolResult(result_type="error", content=f"Error, event search failed. {e}")

    def handle_update_calendar_event(self, arguments: Dict[str, Any]) -> ToolResult:
        try:
            # Filter out empty values
            arguments = {k: v for k, v in arguments.items() if v not in (None, "")}
            event_id = arguments.get("event_id")
            if not event_id:
                raise ValueError("Missing 'event_id' for updating event.")

            # Convert times to local timezone (e.g., PST) using utc_to_local
            local_tz = get_local_timezone().key  # Should be 'America/Los_Angeles'
            for key in ["start", "end"]:
                if key in arguments:
                    original = arguments[key]
                    # Assuming original is an ISO time string, e.g., "2025-07-02T08:00:00Z"
                    converted = utc_to_local(original)
                    arguments[key] = {"dateTime": converted, "timeZone": local_tz}
                    logger.debug(f"Updated {key} for event update: {original} -> {arguments[key]}")

            # Ensure recurrence rule is explicitly replaced
            if "recurrence" in arguments:
                if not isinstance(arguments["recurrence"], list):
                    arguments["recurrence"] = [arguments["recurrence"]]

            # Call the edit_event function
            updated_event = edit_event(self.service, event_id, arguments)
            if not updated_event:
                raise ValueError("Failed to update the event.")

            # Normalize times from Google before storing

            updated_event = normalize_google_event_times(updated_event)

            repo_msg = Message(
                data_type="repo_update",
                sender="CalenderTool",
                receiver=None,
                data={
                    "data_type": "calendar_task",
                    "action": "update",
                    "entity_id": event_id
                }
            )
            event_hub = DI.event_hub
            repo_msg.event_topic = 'repo_update'
            event_hub.publish(repo_msg)

            self.repo_manager.store_event(event_id, event_data=updated_event, data_type="calendar")

            return ToolResult(result_type="success", content=f"Event {event_id} updated successfully")
        except Exception as e:
            logger.error(f"Failed to handle_update_calendar_event: {e}")
            return ToolResult(result_type="error", content=f"Error, event not updated. {e}")

    def handle_delete_calendar_event(self, arguments: Dict[str, Any]) -> ToolResult:
        """
        Deletes an event from Google Calendar and removes it from the repository.
        """
        try:
            event_id = arguments.get('event_id')
            if not event_id:
                raise ValueError("Missing 'event_id' for deleting event.")

            success = delete_event(self.service, event_id)
            if not success:
                raise ValueError("Failed to delete the event.")

            repo_msg = Message(
                data_type="repo_update",
                sender="CalenderTool",
                receiver=None,
                data={
                    "data_type": "calendar_task",
                    "action": "delete",
                    "entity_id": event_id
                }
            )
            event_hub = DI.event_hub
            repo_msg.event_topic = 'repo_update'
            event_hub.publish(repo_msg)

            self.repo_manager.delete_event(event_id, data_type="calendar")

            return ToolResult(result_type="success", content="Event deleted successfully.")
        except Exception as e:
            logger.error(f"Failed to handle_delete_event: {e}")
            return ToolResult(result_type="error", content=f"Error, event not deleted. {e}")


def normalize_start_end(event: dict, calendar_timezone: str = None) -> (str, str):
    """
    Normalize event start and end into UTC ISO strings.

    If calendar_timezone is provided, it will be used for interpreting all-day events.
    Otherwise, falls back to system local timezone.
    """
    start_info = event.get("start", {})
    end_info = event.get("end", {})

    tzinfo = get_local_timezone()
    if calendar_timezone:
        try:
            from zoneinfo import ZoneInfo
            tzinfo = ZoneInfo(calendar_timezone)
        except Exception:
            pass  # fallback to system local timezone if calendar_timezone is invalid

    def convert(field_info):
        if 'dateTime' in field_info:
            return parse_time_string(field_info['dateTime'])  # already tz-aware
        elif 'date' in field_info:
            local_midnight = datetime.strptime(field_info['date'], "%Y-%m-%d")
            local_midnight = local_midnight.replace(tzinfo=tzinfo)
            return local_midnight.astimezone(timezone.utc)
        else:
            return None

    start_dt = convert(start_info)
    end_dt = convert(end_info)

    return (
        start_dt.isoformat() if start_dt else None,
        end_dt.isoformat() if end_dt else None,
    )
