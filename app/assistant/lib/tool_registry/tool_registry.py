import copy
from pathlib import Path
from importlib import util as import_util
from jinja2 import Environment, FileSystemLoader


from app.assistant.utils.logging_config import get_logger
logger = get_logger(__name__)


def get_tool_registry_dir():
    # Go up 2 levels to get the actual project root
    PROJECT_ROOT = Path(__file__).resolve().parents[2]
    print("PROJECT_ROOT:", PROJECT_ROOT)

    # Define tool directory dynamically
    tool_dir = PROJECT_ROOT / "lib" / "tools"
    print("Tool directory:", tool_dir)

    return str(tool_dir)

class ToolRegistry:
    def __init__(self, tools_dir=None):
        """
        Initialize the registry by scanning the given tools directory.
        Each subdirectory should be named after the tool and contain:
         - <tool_name>.py (with a get_tool_class() function)
         - tool_forms/ (containing a <tool_name>_form.py with a Pydantic model)
         - prompts/ (with description.j2, args.j2 and select.j2)
        """
        if tools_dir is None:
            tools_dir = get_tool_registry_dir()
        self.tools_dir = Path(tools_dir)
        self.registry = {}

    def load_tool_registry(self):
        self.load_tools()

    def load_tools(self):
        for tool_dir in self.tools_dir.iterdir():
            if tool_dir.is_dir():
                tool_name = tool_dir.name
                try:
                    tool_class = self.load_tool_class(tool_dir, tool_name)
                    tool_args = self.load_tool_args(tool_dir, tool_name)
                    prompts = self.load_prompts(tool_dir, tool_name)
                    self.registry[tool_name] = {
                        "tool_class": tool_class,
                        "tool_args": tool_args,
                        "prompts": prompts,
                    }
                    logger.info(f"Registered tool: {tool_name}")
                except Exception as e:
                    logger.error(f"Failed to load tool '{tool_name}': {e}")

    def load_tool_class(self, tool_dir: Path, tool_name: str):
        tool_file = tool_dir / f"{tool_name}.py"
        if not tool_file.exists():
            raise FileNotFoundError(f"{tool_file} does not exist.")
        module_name = f"{tool_name}_tool"
        spec = import_util.spec_from_file_location(module_name, str(tool_file))
        module = import_util.module_from_spec(spec)
        spec.loader.exec_module(module)
        if not hasattr(module, "get_tool_class"):
            raise AttributeError(f"Module {module_name} must define get_tool_class().")
        return module.get_tool_class()

    def load_tool_args(self, tool_dir: Path, tool_name: str):
        forms_dir = tool_dir / "tool_forms"
        if not forms_dir.exists():
            raise FileNotFoundError(f"Directory {forms_dir} not found for tool '{tool_name}'.")
        form_file = forms_dir / "tool_forms.py"
        if not form_file.exists():
            raise FileNotFoundError(f"{form_file} not found for tool '{tool_name}'.")
        module_name = f"{tool_name}_form"
        spec = import_util.spec_from_file_location(module_name, str(form_file))
        module = import_util.module_from_spec(spec)
        spec.loader.exec_module(module)

        args_class_name = f"{tool_name}_args"
        arguments_class_name = f"{tool_name}_arguments"

        if not hasattr(module, args_class_name):
            raise ValueError(f"{args_class_name} not found in {form_file}.")
        if not hasattr(module, arguments_class_name):
            raise ValueError(f"{arguments_class_name} not found in {form_file}.")

        args_class = getattr(module, args_class_name)
        arguments_class = getattr(module, arguments_class_name)

        from pydantic import BaseModel
        if not (issubclass(args_class, BaseModel) and issubclass(arguments_class, BaseModel)):
            raise TypeError("Both classes must be subclasses of BaseModel.")

        return {"args": args_class, "arguments": arguments_class}

    def load_prompts(self, tool_dir: Path, tool_name: str):
        prompts_dir = tool_dir / "prompts"
        if not prompts_dir.exists():
            raise FileNotFoundError(f"Prompts directory not found in {tool_dir}.")
        env = Environment(loader=FileSystemLoader(str(prompts_dir)))
        prompts = {}
        # Only load description and args prompts - select prompts are not used
        for prompt in [f"{tool_name}_description.j2", f"{tool_name}_args.j2"]:
            key = prompt.split(".")[0]
            try:
                template = env.get_template(prompt)
                prompts[key] = template
            except Exception as e:
                logger.error(f"Failed to load prompt '{prompt}' for tool '{tool_dir.name}': {e}")
                prompts[key] = None
        return prompts

    def get_tool(self, tool_name: str):
        """
        Retrieves the configuration for a specified tool.
        """
        tool_config = self.registry.get(tool_name)
        if not tool_config:
            logger.debug(f"Tool '{tool_name}' not found in registry.")
            return None

        # Ensure correct structure for tool_form
        return {
            **tool_config,
            "tool_form": tool_config["tool_args"]["arguments"]
        }

    def list_tools(self):
        return list(self.registry.keys())


    def get_all_tools(self):
        """
        Returns a copy of the entire tool registry.

        Returns:
        - Dictionary containing all registered tools.
        """
        return self.registry.copy()

    def get_tool_description(self, tool_name: str):
        """Retrieve and render the tool description template."""
        tool = self.registry.get(tool_name)
        if not tool:
            logger.debug(f"Tool '{tool_name}' not found in registry.")
            return None

        description_template = tool["prompts"].get(f"{tool_name}_description")
        if description_template:
            try:
                return description_template.render()
            except Exception as e:
                logger.error(f"Error rendering description for '{tool_name}': {e}")
                return "Error rendering description."
        return "No description available."


    def get_tool_arguments_prompt(self, tool_name: str, user_context: dict = None):
        """Retrieve and render the tool arguments prompt."""
        tool = self.registry.get(tool_name)
        if not tool:
            logger.debug(f"Tool '{tool_name}' not found in registry.")
            return None

        args_template = tool["prompts"].get(f"{tool_name}_args")
        if args_template:
            try:
                return args_template.render(user_context or {})
            except Exception as e:
                logger.error(f"Error rendering arguments prompt for '{tool_name}': {e}")
                return "Error rendering arguments prompt."
        return "No arguments prompt available."

    def get_tool_arguments_prompt_template(self, tool_name: str):
        """Retrieve and render the tool arguments prompt."""
        tool = self.registry.get(tool_name)
        if not tool:
            logger.debug(f"Tool '{tool_name}' not found in registry.")
            return None

        return tool["prompts"].get(f"{tool_name}_args")


    def get_tool_descriptions(self, allowed_tools: list) -> dict:
        """Retrieve descriptions only for allowed tools."""
        return {tool: self.get_tool_description(tool) for tool in allowed_tools}


    def get_tool_arguments_prompts(self, allowed_tools: list, user_context: dict = None) -> dict:
        """Retrieve argument prompts only for allowed tools."""
        return {tool: self.get_tool_arguments_prompt(tool, user_context) for tool in allowed_tools}

    def get_tool_form(self, tool_name: str):
        """Retrieve the tool form (arguments schema) for a specified tool."""
        tool_config = self.get_tool(tool_name)
        if not tool_config:
            logger.debug(f"Tool '{tool_name}' not found in registry.")
            return None
        return tool_config.get("tool_form")

    def get_tool_class(self, tool_name: str):
        tool_config = self.get_tool(tool_name)
        if not tool_config:
            logger.debug(f"Tool '{tool_name}' not found in registry.")
            return None
        return tool_config.get("tool_class")


    def filter_tools(self, allowed_tools):
        """
        Returns a filtered registry containing only the allowed tools.
        This avoids reinitializing the ToolRegistry.
        """
        filtered_registry = copy.copy(self)  # Shallow copy to avoid reinitialization
        filtered_registry.registry = {
            tool: self.registry[tool] for tool in allowed_tools if tool in self.registry
        }
        return filtered_registry



