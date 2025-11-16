import json
from datetime import datetime
from typing import Dict

from app.assistant.utils.pydantic_classes import ToolResult

from app.assistant.utils.time_utils import utc_to_local

from app.assistant.utils.logging_config import get_logger
logger = get_logger(__name__)

class DataConversionModule:
    def __init__(self):
        return

    @staticmethod
    def convert(tool_result: ToolResult, level: str = "summary") -> Dict:
        """
        Converts tool result into a summarized form.
        Uses a mapping to route to the correct conversion function.
        """
        result_type = tool_result.result_type
        print("At convert function")
        conversion_methods = {
            "fetch_email": DataConversionModule._convert_email,
            "search_result": DataConversionModule._convert_search,
            "send_email": DataConversionModule._convert_send_email,
            "search1": DataConversionModule._convert_search1,
            "scrape": DataConversionModule._convert_scrape,
            "calendar_events": DataConversionModule._convert_calendar,
            "scheduler_events": DataConversionModule._convert_scheduler_events,
            "todo_tasks": DataConversionModule._convert_todo_tasks,
            "weather": DataConversionModule._convert_weather,
            "news": DataConversionModule._convert_news,
            "final_answer": DataConversionModule._convert_final_answer,
            "node_description": DataConversionModule._convert_node_description,
            "search_web": DataConversionModule._convert_search_web,
            "taxonomy_paths": DataConversionModule._convert_taxonomy_paths
        }
        if result_type in conversion_methods:
            return conversion_methods[result_type](tool_result, level)
        else:
            # Fallback for unknown result types: convert everything to readable string
            result_data = {
                "result_type": result_type,
                "content": tool_result.content if tool_result.content else "No content"
            }
            
            # Add data_list if present
            if tool_result.data_list:
                result_data["data"] = tool_result.data_list
            
            # Add data if present
            if tool_result.data:
                result_data["data"] = tool_result.data
            
            # Convert to a readable string for the planner
            readable_output = f"Tool '{result_type}' returned:\n{json.dumps(result_data, indent=2, default=str)}"
            
            return {"tool_result": readable_output}

    @staticmethod
    def _convert_email(tool_result: ToolResult, level: str, importance_threshold: int = 5) -> Dict:
        emails = tool_result.data_list
        formatted_emails = []

        for email in emails:
            importance = email.get("importance", 0)
            if importance < importance_threshold:
                continue  # Skip emails below threshold

            email_details = {
                "uid": email.get("uid", "No UID"),
                "subject": email.get("subject", "[No Subject]"),
                "sender": email.get("sender", "[Unknown Sender]"),
                "email_address": email.get("email_address", "[unknown@example.com]"),
                "date": email.get("date", "[No Date]"),
                "snippet": email.get("snippet", ""),
                "summary": email.get("summary", "[No Summary]"),
                "action_items": email.get("action_items", []),
                "importance": importance,
                "has_attachment": email.get("has_attachment", False),
            }
            if level == "full":
                email_details["body"] = email.get("body", "[No Content]")

            formatted_emails.append(email_details)

        if level == "full":
            return {"emails": formatted_emails}
        elif level == "summary":
            email_summaries = [
                {
                    "uid": e["uid"],
                    "subject": e["subject"],
                    "sender": e["sender"],
                    "date": e["date"],
                    "summary": e["summary"],
                }
                for e in formatted_emails
            ]
            return {"emails": email_summaries}
        elif level == "minimal":
            minimal_emails = [
                {"uid": e["uid"], "subject": e["subject"], "date": e["date"]}
                for e in formatted_emails
            ]
            return {"emails": minimal_emails}

        return {}




    @staticmethod
    def _convert_calendar(tool_result: ToolResult, level: str) -> Dict:
        events = tool_result.data_list

        logger.debug("Raw tool_result.data_list:")
        for event_obj in events:
            logger.debug(event_obj)  # Log the full event structure

        formatted_events = []

        for event_obj in events:
            event_id = event_obj.get("id", "No ID")
            title = event_obj.get("summary", "No Title")

            # Convert UTC to local time
            start_utc = event_obj.get("start")
            end_utc = event_obj.get("end")
            start_local = utc_to_local(start_utc).isoformat() if start_utc else None
            end_local = utc_to_local(end_utc).isoformat() if end_utc else None

            # Extract recurrence rule properly
            recurrence_list = event_obj.get("recurrence_rule", [])
            recurrence_rule = " ".join(recurrence_list) if recurrence_list else "Not a recurring event"

            # Build base event details
            event_details = {
                "event_id": event_id,
                "title": title,
                "start": start_local,  # Now in local time
                "end": end_local,  # Now in local time
                "recurrence_rule": recurrence_rule,
            }

            # Add extra fields for 'full' level
            if level == "full":
                event_details.update({
                    "description": event_obj.get("description", ""),
                    "attendees": event_obj.get("participants", []),
                    "link": event_obj.get("link"),
                })

            # Add extra fields for 'summary' only if they are non-empty
            elif level == "summary":
                if event_obj.get("description"):
                    event_details["description"] = event_obj["description"]
                if event_obj.get("participants"):
                    event_details["attendees"] = event_obj["participants"]

            formatted_events.append(event_details)

        if level == "full":
            return {"events": formatted_events}
        elif level == "summary":
            return {"events": formatted_events}  # Includes only non-empty fields
        elif level == "minimal":
            minimal_events = [{"event_id": e["event_id"], "title": e["title"]} for e in formatted_events]
            return {"events": minimal_events}

        return {}


    @staticmethod
    def _convert_scheduler_events(tool_result: ToolResult, level: str) -> Dict:
        events = tool_result.data_list

        # Group events by original_event_id to identify duplicates
        grouped_events = {}
        for event in events:
            original_event_id = event.get("original_event_id", event.get("event_id", "No ID"))
            occurrence = event.get("occurrence") or event.get("event_payload", {}).get("occurrence")

            if occurrence:
                try:
                    occurrence_dt = datetime.fromisoformat(occurrence)
                except ValueError:
                    occurrence_dt = None

                if original_event_id not in grouped_events or \
                        (occurrence_dt and occurrence_dt < grouped_events[original_event_id]["occurrence_dt"]):
                    grouped_events[original_event_id] = {**event, "occurrence_dt": occurrence_dt}
            else:
                # No occurrence, assume it's a one-time event
                if original_event_id not in grouped_events:
                    grouped_events[original_event_id] = {**event, "occurrence_dt": None}

        # Format the collapsed events
        formatted_events = []
        summary_events = []
        minimal_events = []
        for event in grouped_events.values():
            original_event_id = event.get("original_event_id") or event.get("event_id", "No ID")
            event_id = original_event_id
            event_type = event.get("event_type", "unknown")
            start_date = event.get("start_date")
            end_date = event.get("end_date")
            occurrence = event.get("occurrence")
            interval = event.get("interval")
            payload = event.get("event_payload", {})
            title = event.get("title") or payload.get("title")
            task_type = event.get("task_type") or payload.get("task_type")
            importance = event.get("importance") or payload.get("importance")
            sound = event.get("sound") or payload.get("sound")
            event_payload = payload.get("payload_message", "")


            event_details = {
                "event_id": event_id,
                "title": title,
                "event_type": event_type,
                "start_date": start_date,
                "end_date": end_date,
                "occurrence": occurrence,
                "task_type": task_type,
                "interval": interval,
                "importance": importance,
                "sound": sound,
                "payload": event_payload,
            }
            formatted_events.append(event_details)

        # Return based on level of detail requested
        if level == "full":
            return {"events": formatted_events}

        elif level == "summary":
            for event in formatted_events:

                event_details = {
                    key: value for key, value in {
                        "event_id": event.get("event_id"),
                        "title": event.get("title"),
                        "event_type": event.get("event_type"),
                        "start_date": event.get("start_date"),
                        "end_date": event.get("end_date"),
                        "interval": f"{event.get('interval')} seconds",
                        "payload": event.get("payload"),
                    }.items() if value is not None
                }
                summary_events.append(event_details)
            return {"events": summary_events}


        elif level == "minimal":
            for event in formatted_events:
                allowed_keys = {"event_id", "event_title", "event_type", "start_date", "interval"}

                event_details = {
                    key: value for key, value in {
                        "event_id": event.get("event_id"),
                        "title": event.get("title"),
                        "event_type": event.get("event_type"),
                        "start_date": event.get("start_date"),
                    }.items() if value is not None and key in allowed_keys
                }
                minimal_events.append(event_details)
            return {"events": minimal_events}
        return {}


    @staticmethod
    def _convert_search(tool_result: ToolResult, level: str) -> Dict:
        results = tool_result.data_list
        links = getattr(tool_result, "links", {})
        if level == "full":
            return {"results": results, "links": links}
        elif level == "summary":
            top_link = list(links.keys())[0] if links else None
            return {"top_link": top_link}
        elif level == "minimal":
            return {"count": len(results)}
        return {}

    @staticmethod
    def _convert_send_email(tool_result: ToolResult, level: str) -> Dict:
        content = tool_result.content
        result = {
            "content": content,
        }
        if level == "full":
            return result
        elif level == "summary":
            return result
        elif level == "minimal":
            return result
        return {}

    @staticmethod
    def _convert_search1(tool_result: ToolResult, level: str) -> Dict:
        search_items = tool_result.data_list or []
        detailed_items = []
        for index, item in enumerate(search_items, start=1):
            summary_text = item.get("description", "No summary provided.")
            link = item.get("link", "No link provided.")
            item_details = {"description": summary_text, "link": link}
            if link != "No link provided.":
                item_details["link_details"] = f"Link: {link}"
            detailed_items.append(item_details)
        if level == "full":
            return {"results": detailed_items}
        elif level == "summary":
            return {"results": detailed_items}
        elif level == "minimal":
            return {"count": len(search_items)}
        return {}

    @staticmethod
    def _convert_scrape(tool_result: ToolResult, level: str) -> Dict:
        scraped_content = tool_result.content
        data_list = tool_result.data_list[:]  # copy the list
        found_links = []
        if data_list:
            # Assume the first item is metadata and skip it.
            for link_item in data_list[1:]:
                for link_url, link_sum in link_item.items():
                    found_links.append({"link": link_url, "description": link_sum})
        if level == "full":
            return {"found_links": found_links, "scraped_content": scraped_content}
        elif level == "summary":
            return {"scraped_content": scraped_content, "links": found_links}
        elif level == "minimal":
            return {"content": scraped_content}
        return {}

    @staticmethod
    def _convert_todo_tasks(tool_result: ToolResult, level: str) -> Dict:
        tasks = tool_result.data_list
        task_details = "TODO Tasks:\n"
        for idx, task in enumerate(tasks, start=1):
            try:
                task_id = task.get("id", "N/A")
                title = task.get("title", "Untitled")
                due = task.get("due")
                notes = task.get("notes", "")
                status = task.get("status", "No status")
                tasklist_name = task.get("tasklist_title", "Unknown")
                if due:
                    try:
                        due_datetime = datetime.fromisoformat(due.replace("Z", "+00:00"))
                        due_date = due_datetime.strftime("%Y-%m-%d")
                    except Exception:
                        due_date = "Invalid date"
                else:
                    due_date = "No due date"
                task_details += (
                    f"Task {idx}:\n"
                    f"  - ID: {task_id}\n"
                    f"  - Title: {title}\n"
                    f"  - Due Date: {due_date}\n"
                    f"  - Status: {status}\n"
                    f"  - Notes: {notes if notes else 'No notes'}\n"
                    f"  - Task List: {tasklist_name}\n"
                )
            except Exception as e:
                task_details += f"Error processing task {idx}: {e}\n"
        if level == "full":
            return {"tasks": tasks, "details": task_details}
        elif level == "summary":
            return {"details": task_details}
        elif level == "minimal":
            return {"count": len(tasks)}
        return {}

    @staticmethod
    def _convert_weather(tool_result: ToolResult, level: str) -> Dict:
        if level == "full":
            return {"weather": tool_result.content, "details": tool_result.data_list}
        elif level == "summary":
            return {"weather": tool_result.content}
        elif level == "minimal":
            return {"weather": tool_result.content}
        return {}

    @staticmethod
    def _convert_news(tool_result: ToolResult, level: str) -> Dict:
        if level == "full":
            return {"news": tool_result.content, "articles": tool_result.data_list}
        elif level == "summary":
            return {"news": tool_result.content}
        elif level == "minimal":
            return {"count": len(tool_result.data_list)}
        return {}

    @staticmethod
    def _convert_success(tool_result: ToolResult, level: str) -> Dict:
        content = tool_result.content
        if level in ("full", "summary"):
            return {"success": True, "content": content}
        elif level == "minimal":
            return {"success": True}
        return {}

    @staticmethod
    def _convert_error(tool_result: ToolResult, level: str) -> Dict:
        content = tool_result.content
        if level in ("full", "summary"):
            return {"error": True, "content": content}
        elif level == "minimal":
            return {"error": True}
        return {}

    @staticmethod
    def _convert_final_answer(tool_result: ToolResult, level: str) -> Dict:
        data_list = tool_result.data_list
        content = tool_result.content
        if data_list:
            content += "\n" + json.dumps(data_list, indent=4)
        if level in ("full", "summary"):
            return {"final_answer": content}
        elif level == "minimal":
            return {"final_answer": content}
        return {}

    @staticmethod
    def _convert_ask_user_response(tool_result: ToolResult, level: str) -> Dict:
        user_response = tool_result.content
        if level in ("full", "summary"):
            return {"user_response": f"User responded with: {user_response}"}
        elif level == "minimal":
            return {"user_response": user_response}
        return {}

    @staticmethod
    def _convert_tool_success(tool_result: ToolResult, level: str) -> Dict:
        content = tool_result.content
        if level in ("full", "summary"):
            return {"tool_success": content}
        elif level == "minimal":
            return {"tool_success": content[:50]}
        return {}

    @staticmethod
    def _convert_tool_failure(tool_result: ToolResult, level: str) -> Dict:
        content = tool_result.content
        if level in ("full", "summary"):
            return {"tool_failure": content}
        elif level == "minimal":
            return {"tool_failure": content[:50]}
        return {}

    @staticmethod
    def _convert_search_web(tool_result: ToolResult, level: str) -> Dict:
        """
        Convert search_web tool results into a formatted summary.
        Includes both the content from web_parser and any links.
        """
        content = tool_result.content or "No content returned"
        links = tool_result.data_list or []
        
        if level in ("full", "summary"):
            result = {"search_results": content}
            if links:
                result["sources"] = [
                    {"url": link.get('url', 'N/A'), "summary": link.get('summary', 'N/A')}
                    for link in links
                ]
            return result
        elif level == "minimal":
            return {"search_results": content[:200] + "..." if len(content) > 200 else content}
        return {}
    
    @staticmethod
    def _convert_node_description(tool_result: ToolResult, level: str) -> Dict:
        """
        Convert kg_describe_node results into a compact, agent-readable format.
        The tool already formats data as clean JSON, so just return it as-is.
        """
        if not tool_result.data:
            return {"node_description": "No node data available"}
        
        # Return the data as-is since kg_describe_node already formats it nicely
        return {"node_data": tool_result.data}
        
        # Old formatting code (kept for reference but not used)
        data = tool_result.data
        lines = []
        
        # Node header with core info
        lines.append(f"Node: {data['label']} ({data['node_type']})")
        lines.append(f"ID: {data['id']}")
        
        # Add warning if present
        if data.get('warning'):
            lines.append(f"WARNING: {data['warning']}")
        
        # Add description if present
        if data.get('description'):
            lines.append(f"Description: {data['description']}")
        
        # Add aliases if present
        if data.get('aliases'):
            aliases_str = ", ".join(data['aliases'])
            lines.append(f"Aliases: {aliases_str}")
        
        # Add temporal info if present
        if data.get('start_date') or data.get('end_date'):
            date_parts = []
            if data.get('start_date'):
                date_parts.append(f"from {data['start_date']}")
            if data.get('end_date'):
                date_parts.append(f"to {data['end_date']}")
            if data.get('start_date_confidence') or data.get('end_date_confidence'):
                conf_parts = []
                if data.get('start_date_confidence'):
                    conf_parts.append(f"start: {data['start_date_confidence']}")
                if data.get('end_date_confidence'):
                    conf_parts.append(f"end: {data['end_date_confidence']}")
                date_parts.append(f"({', '.join(conf_parts)})")
            lines.append(f"Dates: {' '.join(date_parts)}")
        
        # Add attributes if present and not empty
        if data.get('attributes') and data['attributes']:
            lines.append(f"Attributes: {json.dumps(data['attributes'])}")
        
        # Add connections
        connections = []
        
        # Outbound connections (this node -> target node)
        for edge in data.get('outbound_edges', []):
            # New format uses target_node_label and relationship_type
            label = edge.get('target_node_label', edge.get('to_node_label', 'Unknown'))
            rel_type = edge.get('relationship_type', edge.get('edge_type', 'Unknown'))
            node_id = edge.get('target_node_id', edge.get('to_node_id', 'N/A'))
            
            conn = f"→ {label} ({rel_type})"
            if edge.get('sentence'):
                conn += f": \"{edge['sentence']}\""
            conn += f" [Node ID: {node_id}]"
            connections.append(conn)
        
        # Inbound connections (source node -> this node)
        for edge in data.get('inbound_edges', []):
            # New format uses source_node_label and relationship_type
            label = edge.get('source_node_label', edge.get('from_node_label', 'Unknown'))
            rel_type = edge.get('relationship_type', edge.get('edge_type', 'Unknown'))
            node_id = edge.get('source_node_id', edge.get('from_node_id', 'N/A'))
            
            conn = f"← {label} ({rel_type})"
            if edge.get('sentence'):
                conn += f": \"{edge['sentence']}\""
            conn += f" [Node ID: {node_id}]"
            connections.append(conn)
        
        if connections:
            lines.append("Connections:")
            lines.extend(f"  {conn}" for conn in connections)
        
        # Join all lines
        formatted_text = "\n".join(lines)
        
        if level in ("full", "summary"):
            return {"node_description": formatted_text}
        elif level == "minimal":
            # For minimal, just show core info and connection count
            minimal_lines = [
                f"Node: {data['label']} ({data['node_type']})",
                f"ID: {data['id']}"
            ]
            if data.get('description'):
                minimal_lines.append(f"Description: {data['description']}")
            
            total_connections = len(data.get('outbound_edges', [])) + len(data.get('inbound_edges', []))
            minimal_lines.append(f"Connections: {total_connections} total")
            
            return {"node_description": "\n".join(minimal_lines)}
        return {}

    @staticmethod
    def _convert_taxonomy_paths(tool_result: ToolResult, level: str) -> Dict:
        """
        Convert taxonomy path finder results into a readable format.
        The content is now just a list of paths directly.
        """
        try:
            # Parse the JSON content (which is now just a list of paths)
            import json
            relevant_paths = json.loads(tool_result.content)
            
            result = {
                "tool_type": "taxonomy_path_finder",
                "relevant_paths": relevant_paths
            }
            
            return result
            
        except Exception as e:
            return {"error": f"Failed to parse taxonomy paths result: {str(e)}"}


