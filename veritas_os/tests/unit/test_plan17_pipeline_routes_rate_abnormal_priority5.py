"""Plan #17: prioritized abnormal-path tests for sub-80 modules.

Priority order:
1) pipeline_*
2) routes_decide
3) rate_limiting
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from veritas_os.api import rate_limiting as rl
from veritas_os.api import routes_decide as rd
from veritas_os.api.schemas import DecideRequest
from veritas_os.core.pipeline import pipeline_execute as pe
from veritas_os.core.pipeline.pipeline_types import PipelineContext


@pytest.mark.anyio
async def test_stage_core_execute_handles_broken_veritas_core_attribute_access() -> None:
    """Broken veritas_core attribute access should degrade gracefully to kernel-missing path."""

    class _BrokenCore:
        def __getattribute__(self, name: str) -> Any:
            if name == "decide":
                raise TypeError("broken decide attribute")
            return super().__getattribute__(name)

    ctx = PipelineContext(query="q", request_id="req-plan17", context={})

    async def _unused_call(**_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("core decide should not be called when attribute lookup fails")

    await pe.stage_core_execute(
        ctx,
        call_core_decide_fn=_unused_call,
        append_trust_log_fn=lambda _entry: None,
        veritas_core=_BrokenCore(),
    )

    assert ctx.raw == {}
    assert ctx.response_extras["env_tools"]["kernel_missing"] is True


@pytest.mark.anyio
async def test_decide_uses_anonymous_user_when_request_context_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """decide should send anonymous user_id when request.state and context user_id are absent."""
    telos_calls: list[tuple[str, Any]] = []

    class _Pipeline:
        @staticmethod
        async def run_decide_pipeline(**_kwargs: Any) -> dict[str, Any]:
            return {
                "request_id": "req-anon",
                "fuji": {"decision_status": "allow"},
                "telos_score": 0.77,
            }

    class _Server:
        class _LazyState:
            def __init__(self) -> None:
                self.obj = None
                self.attempted = False
                self.err = None

        _pipeline_state = _LazyState()

        @staticmethod
        def get_decision_pipeline() -> _Pipeline:
            return _Pipeline()

        @staticmethod
        def _publish_event(*_args: Any, **_kwargs: Any) -> None:
            return None

    monkeypatch.setattr(rd, "_get_server", lambda: _Server)
    monkeypatch.setattr(rd, "set_telos_score", lambda user_id, score: telos_calls.append((user_id, score)))

    req = DecideRequest(query="hello", context={})
    request = SimpleNamespace(state=SimpleNamespace())

    response = await rd.decide(req, request)

    assert getattr(response, "request_id", "") == "req-anon"
    assert telos_calls == [("anonymous", 0.77)]


def test_effective_nonce_max_prefers_server_integer_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Integer override from api.server should be honored for nonce capacity limits."""

    class _ServerOverride:
        _NONCE_MAX = 1234

    monkeypatch.setattr(rl, "_NONCE_MAX", 77)
    monkeypatch.setattr("veritas_os.api.server", _ServerOverride(), raising=False)

    assert rl._effective_nonce_max() == 1234
