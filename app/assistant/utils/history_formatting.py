from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Iterable

from app.assistant.utils.time_utils import utc_to_local


def _safe_content(m: Any) -> str:
    c = getattr(m, "content", "")
    return "" if c is None else str(c).strip()


def _tool_result_ref_markers(m: Any) -> str:
    meta = getattr(m, "metadata", None)
    if not isinstance(meta, dict):
        return ""
    tool_result_id = meta.get("tool_result_id")
    parts: list[str] = []
    if isinstance(tool_result_id, str) and tool_result_id.strip():
        parts.append(f"Result ID: {tool_result_id.strip()}")
    return "\n".join(parts).strip()

def _tool_result_summary_link_markers(m: Any) -> str:
    meta = getattr(m, "metadata", None)
    if not isinstance(meta, dict):
        return ""
    tid = meta.get("summarizes_tool_result_id")
    parts: list[str] = []
    if isinstance(tid, str) and tid.strip():
        parts.append(f"Result ID: {tid.strip()}")
    if parts:
        return "\n".join(parts).strip()
    return ""


def _fmt_time(m: Any) -> str:
    ts = getattr(m, "timestamp", None)
    if not ts:
        return ""
    try:
        local_ts = utc_to_local(ts)
        return local_ts.strftime("%H:%M")
    except Exception:
        return ""


def _fmt_header(idx: int, time_s: str, title: str) -> str:
    parts = [f"[{idx:02d}]"]
    if time_s:
        parts.append(time_s)
    if title:
        parts.append(f"- {title}")
    return " ".join(parts).strip()


