# veritas_os/core/pipeline_signature_adapter.py
# -*- coding: utf-8 -*-
"""
Pipeline シグネチャ交渉アダプター。

Public contract:
- ``call_core_decide(core_fn, context, query, alternatives, min_evidence)``
  は kernel.decide / veritas_core.decide のシグネチャ差を吸収する唯一の窓口。

Preferred extension points:
- 新しい呼出パターンの追加はこのモジュール内で行う。
- pipeline.py 本体にはシグネチャ交渉ロジックを置かない。

Compatibility guidance:
- pipeline.py は後方互換のため ``call_core_decide`` を re-export する。
  テストが ``pipeline.call_core_decide`` を monkeypatch するケースを維持する。
"""
from __future__ import annotations

import inspect
import logging
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


async def call_core_decide(
    core_fn: Callable,
    context: Optional[Dict[str, Any]],
    query: str,
    alternatives: Optional[List[Dict[str, Any]]],
    min_evidence: Optional[int] = None,
):
    """
    core_fn のシグネチャ差（kernel.decide / veritas_core.decide の揺れ）を吸収するラッパ。

    対応パターン:
    A) decide(ctx=..., options=..., min_evidence=..., query=...)
    B) decide(context=..., query=..., alternatives=..., min_evidence=...)
    C) decide(context, query, alternatives, min_evidence=?)

    Security/Reliability note:
    - 署名不一致は ``inspect.Signature.bind_partial`` で事前判定する。
    - 実際の呼び出しで発生した ``TypeError`` は内部例外として再送出し、
      フォールバックで握りつぶさない。
    """

    ctx = dict(context or {})
    ctx["query"] = query
    opts = list(alternatives or [])

    def _is_awaitable(x: Any) -> bool:
        return inspect.isawaitable(x)

    def _params(fn) -> Set[str]:
        try:
            return set(inspect.signature(fn).parameters.keys())
        except (TypeError, ValueError, RuntimeError):
            logger.warning(
                "call_core_decide: signature inspection failed for %r",
                fn,
                exc_info=True,
            )
            return set()

    def _can_bind(*args: Any, **kwargs: Any) -> bool:
        """Return True if ``core_fn`` can accept the provided call pattern."""
        try:
            inspect.signature(core_fn).bind_partial(*args, **kwargs)
            return True
        except TypeError:
            return False
        except (ValueError, RuntimeError):
            logger.warning(
                "call_core_decide: bind_partial inspection failed for %r",
                core_fn,
                exc_info=True,
            )
            return True

    p = _params(core_fn)
    attempted_patterns: List[str] = []
    diagnostic_rows: List[str] = []

    # ---- Try A: ctx/options style ----
    kwargs_a = {
        "ctx": ctx,
        "options": opts,
        "min_evidence": min_evidence,
        "query": query,
    }
    can_bind_a = (("ctx" in p) or ("options" in p)) and _can_bind(**kwargs_a)
    diagnostic_rows.append(
        f"A(can_bind={can_bind_a},keys={sorted(kwargs_a.keys())})"
    )
    if can_bind_a:
        attempted_patterns.append("A")
        res = core_fn(**kwargs_a)
        return await res if _is_awaitable(res) else res

    # ---- Try B: context/query/alternatives style ----
    kw = {}
    if "context" in p:
        kw["context"] = ctx
    elif "ctx" in p:
        kw["ctx"] = ctx
    else:
        kw["context"] = ctx

    if "alternatives" in p:
        kw["alternatives"] = opts
    elif "options" in p:
        kw["options"] = opts
    else:
        kw["alternatives"] = opts

    if "query" in p:
        kw["query"] = query

    if "min_evidence" in p:
        kw["min_evidence"] = min_evidence

    can_bind_b = _can_bind(**kw)
    diagnostic_rows.append(f"B(can_bind={can_bind_b},keys={sorted(kw.keys())})")
    if can_bind_b:
        attempted_patterns.append("B")
        res = core_fn(**kw)
        return await res if _is_awaitable(res) else res

    # ---- Try C: positional (last resort) ----
    can_bind_c = _can_bind(ctx, query, opts, min_evidence)
    diagnostic_rows.append("C(can_bind=%s,keys=%s)" % (can_bind_c, ["args"]))
    if can_bind_c:
        attempted_patterns.append("C")
        res = core_fn(ctx, query, opts, min_evidence)
        return await res if _is_awaitable(res) else res

    logger.error(
        "call_core_decide failed signature negotiation: fn=%r diagnostics=%s",
        core_fn,
        "; ".join(diagnostic_rows),
    )
    raise TypeError(
        f"call_core_decide: all calling conventions failed for {core_fn!r}. "
        f"Attempted={attempted_patterns or ['none']}, "
        f"kwargsB={sorted(kw.keys())}, diagnostics={diagnostic_rows}, "
        "last_error=pattern C signature mismatch"
    )


__all__ = ["call_core_decide"]
