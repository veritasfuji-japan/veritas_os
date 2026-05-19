"""Regression tests for pipeline/kernel dependency injection compatibility."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from veritas_os.core import pipeline
from veritas_os.core.pipeline.pipeline_execute import stage_core_execute
from veritas_os.core.pipeline.pipeline_types import PipelineContext


def test_set_veritas_core_supports_monkeypatch_compatible_placeholder() -> None:
    """`set_veritas_core(None)` should preserve attribute-monkeypatch compatibility."""
    pipeline.set_veritas_core(None)
    setattr(pipeline.veritas_core, "decide", lambda **_kwargs: {})
    assert callable(pipeline.veritas_core.decide)


@pytest.mark.asyncio
async def test_stage_core_execute_uses_injected_decide() -> None:
    """Injected kernel adapter should execute the core-decision path."""
    calls: list[dict[str, Any]] = []

    async def _call_core_decide_fn(**kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        return {"alternatives": [{"title": "A"}], "evidence": []}

    ctx = PipelineContext(
        request_id="rid",
        query="q",
        input_alts=[],
        plan=[],
        context={},
        min_ev=0,
    )
    kernel = SimpleNamespace(decide=lambda **_kwargs: {})

    await stage_core_execute(
        ctx,
        call_core_decide_fn=_call_core_decide_fn,
        append_trust_log_fn=lambda _entry: None,
        veritas_core=kernel,
    )

    assert calls
    assert "kernel_missing" not in (ctx.response_extras.get("env_tools") or {})


@pytest.mark.asyncio
async def test_stage_core_execute_marks_kernel_missing_when_not_injected() -> None:
    """Missing injection should take the degraded kernel-missing fallback path."""
    ctx = PipelineContext(
        request_id="rid",
        query="q",
        input_alts=[],
        plan=[],
        context={},
        min_ev=0,
    )

    async def _should_not_run(**_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("core decide should not run without injected decide")

    await stage_core_execute(
        ctx,
        call_core_decide_fn=_should_not_run,
        append_trust_log_fn=lambda _entry: None,
        veritas_core=SimpleNamespace(),
    )

    assert ctx.response_extras["env_tools"]["kernel_missing"] is True
