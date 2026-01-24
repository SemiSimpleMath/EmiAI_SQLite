"""
DEPRECATED: moved to `app/assistant/tests/agent_tests/` to match repo conventions.

This file is intentionally skipped to avoid duplicate test discovery.
"""

import pytest

pytest.skip("Moved to app/assistant/tests/agent_tests/", allow_module_level=True)

import json

import app.assistant.tests.test_setup  # noqa: F401

from app.assistant.ServiceLocator.service_locator import DI
from app.assistant.lib.blackboard.Blackboard import Blackboard
from app.assistant.utils.pydantic_classes import Message


class _StubLLMInterface:
    def __init__(self, result_dict: dict):
        self._result_dict = result_dict

    def structured_output(self, messages, use_json=False, **params):
        return self._result_dict


def test_memory_final_answer_sets_final_answer_state():
    bb = Blackboard()
    bb.update_state_value("task", "Update the appropriate preference file with: User likes Cold Stone ice cream with Heath Bar crunch")
    bb.update_state_value("information", "Category: preference, Confidence: 0.95")
    bb.update_state_value("recent_history", "=== MEMORY::PLANNER FINAL RESULT === ...")

    agent = DI.agent_factory.create_agent("memory::final_answer", blackboard=bb)
    assert agent is not None

    agent.llm_interface = _StubLLMInterface(
        {
            "confirmation_message": "Got it! I've added Cold Stone ice cream with Heath Bar crunch to your food preferences.",
            "changes_made": "Updated food likes with Cold Stone ice cream with Heath Bar crunch.",
        }
    )

    agent.action_handler(Message(data_type="agent_activation"))

    final = bb.get_state_value("final_answer")
    assert isinstance(final, dict)
    assert "confirmation_message" in final
    assert "Cold Stone" in final["confirmation_message"]

    # It also records an agent_response message with JSON content
    msgs = bb.get_messages_for_scope(bb.get_current_scope_id())
    assert any(
        getattr(m, "data_type", None) == "agent_response" and json.loads(getattr(m, "content", "{}"))
        for m in msgs
    )


if __name__ == "__main__":
    test_memory_final_answer_sets_final_answer_state()
    print("OK: test_memory_final_answer_agent")

