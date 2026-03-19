"""Pure helpers for MemoryOS planner summary formatting.

This module keeps the presentation-only shaping logic used by
``MemoryStore.summarize_for_planner()`` out of the storage/orchestration
modules so ``memory.py`` can continue shrinking without changing any runtime
responsibilities.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

_EMPTY_SUMMARY = "MemoryOS から参照すべき重要メモは見つかりませんでした。"
_SUMMARY_HEADER = "【MemoryOS 要約】最近の関連エピソード（スコア順・最大数件）"


def _format_summary_timestamp(value: Any) -> str:
    """Convert a timestamp-like value into a planner summary label."""
    if not value:
        return "unknown"

    try:
        return (
            datetime.fromtimestamp(float(value), tz=timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        )
    except (TypeError, ValueError, OSError):
        return "unknown"


def _truncate_summary_text(text: str, limit: int = 120) -> str:
    """Truncate summary text while preserving the existing ellipsis contract."""
    normalized = str(text or "")
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3] + "..."


def build_planner_summary(episodic: List[Dict[str, Any]]) -> str:
    """Build the planner-facing summary string from normalized episodic hits."""
    if not episodic:
        return _EMPTY_SUMMARY

    lines: List[str] = [_SUMMARY_HEADER]
    for index, episode in enumerate(episodic, start=1):
        text = _truncate_summary_text(str(episode.get("text") or ""))
        tags = episode.get("tags") or []
        tag_suffix = f" tags={tags}" if tags else ""
        ts_str = _format_summary_timestamp(episode.get("ts"))
        lines.append(f"- #{index} [{ts_str}]{tag_suffix} {text}")

    return "\n".join(lines)
