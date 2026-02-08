# Note to coding agents: This file should not be modified without user permission.
from datetime import datetime, timezone
import json
import os
import re
from typing import List, Dict, Any, Optional, Union
from colorama import Fore
from jinja2 import Template
from typing import TYPE_CHECKING
from app.assistant.ServiceLocator.service_locator import DI
from app.assistant.utils.time_utils import get_local_time_str
from app.assistant.utils.utils import normalize_to_ascii

if TYPE_CHECKING:
    from app.assistant.agent_registry.agent_registry import AgentRegistry

from app.assistant.utils.pydantic_classes import Message, ToolResult
from app.assistant.utils.pipeline_state import (
    ensure_pipeline_state,
    get_pending_tool,
    set_pending_tool,
)
from app.services.llm_factory import LLMFactory

from app.assistant.rag.rag_utils import (
    query_rag_database
)

rag_cache = {}

from app.assistant.utils.logging_config import get_logger
from app.assistant.performance.performance_monitor import performance_monitor

logger = get_logger(__name__)


def cache_rag_result(query: str, results: str, cache_duration: int = 48 * 3600):
    expiration_time = datetime.now(timezone.utc).timestamp() + cache_duration
    rag_cache[query] = {"results": results, "expires": expiration_time}


def get_cached_rag_result(query: str):
    if query in rag_cache and rag_cache[query]["expires"] > datetime.now(timezone.utc).timestamp():
        return rag_cache[query]["results"]
    return None


