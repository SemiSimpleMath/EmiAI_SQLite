from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List, Union
from datetime import datetime, timezone
import uuid


# Define the Message class using Pydantic
class Message(BaseModel):
    data_type: Optional[str] = None  # e.g., 'init_agent', 'agent_msg', 'tool_result', 'agent_selection_request', 'agent_selection_response'
    # Additional classification flexibility:
    # This is intentionally a LIST so a message can carry multiple tags for routing/scoping.
    # Example: ["chat", "slash_command", "music"]
    sub_data_type: List[str] = Field(default_factory=list)
    sender: Optional[str] = None  # Name of the agent or 'User'
    receiver: Optional[str] = None
    content: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    task: Optional[str] = ""
    ask_user_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    scope_id: Optional[str] = None
    group_id: Optional[int] = None
    information: Optional[str] = ""
    request_id: Optional[str] = None
    role: Optional[str] = None
    notification: Optional[bool] = False
    is_chat: Optional[bool] = False
    agent_input: Optional[Union[str, Dict[str, Any]]] = None
    event_topic: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None  # For storing additional metadata like entity names
    test_mode: Optional[bool] = False
    memo_mode: Optional[bool] = False


class PlanStruct(Message):
    plan: str
    current_step: str
    action: str
    action_input: str
    status: int
    complete: bool

class ToolResult(BaseModel):
    result_type: Optional[str] = None
    content: str = ""
    data_list: Optional[List[Dict[str, Any]]] = Field(default_factory=list)
    data: Optional[Any] = None


class ToolMessage(Message):  # Assuming Message is similar to BaseModel
    tool_name: str  # Name of the tool being invoked
    tool_data: Optional[Dict[str, Any]] = None # Arguments passed to the tool
    tool_result: Optional[ToolResult] = None  # Result of the tool execution
    request_id: Optional[str] = None


RESULT_TYPE_HANDLERS = {
    "fetch_email": "handle_fetch_email_result",
    "SearchResult": "handle_search_result",
    "SendEmailTool": "handle_send_email_result",
    "search1": "handle_search1_result",
    "scrape": "handle_scrape_result",
    "success": "handle_success_result",
    "error": "handle_error_result",
    "final_answer": "handle_final_answer",
    "calendar_events": "handle_get_calendar_event_result",
    "scheduler_events": "handle_fetch_scheduler_events_result",
    "weather": "handle_get_weather_result",
    "news": "handle_get_news_result",
    "todo_tasks": "handle_get_todo_tasks",
    "ask_user_response": "handle_ask_user_response",
    "tool_success": "handle_tool_success",
    "tool_failure": "handle_tool_failure"

}

RESULT_TYPE_HANDLERS_NEW = {
    "fetch_email": "handle_fetch_email_result",
    "search_result": "handle_search_result",
    "send_email": "handle_send_email_result",
    "search1": "handle_search1_result",
    "scrape": "handle_scrape_result",
    "success": "handle_success_result",
    "error": "handle_error_result",
    "final_answer": "handle_final_answer",
    "calendar_events": "handle_calendar_event_result",
    "scheduler_events": "handle_scheduler_events_result",
    "weather": "handle_weather_result",
    "news": "handle_news_result",
    "todo_tasks": "handle_todo_tasks_result",
    "ask_user_response": "handle_ask_user_response",
    "tool_success": "handle_tool_success",
    "tool_failure": "handle_tool_failure"
}



class EventMessage(Message):
    event_payload: Dict[str, Any]

class UserMessageData(BaseModel):
    feed: Optional[str] = None
    chat: Optional[str] = None
    widget_data: Optional[List[Dict[str,Any]]] = None
    sound: Optional[str] = None
    importance: Optional[int] = 2
    generic_type: Optional[str] = None
    tts: Optional[bool] = False
    tts_text: Optional[str] = None

class UserMessage(Message):
    user_message_data: UserMessageData


# Not sure if these are needed putting these here for safe keeping

class EmailData(BaseModel):
    id: str  # Unique identifier for the email
    sender: Optional[str] = None
    receiver: Optional[List[str]] = None
    cc: Optional[List[str]] = None
    bcc: Optional[List[str]] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    datetime_received: Optional[str] = None  # ISO 8601 format
    has_attachment: Optional[bool] = None


class CalendarEventData(BaseModel):
    id: str  # Unique identifier for the event
    title: Optional[str] = None
    description: Optional[str] = None
    start_time: Optional[str] = None  # ISO 8601 format
    end_time: Optional[str] = None  # ISO 8601 format
    time_zone: Optional[str] = None
    location: Optional[str] = None
    attendees: Optional[List[str]] = None
    recurrence_rule: Optional[str] = None
    link: Optional[str] = None
    metadata: Optional[Dict] = None  # Extra information for flexibility

