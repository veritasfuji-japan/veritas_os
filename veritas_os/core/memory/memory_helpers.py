"""Shared helper utilities for MemoryOS data shaping.

These helpers keep side-effect-free formatting and normalization logic out of
``memory.py`` so the main module can stay focused on storage, vector access,
and Memory Distill orchestration. The helpers remain inside the MemoryOS
boundary and do not change Planner, Kernel, or FUJI responsibilities.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import time


def _isoformat_from_timestamp(value: Any) -> str:
    """Convert a timestamp-like value to an ISO-8601 string or ``unknown``."""
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return "unknown"


def _truncate_text(text: str, limit: int) -> str:
    """Return ``text`` truncated to ``limit`` characters with ellipsis."""
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def build_distill_prompt(user_id: str, episodes: List[Dict[str, Any]]) -> str:
    """Build the LLM prompt used by Memory Distill from episodic records."""
    lines: List[str] = []
    lines.append(
        "You are VERITAS OS's Memory Distill module.\n"
        "Your job is to compress the user's recent episodic memories into a concise, "
        "useful long-term note that VERITAS can reuse later."
    )
    lines.append("")
    lines.append(f"Target user_id: {user_id}")
    lines.append("")
    lines.append("Here are recent episodic records (newest first):")

    for index, episode in enumerate(episodes, start=1):
        text = str(episode.get("text") or "").strip()
        tags = episode.get("tags") or []
        tag_suffix = f" tags={tags}" if tags else ""
        lines.append(
            f"- #{index} [{_isoformat_from_timestamp(episode.get('ts'))}]"
            f"{tag_suffix} {_truncate_text(text, 300)}"
        )

    lines.append("")
    lines.append(
        "Please write a Japanese summary that captures:\n"
        "1. The main topics and decisions the user is working on\n"
        "2. Ongoing projects or threads (e.g., VERITAS, 労働紛争, 音楽制作)\n"
        "3. Open TODOs or follow-ups that seem important\n"
        "4. Any stable preferences or values that appear\n"
        "\n"
        "Format:\n"
        "「概要」セクション: 箇条書きで3〜7行\n"
        "「プロジェクト別ノート」セクション: VERITAS / 労働紛争 / 音楽 / その他 に分けて\n"
        "「TODO / Next Actions」セクション: 箇条書きで3〜10行\n"
    )
    return "\n".join(lines)


def extract_summary_text(response: Any) -> str:
    """Extract summary text from multiple LLM response shapes."""
    if isinstance(response, dict):
        if "choices" in response:
            try:
                content = response["choices"][0]["message"]["content"]
                if content:
                    return str(content).strip()
            except (IndexError, KeyError, TypeError):
                pass
        for key in ("text", "content", "output"):
            value = response.get(key)
            if value:
                return str(value).strip()
        return ""

    if isinstance(response, str):
        return response.strip()

    return str(getattr(response, "text", "") or "").strip()


def collect_episodic_records(
    records: List[Dict[str, Any]],
    *,
    min_text_len: int,
    tags: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Filter MemoryStore records down to distillable episodic entries."""
    episodic: List[Dict[str, Any]] = []
    filter_tags = set(tags or [])

    for record in records:
        value = record.get("value") or {}
        if not isinstance(value, dict):
            continue

        if str(value.get("kind") or "episodic") != "episodic":
            continue

        text = str(value.get("text") or "").strip()
        if len(text) < min_text_len:
            continue

        episode_tags = value.get("tags") or []
        if filter_tags and not (filter_tags & set(episode_tags)):
            continue

        episodic.append(
            {
                "source_key": record.get("key"),
                "text": text,
                "tags": episode_tags,
                "ts": record.get("ts") or time.time(),
            }
        )

    episodic.sort(key=lambda item: item.get("ts", 0.0), reverse=True)
    return episodic


def build_semantic_memory_doc(
    *,
    user_id: str,
    summary_text: str,
    episodes: List[Dict[str, Any]],
    tags: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Build the semantic memory document persisted after distillation."""
    return {
        "kind": "semantic",
        "text": summary_text,
        "tags": (tags or []) + ["memory_distill", "summary", "long_term"],
        "meta": {
            "user_id": user_id,
            "source": "distill_memory_for_user",
            "source_episode_keys": [
                str(episode.get("source_key"))
                for episode in episodes
                if episode.get("source_key")
            ],
            "item_count": len(episodes),
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    }


def build_vector_rebuild_documents(
    records: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Convert MemoryStore records into vector-index rebuild documents."""
    documents: List[Dict[str, Any]] = []

    for record in records:
        value = record.get("value")
        if not isinstance(value, dict):
            continue

        text = str(value.get("text") or "")
        if not text.strip():
            continue

        meta = value.get("meta", {}) or {}
        documents.append(
            {
                "kind": value.get("kind", "episodic"),
                "text": text,
                "tags": value.get("tags", []),
                "meta": {
                    "user_id": record.get("user_id"),
                    "created_at": record.get("ts"),
                    **meta,
                },
            }
        )

    return documents
