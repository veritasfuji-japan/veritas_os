# veritas_os/core/memory_distillation.py
"""
Memory Distillation - episodic to semantic LLM summarization.

Extracted from ``memory.py`` so distill orchestration lives in its own module.
Uses the shared helpers in ``memory_helpers.py`` for prompt building, episode
collection, summary extraction, and semantic doc construction.

Provides:
- distill_memory_for_user(): Full distill pipeline (gather episodes -> LLM -> save)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
import logging

from .memory_helpers import (
    build_distill_prompt,
    build_semantic_memory_doc,
    collect_episodic_records,
    extract_summary_text,
)

logger = logging.getLogger(__name__)


def distill_memory_for_user(
    user_id: str,
    *,
    max_items: int = 200,
    min_text_len: int = 10,
    tags: Optional[List[str]] = None,
    model: Optional[str] = None,
    mem_store: Any = None,
    llm_client_module: Any = None,
    put_fn: Any = None,
) -> Optional[Dict[str, Any]]:
    """
    指定ユーザーの episodic メモリをまとめて「長期記憶ノート（semantic）」に蒸留する。

    Args:
        user_id: Target user ID.
        max_items: Maximum number of episodes to include.
        min_text_len: Minimum text length to include an episode.
        tags: Optional tag filter.
        model: Optional LLM model override.
        mem_store: MemoryStore instance (or lazy proxy) to read from.
        llm_client_module: The llm_client module for chat_completion.
        put_fn: The put() function to save the resulting semantic memory.

    Returns:
        保存した semantic メモリの dict（失敗時は None）
    """
    # 1) memory.json から対象ユーザーのレコードを取得
    try:
        all_records = mem_store.list_all(user_id=user_id)
    except (OSError, RuntimeError, ValueError, TypeError) as e:
        logger.error("[MemoryDistill] list_all failed for user=%s: %s", user_id, e)
        return None

    episodic = collect_episodic_records(
        all_records,
        min_text_len=min_text_len,
        tags=tags,
    )

    if not episodic:
        logger.info("[MemoryDistill] no episodic records for user=%s", user_id)
        return None

    target_eps = episodic[:max_items]

    # 2) プロンプト生成
    prompt = build_distill_prompt(user_id, target_eps)
    system_msg = "You are VERITAS Memory Distill module."

    # 3) LLM コール（唯一の境界: llm_client.chat_completion）
    try:
        chat_fn = getattr(llm_client_module, "chat_completion", None)
        if not callable(chat_fn):
            logger.error("[MemoryDistill] llm_client.chat_completion not available")
            return None
        kwargs: Dict[str, Any] = {"max_tokens": 1024}
        if model:
            kwargs["model"] = model

        resp = chat_fn(
            system_prompt=system_msg,
            user_prompt=prompt,
            **kwargs,
        )

    except TypeError as e:
        logger.error("[MemoryDistill] LLM call TypeError: %s", e)
        return None
    except (RuntimeError, ValueError, OSError) as e:
        logger.error("[MemoryDistill] LLM call failed: %s", e)
        return None

    # 4) レスポンスからテキストを取り出す
    summary_text = extract_summary_text(resp)
    if not summary_text:
        logger.error("[MemoryDistill] empty summary_text from LLM")
        return None

    # 5) semantic メモリとして永続化
    doc = build_semantic_memory_doc(
        user_id=user_id,
        summary_text=summary_text,
        episodes=target_eps,
        tags=tags,
    )

    ok = put_fn("semantic", doc)
    if not ok:
        logger.error("[MemoryDistill] failed to save semantic memory")
        return None

    logger.info(
        "[MemoryDistill] semantic note saved for user=%s (items=%d, chars=%d)",
        user_id,
        len(target_eps),
        len(summary_text),
    )
    return doc
