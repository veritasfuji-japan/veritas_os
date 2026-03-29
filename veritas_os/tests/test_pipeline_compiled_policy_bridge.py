from __future__ import annotations

from pathlib import Path

from veritas_os.core.pipeline_policy import stage_fuji_precheck
from veritas_os.core.pipeline_types import PipelineContext
from veritas_os.policy.compiler import compile_policy_to_bundle

EXAMPLES_DIR = Path("policies/examples")


def test_pipeline_bridge_surfaces_compiled_policy_decision(tmp_path: Path) -> None:
    compiled = compile_policy_to_bundle(
        EXAMPLES_DIR / "external_tool_usage_denied.yaml",
        tmp_path,
        compiled_at="2026-03-28T00:00:00Z",
    )

    ctx = PipelineContext(
        query="use external tool",
        context={
            "compiled_policy_bundle_dir": compiled.bundle_dir.as_posix(),
            "domain": "security",
            "route": "/api/tools",
            "actor": "kernel",
            "tool": {"external": True, "name": "unapproved_webhook"},
            "data": {"classification": "restricted"},
            "evidence": {"available": ["data_classification_label"]},
            "approvals": {"approved_by": ["security_officer"]},
        },
    )

    stage_fuji_precheck(ctx)

    governance = ctx.response_extras["governance"]["compiled_policy"]
    assert governance["final_outcome"] == "deny"


def test_pipeline_bridge_enforcement_updates_fuji_status(tmp_path: Path) -> None:
    compiled = compile_policy_to_bundle(
        EXAMPLES_DIR / "missing_mandatory_evidence_halt.yaml",
        tmp_path,
        compiled_at="2026-03-28T00:00:00Z",
    )

    ctx = PipelineContext(
        query="critical decision",
        context={
            "compiled_policy_bundle_dir": compiled.bundle_dir.as_posix(),
            "policy_runtime_enforce": True,
            "domain": "governance",
            "route": "/api/decide",
            "actor": "planner",
            "decision": {"criticality": "critical"},
            "evidence": {"available": ["source_citation"], "missing_count": 2},
            "approvals": {"approved_by": ["audit_reviewer"]},
        },
    )

    stage_fuji_precheck(ctx)

    assert ctx.fuji_dict["status"] == "rejected"
    assert "compiled_policy:halt" in ctx.fuji_dict["reasons"]
