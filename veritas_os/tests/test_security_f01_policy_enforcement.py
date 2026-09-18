"""Regression tests for security finding F-01: policy enforcement trust boundary."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from veritas_os.core.pipeline import pipeline_policy as pp
from veritas_os.core.pipeline.pipeline_types import PipelineContext


class _Decision:
    def __init__(self, outcome: str = "deny", *, metadata: dict[str, Any] | None = None):
        self._outcome = outcome
        self._metadata = metadata or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "final_outcome": self._outcome,
            "triggered_policies": ["policy.security.f01"],
            "policy_results": [
                {
                    "triggered": True,
                    "metadata": self._metadata,
                }
            ],
        }


def _ctx(context: dict[str, Any] | None = None) -> PipelineContext:
    return PipelineContext(
        query="security regression",
        context=context or {},
        response_extras={},
        fuji_dict={"status": "allow", "reasons": []},
    )


def test_request_false_cannot_disable_server_mandated_enforcement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VERITAS_POLICY_RUNTIME_ENFORCE", "true")
    monkeypatch.setenv("VERITAS_POLICY_RUNTIME_BUNDLE_DIR", "/trusted/bundle")
    monkeypatch.setattr(pp, "load_runtime_bundle", lambda path: SimpleNamespace(
        manifest={}, version="1", semantic_hash="sha256:test"
    ))
    monkeypatch.setattr(
        pp,
        "evaluate_runtime_policies",
        lambda _bundle, _context: _Decision("deny"),
    )

    ctx = _ctx(
        {
            "policy_runtime_enforce": False,
            "compiled_policy_bundle_dir": "/attacker/allow-bundle",
        }
    )
    pp._apply_compiled_policy_runtime_bridge(ctx)

    assert ctx.fuji_dict["status"] == "rejected"
    assert "compiled_policy:deny" in ctx.fuji_dict["reasons"]


def test_server_mandated_enforcement_ignores_request_bundle_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VERITAS_POLICY_RUNTIME_ENFORCE", "true")
    monkeypatch.setenv("VERITAS_POLICY_RUNTIME_BUNDLE_DIR", "/trusted/bundle")
    loaded: list[str] = []

    def _load(path: str) -> Any:
        loaded.append(str(path))
        return SimpleNamespace(manifest={}, version="1", semantic_hash="sha256:test")

    monkeypatch.setattr(pp, "load_runtime_bundle", _load)
    monkeypatch.setattr(
        pp,
        "evaluate_runtime_policies",
        lambda _bundle, _context: _Decision("deny"),
    )

    ctx = _ctx({"compiled_policy_bundle_dir": "/attacker/missing"})
    pp._apply_compiled_policy_runtime_bridge(ctx)

    assert loaded == ["/trusted/bundle"]
    assert ctx.fuji_dict["status"] == "rejected"


def test_missing_trusted_bundle_fails_closed_when_enforcement_is_mandatory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("VERITAS_POLICY_RUNTIME_ENFORCE", "true")
    monkeypatch.delenv("VERITAS_POLICY_RUNTIME_BUNDLE_DIR", raising=False)
    monkeypatch.setenv(
        "VERITAS_POLICY_ACTIVE_POINTER_PATH",
        str(tmp_path / "missing-active-bundle.json"),
    )

    ctx = _ctx({"compiled_policy_bundle_dir": "/attacker/bundle"})
    pp._apply_compiled_policy_runtime_bridge(ctx)

    assert ctx.fuji_dict["status"] == "rejected"
    assert "compiled_policy:required_bundle_unavailable" in ctx.fuji_dict["reasons"]
    rollout = ctx.response_extras["governance"]["compiled_policy_rollout"]
    assert rollout["enforced"] is True
    assert rollout["state"] == "fail_closed"


def test_policy_load_failure_fails_closed_when_enforcement_is_mandatory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VERITAS_POLICY_RUNTIME_ENFORCE", "true")
    monkeypatch.setenv("VERITAS_POLICY_RUNTIME_BUNDLE_DIR", "/trusted/bundle")
    monkeypatch.setattr(
        pp,
        "load_runtime_bundle",
        lambda _path: (_ for _ in ()).throw(ValueError("invalid bundle")),
    )

    ctx = _ctx()
    pp._apply_compiled_policy_runtime_bridge(ctx)

    assert ctx.fuji_dict["status"] == "rejected"
    assert "compiled_policy:runtime_unavailable" in ctx.fuji_dict["reasons"]


def test_mandatory_canary_without_trusted_rollout_key_enforces_full(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VERITAS_POLICY_RUNTIME_ENFORCE", "true")
    monkeypatch.delenv("VERITAS_POLICY_ROLLOUT_KEY", raising=False)

    decision = _Decision(
        "deny",
        metadata={
            "rollout_controls": {
                "strategy": "canary",
                "canary_percent": 0,
            }
        },
    ).to_dict()

    enforced, state = pp._is_enforcement_enabled_for_rollout(
        {
            "request_id": "caller-selectable",
            "policy_rollout_key": "caller-selectable",
            "policy_runtime_enforce": False,
        },
        decision,
    )

    assert enforced is True
    assert state == "full_no_trusted_rollout_key"


def test_trusted_active_pointer_is_constrained_to_bundles_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    bundles_root = tmp_path / "bundles"
    bundles_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    pointer = tmp_path / "active.json"
    pointer.write_text(
        '{"active_bundle_dir": "' + str(outside.resolve()).replace("\\", "\\\\") + '"}',
        encoding="utf-8",
    )

    monkeypatch.delenv("VERITAS_POLICY_RUNTIME_BUNDLE_DIR", raising=False)
    monkeypatch.setenv("VERITAS_POLICY_BUNDLES_ROOT", str(bundles_root))
    monkeypatch.setenv("VERITAS_POLICY_ACTIVE_POINTER_PATH", str(pointer))

    with pytest.raises(ValueError, match="escapes"):
        pp._resolve_trusted_runtime_bundle_dir()
