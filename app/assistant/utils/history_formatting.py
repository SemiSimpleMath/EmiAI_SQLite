from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Iterable


def _safe_content(m: Any) -> str:
    c = getattr(m, "content", "")
    return "" if c is None else str(c).strip()


def _attachment_markers(m: Any) -> str:
    """
    Preserve image attachment hints as plain text markers.
    """
    meta = getattr(m, "metadata", None)
    if not isinstance(meta, dict):
        return ""
    atts = meta.get("attachments")
    if not isinstance(atts, list) or not atts:
        return ""
    lines: list[str] = []
    for att in atts:
        if not isinstance(att, dict):
            continue
        if att.get("type") != "image":
            continue
        p = att.get("path")
        if not isinstance(p, str) or not p.strip():
            continue
        fname = att.get("original_filename") or os.path.basename(p)
        lines.append(f"[image attached: {fname}]")
    return "\n".join(lines).strip()


def _tool_result_ref_markers(m: Any) -> str:
    meta = getattr(m, "metadata", None)
    if not isinstance(meta, dict):
        return ""
    tool_result_id = meta.get("tool_result_id")
    tool_result_path = meta.get("path")
    parts: list[str] = []
    if isinstance(tool_result_id, str) and tool_result_id.strip():
        parts.append(f"[tool_result_id: {tool_result_id.strip()}]")
    if isinstance(tool_result_path, str) and tool_result_path.strip():
        parts.append(f"[tool_result_path: {tool_result_path.strip()}]")
    return "\n".join(parts).strip()

def _tool_result_summary_link_markers(m: Any) -> str:
    meta = getattr(m, "metadata", None)
    if not isinstance(meta, dict):
        return ""
    tid = meta.get("summarizes_tool_result_id")
    tpath = meta.get("summarizes_tool_result_path")
    parts: list[str] = []
    if isinstance(tid, str) and tid.strip():
        parts.append(f"[tool_result_id: {tid.strip()}]")
    if isinstance(tpath, str) and tpath.strip():
        parts.append(f"[tool_result_path: {tpath.strip()}]")
    if parts:
        return "\n".join(parts).strip()
    return ""


def _fmt_header(m: Any, idx: int) -> str:
    dt = getattr(m, "data_type", None) or "message"
    sub = getattr(m, "sub_data_type", None)
    sub_s = ""
    if isinstance(sub, list) and sub:
        sub_s = f" ({','.join(str(x) for x in sub if x)})"
    sender = getattr(m, "sender", None) or "?"
    receiver = getattr(m, "receiver", None) or "?"

    ts = getattr(m, "timestamp", None)
    ts_s = ""
    if isinstance(ts, datetime):
        # Keep as ISO string; user asked for timestamps and this is unambiguous.
        ts_s = ts.isoformat()
    elif ts:
        ts_s = str(ts)

    parts = [f"[{idx:02d}]"]
    if ts_s:
        parts.append(ts_s)
    parts.append(f"{dt}{sub_s}")
    parts.append(f"{sender}->{receiver}")
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

    # Build a set of tool_result_ids that have been summarized by a later summary message.
    summarized_ids: set[str] = set()
    for m in msgs:
        if getattr(m, "data_type", None) != "tool_result_summary":
            continue
        meta = getattr(m, "metadata", None)
        if not isinstance(meta, dict):
            continue
        tid = meta.get("summarizes_tool_result_id")
        if isinstance(tid, str) and tid.strip():
            summarized_ids.add(tid.strip())

    # Identify the last tool_result_id in the window (we always keep it even if summarized_ids is weird).
    last_tool_result_id: str | None = None
    for m in reversed(msgs):
        if getattr(m, "data_type", None) != "tool_result":
            continue
        meta = getattr(m, "metadata", None)
        if isinstance(meta, dict) and isinstance(meta.get("tool_result_id"), str) and meta["tool_result_id"].strip():
            last_tool_result_id = meta["tool_result_id"].strip()
            break

    def _emit(entry_m: Any, idx: int, body: str, *, attach_from: Any | None = None, ref_from: Any | None = None) -> str:
        header = _fmt_header(entry_m, idx)
        extras: list[str] = []
        if attach_from is not None:
            extras.append(_attachment_markers(attach_from))
        if ref_from is not None:
            extras.append(_tool_result_ref_markers(ref_from))
        # If this is a summary, show what it summarizes.
        extras.append(_tool_result_summary_link_markers(entry_m))
        extra = "\n".join([x for x in extras if x]).strip()
        combined = "\n".join([x for x in (header, body.strip() if body else "", extra) if x]).strip()
        return combined

    pieces: list[str] = []
    i = 0
    n = len(msgs)
    out_idx = 1

    while i < n:
        m = msgs[i]
        dt = getattr(m, "data_type", None)

        if dt in ("tool_request", "agent_request"):
            body = _safe_content(m)
            combined = _emit(m, out_idx, body)
            if combined:
                pieces.append(combined)
                out_idx += 1
            i += 1
            continue

        if dt == "tool_result_summary":
            # Summary is a first-class history message; include it as-is.
            body = _safe_content(m)
            combined = _emit(m, out_idx, body)
            if combined:
                pieces.append(combined)
                out_idx += 1
            i += 1
            continue

        if dt in ("tool_result", "agent_result"):
            # Suppress tool_results that have been summarized, unless it's the latest tool_result in this window.
            keep = True
            if dt == "tool_result":
                meta = getattr(m, "metadata", None)
                tid = meta.get("tool_result_id") if isinstance(meta, dict) else None
                if isinstance(tid, str) and tid.strip():
                    tid = tid.strip()
                    if tid in summarized_ids and (last_tool_result_id is None or tid != last_tool_result_id):
                        keep = False
                        # IMPORTANT UX:
                        # Keep a small placeholder so the planner still "sees" that a tool_result happened,
                        # and can follow the summary immediately below it.
                        body = "(tool_result suppressed; see tool_result_summary below)"
                        combined = _emit(m, out_idx, body, attach_from=m, ref_from=m)
                        if combined:
                            pieces.append(combined)
                            out_idx += 1
                        i += 1
                        continue
            if keep:
                body = _safe_content(m)
                combined = _emit(m, out_idx, body, attach_from=m, ref_from=m)
                if combined:
                    pieces.append(combined)
                    out_idx += 1
            i += 1
            continue

        body = _safe_content(m)
        combined = _emit(m, out_idx, body)
        if combined:
            pieces.append(combined)
            out_idx += 1
        i += 1

    return "\n\n".join(pieces).strip()

