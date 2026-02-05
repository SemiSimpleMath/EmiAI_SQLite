# config_loader.py

import os
import re
from pathlib import Path
import yaml
from typing import Dict, Any, Tuple

from app.assistant.utils.logging_config import get_logger
logger = get_logger(__name__)

#
# NOTE: Configs are edited frequently during development. We cache for performance,
# but we must invalidate when the file changes on disk (mtime).
#
config_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}

def load_config(config_path: str) -> Dict[str, Any]:
    """
    Loads a YAML configuration file, replaces environment variables, and caches the result.

    Parameters:
    - config_path (str): Path to the YAML configuration file.

    Returns:
    - Dict[str, Any]: Parsed configuration dictionary.
    """
    path = Path(config_path)
    mtime = path.stat().st_mtime if path.exists() else 0.0
    cached = config_cache.get(config_path)
    if cached:
        cached_mtime, cached_config = cached
        if cached_mtime == mtime:
            logger.debug(f"Configuration loaded from cache: {config_path}")
            return cached_config

    try:
        with open(config_path, 'r') as file:
            content = file.read()
            # Replace environment variables like ${VAR_NAME} with their actual values
            content = re.sub(r'\$\{(\w+)\}', lambda m: os.environ.get(m.group(1), ''), content)
            config = yaml.safe_load(content)
            # Refresh cache with current mtime
            config_cache[config_path] = (mtime, config)
            logger.info(f"Configuration loaded and cached: {config_path}")
            return config
    except Exception as e:
        logger.error(f"Failed to load configuration from {config_path}: {e}")
        raise
