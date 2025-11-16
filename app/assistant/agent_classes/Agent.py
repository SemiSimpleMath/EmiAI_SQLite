from datetime import datetime, timezone
import json
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
            "engine": "gpt-4o-mini",
            "temperature": 0.1,
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
                logger.error(f"❌ LLM QUOTA ERROR DETECTED in agent: {self.name}")
                logger.error(f"   Response preview: {str(response_text)[:500]}")
                logger.error(f"   Keyword: '{keyword}'")
                logger.error(f"🛑 Exiting pipeline due to LLM quota exhaustion")
                print(f"\n{'=' * 80}")
                print(f"❌ CRITICAL ERROR: LLM Quota Exhausted")
                print(f"{'=' * 80}")
                print(f"Agent: {self.name}")
                print(f"Detected keyword: '{keyword}'")
                print(f"Response preview: {str(response_text)[:500]}")
                print(f"{'=' * 80}")
                print(f"🛑 Pipeline stopped. Please check your LLM quota and try again.")
                print(f"{'=' * 80}\n")
                sys.exit(1)

    def _update_blackboard_state(self, message: Message):
        self.blackboard.update_state_value('next_agent', None)
        self.blackboard.update_state_value('tool_call', None)
        self.blackboard.update_state_value('tool_arguments', None)

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
        self._update_blackboard_state(message)
        self._store_incoming_message(message)

        # Update last acting agent
        self.blackboard.update_state_value('last_agent', self.name)

        try:
            messages = self.construct_prompt(message)
        except Exception as e:
            logger.error(f"[{self.name}] Error during prompt construction: {e}, {message}")
            performance_monitor.end_timer(timer_id, {'status': 'error', 'error': 'prompt_construction_failed'})
            exit(1)

        schema = self.config.get('structured_output')

        result = self._run_llm_with_schema(messages, schema)

        self._add_extra_msgs(message)

        try:
            result = self.process_llm_result(result)
        except Exception as e:
            print(f"Error: {e}")
            performance_monitor.end_timer(timer_id, {'status': 'error', 'error': 'llm_result_processing_failed'})
            raise

        self._set_agent_idle()

        # End timing and record success
        performance_monitor.end_timer(timer_id, {
            'status': 'success',
            'agent_name': self.name,
            'message_id': message.id
        })

        return result

    def call_llm(
            self,
            messages: List[Dict[str, str]],
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

            # Debug print prompts
            for msg in messages:
                role = msg.get("role")
                content = msg.get("content", "")
                if role == "system":
                    print(f"\n{'=' * 60}")
                    print(f"SYSTEM PROMPT {self.name}")
                    print(f"{'=' * 60}")
                    print(content)
                    print(f"{'=' * 60}\n")
                elif role == "user":
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

    def construct_prompt(self, message: Message = None) -> List[Dict[str, str]]:
        system_prompt = self.get_system_prompt(message).replace('\n\n', '\n')
        user_prompt = self.get_user_prompt(message).replace('\n\n', '\n')

        if not system_prompt:
            logger.error(f"[{self.name}] Error forming the system prompt.")
        if not user_prompt:
            logger.error(f"[{self.name}] Error forming the user prompt.")

        system_prompt = re.sub(r'\n{3,}', '\n\n', system_prompt)
        user_prompt = re.sub(r'\n{3,}', '\n\n', user_prompt)

        # Normalize to ASCII to prevent encoding issues
        system_prompt = normalize_to_ascii(system_prompt)
        user_prompt = normalize_to_ascii(user_prompt)

        msg = [
            {'role': 'system', 'content': system_prompt or f"[{self.name}] Error forming system prompt."},
            {'role': 'user', 'content': user_prompt or f"[{self.name}] Error forming user prompt."}
        ]
        return msg

    def get_system_prompt(self, message: Message = None):
        system_prompt_template = self.config.get("prompts", {}).get("system", "")

        if not system_prompt_template:
            logger.error(f"[{self.name}] No system prompt found.")
            exit(1)
            return f"No system prompt available for {self.name}."

        # Load context items
        prompt_injections = self.config.get("system_context_items", [])
        
        # DEBUG
        logger.info(f"[{self.name}] system_context_items from config: {prompt_injections}")

        if prompt_injections is not None:
            system_context = self.generate_injections_block(prompt_injections, message)
            # DEBUG
            logger.info(f"[{self.name}] Generated system_context keys: {list(system_context.keys())}")
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
                print(f"Error: {e}")
                raise e
        else:
            user_context = {}

        try:
            template = Template(user_prompt_template)
            rendered_output = template.render(**user_context or {}).replace('\n\n', '\n')
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
        valid_nodes = [a for a in allowed_nodes if a in all_nodes and a not in except_nodes]

        missing_agents = allowed_nodes - all_nodes
        if missing_agents:
            logger.warning(f"[{self.name}] References unavailable agents: {missing_agents}")

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

        # 2) Simple path if no summaries present
        has_summary = any(getattr(m, "data_type", None) == "tool_result_summary" for m in msgs)
        if not has_summary:
            pieces = [ct for ct in (_safe_content(m) for m in msgs) if ct]
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
                    if ct:
                        pieces.append(ct)
                    i += 1
                    continue

                # Prefer immediate summary if present
                nxt = msgs[i + 1]
                if getattr(nxt, "data_type", None) == "tool_result_summary":
                    ct = _safe_content(nxt)
                    if len(ct) > 0:
                        ct = "SUMMARY CREATED: " + ct
                    if ct:
                        pieces.append(ct)
                    i += 2  # skip the summary we just emitted
                else:
                    ct = _safe_content(m)
                    if ct:
                        pieces.append(ct)
                    i += 1
                continue

            if dt == "tool_result_summary":
                # With your invariants, summaries are emitted via the raw branch. Skip here.
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
                    for key in ['resource_user_data', 'resource_assistant_personality_data', 
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
          - If any entity_* keys are requested, run a single entity detection pass
            over the serialized context and fill all entity_* injections from that.
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

            # Resource injection: keys starting with "resource_"
            # Example:
            #   system_context_items: ["resource_daily_schedule"]
            #   Template: {{ resource_daily_schedule }}
            #   Source: DI.global_blackboard["resource_daily_schedule"]
            if key.startswith("resource_"):
                # Keep the full resource_ prefix in the context
                logger.info(f"[{self.name}] Processing resource: {key}")
                resolved_value = self._resolve_resource(key)
                logger.info(f"[{self.name}] Resolved resource '{key}' type: {type(resolved_value)}, value preview: {str(resolved_value)[:100] if resolved_value else 'None'}")
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

        # ------------------------------------------------------------
        # Phase 2: single entity detection over full context
        # ------------------------------------------------------------

        try:
            # Serialize the current context (Phase 1 only) to a single text blob
            serialized_context = json.dumps(context, default=str, ensure_ascii=False)
        except Exception as e:
            logger.error(f"[{self.name}] Failed to serialize context for entity detection: {e}")
            serialized_context = " ".join(str(v) for v in context.values() if v is not None)

        detected_entities: List[str] = []
        if serialized_context.strip():
            try:
                from app.assistant.entity_management.entity_card_injector import EntityCardInjector
                injector = EntityCardInjector()
                detected = injector.detect_entities_in_text(serialized_context) or []
                # Deduplicate while preserving order
                seen = set()
                for ent in detected:
                    if ent not in seen:
                        seen.add(ent)
                        detected_entities.append(ent)
                if detected_entities:
                    logger.info(f"[{self.name}] Detected entities in composed context: {detected_entities}")
            except Exception as e:
                logger.error(f"[{self.name}] Entity detection failed: {e}")

        # If no entities found, still set all requested entity_* keys to ""
        if not detected_entities:
            for key in entity_keys:
                context.setdefault(key, "")
            # Also set entity_info if any entity fields were requested (even just one)
            if len(entity_field_keys) > 0:
                context["entity_info"] = ""
            return context

        # ------------------------------------------------------------
        # Phase 3: populate entity_* injections from detected_entities
        # ------------------------------------------------------------
        # Always group entity fields under "entity_info" (even if just one field)
        # This ensures consistent grouping by entity rather than by field

        # Check if we have any entity fields
        has_entity_fields = len(entity_field_keys) > 0

        if has_entity_fields:
            # Gather ALL entity info, then group by entity under "entity_info"
            context["entity_info"] = self._format_entity_multi_field(detected_entities, entity_field_keys)
            # Set all individual entity_* keys to empty since we're using entity_info instead
            for key in entity_keys:
                if key.startswith("entity_"):
                    context[key] = ""  # Empty since we're using entity_info instead

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
        sub_data_type = "result" if is_exit_action else None

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
        # All control variables are written to the local scope
        self.blackboard.update_state_value("selected_tool", action)

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
                self.blackboard.update_state_value("original_calling_agent", self.name)
                self.blackboard.update_state_value("next_agent", "shared::tool_arguments")

    def process_llm_result(self, result):
        """
        The main template method for processing LLM results.
        It orchestrates the validation, state updates, messaging, and flow control.
        """

        print(f"\n\n--- LLM RESULT for {self.name} ---")
        print(json.dumps(result, indent=2) if isinstance(result, dict) else result)
        print("---------------------------------\n")

        # Step 1: Validate input HARD
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

        return ToolResult(
            result_type="llm_result",
            content=f"{self.name} acted.",
            data=result_dict
        )
