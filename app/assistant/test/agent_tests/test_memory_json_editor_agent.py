"""
DEPRECATED: moved to `app/assistant/tests/agent_tests/` to match repo conventions.

This file is intentionally skipped to avoid duplicate test discovery.
"""

import pytest

pytest.skip("Moved to app/assistant/tests/agent_tests/", allow_module_level=True)

import app.assistant.tests.test_setup  # noqa: F401

from app.assistant.ServiceLocator.service_locator import DI
from app.assistant.lib.blackboard.Blackboard import Blackboard
from app.assistant.utils.pydantic_classes import Message


class _StubLLMInterface:
    def __init__(self, result_dict: dict):
        self._result_dict = result_dict

    def structured_output(self, messages, use_json=False, **params):
        return self._result_dict


def test_memory_json_editor_produces_insert_edit():
    bb = Blackboard()
    bb.update_state_value(
        "json_content",
        {
            "_metadata": {"resource_id": "resource_user_food_prefs"},
            "food": {"likes": [{"item": "pizza", "display": "Pizza"}]},
        },
    )
    bb.update_state_value("query", "User likes Cold Stone ice cream with Heath Bar crunch")
    bb.update_state_value(
        "found_locations",
        [
            {
                "path": "food.likes[0]",
                "current_value": "{'item': 'pizza', 'display': 'Pizza'}",
                "relevance": "Existing likes list; new like should be added here.",
            }
        ],
    )
    bb.update_state_value("suggested_insert_path", "food.likes")

    agent = DI.agent_factory.create_agent("memory::json_editor", blackboard=bb)
    assert agent is not None

    agent.llm_interface = _StubLLMInterface(
        {
            "edits": [
                {
                    "operation": "insert",
                    "path": "food.likes[0]",
                    "new_value": {
                        "item": "cold_stone_ice_cream_with_heath_bar_crunch",
                        "display": "Cold Stone ice cream with Heath Bar crunch",
                    },
                    "reason": "Append new like to the food.likes list.",
                }
            ],
            "decision": "proceed",
            "reasoning": "Clear new like; not present in existing list.",
        }
    )

    agent.action_handler(Message(data_type="agent_activation"))

    assert bb.get_state_value("decision") == "proceed"
    edits = bb.get_state_value("edits")
    assert isinstance(edits, list) and edits
    assert edits[0]["operation"] == "insert"


if __name__ == "__main__":
    test_memory_json_editor_produces_insert_edit()
    print("OK: test_memory_json_editor_agent")

