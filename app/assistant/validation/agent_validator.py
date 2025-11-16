import re
from pathlib import Path
import yaml
from app.assistant.agent_registry.agent_registry import AgentRegistry

def validate_all(agent_registry: AgentRegistry):
    print("🔍 Running agent registry validation...")

    _check_namespace_consistency()
    _check_prompt_integrity(agent_registry)
    _check_context_usage(agent_registry)
    _check_manager_configs(set(agent_registry.list_agents()))

    print("✅ Agent system validation complete.")

def _check_namespace_consistency():
    base_dir = Path("app/assistant/agents")
    seen = set()
    for folder in base_dir.rglob("config.yaml"):
        rel = folder.parent.relative_to(base_dir)
        namespace = str(rel.parent).replace("/", "_") if rel.parent != Path(".") else None
        with open(folder) as f:
            config = yaml.safe_load(f)

        if not isinstance(config, dict):
            raise RuntimeError(f"❌ Invalid or empty config in {folder}. Got: {config}")

        name = config.get("name")
        expected = f"{namespace}::{name}" if namespace else name
        if expected in seen:
            raise RuntimeError(f"❌ Duplicate agent name: {expected}")
        seen.add(expected)

def _check_prompt_integrity(registry: AgentRegistry):
    for agent_name, config in registry.configs.items():
        # Skip control nodes - they don't have prompts
        if config.get("type") == "control_node":
            continue
            
        prompt_dir = Path("app/assistant/agents") / agent_name.replace("::", "/") / "prompts"
        if not (prompt_dir / "system.j2").exists():
            print(f"❌ {agent_name} is missing system.j2")
        if not (prompt_dir / "user.j2").exists():
            print(f"⚠️  {agent_name} is missing user.j2")
        # Note: description.j2 is only needed for agents that are called by other agents (e.g., shared::writer)
        # Most workflow agents don't need descriptions, so we don't warn about missing description.j2

def _check_context_usage(registry: AgentRegistry):
    # Map of sub-components to their parent components
    # These are declared separately in config but injected as part of their parent
    SUB_COMPONENT_MAP = {
        'entity_summary': 'entity_info',
        'entity_metadata': 'entity_info',
        # Add more mappings here as needed
    }
    
    for agent_name, config in registry.configs.items():
        # Skip control nodes - they don't have prompts
        if config.get("type") == "control_node":
            continue
            
        prompts = config.get("prompts", {})

        def check_usage(context_key: str, prompt_text: str, prompt_name: str):
            fields = config.get(context_key, [])
            for field in fields:
                # Check if field is a sub-component
                parent_field = SUB_COMPONENT_MAP.get(field)
                
                if parent_field:
                    # For sub-components, check if parent is present in the prompt
                    if parent_field not in prompt_text:
                        print(
                            f"❌ {agent_name}: {context_key} declares sub-component '{field}', "
                            f"but parent '{parent_field}' is not found in {prompt_name}.j2"
                        )
                else:
                    # Standard check: if the field name appears anywhere in the prompt, it's used
                    if field not in prompt_text:
                        print(
                            f"❌ {agent_name}: {context_key} declares '{field}', but it's not found in {prompt_name}.j2"
                        )

        if "system" in prompts:
            check_usage("system_context_items", prompts["system"], "system")

        if "user" in prompts:
            check_usage("user_context_items", prompts["user"], "user")


def _check_manager_configs(agent_names):
    managers_dir = Path("app/assistant/multi_agents")
    for path in managers_dir.rglob("*.yaml"):
        with open(path) as f:
            config = yaml.safe_load(f)

        used_agents = {a["name"] for a in config.get("agents", [])}
        unknown = used_agents - agent_names
        if unknown:
            raise RuntimeError(f"❌ {path} {path.name}: references unknown agents: {unknown}")

        state_map = config.get("flow_config", {}).get("state_map", {})
        flow_keys = set(state_map.keys())
        flow_targets = set(state_map.values())
        all_flow = flow_keys | flow_targets

        unused = used_agents - all_flow
        if unused:
            print(f"⚠️  {path.name}: declared agents not used in flow_config: {unused}")
