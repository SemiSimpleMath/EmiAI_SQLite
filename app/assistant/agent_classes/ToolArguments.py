import json
import re
import os
from pathlib import Path
from typing import List, Dict

from jinja2 import Template

from app.assistant.agent_classes.Agent import Agent
from app.assistant.utils.pydantic_classes import Message

from app.assistant.utils.logging_config import get_logger
logger = get_logger(__name__)


class ToolArguments(Agent):
    def __init__(self, name, blackboard, agent_registry, tool_registry, llm_params=None, parent=None):
        super().__init__(name, blackboard, agent_registry, tool_registry, llm_params, parent)
        self.tool_name = None
        self.tool_type = None
    def action_handler(self, message: Message):
        self._set_agent_busy()
        try:
            self.blackboard.update_state_value("next_agent", None)

            # Update last acting agent
            self.blackboard.update_state_value('last_agent', self.name)

            logger.debug(f"[{self.name}] Handling tool/agent argument selection.")

            selected_node = self.blackboard.get_state_value("selected_tool")
            if not selected_node:
                logger.error(f"[{self.name}] No tool or agent selected to generate arguments for.")
                return

            try:
                messages = self.construct_prompt(message)
            except Exception as e:
                logger.error(f"[{self.name}] Error during prompt construction: {e}")
                exit(1)

            # 🔀 Determine if it's a tool, agent, or control node
            if self.tool_registry.get_tool(selected_node):
                schema = self.tool_registry.get_tool_form(selected_node)
                self.tool_type = "Tool"
            elif self.agent_registry.get_agent_config(selected_node):
                agent_config = self.agent_registry.get_agent_config(selected_node)
                # Check if it's a control node
                if agent_config.get("type") == "control_node":
                    # It's a control node - no arguments needed, just pass it through
                    logger.info(f"[{self.name}] '{selected_node}' is a control node, no arguments needed.")
                    self.blackboard.update_state_value("tool_arguments", {})
                    return
                else:
                    # It's a local agent - check if it has an input schema
                    schema = self.agent_registry.get_agent_input_form(selected_node)
                    if schema:
                        # Agent has input schema - generate arguments
                        logger.info(f"[{self.name}] '{selected_node}' is a local agent with input schema, generating arguments.")
                        self.tool_type = "Agent"
                    else:
                        # Agent has no input schema - no arguments needed
                        logger.info(f"[{self.name}] '{selected_node}' is a local agent without input schema, no arguments needed.")
                        self.blackboard.update_state_value("tool_arguments", {})
                        return
            else:
                logger.error(f"[{self.name}] '{selected_node}' is neither a tool nor a registered agent.")
                return

            if not schema:
                logger.info(f"[{self.name}] No argument schema found for '{selected_node}' returning None.")
                return

            result = self._run_llm_with_schema(messages, schema)

            try:
                result = self.process_llm_result(result)
            except Exception as e:
                logger.error(f"Error processing result: {e}")
                raise

            return result
        except Exception as e:
            logger.error(f"[{self.name}] Unhandled exception in action_handler: {e}")
            print(f"🛑 [{self.name}] action_handler exception: {e}")
            raise
        finally:
            # ALWAYS release the busy lock, even on exceptions
            try:
                self._set_agent_idle()
            except Exception as e:
                logger.error(f"[{self.name}] Failed to release busy lock: {e}")
                print(f"🛑 [{self.name}] Failed to release busy lock: {e}")



    def construct_prompt(self, message: Message = None) -> List[Dict[str, str]]:
        """
        Constructs the system + user prompt using the correct tool's argument template.
        """
        system_prompt = self.get_system_prompt(message).replace('\n\n', '\n')
        user_prompt = self.get_user_prompt(message).replace('\n\n', '\n')

        system_prompt = re.sub(r'\n{3,}', '\n\n', system_prompt)
        user_prompt = re.sub(r'\n{3,}', '\n\n', user_prompt)

        msg = [
            {'role': 'system', 'content': system_prompt or f"[{self.name}] Error forming system prompt."},
            {'role': 'user', 'content': user_prompt or f"[{self.name}] Error forming user prompt."}
        ]
        return msg

    def get_system_prompt(self, message: Message = None):

        system_prompt_template = self.config.get("prompts", {}).get("system", "")

        if not system_prompt_template:
            logger.error(f"[{self.name}] No system prompt found.")
            return f"No system prompt available for {self.name}."

        # Load context items
        prompt_injections = self.config.get("system_context_items", {})
        if prompt_injections is not None:
            system_context = self.generate_injections_block(prompt_injections, message)
        else:
            system_context = None

        try:
            template = Template(system_prompt_template)
            rendered_output = template.render(**system_context or {}).replace('\n\n', '\n')
            return rendered_output

        except Exception as e:
            logger.error(f"[{self.name}] ERROR while rendering system prompt: {e}")
            raise

    def get_user_prompt(self, message: Message = None):
        """
        Retrieves and renders the user prompt for the selected tool's argument generation.
        """

        selected_tool = self.blackboard.get_state_value('selected_tool')

        user_prompt_template = self.config.get("prompts", {}).get("user", "")

        prompt_injections = self.config.get("user_context_items", {})
        user_context = self.generate_injections_block(prompt_injections, message)

        tool_args = self.tool_registry.get_tool_arguments_prompt(selected_tool)  # this function already renders it

        # Fetch the tool description and tool prompt. Already rendered
        tool_description = self.tool_registry.get_tool_description(selected_tool)

        user_context.update({'tool_description': tool_description,
                             'tool_args': tool_args})

        # Get agent configuration to get agents system prompt

        try:
            template = Template(user_prompt_template)
            rendered_output = template.render(**user_context or {}).replace('\n\n', '\n')
            return rendered_output

        except Exception as e:
            logger.error(f"[{self.name}] ERROR while rendering system prompt: {e}")
            raise


    def process_llm_result(self, result):
        logger.debug(f"[{self.name}] Processing LLM Result: {result}")
        print(f"\n\n\n -------------LLM RESULT {self.name}------------")
        print(result)
        print("\n -----------------------------------")

        # Handle case where result is a string (error message)
        if isinstance(result, str):
            logger.error(f"[{self.name}] LLM returned string instead of dict: {result}")
            # Create a proper error structure
            result_dict = {
                "error": result,
                "action": "error",
                "content": f"LLM Error: {result}"
            }
        else:
            # Convert result to dictionary
            result_dict = result

        if not isinstance(result_dict, dict):
            logger.error(f"[{self.name}] LLM result is not a dict: {type(result_dict)} - {result_dict}")
            # Create a proper error structure
            result_dict = {
                "error": f"Invalid result type: {type(result_dict)}",
                "action": "error",
                "content": f"Invalid result type: {type(result_dict)}"
            }

        # Heuristic normalizations for specific tools where units are easy to confuse.
        # Example: Playwright MCP `browser_wait_for.time` is in SECONDS, but agents sometimes
        # provide milliseconds (e.g. 2000 meaning 2 seconds). If it looks like milliseconds,
        # convert to seconds.
        try:
            selected_tool = self.blackboard.get_state_value("selected_tool")
            if (
                isinstance(result_dict, dict)
                and selected_tool == "mcp::npm/playwright-mcp::browser_wait_for"
                and isinstance(result_dict.get("time"), (int, float))
            ):
                t = result_dict.get("time")
                # Only apply when it strongly looks like ms (>=1000 and divisible by 1000).
                if isinstance(t, (int, float)) and t >= 1000 and float(t).is_integer() and int(t) % 1000 == 0:
                    result_dict["time"] = int(t) // 1000
        except Exception:
            pass

        # Deterministic normalization for vision helper agent inputs:
        # Vision agents require an absolute path to an on-disk PNG.
        #
        # The planner often only sees the screenshot filename (e.g. "mcp_....png") in summaries,
        # because `[mcp_image_path: ...]` markers are stripped and converted to multimodal blocks
        # before the LLM sees them.
        #
        # So: if the callee expects `image` and it is not absolute, resolve it to:
        #   <repo_root>/uploads/temp/<filename>
        #
        # Fail loudly if the resulting file does not exist.
        try:
            selected_node = self.blackboard.get_state_value("selected_tool")
            if (
                isinstance(result_dict, dict)
                and isinstance(result_dict.get("image"), str)
                and isinstance(selected_node, str)
                and selected_node in {"shared::vision_page_scout", "shared::vision_target_picker"}
            ):
                raw_image = (result_dict.get("image") or "").strip()
                if not raw_image:
                    raise RuntimeError(
                        f"[{self.name}] Vision agent '{selected_node}' requires image path, but got empty 'image'."
                    )

                # Resolve relative/filename-only to uploads/temp/<filename>
                img_path = Path(raw_image)
                if not os.path.isabs(raw_image):
                    fname = img_path.name
                    if not fname:
                        raise RuntimeError(
                            f"[{self.name}] Vision agent '{selected_node}' got invalid image value: {raw_image!r}"
                        )
                    repo_root = Path(__file__).resolve().parents[3]
                    candidate = (repo_root / "uploads" / "temp" / fname).resolve()
                    result_dict["image"] = str(candidate)
                    img_path = candidate

                # Validate existence
                if not img_path.exists():
                    raise RuntimeError(
                        f"[{self.name}] Vision agent '{selected_node}' image path does not exist: {str(img_path)}"
                    )
                # Validate png
                if img_path.suffix.lower() != ".png":
                    raise RuntimeError(
                        f"[{self.name}] Vision agent '{selected_node}' requires a .png image, got: {str(img_path)}"
                    )
        except Exception as e:
            logger.error(f"[{self.name}] Vision image normalization failed: {e}")
            raise

        self.blackboard.update_state_value("tool_arguments", result_dict)

        response_message = Message(
            data_type="agent_response",
            sender=self.name,
            receiver="Blackboard",
            content=f"{self.name} acted\n Result: {json.dumps(result_dict)}"
        )
        self.blackboard.add_msg(response_message)
        logger.info(f"[{self.name}] Recorded response in blackboard history.")

        return result