def format_recent_history(agent_messages: Iterable[Any]) -> str:
    """
    Produce a readable, chronological, numbered recent_history string.

    Intended behavior for planner readability:
    - Summaries are first-class history messages (tool_result_summary).
    - Once a tool_result has been summarized (summary links to tool_result_id),
      suppress that older tool_result in history to keep context compact.
    - Always keep the most recent tool_result(s) that have not yet been summarized.
    """
    ALLOWED = {
        "tool_result",
        "agent_result",
        "tool_request",
        "tool_result_summary",
        "agent_request",
    }
    msgs = [m for m in list(agent_messages or []) if getattr(m, "data_type", None) in ALLOWED]

    def _emit(idx: int, time_s: str, title: str, body_lines: list[str]) -> str:
        header = _fmt_header(idx, time_s, title)
        extras: list[str] = []
        extra = "\n".join([x for x in extras if x]).strip()
        body = "\n".join([x for x in body_lines if x]).strip()
        combined = "\n".join([x for x in (header, body, extra) if x]).strip()
        return combined

    pieces: list[str] = []
    out_idx = 1
    i = 0
    n = len(msgs)
    pending_request: dict[str, Any] | None = None
    pending_agent_request: dict[str, Any] | None = None
    by_tool_result_id: dict[str, dict[str, Any]] = {}
    last_tool_result_id: str | None = None

    def _parse_tool_request(content: str) -> tuple[str | None, str | None]:
        m = re.match(r"Calling tool\\s+([^\\s]+)\\s+with arguments\\s+(.+)", content.strip())
        if not m:
            return None, content.strip() or None
        return m.group(1), m.group(2)

    def _parse_agent_request(content: str) -> tuple[str | None, str | None]:
        m = re.match(r"Calling agent\\s+'([^']+)'\\s+with arguments:\\s+(.+)", content.strip())
        if not m:
            return None, None
        return m.group(1), m.group(2)

    def _finalize_pending_request() -> None:
        nonlocal out_idx, pending_request
        if not pending_request:
            return
        time_s = pending_request.get("time_s", "")
        tool_name = pending_request.get("tool_name") or "tool"
        args = pending_request.get("args")
        lines = []
        if args:
            lines.append(f"Args: {args}")
        combined = _emit(out_idx, time_s, tool_name, lines)
        if combined:
            pieces.append(combined)
            out_idx += 1
        pending_request = None

    while i < n:
        m = msgs[i]
        dt = getattr(m, "data_type", None)

        if dt == "tool_request":
            content = _safe_content(m)
            agent_name, agent_args = _parse_agent_request(content)
            if agent_name:
                pending_agent_request = {
                    "time_s": _fmt_time(m),
                    "agent_name": agent_name,
                    "args": agent_args,
                }
            else:
                tool_name, args = _parse_tool_request(content)
                pending_request = {
                    "time_s": _fmt_time(m),
                    "tool_name": tool_name or "tool",
                    "args": args,
                }
            i += 1
            continue

        if dt == "tool_result":
            meta = getattr(m, "metadata", None)
            tid = meta.get("tool_result_id") if isinstance(meta, dict) else None
            tid = tid.strip() if isinstance(tid, str) else None
            if tid:
                last_tool_result_id = tid
            sub = getattr(m, "sub_data_type", None)
            tool_name = None
            if isinstance(sub, list) and sub:
                tool_name = str(sub[0]) if sub[0] else None
            content_str = _safe_content(m)
            entry = {
                "time_s": _fmt_time(m),
                "tool_name": tool_name or (pending_request or {}).get("tool_name") or "tool",
                "args": (pending_request or {}).get("args"),
                "tool_result_id": tid,
                "summary": None,
                "content": content_str,
            }
            if pending_request and pending_request.get("time_s"):
                entry["time_s"] = pending_request.get("time_s")
            if tid:
                by_tool_result_id[tid] = entry
            # Emit immediately only if no summary will follow.
            # We'll hold it and emit when summary arrives (or at end).
            if pending_request:
                pending_request = None
            i += 1
            continue

        if dt == "tool_result_summary":
            meta = getattr(m, "metadata", None)
            tid = meta.get("summarizes_tool_result_id") if isinstance(meta, dict) else None
            tid = tid.strip() if isinstance(tid, str) else None
            summary = _safe_content(m)
            entry = by_tool_result_id.get(tid) if tid else None
            if entry is None:
                entry = {
                    "time_s": _fmt_time(m),
                    "tool_name": "tool",
                    "args": None,
                    "tool_result_id": tid,
                    "summary": summary,
                }
            else:
                entry["summary"] = summary
                if not entry.get("time_s"):
                    entry["time_s"] = _fmt_time(m)

            lines: list[str] = []
            if entry.get("args"):
                lines.append(f"Args: {entry['args']}")
            if entry.get("tool_result_id"):
                lines.append(f"Result ID: {entry['tool_result_id']}")
            if entry.get("summary"):
                lines.append(f"Summary: {entry['summary']}")
            combined = _emit(out_idx, entry.get("time_s", ""), entry.get("tool_name") or "tool", lines)
            if combined:
                pieces.append(combined)
                out_idx += 1
            if tid and tid in by_tool_result_id:
                del by_tool_result_id[tid]
            i += 1
            continue

        if dt in ("agent_result", "agent_request"):
            if dt == "agent_result" and pending_agent_request:
                time_s = pending_agent_request.get("time_s", "") or _fmt_time(m)
                agent_name = pending_agent_request.get("agent_name") or getattr(m, "sender", None) or "agent"
                args = pending_agent_request.get("args")
                lines: list[str] = []
                if args:
                    lines.append(f"Args: {args}")
                result_body = _safe_content(m)
                if result_body:
                    lines.append(f"Result: {result_body}")
                combined = _emit(out_idx, time_s, f"Calling agent {agent_name}", lines)
                if combined:
                    pieces.append(combined)
                    out_idx += 1
                pending_agent_request = None
                i += 1
                continue
            time_s = _fmt_time(m)
            title = getattr(m, "sender", None) or "agent"
            body = _safe_content(m)
            combined = _emit(out_idx, time_s, title, [body] if body else [])
            if combined:
                pieces.append(combined)
                out_idx += 1
            i += 1
            continue

        i += 1

    # Emit any held tool_results without summaries.
    for tid, entry in list(by_tool_result_id.items()):
        lines: list[str] = []
        if entry.get("args"):
            lines.append(f"Args: {entry['args']}")
        if entry.get("tool_result_id"):
            lines.append(f"Result ID: {entry['tool_result_id']}")
        if tid == last_tool_result_id and entry.get("content"):
            lines.append(f"Result: {entry['content']}")
        combined = _emit(out_idx, entry.get("time_s", ""), entry.get("tool_name") or "tool", lines)
        if combined:
            pieces.append(combined)
            out_idx += 1

    _finalize_pending_request()

    return "\n\n".join(pieces).strip()

