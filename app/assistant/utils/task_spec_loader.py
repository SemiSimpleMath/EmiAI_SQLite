from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from app.assistant.ServiceLocator.service_locator import DI
from app.assistant.utils.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class TaskSpec:
    task_id: str | None
    manager: str | None
    description: str | None
    task_body: str
    includes: list[str]
    allowed_resources: list[str]
    allowed_read_files: list[str]
    allowed_write_files: list[str]
    frontmatter: dict[str, Any]
    task_includes: str


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    raw = text.lstrip("\ufeff")
    if not raw.startswith("---"):
        return {}, text
    parts = raw.split("\n", 1)
    if len(parts) < 2:
        return {}, text
    rest = parts[1]
    if "\n---" not in rest:
        return {}, text
    fm_text, body = rest.split("\n---", 1)
    try:
        frontmatter = yaml.safe_load(fm_text) or {}
    except Exception as e:
        logger.warning("Failed to parse task frontmatter: %s", e)
        frontmatter = {}
    # Strip leading newline if present.
    if body.startswith("\n"):
        body = body[1:]
    return frontmatter, body


def _resolve_resource(name: str) -> str:
    key = (name or "").strip()
    if not key:
        return ""
    # Strip optional @version suffix.
    if "@" in key:
        key = key.split("@", 1)[0].strip()
    if not key:
        return ""
    try:
        val = DI.global_blackboard.get_state_value(key, "")
        return "" if val is None else str(val)
    except Exception:
        return ""


def _resolve_include_text(name: str, repo_root: Path) -> str:
    raw = (name or "").strip()
    if not raw:
        return ""
    # Explicit resource id
    if raw.startswith("resource:"):
        return _resolve_resource(raw.split(":", 1)[1].strip())

    # File path (relative to repo root or absolute)
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = (repo_root / candidate).resolve()
    if candidate.exists() and candidate.is_file():
        try:
            return candidate.read_text(encoding="utf-8")
        except Exception:
            return ""

    # Fallback to resource id in global blackboard
    return _resolve_resource(raw)


def _normalize_paths(paths: list[str] | None) -> list[str]:
    out: list[str] = []
    for p in paths or []:
        if not isinstance(p, str) or not p.strip():
            continue
        out.append(p.strip())
    return out


def load_task_spec(path_str: str) -> TaskSpec:
    if not isinstance(path_str, str) or not path_str.strip():
        raise ValueError("task_file must be a non-empty string")
    repo_root = _repo_root()
    path = Path(path_str.strip())
    if not path.is_absolute():
        path = (repo_root / path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Task spec not found: {path}")
    text = path.read_text(encoding="utf-8")
    frontmatter, body = _split_frontmatter(text)

    includes = _normalize_paths(frontmatter.get("includes"))
    allowed_resources = _normalize_paths(frontmatter.get("allowed_resources"))
    inputs = frontmatter.get("inputs") or []
    outputs = frontmatter.get("outputs") or []
    allowed_read_files = _normalize_paths([i.get("path") for i in inputs if isinstance(i, dict)])
    allowed_write_files = _normalize_paths([o.get("path") for o in outputs if isinstance(o, dict)])

    include_texts: list[str] = []
    for inc in includes:
        content = _resolve_include_text(inc, repo_root)
        if content:
            include_texts.append(content)
        else:
            logger.warning("Task include not found or empty: %s", inc)
    task_includes = "\n\n".join([t.strip() for t in include_texts if t.strip()])

    return TaskSpec(
        task_id=str(frontmatter.get("task_id") or "") or None,
        manager=str(frontmatter.get("manager") or "") or None,
        description=str(frontmatter.get("description") or "") or None,
        task_body=body.strip(),
        includes=includes,
        allowed_resources=allowed_resources,
        allowed_read_files=allowed_read_files,
        allowed_write_files=allowed_write_files,
        frontmatter=frontmatter if isinstance(frontmatter, dict) else {},
        task_includes=task_includes,
    )
