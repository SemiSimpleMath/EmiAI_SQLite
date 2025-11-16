# config_loader.py

import os
import re
import yaml
from typing import Dict, Any, Optional

from app.assistant.utils.logging_config import get_logger
logger = get_logger(__name__)

config_cache: Dict[str, Dict[str, Any]] = {}

def load_config(config_path: str) -> Dict[str, Any]:
    """
    Loads a YAML configuration file, replaces environment variables, and caches the result.

    Parameters:
    - config_path (str): Path to the YAML configuration file.

    Returns:
    - Dict[str, Any]: Parsed configuration dictionary.
    """
    if config_path in config_cache:
        logger.debug(f"Configuration loaded from cache: {config_path}")
        return config_cache[config_path]

    try:
        with open(config_path, 'r') as file:
            content = file.read()
            # Replace environment variables like ${VAR_NAME} with their actual values
            content = re.sub(r'\$\{(\w+)\}', lambda m: os.environ.get(m.group(1), ''), content)
            config = yaml.safe_load(content)
            config_cache[config_path] = config
            logger.info(f"Configuration loaded and cached: {config_path}")
            return config
    except Exception as e:
        logger.error(f"Failed to load configuration from {config_path}: {e}")
        raise
