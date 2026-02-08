from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import yaml

from app.assistant.utils.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class TaskRegistryEntry:
    task_id: str
    name: str
    task_file: str
    description: str | None
    aliases: list[str]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _normalize(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


def _entry_keys(entry: TaskRegistryEntry) -> list[str]:
    keys = [entry.task_id, entry.name]
    keys.extend(entry.aliases or [])
    return [_normalize(k) for k in keys if k]


def load_task_registry(path: str | None = None) -> list[TaskRegistryEntry]:
    registry_path = path or "tasks/registry.yaml"
    repo_root = _repo_root()
    file_path = Path(registry_path)
    if not file_path.is_absolute():
        file_path = (repo_root / file_path).resolve()
    if not file_path.exists():
        logger.warning("Task registry not found: %s", file_path)
        return []

    try:
        data = yaml.safe_load(file_path.read_text(encoding="utf-8")) or {}
    except Exception as e:
        logger.warning("Failed to parse task registry: %s", e)
        return []

    items = data.get("tasks") or []
    entries: list[TaskRegistryEntry] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        task_id = str(item.get("id") or "").strip()
        name = str(item.get("name") or "").strip()
        task_file = str(item.get("task_file") or "").strip()
        if not (task_id and name and task_file):
            continue
        description = str(item.get("description") or "").strip() or None
        aliases = [str(a).strip() for a in (item.get("aliases") or []) if str(a).strip()]
        entries.append(
            TaskRegistryEntry(
                task_id=task_id,
                name=name,
                task_file=task_file,
                description=description,
                aliases=aliases,
            )
        )
    return entries


def resolve_task_entry(query: str, registry: Iterable[TaskRegistryEntry] | None = None) -> tuple[TaskRegistryEntry | None, list[TaskRegistryEntry]]:
    q = _normalize(query)
    if not q:
        return None, []

    entries = list(registry or load_task_registry())
    if not entries:
        return None, []

    exact_matches = [e for e in entries if q in _entry_keys(e)]
    if len(exact_matches) == 1:
        return exact_matches[0], exact_matches
    if len(exact_matches) > 1:
        return None, exact_matches

    substring_matches = []
    for entry in entries:
        for key in _entry_keys(entry):
            if key and (key in q or q in key):
                substring_matches.append(entry)
                break

    if len(substring_matches) == 1:
        return substring_matches[0], substring_matches
    if len(substring_matches) > 1:
        return None, substring_matches

    return None, []