# ------------------------- Testing -------------------------
if __name__ == "__main__":
    # Sample calendar event data
    sample_calendar_result = ToolResult(
        result_type="calendar_events",
        data_list=[
            {
                "data": {
                    "summary": "Friday Night Meats",
                    "description": "Weekly Zoom meeting",
                    "htmlLink": "https://www.google.com/calendar/event?eid=some_id",
                    "start": {"dateTime": "2025-02-21T20:00:00-08:00"},
                    "end": {"dateTime": "2025-02-21T22:00:00-08:00"},
                    "attendees": [
                        {"email": "person1@example.com"},
                        {"email": "person2@example.com"},
                    ],
                    "id": "event123",
                }
            },
            {
                "data": {
                    "summary": "Kitchen Patrol",
                    "description": "Reminder for cleaning duties.",
                    "htmlLink": "https://www.google.com/calendar/event?eid=some_id_2",
                    "start": {"date": "2025-02-23"},
                    "end": {"date": "2025-02-24"},
                    "attendees": [{"email": "housemate@example.com"}],
                    "id": "event456",
                }
            },
        ],
    )

    print("\n==== Testing Calendar Conversion ====")
    print("\nFULL DETAIL:")
    print(json.dumps(DataConversionModule.convert(sample_calendar_result, "full"), indent=4))
    print("\nSUMMARY:")
    print(json.dumps(DataConversionModule.convert(sample_calendar_result, "summary"), indent=4))
    print("\nMINIMAL:")
    print(json.dumps(DataConversionModule.convert(sample_calendar_result, "minimal"), indent=4))

    # Sample email data
    sample_email_result = ToolResult(
        result_type="fetch_email",
        data_list=[
            {
                "uid": "12345",
                "subject": "Project Update",
                "sender": "Alice Johnson",
                "email_address": "alice@example.com",
                "date": "2025-02-20",
                "snippet": "Here's the latest update on the project...",
                "summary": "Key project updates and next steps.",
                "action_items": ["Follow up with Bob", "Update the report"],
                "importance": 8,
                "has_attachment": True,
                "body": "Dear team, Here’s the latest update on the project...",
            },
            {
                "uid": "67890",
                "subject": "Meeting Reminder",
                "sender": "Bob Smith",
                "email_address": "bob@example.com",
                "date": "2025-02-19",
                "snippet": "Reminder: Team meeting at 10 AM...",
                "summary": "Upcoming team meeting scheduled for 10 AM.",
                "action_items": ["Prepare agenda", "Confirm attendance"],
                "importance": 5,
                "has_attachment": False,
                "body": "Just a reminder that our team meeting is scheduled for tomorrow at 10 AM.",
            },
        ],
    )

    print("\n==== Testing Email Conversion ====")
    print("\nFULL DETAIL:")
    print(json.dumps(DataConversionModule.convert(sample_email_result, "full"), indent=4))
    print("\nSUMMARY:")
    print(json.dumps(DataConversionModule.convert(sample_email_result, "summary"), indent=4))
    print("\nMINIMAL:")
    print(json.dumps(DataConversionModule.convert(sample_email_result, "minimal"), indent=4))