class Agent:
    def __init__(self, name, blackboard, agent_registry: "AgentRegistry", tool_registry, llm_params=None,
                 parent=None):
        self.name = name
        self.parent = parent
        self.blackboard = blackboard
        self.agent_registry = agent_registry
        self.config = agent_registry.get_agent_config(self.name)
        self.color = Fore.GREEN if self.config.get('color', 'green') == "green" else Fore.RESET
        self.tool_registry = tool_registry
        self.llm_params = llm_params if llm_params else self.get_default_llm_params()
        self.llm_interface = None
        self.retriever = None
        self.append_fields = self.config.get("append_fields", [])

    def resolve_role_binding(self, role_name):
        bindings = self.blackboard.get_state_value('manager_role_bindings', {})
        return bindings.get(role_name, role_name)

    def get_llm_interface(self):
        if self.llm_interface is None:
            self.llm_interface = LLMFactory.get_llm_interface(**self.llm_params)
            logger.info(f"Initialized LLM interface for agent: {self.name}")
        return self.llm_interface

    def get_default_llm_params(self):
        return {
            "llm_provider": "openai",
            "engine": "gpt-5-mini",
            "temperature": 1,
            "api_key": "dummy_api_key"
        }

    def _set_agent_busy(self):
        DI.event_hub.set_agent_status(self.name, True)

    def _set_agent_idle(self):
        DI.event_hub.set_agent_status(self.name, False)

    def _check_for_quota_error(self, response_text: Any) -> None:
        """
        Check if LLM response contains quota error and exit if found.
        
        Args:
            response_text: The response from LLM (can be any type)
        """
        import sys

        if not response_text:
            return

        # Convert to string if needed
        response_str = str(response_text).lower()

        # Check for quota-related keywords
        quota_keywords = [
            "llm quota",
            "quota exceeded",
            "rate limit exceeded",
            "insufficient quota",
            "quota exhausted",
            "billing quota",
            "usage quota"
        ]

        for keyword in quota_keywords:
            if keyword in response_str:
                logger.critical(f"❌ LLM QUOTA ERROR DETECTED in agent: {self.name}")
                logger.critical(f"   Response preview: {str(response_text)[:500]}")
                logger.critical(f"   Keyword: '{keyword}'")
                logger.critical(f"🛑 Forcing program exit to prevent data corruption")
                print(f"\n{'=' * 80}")
                print(f"❌ CRITICAL ERROR: LLM Quota Exhausted")
                print(f"{'=' * 80}")
                print(f"Agent: {self.name}")
                print(f"Detected keyword: '{keyword}'")
                print(f"Response preview: {str(response_text)[:500]}")
                print(f"{'=' * 80}")
                print(f"🛑 Program terminated. Please check your LLM quota and billing.")
                print(f"{'=' * 80}\n")
                # Use os._exit() instead of sys.exit() - works in threads and bypasses exception handlers
                os._exit(1)

    def _update_blackboard_state(self, message: Message):
        self.blackboard.update_state_value('next_agent', None)

        ai = message.agent_input
        if isinstance(ai, dict):
            # unpack dict into individual state entries
            logger.debug(f"[{self.name}] Unpacking agent_input dict with keys: {list(ai.keys())}")
            for k, v in ai.items():
                logger.debug(f"[{self.name}] Setting blackboard['{k}'] = {str(v)[:100] if v else 'None'}...")
                self.blackboard.update_state_value(k, v)
        elif isinstance(ai, str):
            # legacy single-string behavior
            logger.debug(f"[{self.name}] Setting agent_input as string: {ai[:50]}...")
            self.blackboard.update_state_value('agent_input', ai)
        else:
            # no input or unsupported type
            logger.debug(f"[{self.name}] No agent_input or unsupported type: {type(ai)}")
            self.blackboard.update_state_value('agent_input', None)

    def _store_incoming_message(self, message: Message):
        if message.content:
            self.blackboard.add_msg(message)

    def _add_extra_msgs(self, message: Message):
        # default no-op; override in subclasses if needed
        pass

    def _run_llm_with_schema(self, messages, schema: Union[dict, str, None]):
        """
        Run the LLM with an optional structured output schema.

        schema:
          - dict: JSON schema, use_json = True
          - str: model specific format hint, use_json = False
          - None: no structured output
        """
        use_json = isinstance(schema, dict)

        try:
            result = self.call_llm(
                messages=messages,
                response_format=schema,
                use_json=use_json,
            )
            return result
        except Exception as e:
            logger.error(f"[{self.name}] LLM execution failed: {e}")
            return None

    def action_handler(self, message: Message) -> Any:
        # Start timing the entire agent action
        timer_id = performance_monitor.start_timer(f'agent_{self.name}', message.id)

        self._set_agent_busy()
        try:
            self._update_blackboard_state(message)
            self._store_incoming_message(message)

            # Update last acting agent
            self.blackboard.update_state_value('last_agent', self.name)

            try:
                messages = self.construct_prompt(message)
            except Exception as e:
                logger.error(f"[{self.name}] Error during prompt construction: {e}, {message}")
                performance_monitor.end_timer(timer_id, {'status': 'error', 'error': 'prompt_construction_failed'})
                print(f"\n{'=' * 80}")
                print(f"🛑 FATAL: Agent '{self.name}' failed to construct prompt")
                print(f"   Error: {e}")
                print(f"   Message: {message}")
                print(f"{'=' * 80}\n")
                exit(1)

            schema = self.config.get('structured_output')

            result = self._run_llm_with_schema(messages, schema)

            self._add_extra_msgs(message)

            try:
                result = self.process_llm_result(result)
            except Exception as e:
                logger.error(f"[{self.name}] Error processing LLM result: {e}")
                print(f"🛑 [{self.name}] Error processing LLM result: {e}")
                performance_monitor.end_timer(timer_id, {'status': 'error', 'error': 'llm_result_processing_failed'})
                raise

            # End timing and record success
            performance_monitor.end_timer(timer_id, {
                'status': 'success',
                'agent_name': self.name,
                'message_id': message.id
            })

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

    def call_llm(
            self,
            messages: List[Dict[str, Any]],
            response_format: Optional[Union[dict, str]] = None,
            use_json: bool = False,
    ) -> Any:
        """
        Core LLM caller.

        - Uses self.llm_params as the base configuration.
        - Optionally applies a per call response_format.
        - Does not mutate self.llm_params.
        """
        try:
            if self.llm_interface is None:
                self.llm_interface = self.get_llm_interface()

            # Start from base params, then layer per call overrides
            params = dict(self.llm_params)

            if response_format is not None:
                params["response_format"] = response_format

            # Debug print prompts (disabled by default; parallel agents interleave stdout).
            # To enable temporarily, set: EMI_PRINT_PROMPTS=1
            print_system, print_user = self._resolve_prompt_debug_flags()
            if print_system or print_user:
                for msg in messages:
                    role = msg.get("role")
                    content = msg.get("content", "")
                    # Multimodal content can be a list of blocks; print just the text and placeholders.
                    if isinstance(content, list):
                        parts = []
                        for part in content:
                            if isinstance(part, str):
                                parts.append(part)
                                continue
                            if not isinstance(part, dict):
                                continue
                            ptype = part.get("type")
                            if ptype in ("input_text", "text"):
                                parts.append(part.get("text") or "")
                            elif ptype in ("input_image", "image_url", "image_path", "image_base64"):
                                parts.append("[image]")
                            else:
                                parts.append(f"[{ptype or 'block'}]")
                        content = "\n".join([p for p in parts if p])
                    if role == "system" and print_system:
                        print(f"\n{'=' * 60}")
                        print(f"SYSTEM PROMPT {self.name}")
                        print(f"{'=' * 60}")
                        print(content)
                        print(f"{'=' * 60}\n")
                    elif role == "user" and print_user:
                        print(f"\n{'=' * 60}")
                        print(f"USER PROMPT {self.name}")
                        print(f"{'=' * 60}")
                        print(content)
                        print(f"{'=' * 60}\n")

            response = self.llm_interface.structured_output(
                messages,
                use_json=use_json,
                **params,
            )

            # Check for LLM quota errors
            self._check_for_quota_error(response)

            return response

        except Exception as e:
            logger.error(f"[{self.name}] LLM call failed: {e}")

            # Check if the error is quota related
            self._check_for_quota_error(str(e))

            return "An error occurred while processing the request."

    def _resolve_prompt_debug_flags(self) -> tuple[bool, bool]:
        # Global override for emergency debugging.
        if os.environ.get("EMI_PRINT_PROMPTS", "0") == "1":
            return True, True

        config_flags = {}
        try:
            cfg = self.config.get("prompt_debug", {}) if isinstance(self.config, dict) else {}
            if isinstance(cfg, dict):
                config_flags = cfg
        except Exception:
            config_flags = {}

        system_flag = None
        user_flag = None
        if "system" in config_flags or "print_system" in config_flags:
            system_flag = bool(config_flags.get("system", config_flags.get("print_system")))
        if "user" in config_flags or "print_user" in config_flags:
            user_flag = bool(config_flags.get("user", config_flags.get("print_user")))

        # User settings can override config flags.
        try:
            from app.assistant.user_settings_manager.user_settings import get_settings_manager
            settings_mgr = get_settings_manager()
            pd = settings_mgr.get("prompt_debug", {}) if settings_mgr else {}
            if isinstance(pd, dict):
                default_cfg = pd.get("default", {}) if isinstance(pd.get("default"), dict) else {}
                agents_cfg = pd.get("agents", {}) if isinstance(pd.get("agents"), dict) else {}
                agent_cfg = agents_cfg.get(self.name, {}) if isinstance(agents_cfg.get(self.name), dict) else {}
                if "system" in agent_cfg:
                    system_flag = bool(agent_cfg.get("system"))
                elif "system" in default_cfg and system_flag is None:
                    system_flag = bool(default_cfg.get("system"))
                if "user" in agent_cfg:
                    user_flag = bool(agent_cfg.get("user"))
                elif "user" in default_cfg and user_flag is None:
                    user_flag = bool(default_cfg.get("user"))
        except Exception:
            pass

        return bool(system_flag), bool(user_flag)

    def _resolve_llm_result_debug_flag(self) -> bool:
        # Global override for emergency debugging.
        if os.environ.get("EMI_PRINT_LLM_RESULTS", "0") == "1":
            return True

        config_flag = None
        try:
            cfg = self.config.get("prompt_debug", {}) if isinstance(self.config, dict) else {}
            if isinstance(cfg, dict) and "results" in cfg:
                config_flag = bool(cfg.get("results"))
        except Exception:
            config_flag = None

        # User settings can override config flags.
        try:
            from app.assistant.user_settings_manager.user_settings import get_settings_manager
            settings_mgr = get_settings_manager()
            pd = settings_mgr.get("prompt_debug", {}) if settings_mgr else {}
            if isinstance(pd, dict):
                default_cfg = pd.get("default", {}) if isinstance(pd.get("default"), dict) else {}
                agents_cfg = pd.get("agents", {}) if isinstance(pd.get("agents"), dict) else {}
                agent_cfg = agents_cfg.get(self.name, {}) if isinstance(agents_cfg.get(self.name), dict) else {}
                if "results" in agent_cfg:
                    config_flag = bool(agent_cfg.get("results"))
                elif "results" in default_cfg and config_flag is None:
                    config_flag = bool(default_cfg.get("results"))
        except Exception:
            pass

        return bool(config_flag)

    def _maybe_print_llm_result(self, result: Any) -> None:
        if not self._resolve_llm_result_debug_flag():
            return
        print(f"\n\n--- LLM RESULT for {self.name} ---")
        print(json.dumps(result, indent=2) if isinstance(result, dict) else result)
        print("---------------------------------\n")

    def construct_prompt(self, message: Message = None) -> List[Dict[str, str]]:
        system_prompt = self.get_system_prompt(message).replace('\n\n', '\n')
        user_prompt = self.get_user_prompt(message).replace('\n\n', '\n')

        if not system_prompt:
            logger.error(f"[{self.name}] Error forming the system prompt.")
        if not user_prompt:
            logger.error(f"[{self.name}] Error forming the user prompt.")

        system_prompt = re.sub(r'\n{3,}', '\n\n', system_prompt)
        user_prompt = re.sub(r'\n{3,}', '\n\n', user_prompt)

        # If the prompt includes Emi image markers, convert this turn into a multimodal
        # content-block list so OpenAI can analyze the referenced image(s).
        #
        # Marker format:
        #   [emi_image: mcp_<id>.png]
        #   [emi_image: E:\EmiAi_sqlite\uploads\temp\mcp_<id>.png]
        #
        # IMPORTANT:
        # - We intentionally do NOT inject this marker into generic recent_history. Planners should remain text-only.
        # - Vision agents may include this marker explicitly in their own prompts.
        emi_image_refs: list[str] = []
        try:
            pat = re.compile(r"\[emi_image:\s*([^\]]+?)\s*\]")
            for m in pat.finditer(user_prompt or ""):
                p = (m.group(1) or "").strip()
                if p:
                    emi_image_refs.append(p)
            # Back-compat: accept legacy marker too (from older logs/prompts).
            pat_legacy = re.compile(r"\[mcp_image_path:\s*([^\]]+?)\s*\]")
            for m in pat_legacy.finditer(user_prompt or ""):
                p = (m.group(1) or "").strip()
                if p:
                    emi_image_refs.append(p)

            # Remove only the marker lines from the text.
            user_prompt = pat.sub("", user_prompt or "")
            user_prompt = pat_legacy.sub("", user_prompt or "")
        except Exception:
            emi_image_refs = []

        # Normalize to ASCII to prevent encoding issues
        system_prompt = normalize_to_ascii(system_prompt)
        user_prompt = normalize_to_ascii(user_prompt)

        msg = [
            {'role': 'system', 'content': system_prompt or f"[{self.name}] Error forming system prompt."},
            {'role': 'user', 'content': user_prompt or f"[{self.name}] Error forming user prompt."}
        ]

        if emi_image_refs:
            blocks = [{"type": "input_text", "text": msg[1]["content"]}]
            for p in emi_image_refs:
                blocks.append({"type": "image_path", "path": p})
            msg[1]["content"] = blocks
        return msg

    def get_system_prompt(self, message: Message = None):
        system_prompt_template = self.config.get("prompts", {}).get("system", "")

        if not system_prompt_template:
            logger.error(f"[{self.name}] No system prompt found.")
            print(f"\n{'=' * 80}")
            print(f"🛑 FATAL: Agent '{self.name}' has no system prompt configured")
            print(f"   Check the agent's config.yaml for 'prompts.system' or 'prompts.system_file'")
            print(f"{'=' * 80}\n")
            exit(1)
            return f"No system prompt available for {self.name}."

        # Load context items
        prompt_injections = self.config.get("system_context_items", [])

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
            # DEBUG: show what we tried to render with
            logger.error(f"[{self.name}] Context available for rendering: {list((system_context or {}).keys())}")
            raise

    def get_user_prompt(self, message: Message = None):
        user_prompt_template = self.config.get("prompts", {}).get("user", "")
        if not user_prompt_template:
            logger.error(f"[{self.name}] No user prompt found.")
            return f"No user prompt available for {self.name}."
        prompt_injections = self.config.get("user_context_items", [])

        if prompt_injections is not None:
            try:
                user_context = self.generate_injections_block(prompt_injections, message)
            except Exception as e:
                logger.error(f"[{self.name}] Error generating injections: {e}")
                print(f"🛑 [{self.name}] Error generating injections: {e}")
                raise e
        else:
            user_context = {}

        try:
            template = Template(user_prompt_template)
            # Pass 1: render with empty entity fields (generate_injections_block ensures placeholders)
            rendered_output = template.render(**user_context or {}).replace('\n\n', '\n')

            # If no entity_* fields are requested, return as-is
            entity_keys = [k for k in (prompt_injections or []) if isinstance(k, str) and k.startswith("entity_")]
            if not entity_keys:
                return rendered_output

            # Pass 2: detect entities from the rendered prompt (without entity cards) and re-render with entity_info.
            entity_field_keys = [k[len("entity_"):] for k in entity_keys if k.startswith("entity_")]

            detected_entities = []
            try:
                from app.assistant.entity_management.entity_card_injector import EntityCardInjector
                injector = EntityCardInjector()
                detected = injector.detect_entities_in_text(rendered_output) or []
                # Deduplicate while preserving order
                seen = set()
                for ent in detected:
                    if ent not in seen:
                        seen.add(ent)
                        detected_entities.append(ent)
            except Exception as e:
                logger.error(f"[{self.name}] Entity detection failed (rendered prompt scan): {e}")
                detected_entities = []

            if not detected_entities or not entity_field_keys:
                return rendered_output

            try:
                user_context = dict(user_context or {})
                user_context["entity_info"] = self._format_entity_multi_field(detected_entities, entity_field_keys)
                # Keep entity_* keys empty; entity_info is the canonical grouped injection.
                for k in entity_keys:
                    user_context[k] = ""
                rendered_with_entities = template.render(**user_context).replace('\n\n', '\n')
                return rendered_with_entities
            except Exception as e:
                logger.error(f"[{self.name}] Failed to render user prompt with entity_info: {e}")
                return rendered_output
        except Exception as e:
            logger.error(f"[{self.name}] ERROR while rendering user prompt: {e}")
            raise

    def get_allowed_nodes(self) -> List[str]:
        agent_config = self.agent_registry.get_agent_config(self.name)
        if not agent_config:
            logger.warning(f"[{self.name}] Agent not found in registry.")
            return []

        allowed_nodes = agent_config.get("allowed_nodes", [])
        if allowed_nodes == "all":
            allowed_nodes = set(self.agent_registry.list_agents())
        else:
            allowed_nodes = set(allowed_nodes)

        except_nodes = set(agent_config.get("except_nodes", []))
        all_nodes = set(self.agent_registry.list_agents())

        # In manager runtimes, an agent is only truly callable if it has an instantiated
        # instance registered in the AgentRegistry. (Otherwise ToolCaller will crash later.)
        instantiated_nodes = set()
        try:
            # AgentRegistry stores instances under configs[name]["instance"] once loaded by AgentLoader.
            for name, cfg in (getattr(self.agent_registry, "configs", {}) or {}).items():
                if isinstance(cfg, dict) and cfg.get("instance") is not None:
                    instantiated_nodes.add(name)
        except Exception:
            instantiated_nodes = set()

        # If we have any instantiated nodes at all, enforce "callable" == "instantiated".
        # Otherwise (e.g., non-manager AgentFactory usage), fall back to config-exists behavior.
        enforce_instantiated = len(instantiated_nodes) > 0
        availability_set = instantiated_nodes if enforce_instantiated else all_nodes

        valid_nodes = [a for a in allowed_nodes if a in availability_set and a not in except_nodes]

        missing_configs = allowed_nodes - all_nodes
        if missing_configs:
            logger.warning(f"[{self.name}] References unavailable agents (no config): {missing_configs}")

        if enforce_instantiated:
            not_instantiated = (allowed_nodes & all_nodes) - instantiated_nodes
            if not_instantiated:
                logger.warning(
                    f"[{self.name}] References agents not instantiated in this runtime: {not_instantiated}"
                )

        logger.debug(f"[{self.name}] Final allowed nodes: {valid_nodes}")
        return valid_nodes

    def get_tools(self) -> list:
        agent_config = self.agent_registry.get_agent_config(self.name)
        if not agent_config:
            logger.warning(f"[{self.name}] Agent not found in registry.")
            return []
        allowed_tools = agent_config.get("allowed_tools", [])
        if allowed_tools == "all":
            allowed_tools = set(self.tool_registry.list_tools())  # ✅ Get all tools
        else:
            allowed_tools = set(allowed_tools)
        except_tools = set(agent_config.get("except_tools", []))
        all_available_tools = set(self.tool_registry.list_tools())
        valid_tools = [tool for tool in allowed_tools if tool in all_available_tools and tool not in except_tools]
        missing_tools = allowed_tools - all_available_tools
        if missing_tools:
            logger.warning(f"[{self.name}] References unavailable tools: {missing_tools}")
        logger.debug(f"[{self.name}] Final allowed tools: {valid_tools}")
        return valid_tools

    def get_tool_descriptions(self):
        allowed_tools = self.get_tools()
        tool_descriptions = self.tool_registry.get_tool_descriptions(allowed_tools)
        # logger.info(f"[{self.name}] Tool descriptions fetched: {tool_descriptions}")
        return tool_descriptions

    def get_tool_arguments_prompt(self):
        allowed_tools = self.get_tools()
        tool_argument_prompts = self.tool_registry.get_tool_arguments_prompt(allowed_tools)
        return tool_argument_prompts

    # Build a labeled, chronological log with only the last real tool_result

    def build_recent_history(self, agent_messages):
        """
        Build a single content string from an agent's message history.

        Rules:
        - Only consider these types: tool_request, agent_request, tool_result, agent_result, tool_result_summary.
        - If there are no summaries at all, concatenate contents in order and return.
        - If summaries exist, prefer the summary right after a raw result, except keep the very last raw result as raw.
        - Messages are already in creation order.
        """
        ALLOWED = {
            "tool_result",
            "agent_result",
            "tool_request",
            "tool_result_summary",
            "agent_request",
        }

        # 1) Prune to the five kinds
        msgs = [m for m in agent_messages if getattr(m, "data_type", None) in ALLOWED]

        # Helper to get safe content
        def _safe_content(m):
            c = getattr(m, "content", "")
            return "" if c is None else str(c).strip()

        # Helper to include attachment markers (e.g., MCP screenshots saved to disk).
        # We keep these as plain text lines so downstream prompt parsing can extract paths
        # without dealing with JSON escaping.
        def _attachment_markers(m) -> str:
            meta = getattr(m, "metadata", None)
            if not isinstance(meta, dict):
                return ""
            atts = meta.get("attachments")
            if not isinstance(atts, list) or not atts:
                return ""
            lines: list[str] = []
            for att in atts:
                if not isinstance(att, dict):
                    continue
                if att.get("type") != "image":
                    continue
                p = att.get("path")
                if not isinstance(p, str) or not p.strip():
                    continue
                fname = att.get("original_filename") or os.path.basename(p)
                lines.append(f"[image attached: {fname}]")
            return "\n".join(lines).strip()

        # Helper to include tool-result artifact pointers for on-demand retrieval.
        # These are intentionally short; the agent can call `read_tool_result` if needed.
        def _tool_result_ref_markers(m) -> str:
            meta = getattr(m, "metadata", None)
            if not isinstance(meta, dict):
                return ""
            tool_result_id = meta.get("tool_result_id")
            if isinstance(tool_result_id, str) and tool_result_id.strip():
                return f"[tool_result_id: {tool_result_id.strip()}]"
            return ""

        # 2) Simple path if no summaries present
        has_summary = any(getattr(m, "data_type", None) == "tool_result_summary" for m in msgs)
        if not has_summary:
            pieces = []
            for m in msgs:
                ct = _safe_content(m)
                extra_a = _attachment_markers(m)
                extra_r = _tool_result_ref_markers(m)
                combined = "\n".join([x for x in (ct, extra_a, extra_r) if x]).strip()
                if combined:
                    pieces.append(combined)
            return "\n\n".join(pieces).strip()

        # 3) Summary path with single pass and lookahead
        pieces = []
        i = 0
        n = len(msgs)

        while i < n:
            m = msgs[i]
            dt = getattr(m, "data_type", None)

            if dt in ("tool_request", "agent_request"):
                ct = _safe_content(m)
                if ct:
                    pieces.append(ct)
                i += 1
                continue

            if dt in ("tool_result", "agent_result"):
                # If this is the last message, keep raw
                if i == n - 1:
                    ct = _safe_content(m)
                    extra = _attachment_markers(m)
                    combined = "\n".join([x for x in (ct, extra) if x]).strip()
                    if combined:
                        pieces.append(combined)
                    i += 1
                    continue

                # Prefer immediate summary if present
                nxt = msgs[i + 1]
                if getattr(nxt, "data_type", None) == "tool_result_summary":
                    ct = _safe_content(nxt)
                    if len(ct) > 0:
                        ct = "SUMMARY CREATED: " + ct
                    extra_a = _attachment_markers(m)
                    extra_r = _tool_result_ref_markers(m)
                    combined = "\n".join([x for x in (ct, extra_a, extra_r) if x]).strip()
                    if combined:
                        pieces.append(combined)
                    i += 2  # skip the summary we just emitted
                else:
                    ct = _safe_content(m)
                    extra_a = _attachment_markers(m)
                    extra_r = _tool_result_ref_markers(m)
                    combined = "\n".join([x for x in (ct, extra_a, extra_r) if x]).strip()
                    if combined:
                        pieces.append(combined)
                    i += 1
                continue

            if dt == "tool_result_summary":
                i += 1
                continue

            # Fallback for any unexpected type that slipped through
            ct = _safe_content(m)
            if ct:
                pieces.append(ct)
            i += 1

        return "\n\n".join(pieces).strip()

    def _format_entity_field(self, entities: List[str], field_name: str) -> str:
        if not entities: return ""
        from app.models.base import get_session
        from app.assistant.entity_management.entity_cards import get_entity_card_by_name, extract_entity_field
        session = get_session()
        blocks = []
        try:
            for name in entities:
                card = get_entity_card_by_name(session, name)
                if card:
                    val = extract_entity_field(card, field_name)
                    if val: blocks.append(f"• {name}:\n{val}")
        finally:
            session.close()
        return "\n\n".join(blocks)

    def _format_entity_multi_field(self, entities: List[str], field_names: List[str]) -> str:
        """
        Format multiple entity fields grouped by entity.
        Example output:
            Entity1:
              Summary: ...
              Key Facts: ...
              Relationships: ...
            
            Entity2:
              Summary: ...
              Key Facts: ...
        """
        if not entities or not field_names:
            return ""

        from app.models.base import get_session
        from app.assistant.entity_management.entity_cards import get_entity_card_by_name, extract_entity_field
        session = get_session()
        blocks = []
        try:
            for entity_name in entities:
                card = get_entity_card_by_name(session, entity_name)
                if not card:
                    continue

                # Gather all requested fields for this entity
                entity_parts = [f"{entity_name}:"]
                for field_name in field_names:
                    val = extract_entity_field(card, field_name)
                    # Debug logging for metadata
                    if field_name == "metadata":
                        from app.assistant.utils.logging_config import get_logger
                        logger = get_logger(__name__)
                        meta_raw = getattr(card, "card_metadata", None)
                        logger.debug(
                            f"Entity {entity_name} metadata extraction: field_name={field_name}, meta_raw={meta_raw}, val={val[:100] if val else 'EMPTY'}")
                    if val:
                        # Format field name nicely (e.g., "key_facts" -> "Key Facts")
                        display_name = field_name.replace("_", " ").title()
                        entity_parts.append(f"  {display_name}: {val}")

                # Only add if we got at least one field
                if len(entity_parts) > 1:
                    blocks.append("\n".join(entity_parts))
        finally:
            session.close()

        return "\n\n".join(blocks)

    def _resolve_resource(self, resource_id: str) -> Any:
        """
        Resolve a resource by its identifier.

        For now:
          - Read from DI.global_blackboard, which is shared across managers.
          - If not found there, fall back to this agent's local blackboard.
          - If value is a Jinja template, render it on-demand with current context
          - Always return a concrete value (or "").
        """
        if not resource_id:
            return ""

        value = None

        # Preferred: global blackboard shared by all managers
        global_bb = getattr(DI, "global_blackboard", None)
        if global_bb is not None:
            try:
                getter = getattr(global_bb, "get_state_value", None)
                if callable(getter):
                    value = getter(resource_id, None)
            except Exception as e:
                logger.error(f"[{self.name}] Error reading resource '{resource_id}' from global_blackboard: {e}")

        # Fallback: local blackboard (useful in tests or bootstrap)
        if value is None:
            try:
                value = self.blackboard.get_state_value(resource_id, None)
            except Exception as e:
                logger.error(f"[{self.name}] Error reading resource '{resource_id}' from local blackboard: {e}")

        if value is None:
            logger.info(f"[{self.name}] Resource '{resource_id}' not found in global or local blackboard.")
            return ""

        # If value is a Jinja template string, render it on-demand with current data
        if isinstance(value, str) and ('{{' in value or '{%' in value):
            try:
                from jinja2 import Template
                # Build context from all resources in global blackboard
                context = {}
                if global_bb is not None:
                    # Get all *_data resources for template context
                    for key in ['resource_user_data', 'resource_assistant_data',
                                'resource_assistant_personality_data', 
                                'resource_relationship_config', 'resource_chat_guidelines_data']:
                        data = global_bb.get_state_value(key, None)
                        if data is not None:
                            context[key] = data
                
                template = Template(value)
                rendered = template.render(**context)
                return rendered
            except Exception as e:
                logger.error(f"[{self.name}] Error rendering template for '{resource_id}': {e}")
                return value  # Return raw template as fallback

        return value

    def generate_injections_block(self, prompt_injections, message=None):
        """
        Build a context dict for prompt rendering.

        Phase 1:
          - Resolve all non-entity injections from blackboard and helpers.
        Phase 2:
          - If any entity_* keys are requested, entity injection is handled as a two-pass render
            in get_user_prompt() (render-without-entities -> detect -> render-with-entities).
            This method only ensures entity placeholders exist.
        """

        if not isinstance(prompt_injections, list):
            raise ValueError(
                f"[{self.name}] 'context_items' must be a list, but got: "
                f"{type(prompt_injections).__name__} ({prompt_injections})"
            )

        # Split requested keys
        entity_keys = [
            key for key in prompt_injections
            if key.startswith("entity_")
        ]
        non_entity_keys = [
            key for key in prompt_injections
            if key not in entity_keys
        ]

        # Extract field names from entity_* keys
        entity_field_keys = [
            key[len("entity_"):] for key in entity_keys
            if key.startswith("entity_")
        ]

        # Base context
        context: Dict[str, Any] = {
            "date_time": get_local_time_str(),
            "action_count": self.blackboard.get_state_value(f"{self.name}_action_count", 0),
            "rag": "",
        }

        # Optional: keep incoming_message for templates, but do not rely on it for entities
        if message and getattr(message, "content", None):
            context["incoming_message"] = message.content.strip()

        rag_fields = self.config.get("rag_fields", {})

        # ------------------------------------------------------------
        # Phase 1: resolve all non entity injections
        # ------------------------------------------------------------
        for key in non_entity_keys:
            if key in context:
                # Already set (date_time, action_count, incoming_message, etc.)
                continue

            # Pipeline state injections (no legacy blackboard keys).
            if key in {
                "selected_tool",
                "pending_tool_name",
                "tool_arguments",
                "pending_tool_arguments",
                "action_input",
                "pending_action_input",
                "pending_tool_calling_agent",
                "pipeline_stage",
            }:
                ps = ensure_pipeline_state(self.blackboard)
                pending = get_pending_tool(self.blackboard) or {}
                if key in ("selected_tool", "pending_tool_name"):
                    context[key] = pending.get("name")
                elif key in ("tool_arguments", "pending_tool_arguments"):
                    context[key] = pending.get("arguments")
                elif key in ("action_input", "pending_action_input"):
                    context[key] = pending.get("action_input")
                elif key == "pending_tool_calling_agent":
                    context[key] = pending.get("calling_agent")
                elif key == "pipeline_stage":
                    context[key] = ps.get("stage")
                continue

            # Resource injection: keys starting with "resource_"
            # Example:
            #   system_context_items: ["resource_daily_schedule"]
            #   Template: {{ resource_daily_schedule }}
            #   Source: DI.global_blackboard["resource_daily_schedule"]
            if key.startswith("resource_"):
                # Keep the full resource_ prefix in the context
                resolved_value = self._resolve_resource(key)
                context[key] = resolved_value
                continue

            if key == "tool_descriptions":
                tool_desc = self.get_tool_descriptions() or {}
                if not isinstance(tool_desc, dict):
                    logger.error(f"[{self.name}] tool_descriptions must be a dict, got: {type(tool_desc)}")
                    tool_desc = {}
                context[key] = tool_desc
                continue

            if key == "allowed_nodes":
                allowed = self.get_allowed_nodes()
                agent_descriptions = []
                for name in allowed:
                    agent_config = self.agent_registry.get_agent_config(name) or {}
                    prompts = agent_config.get("prompts", {})
                    raw_description = prompts.get("description", "")

                    try:
                        template = Template(raw_description)
                        rendered_description = template.render(
                            self_name=name,
                            self_short_name=name.split("::")[-1]
                        )
                    except Exception as e:
                        logger.error(f"[{self.name}] Error rendering description for agent '{name}': {e}")
                        rendered_description = raw_description  # fallback to unrendered

                    agent_descriptions.append({
                        "name": name,
                        "description": rendered_description
                    })

                context[key] = agent_descriptions
                continue

            if key == "recent_history":
                current_scope_id = self.blackboard.get_current_scope_id()
                msgs = self.blackboard.get_messages_for_scope(current_scope_id)
                context[key] = self.build_recent_history(msgs)
                continue

            # Default: pull from blackboard
            value = self.blackboard.get_state_value(key, None)

            # Attach RAG if configured for this key
            if isinstance(rag_fields, dict) and key in rag_fields:
                scopes = rag_fields.get(key) or []
                rag_val = self.retrieve_rag_context(value, scopes=scopes)
                if rag_val:
                    context["rag"] += f"{rag_val}\n"

            context[key] = value

        # If no entity based injections requested, we are done
        if not entity_keys:
            return context

        # Ensure consistent placeholders exist for two-pass render logic.
        for key in entity_keys:
            context.setdefault(key, "")
        if len(entity_field_keys) > 0:
            context.setdefault("entity_info", "")

        return context

    def retrieve_rag_context(self, query, scopes=None):
        """
        Retrieve relevant context using semantic retrieval only.
        Caches results to avoid redundant computation.
        """
        if not query or query == "[MISSING]":
            return None

        cached_results = get_cached_rag_result(query)
        if cached_results:
            logger.debug(f"[{self.name}] Using cached RAG results for query: {query}")
            return cached_results

        # Start timing RAG retrieval
        timer_id = performance_monitor.start_timer(f'rag_retrieval_{self.name}', f"{len(scopes or [])}_scopes")

        retrieved_info = []
        try:
            semantic_results = query_rag_database(query, scopes=scopes, top_k=2,
                                                  threshold=0.55)  # Reduced top_k from 3 to 2, threshold from 0.65 to 0.55
        except Exception as e:
            logger.error(f"[{self.name}] Error in semantic RAG retrieval: {e}")
            performance_monitor.end_timer(timer_id, {'status': 'error', 'error': str(e)})
            return None

        if semantic_results:
            retrieved_info.append("### Semantic Retrieved Documents:")
            for result in semantic_results:
                retrieved_info.append(
                    f"- {result['document']} (source: {result['source']}, similarity: {result['similarity']:.2f})"
                )

        formatted_results = "\n".join(retrieved_info) if retrieved_info else None
        cache_rag_result(query, formatted_results)

        # End timing and record success
        performance_monitor.end_timer(timer_id, {
            'status': 'success',
            'agent_name': self.name,
            'query_length': len(query),
            'scopes_count': len(scopes or []),
            'results_count': len(semantic_results) if semantic_results else 0
        })

        return formatted_results

    def _apply_llm_result_to_state(self, result_dict: dict):
        """
        SHARED LOGIC: Handles writing LLM output to the correct state scope
        (local or global) based on the agent's configuration.
        This is a core part of the template and is not meant to be overridden.
        """
        if not isinstance(result_dict, dict):
            return

        global_keys = self.config.get("global_output_keys", [])

        for key, value in result_dict.items():
            is_global = key in global_keys

            if key in self.append_fields:
                if is_global:
                    self.blackboard.append_global_state_value(key, value)
                else:
                    self.blackboard.append_state_value(key, value)
            else:
                if is_global:
                    self.blackboard.update_global_state_value(key, value)
                else:
                    self.blackboard.update_state_value(key, value)

    def _create_response_message(self, result_dict: dict):
        if not isinstance(result_dict, dict):
            raise TypeError(f"[{self.name}] Expected dict in _create_response_message, got {type(result_dict)}")

        try:
            result_json = json.dumps(result_dict)
        except TypeError as e:
            logger.error(f"[{self.name}] Non serializable data in result_dict: {e}. Data: {result_dict}")
            raise

        action = str(result_dict.get("action", "")).lower()
        is_exit_action = "exit" in action
        sub_data_type = ["result"] if is_exit_action else []

        msg = Message(
            data_type="agent_response",
            sub_data_type=sub_data_type,
            sender=self.name,
            receiver="Blackboard",
            content=f"{self.name} acted. Result: {result_json}",
        )
        self.blackboard.add_msg(msg)

    def _handle_flow_control(self, result_dict: dict):
        """
        SHARED LOGIC: Handles the generic logic for tool calls, agent transitions,
        and exiting the flow. This is a core part of the template.
        """
        action = result_dict.get('action')

        assert action != "error", f"[{self.name}] Invalid action 'error' leaked into flow control."

        if action:
            if action == "flow_exit_node":
                exit_signal = f"{self.name}_flow_exit_node"
                print(f"\n🚪 [{self.name}] FLOW EXIT: Setting last_agent = '{exit_signal}'")
                self.blackboard.update_state_value("last_agent", exit_signal)
                self.blackboard.update_state_value("next_agent", None)
                # The agent's final result is stored in the current scope (not global, not agent-specific)
                # ToolResultHandler will retrieve this before popping the scope
                if result_dict.get('result'):
                    print(f"📦 [{self.name}] Storing result in current scope")
                    self.blackboard.update_state_value("result", result_dict.get('result'))
                else:
                    print(f"📦 [{self.name}] Storing result_dict in current scope")
                    self.blackboard.update_state_value("result", result_dict)
            elif action == "done":
                # Agent is finished but NOT exiting the scope - let flow config handle routing
                print(f"\n✅ [{self.name}] DONE: Setting last_agent = '{self.name}', next_agent = None")
                self.blackboard.update_state_value("last_agent", self.name)
                self.blackboard.update_state_value("next_agent", None)
                # Store result if provided (for flow transitions)
                if result_dict.get('result'):
                    print(f"📦 [{self.name}] Storing result in current scope")
                    self.blackboard.update_state_value("result", result_dict.get('result'))
            else:
                set_pending_tool(
                    self.blackboard,
                    name=action,
                    calling_agent=self.name,
                    action_input=result_dict.get("action_input"),
                    arguments=None,
                    kind=None,
                )
                self.blackboard.update_state_value("next_agent", "shared::tool_arguments")

    def process_llm_result(self, result):
        """
        The main template method for processing LLM results.
        It orchestrates the validation, state updates, messaging, and flow control.
        """

        self._maybe_print_llm_result(result)

        # Step 1: Validate input
        if isinstance(result, str):
            logger.error(f"[{self.name}] LLM returned plain string (invalid structured output): {result}")
            raise ValueError(f"[{self.name}] Expected dict from LLM, got string.")
        if not isinstance(result, dict):
            logger.error(f"[{self.name}] LLM result is not a dict: {type(result)}")
            raise TypeError(f"[{self.name}] Expected dict from LLM, got {type(result)}.")

        result_dict = result

        # Step 2: Apply state changes (Shared Logic)
        self._apply_llm_result_to_state(result_dict)

        # Step 3: Create response message (Overridable Logic)
        self._create_response_message(result_dict)

        # Step 4: Handle flow control (Shared Logic)
        self._handle_flow_control(result_dict)

        # Step 4b: Emit a small progress fact for UI (no chain-of-thought).
        # Only do this for planners to avoid flooding the UI.
        try:
            if str(self.name).endswith("::planner") or str(self.name).endswith(":planner") or str(self.name).endswith("_planner"):
                task = self.blackboard.get_state_value("task")
                manager_name = ""
                try:
                    manager_name = getattr(self.parent, "name", "") if self.parent is not None else ""
                except Exception:
                    manager_name = ""

                fact = {
                    "kind": "planner_decision",
                    "agent": self.name,
                    "manager": manager_name,
                    "task": task,
                    "action": result_dict.get("action"),
                    "action_input": result_dict.get("action_input"),
                    # Avoid what_i_am_thinking; it is not for UI.
                    "learned": (result_dict.get("summary") or "").strip() if isinstance(result_dict.get("summary"), str) else "",
                    "action_count": self.blackboard.get_state_value("action_count"),
                }
                DI.event_hub.publish(
                    Message(
                        sender=self.name,
                        receiver=None,
                        event_topic="agent_progress_fact",
                        data=fact,
                    )
                )
        except Exception:
            pass

        return ToolResult(
            result_type="llm_result",
            content=f"{self.name} acted.",
            data=result_dict
        )
