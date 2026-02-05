# app/assistant/agent_registry/agent_registry.py
import importlib.util
from typing import List

import yaml
from pathlib import Path
from pydantic import BaseModel

# Set up logging
from app.assistant.control_nodes.control_node import ControlNode

from app.assistant.utils.logging_config import get_logger
logger = get_logger(__name__)


PROJECT_ROOT = Path(__file__).resolve().parents[2]  # Ensure absolute root path


class AgentRegistry:
    def __init__(self, agents_dir=None, control_nodes_dir=None):
        """Ensure proper paths to avoid duplicate 'app' in directory paths."""
        self.agents_dir = Path(agents_dir or (PROJECT_ROOT / "assistant/agents")).resolve()
        self.control_nodes_dir = Path(control_nodes_dir or (PROJECT_ROOT / "assistant/control_nodes")).resolve()

        self.configs = {}

        self.registry_loaded = False

    def load_agents(self):
        # load agents
        self._load_all_agent_configs()
        # Load control nodes
        self.control_nodes = self._load_all_control_nodes()

        self.registry_loaded = True

    def fork(self):
        """
        Create a lightweight copy of the registry suitable for parallel managers/orchestrators.

        - Shares immutable config data and loaded classes/prompts
        - Clears per-agent `instance` fields so each runtime can instantiate independently
        - Avoids deepcopy (locks/clients/lambdas can break deepcopy and it's expensive)
        """
        child = AgentRegistry(agents_dir=self.agents_dir, control_nodes_dir=self.control_nodes_dir)
        # Preserve loaded state and control nodes.
        child.registry_loaded = bool(getattr(self, "registry_loaded", False))
        if hasattr(self, "control_nodes"):
            child.control_nodes = getattr(self, "control_nodes")

        # Shallow-copy configs, but remove any instantiated agent objects.
        new_configs = {}
        for name, cfg in (getattr(self, "configs", {}) or {}).items():
            if not isinstance(cfg, dict):
                new_configs[name] = cfg
                continue
            cfg2 = dict(cfg)
            cfg2.pop("instance", None)
            new_configs[name] = cfg2
        child.configs = new_configs
        return child

    def _load_all_agent_configs(self):
        """Load all agent configurations, prompts, structured outputs, and dynamically load agent classes."""

        if self.registry_loaded:
            import traceback
            print("=" * 80)
            print("⚠️  REGISTRY ALREADY LOADED - Attempted to reload!")
            print("=" * 80)
            print("Call stack:")
            for line in traceback.format_stack()[:-1]:
                print(line.strip())
            print("=" * 80)
            return

        if not self.agents_dir.exists():
            logger.error(f"Agents directory '{self.agents_dir}' does not exist.")
            return

        for agent_folder in self.agents_dir.rglob("*"):
            if not agent_folder.is_dir():
                continue
            if not (agent_folder / "config.yaml").exists():
                continue

            if (agent_folder / ".ignore").exists():
                logger.info(f"Skipping agent {agent_folder.name} (marked as .ignore)")
                continue

            config_data = self._load_config(agent_folder / "config.yaml")
            raw_name = config_data.get('name', None)
            if not raw_name:
                logger.warning(f"Agent name not found in {agent_folder.name}")
                continue

            rel_path = agent_folder.relative_to(self.agents_dir)

            # === Canonical name = namespace::name ===
            if "::" in raw_name:
                canonical_name = raw_name  # already fully namespaced
            else:
                if rel_path.parent == Path("."):
                    canonical_name = raw_name
                else:
                    # Handle multi-level directories with proper :: separators
                    namespace_parts = []
                    current_path = rel_path.parent
                    while current_path != Path("."):
                        namespace_parts.insert(0, current_path.name)
                        current_path = current_path.parent
                    
                    namespace = "::".join(namespace_parts)
                    canonical_name = f"{namespace}::{raw_name}"

            logger.info(f"📥 Loading configuration for agent: {canonical_name}")
            prompts = self._load_prompts(agent_folder / "prompts", canonical_name)
            # Structured output precedence:
            # 1) agent_form.py (Pydantic) if present (preferred / strongest)
            # 2) config.yaml structured_output (JSON schema dict) as a fallback
            structured_output = self._load_agent_form(agent_folder / "agent_form.py")
            if structured_output is None:
                structured_output = config_data.get("structured_output")
            else:
                if config_data.get("structured_output") is not None:
                    logger.info(
                        f"Agent {canonical_name} defines both agent_form.py and config.yaml structured_output; "
                        f"preferring agent_form.py."
                    )
            input_schema = self._load_agent_args(agent_folder / "input_schema.py")
            if canonical_name in self.configs:
                import traceback
                logger.warning(f"Duplicate agent name {canonical_name} in folder {agent_folder.name}")
                logger.warning(f"  First loaded from: {self.configs[canonical_name].get('_loaded_from', 'unknown')}")
                logger.warning(f"  Now loading from: {agent_folder}")
                print(f"\n⚠️  DUPLICATE AGENT DETECTED: {canonical_name}")
                print(f"  First: {self.configs[canonical_name].get('_loaded_from', 'unknown')}")
                print(f"  Second: {agent_folder}")
                print("Call stack for second load:")
                for line in traceback.format_stack()[:-1][-5:]:  # Show last 5 frames
                    print(f"  {line.strip()}")

            self.configs[canonical_name] = {
                **config_data,
                "prompts": prompts,
                "structured_output": structured_output,
                "type": "agent",
                "input_schema": input_schema,
                "_loaded_from": str(agent_folder)
            }

            agent_class = self._load_agent_class(canonical_name)
            self.configs[canonical_name]['class'] = agent_class
            logger.info(f"✅ Loaded agent: {canonical_name}, Class: {agent_class}")


        return


    def _load_prompts(self, prompts_dir, agent_name):
        """Load the system and user prompts for an agent."""
        prompts = {}
        if not prompts_dir.exists():
            logger.warning(f"Missing 'prompts' directory for agent: {agent_name}")
            return prompts

        system_prompt = prompts_dir / "system.j2"
        user_prompt = prompts_dir / "user.j2"
        description = prompts_dir/ "description.j2"

        if system_prompt.exists():
            try:
                with open(system_prompt, "r") as f:
                    prompts["system"] = f.read()
                logger.info(f"Loaded system prompt for {agent_name}")
            except Exception as e:
                logger.error(f"Error reading system.j2 for {agent_name}: {e}")
        else:
            logger.error(f"Error: No system prompt for {agent_name}")
            exit(1)

        if user_prompt.exists():
            try:
                with open(user_prompt, "r") as f:
                    prompts["user"] = f.read()
                logger.info(f"Loaded user prompt for {agent_name}")
            except Exception as e:
                logger.error(f"Error reading user.j2 for {agent_name}: {e}")

        else:
            logger.error(f"Error: No system prompt for {agent_name}")
            exit(1)

        if description.exists():
            try:
                with open(description, "r") as f:
                    prompts["description"] = f.read()
                logger.info(f"Loaded description for {agent_name}")
            except Exception as e:
                logger.error(f"Error reading user.j2 for {agent_name}: {e}")

        return prompts

    def _load_agent_args(self, agent_args_path):
        """Dynamically import and load the Pydantic input model from agent_args.py."""
        if not agent_args_path.exists():
            logger.info(f"No agent_args.py found for {agent_args_path.parent.name}")
            return None

        try:
            module_name = agent_args_path.stem
            spec = importlib.util.spec_from_file_location(module_name, agent_args_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Look for a Pydantic model in the module
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if isinstance(attr, type) and issubclass(attr, BaseModel) and attr is not BaseModel:
                    logger.info(f"Loaded input schema class {attr_name} from {agent_args_path}")
                    return attr

            logger.warning(f"No valid Pydantic input model found in {agent_args_path}")
            return None

        except Exception as e:
            logger.error(f"Error loading input schema from {agent_args_path}: {e}")
            return None

    def _load_agent_form(self, agent_form_path: Path):
        """Dynamically import and load the AgentForm class from agent_form.py."""
        if not agent_form_path.exists():
            logger.warning(f"Missing agent_form.py for {agent_form_path.parent.name}")
            return None

        try:
            module_name = agent_form_path.stem
            spec = importlib.util.spec_from_file_location(module_name, agent_form_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            preferred = "AgentForm"
            fallback = None

            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                        isinstance(attr, type)
                        and issubclass(attr, BaseModel)
                        and attr is not BaseModel
                ):
                    if attr_name == preferred:
                        logger.info(f"Loaded preferred structured output class {attr_name}")
                        return attr
                    if fallback is None:
                        fallback = attr

            if fallback:
                logger.warning(f"AgentForm not found, falling back to {fallback.__name__}")
                return fallback

            logger.warning(f"No valid Pydantic model found in {agent_form_path}")
            return None

        except Exception as e:
            logger.error(f"Error loading structured output from {agent_form_path}: {e}")
            return None



    def register_agent_class(self, agent_name, agent_class_reference):
        """Assigns the agent class reference to its config."""
        if agent_name in self.configs:
            self.configs[agent_name]["class"] = agent_class_reference
            logger.info(f"✅ Registered class {agent_class_reference} for agent {agent_name}")
        else:
            logger.warning(f"⚠️ Tried to register {agent_name}, but it's not in the registry.")

    def _load_agent_class(self, agent_name):
        """Dynamically load an agent class from `agent_classes/` based on `class_name` from config.yaml."""
        agent_config = self.configs.get(agent_name)
        if agent_config is None:
            raise RuntimeError(f"❌ Missing config for agent '{agent_name}'. "
                               f"Use full name (e.g., 'shared::tool_selector').")

        expected_class_name = agent_config.get("class_name")
        if not expected_class_name:
            raise ValueError(f"❌ Agent {agent_name} does not specify a `class_name` in its config.")

        agent_class_file = self.agents_dir.parent / "agent_classes" / f"{expected_class_name}.py"

        if not agent_class_file.exists():
            raise FileNotFoundError(f"❌ Expected class file `{agent_class_file}` for {agent_name} not found.")

        try:
            module_name = f"app.assistant.agent_classes.{expected_class_name}"
            spec = importlib.util.spec_from_file_location(module_name, agent_class_file)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # ✅ Ensure class exists and matches the expected name
            agent_class = getattr(module, expected_class_name, None)
            if not agent_class:
                raise ImportError(f"❌ Expected class `{expected_class_name}` not found inside `{agent_class_file}`. "
                                  f"Check that the class name matches the config.")

            logger.info(f"✅ Loaded class {expected_class_name} for agent {agent_name}")
            return agent_class

        except Exception as e:
            logger.error(f"❌ Error loading agent class {expected_class_name} from {agent_class_file}: {e}")
            raise

    def list_agents(self) -> List[str]:
        return list(self.configs.keys())


    def _load_config(self, config_file):
        """Load the agent's configuration file, including extra configs."""
        if not config_file.exists():
            logger.warning(f"Missing config.yaml for agent: {config_file.parent.name}")
            return {}

        try:
            with open(config_file, "r") as f:
                config = yaml.safe_load(f) or {}

            # ✅ Load extra configs if defined
            extra_configs = config.pop("extra_configs", [])
            for extra_config_path in extra_configs:
                extra_path = config_file.parent / extra_config_path
                if extra_path.exists():
                    with open(extra_path, "r") as extra_f:
                        extra_data = yaml.safe_load(extra_f) or {}
                    config_key = Path(extra_config_path).stem
                    config[config_key] = extra_data  # Store under dynamically determined key
                    logger.info(f"🔹 Merged extra config '{extra_config_path}' under key '{config_key}'")

            return config

        except Exception as e:
            logger.error(f"Error loading config file {config_file}: {e}")
            return {}

    def _load_all_control_nodes(self):
        """Scan the `control_nodes/` directory for Python files and dynamically load them."""

        if not self.control_nodes_dir.exists():
            logger.error(f"❌ Control nodes directory '{self.control_nodes_dir}' does not exist.")
            return {}

        control_nodes = {}

        for control_file in self.control_nodes_dir.glob("*.py"):
            if control_file.stem == "control_node" or control_file.name == "__init__.py":
                continue  # Skip base class and init file

            control_name = control_file.stem  # Get filename without .py
            logger.info(f"📥 Loading control node: {control_name}")

            try:
                control_class = self._load_control_node_class(control_file)

                if control_class:
                    # ✅ Store control node info in the same format as agents
                    self.configs[control_name] = {
                        "name": control_name,
                        "class_name": control_class.__name__,
                        "type": "control_node",
                        "class": control_class,
                        "instance": None,  # Placeholder until instantiated
                    }
                    logger.info(f"✅ Loaded control node: {control_name}")
                else:
                    logger.warning(f"⚠️ Failed to load control node class for: {control_name}")
            except Exception as e:
                logger.error(f"❌ Error loading control node {control_name}: {e}")
                continue

        return control_nodes



    def _load_control_node_class(self, control_node_path):
        """Dynamically load a control node class from its Python file, ensuring we do not load the base ControlNode."""
        if not control_node_path.exists():
            logger.warning(f"⚠️ Missing control node file: {control_node_path}")
            return None

        try:
            module_name = control_node_path.stem  # Use filename as module name
            spec = importlib.util.spec_from_file_location(module_name, control_node_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # ✅ Find subclasses of `ControlNode`, excluding the base class
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if isinstance(attr, type) and issubclass(attr, ControlNode) and attr is not ControlNode:
                    return attr  # Return the actual control node class

            logger.warning(f"⚠️ No valid ControlNode subclass found in {control_node_path}")
            return None

        except Exception as e:
            logger.error(f"❌ Error loading control node from {control_node_path}: {e}")
            return None

    def get_agent_config(self, name):
        """Retrieve a specific agent's config."""
        return self.configs.get(name, None)

    def get_agent_class(self, name):
        """Retrieve the registered class reference for an agent."""
        return self.configs.get(name, {}).get("class", None)

    def get_control_node_class(self, name):
        """Retrieve the registered class reference for a control node."""
        return self.control_nodes.get(name, None)

    def get_all_agents(self):
        """Return a dictionary of all available agent configurations."""
        return self.configs

    def register_agent_instance(self, agent_name, agent_instance):
        """Store the instantiated agent inside the registry."""
        if agent_name in self.configs:
            self.configs[agent_name]["instance"] = agent_instance
            logger.info(f"✅ Registered instance for agent {agent_name}")
        else:
            logger.warning(f"⚠️ Tried to register instance for {agent_name}, but it's not in the registry.")

    def get_agent_instance(self, agent_name):
        """Retrieve an initialized agent instance."""
        return self.configs.get(agent_name, {}).get("instance", None)

    def get_agent_input_form(self, agent_name):
        """
        Returns the Pydantic input schema class for an agent, if defined via agent_args.py.
        """
        return self.configs.get(agent_name, {}).get("input_schema", None)



def main():
    registry = AgentRegistry()

    print("\n=== All Agent Configs ===")
    for agent_name, config in registry.get_all_agents().items():
        print(f"\nAgent: {agent_name}")
        print("Config:", config)

    print("\n=== Testing Class Lookup ===")
    print("emi_agent class:", registry.get_agent_class("emi_agent"))
    print("ToolCaller control node:", registry.get_control_node_class("tool_caller"))


if __name__ == "__main__":
    main()
