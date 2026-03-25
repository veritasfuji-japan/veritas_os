# veritas_os/core/kernel_episode.py
# -*- coding: utf-8 -*-
"""Episode logging side-effects extracted from ``kernel.decide()``.

This module owns the "save episode to MemoryOS" responsibility that was
previously inlined inside ``decide()``.  Extracting it makes the decision
core easier to test in isolation and keeps side-effect boundaries explicit.

Backward compatibility:
- Internal helper only; ``decide()`` remains the public contract.
- ``kernel_stages.save_episode_to_memory()`` is a separate, simpler
  implementation used by the staged pipeline path.  This module handles the
  richer variant that includes PII redaction via ``redact_payload``.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict

logger = logging.getLogger(__name__)


def save_episode(
    *,
    query: str,
    chosen: Dict[str, Any],
    ctx: Dict[str, Any],
    intent: str,
    mode: str,
    telos_score: float,
    req_id: str,
    mem_core: Any,
    redact_payload_fn: Any,
    extras: Dict[str, Any],
) -> None:
    """Persist a decision episode to MemoryOS with PII redaction.

    This is a no-op when the pipeline has already saved the episode
    (indicated by ``ctx["_episode_saved_by_pipeline"]``).

    Args:
        query: User query text.
        chosen: The selected alternative dict.
        ctx: Full context dict.
        intent: Detected intent string.
        mode: Decision mode string.
        telos_score: Computed telos score.
        req_id: Request id.
        mem_core: The ``memory`` module (injected).
        redact_payload_fn: ``utils.redact_payload`` callable.
        extras: Mutable dict for metadata / error reporting.
    """
    orchestrated_by_pipeline = bool(ctx.get("_orchestrated_by_pipeline"))
    if orchestrated_by_pipeline and ctx.get("_episode_saved_by_pipeline"):
        return
    if ctx.get("_episode_saved_by_pipeline"):
        return

    user_id = ctx.get("user_id") or "cli"

    try:
        episode_text = (
            f"[query] {query}\n"
            f"[chosen] {chosen.get('title')}\n"
            f"[mode] {mode}\n"
            f"[intent] {intent}\n"
            f"[telos_score] {telos_score}"
        )
        episode_record: Dict[str, Any] = {
            "text": episode_text,
            "tags": ["episode", "decide", "veritas"],
            "meta": {
                "user_id": user_id,
                "request_id": req_id,
                "mode": mode,
                "intent": intent,
            },
        }
        redacted_episode_record = redact_payload_fn(episode_record)
        if redacted_episode_record != episode_record:
            extras.setdefault("memory_log", {})
            extras["memory_log"]["warning"] = (
                "PII detected in episode log; masked before persistence."
            )
        try:
            mem_core.MEM.put("episodic", redacted_episode_record)
        except TypeError:
            mem_core.MEM.put(
                user_id,
                f"decision:{req_id}",
                redacted_episode_record,
            )
    except (TypeError, ValueError, RuntimeError, OSError) as e:
        extras.setdefault("memory_log", {})
        extras["memory_log"]["error"] = repr(e)


__all__ = ["save_episode"]
