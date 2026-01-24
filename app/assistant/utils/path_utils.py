from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def get_repo_root() -> Path:
    env_root = os.getenv("EMI_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()
    return Path(__file__).resolve().parents[3]


@lru_cache(maxsize=1)
def get_resources_dir() -> Path:
    env_resources = os.getenv("EMI_RESOURCES_DIR")
    if env_resources:
        return Path(env_resources).expanduser().resolve()
    return get_repo_root() / "resources"