if __name__ == "__main__":
    from pathlib import Path

    # Go up 2 levels to get the actual project root
    PROJECT_ROOT = Path(__file__).resolve().parents[2]
    print("PROJECT_ROOT:", PROJECT_ROOT)

    # Define tool directory dynamically
    tool_dir = PROJECT_ROOT / "lib" / "tools"
    print("Tool directory:", tool_dir)

    # Initialize and test the ToolRegistry
    registry = ToolRegistry(str(tool_dir))

    # List all tool names
    tool_list = registry.list_tools()
    print("List of tools:", tool_list)

    # Print the full registry (copy)
    full_registry = registry.get_all_tools()
    print("Full registry:", full_registry)

    # Specify a tool to test
    tool_name = "get_email"
    tool_config = registry.get_tool(tool_name)
    if not tool_config:
        print(f"Error: Tool '{tool_name}' not found in registry.")
    else:
        print(f"\nTool configuration for '{tool_name}':")
        print(tool_config)

        # Get and print tool description
        description = registry.get_tool_description(tool_name)
        print(f"\nDescription for '{tool_name}':")
        print(description)


        # Simulate a user_context dictionary and get tool arguments prompt
        user_context = {"user": "test_user", "data": "sample"}
        arguments_prompt = registry.get_tool_arguments_prompt(tool_name, user_context)
        print(f"\nArguments prompt for '{tool_name}':")
        print(arguments_prompt)

        # Get and print the tool form (arguments schema)
        tool_form = registry.get_tool_form(tool_name)
        print(f"\nTool form for '{tool_name}':")
        print(tool_form)
