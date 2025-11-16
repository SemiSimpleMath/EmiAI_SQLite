# slack_tool.py
import os
from typing import Any, Dict
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from app.assistant.utils.pydantic_classes import ToolMessage, ToolResult
from app.assistant.lib.core_tools.base_tool.base_tool import BaseTool

from app.assistant.utils.logging_config import get_logger
logger = get_logger(__name__)

SLACK_TOKEN = os.environ.get('SLACK_TOKEN')

class SlackTool(BaseTool):
    def __init__(self):
        super().__init__('slack_tool')
        self.client = WebClient(token=SLACK_TOKEN)
        self.last_user_timestamps = {}
        self.bot_user_id = None

    def execute(self, tool_message: ToolMessage) -> ToolResult:
        try:
            arguments = tool_message.tool_data.get("arguments", {})
            action = tool_message.tool_data.get("tool_name")
            if not action:
                raise ValueError("Missing tool_name in tool_data.")

            handler = getattr(self, f"handle_{action}", None)
            if not handler:
                raise ValueError(f"Unsupported Slack action: {action}")
            return handler(arguments)

        except Exception as e:
            logger.exception("SlackTool execution error")
            return ToolResult(result_type="error", content=str(e))



    def handle_get_messages(self, arguments: Dict[str, Any]):
        try:
            channel_id = arguments.get("channel_id")
            oldest = arguments.get("oldest")
            if not channel_id:
                raise ValueError("channel_id is required")

            response = self.client.conversations_history(
                channel=channel_id,
                limit=100,
                oldest=oldest,
                inclusive=False
            )

            messages = response.get("messages", [])
            messages = [m for m in messages if m.get("subtype") != "bot_message"]

            user_cache = {}
            formatted_messages = []
            max_ts = oldest

            for msg in messages:
                user_id = msg.get("user", "unknown")
                text = msg.get("text", "")
                ts = msg.get("ts")
                if not ts:
                    continue
                if not max_ts or ts > max_ts:
                    max_ts = ts

                if user_id not in user_cache:
                    try:
                        name = self.resolve_speaker_name(msg, user_cache)
                        user_cache[user_id] = name
                    except (SlackApiError, TimeoutError, Exception) as e:
                        # Handle timeout and other errors gracefully
                        logger.warning(f"Error resolving user name for {user_id}: {e}")
                        user_cache[user_id] = user_id

                formatted_messages.append({
                    "name": user_cache[user_id],
                    "text": text,
                    "ts": ts
                })

            formatted_messages.reverse()

            return ToolResult(result_type="messages", content="Messages retrieved", data_list=formatted_messages)

        except (SlackApiError, TimeoutError, Exception) as e:
            logger.error(f"Slack API error during get_messages: {e}")
            return ToolResult(result_type="error", content=f"Slack API error during get_messages: {e}")

    def handle_send_message(self, arguments: Dict[str, Any]):
        try:
            channel_id = arguments.get("channel_id")
            text = arguments.get("text")
            if not channel_id or not text:
                raise ValueError("Both channel_id and text are required")

            self.client.chat_postMessage(channel=channel_id, text=text)
            return ToolResult(result_type="success", content="Message sent.")
        except SlackApiError as e:
            logger.error("Slack API error during send_message")
            return ToolResult(result_type="error", content=str(e))

    def handle_get_bot_user_id(self, arguments: Dict[str, Any]) -> ToolResult:
        try:
            if not self.bot_user_id:
                response = self.client.auth_test()
                self.bot_user_id = response.get("user_id")
            return ToolResult(result_type="bot_user_id", content=self.bot_user_id)
        except SlackApiError as e:
            return ToolResult(result_type="Error", content=e)


    def resolve_speaker_name(self, msg: dict, user_cache: dict) -> str:
        if "user" in msg:
            user_id = msg["user"]
            if user_id not in user_cache:
                try:
                    info = self.client.users_info(user=user_id)
                    user = info.get("user", {})
                    name = user.get("real_name") or user.get("name") or user_id
                    user_cache[user_id] = name
                except SlackApiError:
                    user_cache[user_id] = user_id
            return user_cache[user_id]

        if "bot_id" in msg:
            return msg.get("username") or msg["bot_id"]

        return "unknown"


def test_get_messages():
    tool = SlackTool()
    channel_id = "C08AB0R54HM"

    msg = ToolMessage(
        tool_name="get_messages",
        tool_data={
            "tool_name": "get_messages",
            "arguments": {
                "channel_id": channel_id,
                "oldest": None  # or a string timestamp if testing incrementally
            }
        }
    )

    result = tool.execute(msg)

    print("=== Get Messages Result ===")
    if isinstance(result, str):
        print("Error or timestamp:", result)
    elif isinstance(result, tuple) and len(result) == 2:
        messages = result

        for msg in messages:
            print(f"- [{msg['ts']}] {msg['name']}: {msg['text']}")
    else:
        print("Unexpected result format:", result)


def test_send_message():
    tool = SlackTool()
    channel_id = "C08AB0R54HM"

    msg = ToolMessage(
        tool_name="send_message",
        tool_data={
            "tool_name": "send_message",
            "arguments": {
                "channel_id": channel_id,
                "text": "Hello from SlackTool test 🎯"
            }
        }
    )

    result = tool.execute(msg)
    print("=== Send Message Result ===")
    if hasattr(result, "json"):
        print(result.model_dump_json(indent=2))
    else:
        print(result)



if __name__ == "__main__":
    test_get_messages()
    #test_send_message()
