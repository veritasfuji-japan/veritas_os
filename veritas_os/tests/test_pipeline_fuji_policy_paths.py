from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import pytest

from veritas_os.core.pipeline_policy import (
    _build_fail_closed_fuji_precheck,
    stage_fuji_precheck,
    stage_gate_decision,
)
from veritas_os.core.pipeline_types import PipelineContext


def test_build_fail_closed_fuji_precheck_contract() -> None:
    payload = _build_fail_closed_fuji_precheck("policy_unavailable")
    assert payload["status"] == "rejected"
    assert payload["risk"] == 1.0
    assert payload["reasons"] == ["policy_unavailable"]
    assert "fuji_precheck_unavailable" in payload["violations"]


def test_stage_fuji_precheck_maps_unknown_status_to_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class DummyFuji:
        @staticmethod
        def validate_action(_query: str, _context: dict[str, Any]) -> dict[str, Any]:
            return {
                "status": "unexpected",
                "risk": "nan",
                "reasons": ["x"],
                "violations": ["y"],
            }

    monkeypatch.setattr(
        "veritas_os.core.pipeline_policy._lazy_import",
        lambda *_args, **_kwargs: DummyFuji,
    )
    ctx = PipelineContext(query="q", context={})
    stage_fuji_precheck(ctx)
    assert ctx.fuji_dict["status"] == "rejected"
    assert any("risk=1.0" in item.get("snippet", "") for item in ctx.evidence)


def test_stage_gate_decision_handles_debate_delta_parse_failure() -> None:
    ctx = PipelineContext(
        fuji_dict={"status": "allow", "risk": 0.3},
        debate=[{"risk_delta": "bad-float"}],
        response_extras={"metrics": {"stage_latency": {"gate": 0}}},
    )
    stage_gate_decision(ctx)
    assert ctx.decision_status == "allow"
    assert ctx.rejection_reason is None


def test_stage_gate_decision_rejects_high_risk_and_low_telos() -> None:
    ctx = PipelineContext(
        fuji_dict={"status": "allow", "risk": 0.95},
        effective_risk=0.95,
        telos=0.2,
        telos_threshold=0.6,
        response_extras={"metrics": {"stage_latency": {"gate": 0}}},
        alternatives=[{"id": "a"}],
        chosen={"id": "a"},
    )
    stage_gate_decision(ctx)
    assert ctx.decision_status == "rejected"
    assert "high risk" in (ctx.rejection_reason or "")
    assert ctx.chosen == {}
    assert ctx.alternatives == []


def test_fuji_policy_path_rejects_outside_absolute_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import veritas_os.core.fuji_policy as fp

    monkeypatch.setenv("VERITAS_FUJI_POLICY", "/tmp/outside.yaml")
    p = fp._policy_path()
    assert p.name == "fuji_default.yaml"


def test_fuji_policy_load_from_str_yaml_parse_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import veritas_os.core.fuji_policy as fp

    class FakeYaml:
        class YAMLError(Exception):
            pass

        @staticmethod
        def safe_load(_content: str) -> dict[str, Any]:
            raise FakeYaml.YAMLError("parse error")

    monkeypatch.setattr(fp, "yaml", FakeYaml)
    monkeypatch.setattr(fp.capability_cfg, "enable_fuji_yaml_policy", True)
    out = fp._load_policy_from_str("x: [", Path("broken.yaml"))
    assert out["version"] in {"fuji_v2_default", "fuji_v2_strict_deny"}


def test_fuji_policy_apply_policy_invalid_precedence_falls_back_to_default() -> None:
    import veritas_os.core.fuji_policy as fp

    policy = {
        "version": "precedence-bad",
        "base_thresholds": {"default": 0.5},
        "categories": {
            "illicit": {"max_risk_allow": 0.1, "action_on_exceed": "deny"},
            "PII": {"max_risk_allow": 0.1, "action_on_exceed": "human_review"},
        },
        "actions": fp._DEFAULT_POLICY["actions"],
        "action_precedence": {"deny": "oops"},
    }
    out = fp._apply_policy(
        risk=0.9,
        categories=["PII", "illicit"],
        stakes=0.5,
        telos_score=0.0,
        policy=policy,
    )
    assert out["decision_status"] == "deny"


def test_fuji_policy_hot_reload_missing_path_noop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import veritas_os.core.fuji_policy as fp

    monkeypatch.setattr(fp, "_policy_path", lambda: Path("/definitely/missing.yaml"))
    before = fp.POLICY
    fp._check_policy_hot_reload()
    assert fp.POLICY is before


def test_fuji_policy_reload_policy_updates_mtime_with_existing_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import veritas_os.core.fuji_policy as fp

    policy_file = tmp_path / "fuji_local.yaml"
    policy_file.write_text("version: local\n", encoding="utf-8")
    monkeypatch.setenv("VERITAS_FUJI_POLICY", str(policy_file))
    monkeypatch.setattr(fp.capability_cfg, "enable_fuji_yaml_policy", False)
    importlib.reload(fp)
    out = fp.reload_policy()
    assert out["version"] == "fuji_v2_default"
