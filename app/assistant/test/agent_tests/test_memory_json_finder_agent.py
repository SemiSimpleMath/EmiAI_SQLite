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


def test_memory_json_finder_returns_locations_and_suggested_insert_path():
    bb = Blackboard()
    bb.update_state_value(
        "json_content",
        {
            "_metadata": {"resource_id": "resource_user_food_prefs"},
            "food": {"likes": [{"item": "pizza", "display": "Pizza"}]},
        },
    )
    bb.update_state_value("query", "User likes Cold Stone ice cream with Heath Bar crunch")

    agent = DI.agent_factory.create_agent("memory::json_finder", blackboard=bb)
    assert agent is not None

    agent.llm_interface = _StubLLMInterface(
        {
            "locations": [
                {
                    "path": "food.likes[0]",
                    "current_value": "{'item': 'pizza', 'display': 'Pizza'}",
                    "relevance": "Existing likes list; new like should be appended here.",
                }
            ],
            "suggested_insert_path": "food.likes",
            "reasoning": "Food preference belongs in food.likes list.",
        }
    )

    agent.action_handler(Message(data_type="agent_activation"))

    assert isinstance(bb.get_state_value("locations"), list)
    assert bb.get_state_value("suggested_insert_path") == "food.likes"
    assert "Food preference" in bb.get_state_value("reasoning")


if __name__ == "__main__":
    test_memory_json_finder_returns_locations_and_suggested_insert_path()
    print("OK: test_memory_json_finder_agent")

