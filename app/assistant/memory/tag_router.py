"""
Tag-Based Routing for Memory Manager

Maps fact tags to resource file subscriptions.
"""
import json
from pathlib import Path
from typing import List, Dict, Any, Set
from app.assistant.utils.logging_config import get_logger
from app.assistant.utils.path_utils import get_resources_dir

logger = get_logger(__name__)


class TagRouter:
    """Routes facts to resource files based on tag subscriptions."""
    
    def __init__(self, resources_dir: Path | None = None):
        self.resources_dir = resources_dir or get_resources_dir()
        self._subscriptions = self._load_subscriptions()
    
    def _load_subscriptions(self) -> Dict[str, Set[str]]:
        """
        Load resource file subscriptions from JSON metadata.
        Returns dict mapping tag -> set of resource file names.
        
        Example:
        {
            "food": {"resource_user_food_prefs.json"},
            "routine": {"resource_user_routine.json"}
        }
        """
        subscriptions: Dict[str, Set[str]] = {}

        resources_dir = self.resources_dir
        if not resources_dir.exists():
            return subscriptions

        # Scan all JSON resources. Any file declaring `_metadata.tags` participates.
        for filepath in sorted(resources_dir.glob("*.json")):
            filename = filepath.name
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)

                metadata = data.get("_metadata", {}) if isinstance(data, dict) else {}
                tags = metadata.get("tags", [])

                # `_metadata.tags` is the designated subscription list for memory routing.
                if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
                    continue

                for tag in tags:
                    subscriptions.setdefault(tag, set()).add(filename)

            except Exception as e:
                logger.warning(f"Could not parse {filename}: {e}")
                continue

        return subscriptions
    
    def get_target_files_for_fact(self, fact: Dict[str, Any]) -> List[str]:
        """
        Determine which resource files should receive this fact based on tags.
        
        Args:
            fact: Dict containing 'tags', 'temporal_scope'
        
        Returns:
            List of resource filenames (e.g., ['resource_user_routine.md'])
        """
        tags = fact.get('tags', [])
        temporal_scope = fact.get('temporal_scope', 'chronic')
        
        # Filter historical facts (KG only, no resource files)
        if temporal_scope == 'historical':
            return []
        
        # Find all matching resource files
        target_files = set()
        for tag in tags:
            if tag in self._subscriptions:
                target_files.update(self._subscriptions[tag])
        
        return list(target_files)
    
    def get_subscriptions(self) -> Dict[str, Set[str]]:
        """Get the current tag -> files mapping."""
        return self._subscriptions

    def get_all_tags(self) -> List[str]:
        """Return a stable, unique list of known routing tags."""
        return sorted(self._subscriptions.keys())

    def reload(self) -> None:
        """Reload subscriptions from disk (useful after resources change)."""
        self._subscriptions = self._load_subscriptions()


# Global instance
_router = None

def get_tag_router() -> TagRouter:
    """Get the global TagRouter instance (singleton)."""
    global _router
    if _router is None:
        _router = TagRouter()
    return _router
