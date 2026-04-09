"""Plan #9: edge-case tests for low-coverage pipeline/routes/rate modules."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from veritas_os.api import rate_limiting as rl
from veritas_os.api import routes_decide as rd
from veritas_os.core.pipeline import pipeline_policy as pp
from veritas_os.core.pipeline.pipeline_types import PipelineContext


def test_rollout_controls_returns_empty_for_non_list_policy_results() -> None:
    """Non-list policy results should not crash rollout control extraction."""
    decision = {"policy_results": "invalid"}

    assert pp._resolve_rollout_controls(decision) == {}


def test_rollback_metadata_skips_non_triggered_or_invalid_metadata() -> None:
    """Rollback extraction should ignore non-triggered entries and bad metadata."""
    decision = {
        "policy_results": [
            {"triggered": False, "metadata": {"rollback": {"ticket": "x"}}},
            {"triggered": True, "metadata": "invalid"},
        ]
    }

    assert pp._resolve_rollback_metadata(decision) == {}


def test_rollout_enforcement_unknown_strategy_defaults_to_safe_full(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unknown rollout strategy should fail safe to full enforcement."""
    monkeypatch.setattr(pp, "_coerce_policy_enforce_flag", lambda _raw: True)

    decision = {
        "policy_results": [
            {
                "triggered": True,
                "metadata": {
                    "rollout_controls": {"strategy": "mystery_mode"},
                },
            }
        ]
    }

    enabled, state = pp._is_enforcement_enabled_for_rollout({}, decision)

    assert enabled is True
    assert state == "full_unknown_strategy"


def test_rollout_enforcement_canary_skip_when_bucket_outside_percent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Canary rollout should be skipped when deterministic bucket is outside target."""
    monkeypatch.setattr(pp, "_coerce_policy_enforce_flag", lambda _raw: True)
    monkeypatch.setattr(pp, "_deterministic_bucket_ratio", lambda _key: 0.9)

    decision = {
        "policy_results": [
            {
                "triggered": True,
                "metadata": {
                    "rollout_controls": {"strategy": "canary", "canary_percent": 10},
                },
            }
        ]
    }

    enabled, state = pp._is_enforcement_enabled_for_rollout(
        {"request_id": "req-1"},
        decision,
    )

    assert enabled is False
    assert state == "canary_skip"


def test_apply_compiled_policy_runtime_bridge_handles_non_dict_governance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bridge should recover when existing governance payload is not a dict."""

    class _Decision:
        @staticmethod
        def to_dict() -> dict[str, Any]:
            return {"final_outcome": "allow", "policy_results": []}

    monkeypatch.setattr(pp, "load_runtime_bundle", lambda _path: object())
    monkeypatch.setattr(pp, "evaluate_runtime_policies", lambda _bundle, _ctx: _Decision())

    ctx = PipelineContext(
        query="q",
        request_id="req-1",
        context={"compiled_policy_bundle_dir": "/tmp/bundle"},
        response_extras={"governance": "invalid"},
        fuji_dict={},
    )

    pp._apply_compiled_policy_runtime_bridge(ctx)

    assert isinstance(ctx.response_extras.get("governance"), dict)
    assert "compiled_policy" in ctx.response_extras["governance"]


@pytest.mark.anyio
async def test_replay_decision_endpoint_parses_mock_external_apis_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """mock_external_apis=off should disable mocks for replay endpoint."""

    class _DummyPipeline:
        async def replay_decision(self, *, decision_id: str, mock_external_apis: bool) -> dict[str, Any]:
            return {
                "decision_id": decision_id,
                "mock_external_apis": mock_external_apis,
            }

    class _DummyServer:
        @staticmethod
        def get_decision_pipeline() -> _DummyPipeline:
            return _DummyPipeline()

    class _DummyRequest:
        query_params = {"mock_external_apis": "off"}

    monkeypatch.setattr(rd, "_get_server", lambda: _DummyServer())

    resp = await rd.replay_decision_endpoint("d-1", _DummyRequest())

    assert resp["decision_id"] == "d-1"
    assert resp["mock_external_apis"] is False


def test_effective_nonce_max_uses_default_when_server_override_is_non_int(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-int server override for nonce max should fall back to module default."""

    class _DummyServer:
        _NONCE_MAX = "500"

    monkeypatch.setattr(rl, "_NONCE_MAX", 77)
    monkeypatch.setattr("veritas_os.api.server", _DummyServer(), raising=False)

    assert rl._effective_nonce_max() == 77


def test_cleanup_rate_bucket_unsafe_trims_overflow(monkeypatch: pytest.MonkeyPatch) -> None:
    """Overflow entries should be trimmed to configured maximum safely."""
    monkeypatch.setattr(rl, "_RATE_BUCKET_MAX", 2)
    monkeypatch.setattr(rl.time, "time", lambda: 1000.0)

    with rl._rate_lock:
        rl._rate_bucket.clear()
        rl._rate_bucket["k1"] = (1, 900.0)
        rl._rate_bucket["k2"] = (1, 900.0)
        rl._rate_bucket["k3"] = (1, 900.0)
        rl._cleanup_rate_bucket_unsafe()
        size_after = len(rl._rate_bucket)
        rl._rate_bucket.clear()

    assert size_after == 2
