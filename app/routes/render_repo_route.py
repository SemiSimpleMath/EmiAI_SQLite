# render_repo_route.py
import json
from flask import Blueprint, jsonify, current_app

from app.assistant.utils.time_utils import utc_to_local
from app.assistant.event_repository.event_repository import EventRepositoryManager

from collections import defaultdict
from datetime import datetime, timezone

render_repo_route_bp = Blueprint('render_repo_route', __name__)


@render_repo_route_bp.route('/render_repo_route', methods=['POST'])
def render_repo_route():
    """
    Fetch all repo data (calendar, scheduler, email, weather, todo_task, news)
    and format it properly for UI widget rendering.
    """
    print("At render_repo_route")
    try:
        event_repo = EventRepositoryManager()
        categories = ["calendar", "scheduler", "email", "weather", "todo_task", "news"]
        widget_data = []
        
        category_counts = {}
        errors = []

        for category in categories:
            try:
                events = event_repo.search_events(data_type=category)
                events = json.loads(events)  # Convert JSON string to dict
                
                # Filter out past calendar events
                if category == "calendar":
                    current_datetime_utc = datetime.now(timezone.utc)
                    filtered_events = []
                    for event in events:
                        event_data = event.get("data", {})
                        # Use END time to filter - keep events that haven't ended yet
                        end_val = event_data.get("end") or event_data.get("start")
                        
                        # Handle both string and dict formats for end time
                        # Dict format: {"dateTime": "...", "timeZone": "..."} or {"date": "..."}
                        # String format: "2025-12-12T10:00:00Z"
                        if isinstance(end_val, dict):
                            end_str = end_val.get("dateTime") or end_val.get("date")
                        else:
                            end_str = end_val
                        
                        if end_str:
                            try:
                                if isinstance(end_str, str):
                                    end_dt = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
                                    # Keep events that haven't ended yet
                                    if end_dt >= current_datetime_utc:
                                        filtered_events.append(event)
                                else:
                                    # If it's not a string, keep the event
                                    filtered_events.append(event)
                            except ValueError:
                                # If we can't parse the date, keep the event
                                filtered_events.append(event)
                        else:
                            filtered_events.append(event)
                    print(f"🗓️ Calendar: Filtered {len(events)} -> {len(filtered_events)} events (removed ended)")
                    events = filtered_events
                
                if category == "scheduler":
                    print(f"🔍 Scheduler: Loaded {len(events)} events before filtering")
                    #print("\n\n\n", events)
                    # Get current UTC time
                    current_datetime_utc = datetime.now(timezone.utc)

                    # Filter out past events before any processing
                    filtered_events = []
                    for event in events:
                        event_data = event.get("data", {})
                        occurrence_str = event_data.get("occurrence") or event_data.get("start_date")

                        if occurrence_str:
                            try:
                                occurrence_dt_utc = datetime.fromisoformat(occurrence_str).astimezone(timezone.utc)

                                # Only keep events that occur in the future
                                if occurrence_dt_utc >= current_datetime_utc:
                                    event['data']['occurrence'] = occurrence_str
                                    filtered_events.append(event)
                            except ValueError as e:
                                print(f"⚠️ Scheduler: Could not parse occurrence '{occurrence_str}': {e}")
                                continue

                    events = filtered_events  # Only pass valid events

                    events = summarize_repeating_events(events)

                for event in events:
                    data = event["data"]
                    if category in ["calendar", "scheduler", "email", "weather", "news"]:
                        payload = data.get("event_payload", {})
                        if "title" not in data and "title" in payload:
                            data["title"] = payload["title"]

                    widget_data.append({
                        "data": data,
                        "data_type": event["data_type"],
                    })
                
                category_counts[category] = len(events)
                
            except Exception as e:
                print(f"🛑 Error loading {category}: {e}")
                current_app.logger.error(f"Error loading {category}: {e}")
                errors.append(f"{category}: {str(e)}")
                category_counts[category] = 0

        if errors:
            current_app.logger.warning(f"render_repo_route had partial errors: {errors}")

        # Construct a UserMessage in the required format
        repo_message = {
            "widget_data": widget_data
        }
        
        # Return success even with partial errors, but include error info
        response = {'success': True, 'repo_data': repo_message}
        if errors:
            response['warnings'] = errors
        
        return jsonify(response), 200

    except Exception as e:
        current_app.logger.error(f"Error retrieving repo data: {e}")
        print(f"🛑 render_repo_route ERROR: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': f'Error retrieving repo data: {str(e)}'}), 500

def summarize_repeating_events(events: list) -> list:
    """
    Converts all event times to local time using utc_to_local, then:
      - For one-time events, includes them as is.
      - For repeating (interval) events, groups by the local day and event_id.
        For each group:
          - If the local date is today, only considers events after the current local time.
          - Otherwise, picks the event with the earliest occurrence.
    Finally, the returned events still have their UTC occurrence strings for the UI.
    """
    daily_events = defaultdict(list)
    skipped_events = []
    # Convert current time to local for proper comparisons
    current_datetime_local = utc_to_local(datetime.now(timezone.utc))

    # Bucket events by local day (and event_id for interval events)
    # print(events)
    for event in events:
        event_data = event.get("data", {})
        occurrence_str = event_data.get("occurrence")
        if not occurrence_str:
            print(f"Skipping event {event_data.get('event_id', 'unknown')} - No 'occurrence' found.")
            skipped_events.append(event)
            continue

        try:
            # Parse the original UTC occurrence
            occurrence_dt_utc = datetime.fromisoformat(occurrence_str).astimezone(timezone.utc)
            # Convert to local time using your utility function
            occurrence_dt_local = utc_to_local(occurrence_dt_utc)
            # Group key: for repeating events, group by (local date, event_id), else just local date
            event_type = event_data.get("event_type")
            if event_type == "interval":
                group_key = (occurrence_dt_local.date(), event_data.get("event_id"))
            else:
                group_key = (occurrence_dt_local.date(), None)
            daily_events[group_key].append((occurrence_dt_local, event))
        except ValueError as e:
            print(f"Skipping event {event_data.get('event_id', 'unknown')} due to date parsing error: {e}")
            skipped_events.append(event)

    summarized = []

    # Process each group (either a day for one-time events or (day, event_id) for repeating events)
    for group, events_in_group in sorted(daily_events.items(), key=lambda item: (item[0][0], item[0][1] or "")):
        # Determine the local date for filtering
        if isinstance(group, tuple):
            group_date = group[0]
        else:
            group_date = group

        repeating = []
        one_time = []
        for occurrence_dt_local, event in events_in_group:
            if event.get("data", {}).get("event_type") == "interval":
                repeating.append((occurrence_dt_local, event))
            else:
                one_time.append(event)

        # Always include one-time events
        summarized.extend(one_time)

        # For repeating events in this group, select the next occurrence
        if repeating:
            if group_date == current_datetime_local.date():
                # For today's events, only consider those after current local time
                valid = [(dt, ev) for dt, ev in repeating if dt > current_datetime_local]
            else:
                valid = repeating
            if valid:
                next_event = min(valid, key=lambda x: x[0])[1]
                summarized.append(next_event)

    print(f"Summarized {len(summarized)} events. Skipped {len(skipped_events)} events.")
    return summarized

events_debug = []

def test_summarize_repeating_events(events: list) -> list:
    """
    Converts all event times to local time using utc_to_local, then:
      - For one-time events, includes them as is.
      - For repeating (interval) events, groups by the local day and event_id.
        For each group:
          - If the local date is today, only considers events after the current local time.
          - Otherwise, picks the event with the earliest occurrence.
    Finally, the returned events still have their UTC occurrence strings for the UI.
    """
    daily_events = defaultdict(list)
    skipped_events = []
    # Convert current time to local for proper comparisons
    current_datetime_local = utc_to_local(datetime.now(timezone.utc))
    print("Current local datetime:", current_datetime_local)

    # Bucket events by local day (and event_id for interval events)
    for event in events:
        event_data = event.get("data", {})
        occurrence_str = event_data.get("occurrence")
        if not occurrence_str:
            print(f"Skipping event {event_data.get('event_id', 'unknown')} - No 'occurrence' found.")
            skipped_events.append(event)
            continue

        try:
            # Parse the original UTC occurrence
            occurrence_dt_utc = datetime.fromisoformat(occurrence_str).astimezone(timezone.utc)
            # Convert to local time using your utility function
            occurrence_dt_local = utc_to_local(occurrence_dt_utc)
            # Group key: for repeating events, group by (local date, event_id), else just local date
            event_type = event_data.get("event_type")
            if event_type == "interval":
                group_key = (occurrence_dt_local.date(), event_data.get("event_id"))
            else:
                group_key = occurrence_dt_local.date()
            daily_events[group_key].append((occurrence_dt_local, event))
        except ValueError as e:
            print(f"Skipping event {event_data.get('event_id', 'unknown')} due to date parsing error: {e}")
            skipped_events.append(event)

    summarized = []

    # Process each group (either a day for one-time events or (day, event_id) for repeating events)
    for group, events_in_group in sorted(daily_events.items()):
        # Determine the local date for filtering
        if isinstance(group, tuple):
            group_date = group[0]
        else:
            group_date = group

        repeating = []
        one_time = []
        for occurrence_dt_local, event in events_in_group:
            if event.get("data", {}).get("event_type") == "interval":
                repeating.append((occurrence_dt_local, event))
            else:
                one_time.append(event)

        # Always include one-time events
        summarized.extend(one_time)

        # For repeating events in this group, select the next occurrence
        if repeating:
            if group_date == current_datetime_local.date():
                # For today's events, only consider those after current local time
                valid = [(dt, ev) for dt, ev in repeating if dt > current_datetime_local]
            else:
                valid = repeating
            if valid:
                next_event = min(valid, key=lambda x: x[0])[1]
                summarized.append(next_event)

    print(f"Summarized {len(summarized)} events. Skipped {len(skipped_events)} events.")
    return summarized

if __name__ == "__main__":


    # Call the summarizer and pretty-print the result
    summarized_events = summarize_repeating_events(events_debug)
    print("\nSummarized Events:")
    print(json.dumps(summarized_events, indent=2))
