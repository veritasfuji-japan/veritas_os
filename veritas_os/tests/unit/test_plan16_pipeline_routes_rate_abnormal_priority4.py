"""Plan #16: prioritized abnormal-path tests for pipeline/routes/rate modules.

Priority order:
1) pipeline_*
2) routes_decide
3) rate_limiting
"""

from __future__ import annotations

from typing import Any

import pytest

from veritas_os.api import rate_limiting as rl
from veritas_os.api import routes_decide as rd
from veritas_os.core.pipeline import pipeline_policy as pp


def test_pipeline_rollout_disabled_strategy_short_circuits_enforcement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rollout strategy=disabled should fail-safe to no enforcement."""
    monkeypatch.setenv("VERITAS_POLICY_RUNTIME_ENFORCE", "true")

    decision = {
        "policy_results": [
            {
                "triggered": True,
                "metadata": {
                    "rollout_controls": {
                        "strategy": "disabled",
                    }
                },
            }
        ]
    }

    enforce, state = pp._is_enforcement_enabled_for_rollout({}, decision)

    assert enforce is False
    assert state == "rollout_disabled"


@pytest.mark.anyio
async def test_routes_replay_endpoint_returns_404_for_missing_decision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Replay endpoint should map ValueError to stable 404 payload."""

    class _DummyServer:
        @staticmethod
        async def verify_signature(*_args: Any, **_kwargs: Any) -> None:
            return None

        @staticmethod
        async def run_replay(*_args: Any, **_kwargs: Any) -> Any:
            raise ValueError("decision not found")

    class _DummyRequest:
        headers: dict[str, str] = {}

    monkeypatch.setattr(rd, "_get_server", lambda: _DummyServer())

    response = await rd.replay_endpoint("missing-decision", _DummyRequest())

    assert response.status_code == 404
    assert b'"error":"decision_not_found"' in response.body


def test_rate_cleanup_bucket_unsafe_removes_expired_and_overflow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rate bucket cleanup should evict expired entries, then cap overflow."""
    monkeypatch.setattr(rl.time, "time", lambda: 1_000.0)

    old_bucket = dict(rl._rate_bucket)
    old_window = rl._RATE_WINDOW
    old_max = rl._RATE_BUCKET_MAX
    try:
        rl._RATE_WINDOW = 60.0
        rl._RATE_BUCKET_MAX = 2
        rl._rate_bucket.clear()
        rl._rate_bucket.update(
            {
                "expired": (1, 700.0),
                "recent_a": (1, 995.0),
                "recent_b": (1, 996.0),
                "recent_c": (1, 997.0),
            }
        )

        rl._cleanup_rate_bucket_unsafe()

        assert "expired" not in rl._rate_bucket
        assert len(rl._rate_bucket) == 2
    finally:
        rl._rate_bucket.clear()
        rl._rate_bucket.update(old_bucket)
        rl._RATE_WINDOW = old_window
        rl._RATE_BUCKET_MAX = old_max
