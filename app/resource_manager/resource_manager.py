import json
from pathlib import Path
from typing import Dict, Any, Optional
from jinja2 import Template

from app.assistant.ServiceLocator.service_locator import DI
from app.assistant.utils.logging_config import get_logger

logger = get_logger(__name__)


class ResourceManager:
    """
    Manages shared resources backed by files and exposed via DI.global_blackboard.

    - Load on startup from config.
    - Read through global_blackboard for agents.
    - Optional persistent updates from agents (learned preferences).
    """

    def __init__(self, base_dir: Optional[Path] = None):
        # Base directory for relative resource paths
        # PROJECT_ROOT points to app/, but resources/ is at project root, so go up one level
        from app.assistant.agent_registry.agent_registry import PROJECT_ROOT
        self.base_dir = base_dir or PROJECT_ROOT.parent
        # resource_id -> absolute file path
        self._resource_files: Dict[str, Path] = {}

    def load_from_config(self, config: Dict[str, Any]) -> None:
        """
        Config shape example:

        shared_resources:
          email_instructions: "resources/email_instructions.md"
          newsletter_prefs: "resources/newsletter_prefs.json"
        """
        shared = config.get("shared_resources", {})
        if not shared:
            return

        if not hasattr(DI, "global_blackboard") or DI.global_blackboard is None:
            logger.error("Global blackboard not initialized, cannot load shared resources.")
            return

        for resource_id, rel_path in shared.items():
            path = (self.base_dir / rel_path).resolve()
            self._resource_files[resource_id] = path

            try:
                if not path.exists():
                    logger.warning(f"Resource file missing for '{resource_id}': {path}")
                    DI.global_blackboard.update_state_value(resource_id, "")
                    continue

                content = self._read_file(path)
                DI.global_blackboard.update_state_value(resource_id, content)
                logger.info(f"Loaded shared resource '{resource_id}' from {path}")
            except Exception as e:
                logger.error(f"Failed to load resource '{resource_id}' from {path}: {e}")
                DI.global_blackboard.update_state_value(resource_id, "")

    def _read_file(self, path: Path) -> Any:
        """Read file and return content - JSON as dict, text files as strings."""
        if path.suffix.lower() in [".json"]:
            with path.open("r", encoding="utf-8") as f:
                return json.load(f)
        else:
            with path.open("r", encoding="utf-8") as f:
                return f.read()

    def _write_file(self, path: Path, value: Any) -> None:
        if path.suffix.lower() in [".json"]:
            with path.open("w", encoding="utf-8") as f:
                json.dump(value, f, indent=2, ensure_ascii=False)
        else:
            with path.open("w", encoding="utf-8") as f:
                if not isinstance(value, str):
                    value = str(value)
                f.write(value)

    def load_all_from_directory(self, resources_dir: Optional[str] = "resources") -> None:
        """
        Automatically load all files from a resources directory into global_blackboard.
        
        Uses the filename (without extension) as the resource_id.
        Example: resources/email_instructions.md -> resource_id: "email_instructions"
        
        Loads in two passes:
        1. First pass: Load all JSON files (these provide context for templates)
        2. Second pass: Load template files (.md, .txt) and render them using JSON context
        
        Args:
            resources_dir: Relative path to resources directory (default: "resources")
        """
        logger.info(f"🔧 Starting resource loading from '{resources_dir}'...")
        logger.info(f"   DI has global_blackboard: {hasattr(DI, 'global_blackboard')}")
        if hasattr(DI, "global_blackboard"):
            logger.info(f"   DI.global_blackboard is None: {DI.global_blackboard is None}")
        
        if not hasattr(DI, "global_blackboard") or DI.global_blackboard is None:
            logger.error("❌ Global blackboard not initialized, cannot load shared resources.")
            return

        resources_path = (self.base_dir / resources_dir).resolve()
        logger.info(f"   Resources path: {resources_path}")
        logger.info(f"   Path exists: {resources_path.exists()}")
        
        if not resources_path.exists():
            logger.error(f"❌ Resources directory does not exist: {resources_path}")
            return
        
        logger.info(f"   Is directory: {resources_path.is_dir()}")
        if not resources_path.is_dir():
            logger.error(f"❌ Resources path is not a directory: {resources_path}")
            return

        logger.info(f"📂 Scanning resources directory: {resources_path}")
        loaded_count = 0
        skipped_count = 0

        # Collect files by type
        json_files = []
        template_files = []
        
        for file_path in resources_path.iterdir():
            if not file_path.is_file() or file_path.name.startswith('.'):
                continue
            
            if file_path in self._resource_files.values():
                skipped_count += 1
                continue
                
            if file_path.suffix.lower() == '.json':
                json_files.append(file_path)
            elif file_path.suffix.lower() in ['.md', '.txt'] or file_path.suffix == '':
                # Include .md, .txt, and files with no extension as templates
                template_files.append(file_path)

        # PASS 1: Load all JSON files first (these provide context)
        for file_path in json_files:
            resource_id = file_path.stem
            try:
                content = self._read_file(file_path)
                DI.global_blackboard.update_state_value(resource_id, content)
                self._resource_files[resource_id] = file_path
                loaded_count += 1
                
                # Debug: Show what we're storing for user preference files
                if resource_id.startswith('resource_user_'):
                    if isinstance(content, str):
                        preview = content[:150].replace('\n', ' ')
                        logger.info(f"✅ Loaded JSON resource '{resource_id}' as MARKDOWN ({len(content)} chars): {preview}...")
                    else:
                        logger.info(f"✅ Loaded JSON resource '{resource_id}' as DICT with keys: {list(content.keys()) if isinstance(content, dict) else type(content)}")
                else:
                    logger.info(f"✅ Loaded JSON resource '{resource_id}' from {file_path.name}")
            except Exception as e:
                logger.error(f"Failed to load JSON resource '{resource_id}' from {file_path}: {e}")
                skipped_count += 1

        # PASS 2: Load template files and render them using JSON context
        # Build context from all currently loaded resources
        template_context = {}
        for res_id in self._resource_files.keys():
            value = DI.global_blackboard.get_state_value(res_id, None)
            if value is not None:
                template_context[res_id] = value
        
        for file_path in template_files:
            resource_id = file_path.stem
            try:
                raw_content = self._read_file(file_path)
                
                # Store raw template - will be rendered on-demand at injection time
                DI.global_blackboard.update_state_value(resource_id, raw_content)
                self._resource_files[resource_id] = file_path
                loaded_count += 1
                logger.info(f"✅ Loaded template resource '{resource_id}' from {file_path.name} (will render on-demand)")
            except Exception as e:
                logger.error(f"Failed to load template resource '{resource_id}' from {file_path}: {e}")
                skipped_count += 1

        logger.info(f"📦 Resources loading complete: {loaded_count} loaded, {skipped_count} skipped")

    def update_resource(self, resource_id: str, value: Any, persist: bool = True) -> None:
        """
        Update a shared resource both in memory and on disk.

        Use case:
          email agent learns "ignore chess.com newsletters" and updates
          'email_instructions' or 'newsletter_prefs'.
        """
        if not hasattr(DI, "global_blackboard") or DI.global_blackboard is None:
            raise RuntimeError("Global blackboard not initialized.")

        DI.global_blackboard.update_state_value(resource_id, value)

        path = self._resource_files.get(resource_id)
        if persist and path is not None:
            try:
                self._write_file(path, value)
                logger.info(f"Persisted shared resource '{resource_id}' to {path}")
            except Exception as e:
                logger.error(f"Failed to persist resource '{resource_id}' to {path}: {e}")
