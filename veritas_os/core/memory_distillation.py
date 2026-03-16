# veritas_os/core/memory_distillation.py
"""
Memory Distillation - episodic to semantic LLM summarization.

Provides:
- build_distill_prompt(): Build a summarization prompt from episodes
- distill_memory_for_user(): Full distill pipeline (gather episodes -> LLM -> save)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
import time
import logging

logger = logging.getLogger(__name__)


def build_distill_prompt(user_id: str, episodes: List[Dict[str, Any]]) -> str:
    """
    エピソードのリストから、LLM に投げる要約プロンプトを組み立てる。
    """
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

    for i, ep in enumerate(episodes, start=1):
        ts = ep.get("ts")
        try:
            ts_f = float(ts)
            ts_str = datetime.fromtimestamp(ts_f, tz=timezone.utc).isoformat()
        except Exception:
            ts_str = "unknown"

        text = str(ep.get("text") or "").strip()
        tags = ep.get("tags") or []
        tag_str = f" tags={tags}" if tags else ""

        if len(text) > 300:
            text_short = text[:297] + "..."
        else:
            text_short = text

        lines.append(f"- #{i} [{ts_str}]{tag_str} {text_short}")

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

    episodic: List[Dict[str, Any]] = []
    filter_tags = set(tags or [])

    for r in all_records:
        value = r.get("value") or {}
        if not isinstance(value, dict):
            continue

        kind = str(value.get("kind") or "episodic")
        if kind != "episodic":
            continue

        text = str(value.get("text") or "").strip()
        if len(text) < min_text_len:
            continue

        ep_tags = value.get("tags") or []

        # tags 指定がある場合は、そのタグを含むものだけ対象
        if filter_tags and not (filter_tags & set(ep_tags)):
            continue

        ep = {
            "source_key": r.get("key"),
            "text": text,
            "tags": ep_tags,
            "ts": r.get("ts") or time.time(),
        }
        episodic.append(ep)

    if not episodic:
        logger.info("[MemoryDistill] no episodic records for user=%s", user_id)
        return None

    # 新しい順にソートして max_items までに圧縮
    episodic.sort(key=lambda x: x.get("ts", 0.0), reverse=True)
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
    summary_text = ""

    if isinstance(resp, dict):
        # 典型的な OpenAI / LLM スタイルのレスポンスも一応ハンドル
        if "choices" in resp:
            try:
                summary_text = (
                    resp["choices"][0]["message"]["content"]
                    or ""
                )
            except (IndexError, KeyError, TypeError):
                summary_text = ""
        if not summary_text:
            summary_text = (
                resp.get("text")
                or resp.get("content")
                or resp.get("output")
                or ""
            )
    elif isinstance(resp, str):
        summary_text = resp
    else:
        summary_text = str(getattr(resp, "text", "") or "")

    summary_text = str(summary_text).strip()
    if not summary_text:
        logger.error("[MemoryDistill] empty summary_text from LLM")
        return None

    # 5) semantic メモリとして永続化
    meta = {
        "user_id": user_id,
        "source": "distill_memory_for_user",
        "source_episode_keys": [
            str(ep.get("source_key"))
            for ep in target_eps
            if ep.get("source_key")
        ],
        "item_count": len(target_eps),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    doc: Dict[str, Any] = {
        "kind": "semantic",
        "text": summary_text,
        "tags": (tags or []) + ["memory_distill", "summary", "long_term"],
        "meta": meta,
    }

    ok = put_fn("semantic", doc)
    if not ok:
        logger.error("[MemoryDistill] failed to save semantic memory")
        return None

    logger.info(
        f"[MemoryDistill] semantic note saved for user={user_id} "
        f"(items={len(target_eps)}, chars={len(summary_text)})"
    )
    return doc
