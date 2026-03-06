from __future__ import annotations

import pytest

from veritas_os.api.pipeline_orchestrator import (
    ComplianceStopException,
    enforce_compliance_stop,
    resolve_dynamic_steps,
    update_runtime_config,
)


def test_dynamic_steps_include_eu_compliance_steps() -> None:
    update_runtime_config(eu_ai_act_mode=True, safety_threshold=0.8)
    payload = {"trust_score": 0.95}
    steps = resolve_dynamic_steps(payload)
    assert "fundamental_rights_impact_assessment" in steps
    assert "human_in_the_loop" in steps


def test_compliance_stop_when_score_below_threshold() -> None:
    update_runtime_config(eu_ai_act_mode=True, safety_threshold=0.9)
    with pytest.raises(ComplianceStopException):
        enforce_compliance_stop({"trust_score": 0.2})


def test_compliance_pass_when_mode_disabled() -> None:
    update_runtime_config(eu_ai_act_mode=False, safety_threshold=0.9)
    result = enforce_compliance_stop({"trust_score": 0.1, "status": "ok"})
    assert result["status"] == "ok"
