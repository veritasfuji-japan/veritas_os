"""Regression tests for pipeline/kernel dependency injection compatibility."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from veritas_os.core import pipeline
from veritas_os.core.pipeline import pipeline_execute
from veritas_os.core.pipeline.pipeline_execute import stage_core_execute
from veritas_os.core.pipeline.pipeline_types import PipelineContext


@pytest.fixture
def _reset_kernel_missing_log_state() -> None:
    """Reset module-level kernel-missing dedup state between tests."""
    original = pipeline_execute._KERNEL_MISSING_LOGGED
    pipeline_execute._KERNEL_MISSING_LOGGED = False
    try:
        yield
    finally:
        pipeline_execute._KERNEL_MISSING_LOGGED = original


def test_set_veritas_core_supports_monkeypatch_compatible_placeholder() -> None:
    """`set_veritas_core(None)` should preserve attribute-monkeypatch compatibility."""
    original = pipeline.veritas_core
    try:
        pipeline.set_veritas_core(None)
        setattr(pipeline.veritas_core, "decide", lambda **_kwargs: {})
        assert callable(pipeline.veritas_core.decide)
    finally:
        pipeline.set_veritas_core(original)


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


@pytest.mark.asyncio
async def test_stage_core_execute_logs_error_when_kernel_missing(
    caplog: pytest.LogCaptureFixture,
    _reset_kernel_missing_log_state: None,
) -> None:
    """Missing kernel decide should emit an ERROR-level governance signal."""
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

    with caplog.at_level("ERROR"):
        await stage_core_execute(
            ctx,
            call_core_decide_fn=_should_not_run,
            append_trust_log_fn=lambda _entry: None,
            veritas_core=SimpleNamespace(),
        )

    assert any("core decide unavailable" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_stage_core_execute_sets_env_tools_safely_when_extras_lacks_env_tools(
    _reset_kernel_missing_log_state: None,
) -> None:
    """Missing env_tools key should be initialized safely in degraded path."""
    ctx = PipelineContext(
        request_id="rid",
        query="q",
        input_alts=[],
        plan=[],
        context={},
        min_ev=0,
    )
    ctx.response_extras = {}

    async def _should_not_run(**_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("core decide should not run without injected decide")

    await stage_core_execute(
        ctx,
        call_core_decide_fn=_should_not_run,
        append_trust_log_fn=lambda _entry: None,
        veritas_core=SimpleNamespace(),
    )

    env_tools = ctx.response_extras["env_tools"]
    assert env_tools["kernel_missing"] is True
    assert "kernel_degraded_at" in env_tools
    assert isinstance(env_tools["kernel_degraded_at"], float)


@pytest.mark.asyncio
async def test_stage_core_execute_error_log_is_deduplicated_per_process(
    caplog: pytest.LogCaptureFixture,
    _reset_kernel_missing_log_state: None,
) -> None:
    """Kernel-missing ERROR log should be emitted once and deduplicated afterwards."""
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

    with caplog.at_level("DEBUG"):
        await stage_core_execute(
            ctx,
            call_core_decide_fn=_should_not_run,
            append_trust_log_fn=lambda _entry: None,
            veritas_core=SimpleNamespace(),
        )
        await stage_core_execute(
            ctx,
            call_core_decide_fn=_should_not_run,
            append_trust_log_fn=lambda _entry: None,
            veritas_core=SimpleNamespace(),
        )

    error_records = [
        record for record in caplog.records
        if record.levelname == "ERROR" and "core decide unavailable" in record.message
    ]
    assert len(error_records) == 1
