"""
DEPRECATED: moved to `app/assistant/tests/agent_tests/` to match repo conventions.

This file is intentionally skipped to avoid duplicate test discovery.
"""

import pytest

pytest.skip("Moved to app/assistant/tests/agent_tests/", allow_module_level=True)

import app.assistant.tests.test_setup  # noqa: F401  (side-effect: initializes DI)

from app.assistant.ServiceLocator.service_locator import DI
from app.assistant.lib.blackboard.Blackboard import Blackboard
from app.assistant.utils.pydantic_classes import Message


class _StubLLMInterface:
    def __init__(self, result_dict: dict):
        self._result_dict = result_dict

    def structured_output(self, messages, use_json=False, **params):
        return self._result_dict


def test_memory_decider_proceed_sets_tags_and_fact_summary():
    bb = Blackboard()
    bb.update_state_value(
        "task",
        "Update the appropriate preference file with: User likes Cold Stone ice cream with Heath Bar crunch",
    )
    bb.update_state_value("information", "Category: preference, Confidence: 0.95")

    agent = DI.agent_factory.create_agent("memory::decider", blackboard=bb)
    assert agent is not None

    agent.llm_interface = _StubLLMInterface(
        {
            "what_i_am_thinking": "Clear explicit preference (likes). Store and route to food prefs.",
            "tags": ["food"],
            "decision": "proceed",
            "fact_summary": "User likes Cold Stone ice cream with Heath Bar crunch.",
            "rejection_reason": "",
            "action": "flow_exit_node",
        }
    )

    agent.action_handler(Message(data_type="agent_activation"))

    assert bb.get_state_value("decision") == "proceed"
    assert bb.get_state_value("tags") == ["food"]
    assert bb.get_state_value("fact_summary") == "User likes Cold Stone ice cream with Heath Bar crunch."
    assert bb.get_state_value("last_agent") == "memory::decider_flow_exit_node"
    assert isinstance(bb.get_state_value("result"), dict)


def test_memory_decider_reject_clears_tags_and_fact_summary():
    bb = Blackboard()
    bb.update_state_value("task", "Update the appropriate preference file with: User had coffee this morning")
    bb.update_state_value("information", "Category: preference, Confidence: 0.40")

    agent = DI.agent_factory.create_agent("memory::decider", blackboard=bb)
    assert agent is not None

    agent.llm_interface = _StubLLMInterface(
        {
            "what_i_am_thinking": "One-off report, not a stable preference or rule.",
            "tags": [],
            "decision": "reject",
            "fact_summary": "",
            "rejection_reason": "One-time action report; no stable preference inferred.",
            "action": "flow_exit_node",
        }
    )

    agent.action_handler(Message(data_type="agent_activation"))

    assert bb.get_state_value("decision") == "reject"
    assert bb.get_state_value("tags") == []
    assert bb.get_state_value("fact_summary") == ""
    assert bb.get_state_value("rejection_reason")


if __name__ == "__main__":
    test_memory_decider_proceed_sets_tags_and_fact_summary()
    test_memory_decider_reject_clears_tags_and_fact_summary()
    print("OK: test_memory_decider_agent")

