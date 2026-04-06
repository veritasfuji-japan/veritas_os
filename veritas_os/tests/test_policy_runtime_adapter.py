from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from veritas_os.policy.compiler import compile_policy_to_bundle
from veritas_os.policy.evaluator import evaluate_runtime_policies
from veritas_os.policy.runtime_adapter import (
    RuntimePolicyBundle,
    adapt_canonical_ir,
    adapt_compiled_payload,
    load_runtime_bundle,
)

EXAMPLES_DIR = Path("policies/examples")


def _compile_bundle(tmp_path: Path, policy_file: str):
    return compile_policy_to_bundle(
        EXAMPLES_DIR / policy_file,
        tmp_path,
        compiled_at="2026-03-28T00:00:00Z",
    )


def test_high_risk_route_requires_human_review(tmp_path: Path) -> None:
    result = _compile_bundle(tmp_path, "high_risk_route_requires_human_review.yaml")
    runtime_bundle = load_runtime_bundle(result.bundle_dir)

    context = {
        "domain": "governance",
        "route": "/api/decide",
        "actor": "planner",
        "risk": {"level": "critical"},
        "runtime": {"auto_execute": False},
        "evidence": {"available": ["risk_assessment", "impact_assessment"]},
        "approvals": {"approved_by": ["governance_officer", "safety_reviewer"]},
    }
    decision = evaluate_runtime_policies(runtime_bundle, context).to_dict()

    assert decision["final_outcome"] == "require_human_review"
    assert "policy.high_risk_route.human_review" in decision["triggered_policies"]


def test_missing_evidence_surfaces_halt_and_evidence_gap(tmp_path: Path) -> None:
    result = _compile_bundle(tmp_path, "missing_mandatory_evidence_halt.yaml")
    runtime_bundle = load_runtime_bundle(result.bundle_dir)

    context = {
        "domain": "governance",
        "route": "/api/decide",
        "actor": "planner",
        "decision": {"criticality": "critical"},
        "evidence": {"available": ["source_citation"], "missing_count": 2},
        "approvals": {"approved_by": ["audit_reviewer"]},
    }
    decision = evaluate_runtime_policies(runtime_bundle, context).to_dict()

    assert decision["final_outcome"] == "halt"
    assert decision["evidence_gaps"][0]["missing_evidence"] == [
        "approval_ticket",
        "impact_assessment",
    ]


def test_prohibited_external_tool_use_is_denied(tmp_path: Path) -> None:
    result = _compile_bundle(tmp_path, "external_tool_usage_denied.yaml")
    runtime_bundle = load_runtime_bundle(result.bundle_dir)

    context = {
        "domain": "security",
        "route": "/api/tools",
        "actor": "kernel",
        "tool": {"external": True, "name": "unapproved_webhook"},
        "data": {"classification": "restricted"},
        "evidence": {"available": ["data_classification_label"]},
        "approvals": {"approved_by": ["security_officer"]},
    }
    decision = evaluate_runtime_policies(runtime_bundle, context).to_dict()

    assert decision["final_outcome"] == "deny"
    assert "emit_security_alert" in decision["obligations"]


def test_explanation_metadata_unmet_approvals_and_obligations_are_surfaced(
    tmp_path: Path,
) -> None:
    result = _compile_bundle(tmp_path, "high_risk_route_requires_human_review.yaml")
    runtime_bundle = load_runtime_bundle(result.bundle_dir)

    context = {
        "domain": "governance",
        "route": "/api/decide",
        "actor": "planner",
        "risk": {"level": "high"},
        "runtime": {"auto_execute": False},
        "evidence": {"available": ["risk_assessment", "impact_assessment"]},
        "approvals": {"approved_by": ["governance_officer"]},
    }
    decision = evaluate_runtime_policies(runtime_bundle, context).to_dict()

    assert decision["explanations"][0]["summary"]
    assert not decision["approval_requirements"][0]["minimum_approval_met"]
    assert "attach_review_ticket" in decision["obligations"]


def test_allow_and_escalate_outcomes_are_supported() -> None:
    allow_bundle = adapt_compiled_payload(
        canonical_ir={
            "schema_version": "1.0",
            "policy_id": "policy.runtime.allow",
            "version": "1",
            "title": "Allow when safe",
            "description": "Allow in safe scenario.",
            "effective_date": None,
            "scope": {
                "domains": ["governance"],
                "routes": ["/api/decide"],
                "actors": ["planner"],
            },
            "conditions": [{"field": "risk.level", "operator": "eq", "value": "low"}],
            "requirements": {
                "required_evidence": [],
                "required_reviewers": [],
                "minimum_approval_count": 0,
            },
            "constraints": [],
            "outcome": {"decision": "allow", "reason": "Low risk."},
            "obligations": [],
            "test_vectors": [],
            "source_refs": [],
            "metadata": {},
        },
        manifest={"schema_version": "0.1"},
    )
    escalate_bundle = adapt_compiled_payload(
        canonical_ir={
            "schema_version": "1.0",
            "policy_id": "policy.runtime.escalate",
            "version": "1",
            "title": "Escalate anomaly",
            "description": "Escalate on anomaly.",
            "effective_date": None,
            "scope": {
                "domains": ["governance"],
                "routes": ["/api/decide"],
                "actors": ["planner"],
            },
            "conditions": [{"field": "risk.level", "operator": "eq", "value": "medium"}],
            "requirements": {
                "required_evidence": [],
                "required_reviewers": [],
                "minimum_approval_count": 0,
            },
            "constraints": [],
            "outcome": {"decision": "escalate", "reason": "Anomaly detected."},
            "obligations": ["notify_governance_channel"],
            "test_vectors": [],
            "source_refs": [],
            "metadata": {},
        },
        manifest={"schema_version": "0.1"},
    )

    allow_decision = evaluate_runtime_policies(
        allow_bundle,
        {
            "domain": "governance",
            "route": "/api/decide",
            "actor": "planner",
            "risk": {"level": "low"},
        },
    ).to_dict()
    escalate_decision = evaluate_runtime_policies(
        escalate_bundle,
        {
            "domain": "governance",
            "route": "/api/decide",
            "actor": "planner",
            "risk": {"level": "medium"},
        },
    ).to_dict()

    assert allow_decision["final_outcome"] == "allow"
    assert escalate_decision["final_outcome"] == "escalate"


def test_regex_condition_respects_runtime_guardrails() -> None:
    regex_bundle = adapt_compiled_payload(
        canonical_ir={
            "schema_version": "1.0",
            "policy_id": "policy.runtime.regex_guardrails",
            "version": "1",
            "title": "Regex guardrail",
            "description": "Use regex condition.",
            "effective_date": None,
            "scope": {
                "domains": ["governance"],
                "routes": ["/api/decide"],
                "actors": ["planner"],
            },
            "conditions": [
                {"field": "request.text", "operator": "regex", "value": "safe"}
            ],
            "requirements": {
                "required_evidence": [],
                "required_reviewers": [],
                "minimum_approval_count": 0,
            },
            "constraints": [],
            "outcome": {"decision": "escalate", "reason": "Regex matched."},
            "obligations": [],
            "test_vectors": [],
            "source_refs": [],
            "metadata": {},
        },
        manifest={"schema_version": "0.1"},
    )

    allowed_decision = evaluate_runtime_policies(
        regex_bundle,
        {
            "domain": "governance",
            "route": "/api/decide",
            "actor": "planner",
            "request": {"text": "safe input"},
        },
    ).to_dict()
    oversized_input_decision = evaluate_runtime_policies(
        regex_bundle,
        {
            "domain": "governance",
            "route": "/api/decide",
            "actor": "planner",
            "request": {"text": "a" * 1025},
        },
    ).to_dict()

    assert allowed_decision["final_outcome"] == "escalate"
    assert oversized_input_decision["final_outcome"] == "allow"


def test_regex_condition_rejects_nested_quantifier_pattern() -> None:
    regex_bundle = adapt_compiled_payload(
        canonical_ir={
            "schema_version": "1.0",
            "policy_id": "policy.runtime.regex_nested_quantifier_guardrails",
            "version": "1",
            "title": "Regex nested quantifier guardrail",
            "description": "Reject potentially expensive regex patterns.",
            "effective_date": None,
            "scope": {
                "domains": ["governance"],
                "routes": ["/api/decide"],
                "actors": ["planner"],
            },
            "conditions": [
                {"field": "request.text", "operator": "regex", "value": "(a+)+$"}
            ],
            "requirements": {
                "required_evidence": [],
                "required_reviewers": [],
                "minimum_approval_count": 0,
            },
            "constraints": [],
            "outcome": {"decision": "escalate", "reason": "Regex matched."},
            "obligations": [],
            "test_vectors": [],
            "source_refs": [],
            "metadata": {},
        },
        manifest={"schema_version": "0.1"},
    )

    guarded_decision = evaluate_runtime_policies(
        regex_bundle,
        {
            "domain": "governance",
            "route": "/api/decide",
            "actor": "planner",
            "request": {"text": "a" * 200},
        },
    ).to_dict()

    assert guarded_decision["final_outcome"] == "allow"


def test_multiple_policy_precedence_resolution() -> None:
    """When multiple policies trigger, the highest-precedence outcome wins."""

    from veritas_os.policy.runtime_adapter import RuntimePolicy, RuntimePolicyBundle

    policies = [
        RuntimePolicy(
            policy_id="policy.a.allow",
            version="1",
            title="Allow",
            description="Allow",
            effective_date=None,
            scope={"domains": ["governance"], "routes": ["/api/decide"], "actors": ["planner"]},
            conditions=[{"field": "risk.level", "operator": "in", "value": ["high", "critical"]}],
            requirements={"required_evidence": [], "required_reviewers": [], "minimum_approval_count": 0},
            constraints=[],
            outcome={"decision": "allow", "reason": "Allowed."},
            obligations=[],
            test_vectors=[],
            metadata={},
            source_refs=[],
        ),
        RuntimePolicy(
            policy_id="policy.b.escalate",
            version="1",
            title="Escalate",
            description="Escalate",
            effective_date=None,
            scope={"domains": ["governance"], "routes": ["/api/decide"], "actors": ["planner"]},
            conditions=[{"field": "risk.level", "operator": "in", "value": ["high", "critical"]}],
            requirements={"required_evidence": [], "required_reviewers": [], "minimum_approval_count": 0},
            constraints=[],
            outcome={"decision": "escalate", "reason": "Anomaly."},
            obligations=["notify_governance_channel"],
            test_vectors=[],
            metadata={},
            source_refs=[],
        ),
        RuntimePolicy(
            policy_id="policy.c.deny",
            version="1",
            title="Deny",
            description="Deny",
            effective_date=None,
            scope={"domains": ["governance"], "routes": ["/api/decide"], "actors": ["planner"]},
            conditions=[{"field": "risk.level", "operator": "in", "value": ["high", "critical"]}],
            requirements={"required_evidence": [], "required_reviewers": [], "minimum_approval_count": 0},
            constraints=[],
            outcome={"decision": "deny", "reason": "Denied."},
            obligations=["emit_security_alert"],
            test_vectors=[],
            metadata={},
            source_refs=[],
        ),
    ]
    bundle = RuntimePolicyBundle(
        schema_version="0.1",
        policy_id="policy.multi.test",
        version="1",
        semantic_hash="sha256:test",
        compiler_version="0.1.0",
        compiled_at="2026-04-02T00:00:00Z",
        manifest={"schema_version": "0.1"},
        runtime_policies=policies,
    )

    context = {
        "domain": "governance",
        "route": "/api/decide",
        "actor": "planner",
        "risk": {"level": "critical"},
    }
    decision = evaluate_runtime_policies(bundle, context).to_dict()

    assert decision["final_outcome"] == "deny"
    assert len(decision["triggered_policies"]) == 3
    assert "notify_governance_channel" in decision["obligations"]
    assert "emit_security_alert" in decision["obligations"]


def test_future_effective_date_policy_is_skipped() -> None:
    """Policies whose effective_date is in the future must not trigger."""
    from veritas_os.policy.runtime_adapter import RuntimePolicy, RuntimePolicyBundle

    future_policy = RuntimePolicy(
        policy_id="policy.future.deny",
        version="1",
        title="Future deny",
        description="Should not fire yet.",
        effective_date="2099-01-01",
        scope={"domains": ["governance"], "routes": ["/api/decide"], "actors": ["planner"]},
        conditions=[{"field": "risk.level", "operator": "eq", "value": "high"}],
        requirements={"required_evidence": [], "required_reviewers": [], "minimum_approval_count": 0},
        constraints=[],
        outcome={"decision": "deny", "reason": "Future policy."},
        obligations=[],
        test_vectors=[],
        metadata={},
        source_refs=[],
    )
    bundle = RuntimePolicyBundle(
        schema_version="0.1",
        policy_id="policy.future.deny",
        version="1",
        semantic_hash="sha256:test",
        compiler_version="0.1.0",
        compiled_at="2026-04-02T00:00:00Z",
        manifest={"schema_version": "0.1"},
        runtime_policies=[future_policy],
    )
    context = {
        "domain": "governance",
        "route": "/api/decide",
        "actor": "planner",
        "risk": {"level": "high"},
    }
    decision = evaluate_runtime_policies(bundle, context).to_dict()

    assert decision["final_outcome"] == "allow"
    assert decision["triggered_policies"] == []


def test_past_effective_date_policy_triggers_normally() -> None:
    """Policies whose effective_date is today or past must trigger normally."""
    from veritas_os.policy.runtime_adapter import RuntimePolicy, RuntimePolicyBundle

    past_policy = RuntimePolicy(
        policy_id="policy.past.deny",
        version="1",
        title="Active deny",
        description="Already effective.",
        effective_date="2020-01-01",
        scope={"domains": ["governance"], "routes": ["/api/decide"], "actors": ["planner"]},
        conditions=[{"field": "risk.level", "operator": "eq", "value": "high"}],
        requirements={"required_evidence": [], "required_reviewers": [], "minimum_approval_count": 0},
        constraints=[],
        outcome={"decision": "deny", "reason": "Past policy."},
        obligations=[],
        test_vectors=[],
        metadata={},
        source_refs=[],
    )
    bundle = RuntimePolicyBundle(
        schema_version="0.1",
        policy_id="policy.past.deny",
        version="1",
        semantic_hash="sha256:test",
        compiler_version="0.1.0",
        compiled_at="2026-04-02T00:00:00Z",
        manifest={"schema_version": "0.1"},
        runtime_policies=[past_policy],
    )
    context = {
        "domain": "governance",
        "route": "/api/decide",
        "actor": "planner",
        "risk": {"level": "high"},
    }
    decision = evaluate_runtime_policies(bundle, context).to_dict()

    assert decision["final_outcome"] == "deny"
    assert "policy.past.deny" in decision["triggered_policies"]


# --- Error handling tests ---


def test_load_runtime_bundle_invalid_json(tmp_path: Path) -> None:
    """load_runtime_bundle raises ValueError for malformed JSON."""
    bundle_dir = tmp_path / "bad_bundle"
    bundle_dir.mkdir()
    # Create invalid JSON but valid signature so sig check passes
    manifest_content = "{not valid json"
    (bundle_dir / "manifest.json").write_text(manifest_content, encoding="utf-8")
    sig = hashlib.sha256(manifest_content.encode("utf-8")).hexdigest()
    (bundle_dir / "manifest.sig").write_text(sig, encoding="utf-8")

    with pytest.raises(ValueError, match="invalid JSON"):
        load_runtime_bundle(bundle_dir)


def test_load_runtime_bundle_missing_manifest(tmp_path: Path) -> None:
    """load_runtime_bundle raises ValueError when manifest.sig is missing."""
    bundle_dir = tmp_path / "no_sig"
    bundle_dir.mkdir()
    (bundle_dir / "manifest.json").write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="signature verification failed"):
        load_runtime_bundle(bundle_dir)


def test_adapt_canonical_ir_missing_key() -> None:
    """adapt_canonical_ir raises ValueError for incomplete IR."""
    incomplete_ir = {"policy_id": "test", "version": "1.0"}
    with pytest.raises(ValueError, match="missing required key"):
        adapt_canonical_ir(incomplete_ir)


# --- Numeric comparison type safety tests ---


def _make_numeric_test_bundle(
    operator: str, value: object
) -> RuntimePolicyBundle:
    """Build a minimal bundle with a single numeric condition."""
    from veritas_os.policy.runtime_adapter import RuntimePolicy

    policy = RuntimePolicy(
        policy_id="policy.numeric.test",
        version="1",
        title="Numeric test",
        description="Tests numeric comparison type coercion.",
        effective_date=None,
        scope={
            "domains": ["governance"],
            "routes": ["/api/decide"],
            "actors": ["planner"],
        },
        conditions=[{"field": "score", "operator": operator, "value": value}],
        constraints=[],
        requirements={
            "required_evidence": [],
            "required_reviewers": [],
            "minimum_approval_count": 0,
        },
        outcome={"decision": "deny", "reason": "numeric test fired"},
        obligations=[],
        test_vectors=[],
        metadata={},
        source_refs=[],
    )
    return RuntimePolicyBundle(
        schema_version="0.1",
        policy_id=policy.policy_id,
        version=policy.version,
        semantic_hash="sha256:test",
        compiler_version="0.1.0",
        compiled_at="2026-04-03T00:00:00Z",
        manifest={"schema_version": "0.1"},
        runtime_policies=[policy],
    )


BASE_NUMERIC_CONTEXT = {
    "domain": "governance",
    "route": "/api/decide",
    "actor": "planner",
}


@pytest.mark.parametrize(
    "operator, policy_value, ctx_value, expected_triggered",
    [
        # int vs int
        ("gt", 5, 10, True),
        ("gt", 5, 3, False),
        # float vs int
        ("gte", 7.0, 7, True),
        ("lt", 5, 3.0, True),
        # string number coerced to float
        ("gt", 5, "10", True),
        ("lte", 10, "10", True),
        ("gt", 5, "3", False),
        # non-numeric string safely returns False
        ("gt", 5, "abc", False),
        ("lt", 5, "xyz", False),
        # None actual safely returns False
        ("gt", 5, None, False),
    ],
)
def test_numeric_comparison_type_coercion(
    operator: str,
    policy_value: object,
    ctx_value: object,
    expected_triggered: bool,
) -> None:
    """Numeric operators (gt/gte/lt/lte) coerce values to float and handle type errors."""
    bundle = _make_numeric_test_bundle(operator, policy_value)
    context = {**BASE_NUMERIC_CONTEXT, "score": ctx_value}
    decision = evaluate_runtime_policies(bundle, context).to_dict()

    if expected_triggered:
        assert decision["final_outcome"] == "deny"
        assert "policy.numeric.test" in decision["triggered_policies"]
    else:
        assert decision["final_outcome"] == "allow"


# --- Unknown operator warning test ---


def test_unknown_operator_logs_warning_and_returns_false(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Unknown operators are logged as warnings and silently fail (no match)."""
    from veritas_os.policy.runtime_adapter import RuntimePolicy, RuntimePolicyBundle

    policy = RuntimePolicy(
        policy_id="policy.unknown_op.test",
        version="1",
        title="Unknown operator test",
        description="Should warn and not trigger.",
        effective_date=None,
        scope={
            "domains": ["governance"],
            "routes": ["/api/decide"],
            "actors": ["planner"],
        },
        conditions=[
            {"field": "risk.level", "operator": "unknown_op", "value": "high"}
        ],
        constraints=[],
        requirements={
            "required_evidence": [],
            "required_reviewers": [],
            "minimum_approval_count": 0,
        },
        outcome={"decision": "deny", "reason": "Should not fire."},
        obligations=[],
        test_vectors=[],
        metadata={},
        source_refs=[],
    )
    bundle = RuntimePolicyBundle(
        schema_version="0.1",
        policy_id=policy.policy_id,
        version=policy.version,
        semantic_hash="sha256:test",
        compiler_version="0.1.0",
        compiled_at="2026-04-03T00:00:00Z",
        manifest={"schema_version": "0.1"},
        runtime_policies=[policy],
    )

    context = {
        "domain": "governance",
        "route": "/api/decide",
        "actor": "planner",
        "risk": {"level": "high"},
    }
    import logging

    with caplog.at_level(logging.WARNING, logger="veritas_os.policy.evaluator"):
        decision = evaluate_runtime_policies(bundle, context).to_dict()

    assert decision["final_outcome"] == "allow"
    assert "unknown operator" in caplog.text
    assert "unknown_op" in caplog.text


# --- Scope missing fields debug log test ---


def test_scope_missing_fields_logs_debug(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Missing scope context fields are logged at DEBUG level."""
    from veritas_os.policy.runtime_adapter import RuntimePolicy, RuntimePolicyBundle

    policy = RuntimePolicy(
        policy_id="policy.scope_debug.test",
        version="1",
        title="Scope debug",
        description="Test scope debug logging.",
        effective_date=None,
        scope={
            "domains": ["governance"],
            "routes": ["/api/decide"],
            "actors": ["planner"],
        },
        conditions=[
            {"field": "risk.level", "operator": "eq", "value": "high"}
        ],
        constraints=[],
        requirements={
            "required_evidence": [],
            "required_reviewers": [],
            "minimum_approval_count": 0,
        },
        outcome={"decision": "deny", "reason": "Test."},
        obligations=[],
        test_vectors=[],
        metadata={},
        source_refs=[],
    )
    bundle = RuntimePolicyBundle(
        schema_version="0.1",
        policy_id=policy.policy_id,
        version=policy.version,
        semantic_hash="sha256:test",
        compiler_version="0.1.0",
        compiled_at="2026-04-03T00:00:00Z",
        manifest={"schema_version": "0.1"},
        runtime_policies=[policy],
    )

    # Context missing domain and actor — should still match but log debug
    context = {
        "route": "/api/decide",
        "risk": {"level": "high"},
    }
    import logging

    with caplog.at_level(logging.DEBUG, logger="veritas_os.policy.evaluator"):
        decision = evaluate_runtime_policies(bundle, context).to_dict()

    assert decision["final_outcome"] == "deny"
    assert "scope fields" in caplog.text
    assert "domain" in caplog.text
    assert "actor" in caplog.text


def test_load_runtime_bundle_logs_success(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Successful bundle load emits INFO log with policy_id and version."""
    import logging

    result = _compile_bundle(tmp_path, "low_risk_route_allow.yaml")

    with caplog.at_level(logging.INFO, logger="veritas_os.policy.runtime_adapter"):
        load_runtime_bundle(result.bundle_dir)

    assert "bundle loaded" in caplog.text
    assert "policy.low_risk_route.allow" in caplog.text


def test_evaluate_runtime_policies_none_context_returns_allow() -> None:
    """Passing ``None`` as context must not crash (defensive guard)."""
    bundle = adapt_compiled_payload(
        canonical_ir={
            "schema_version": "1.0",
            "policy_id": "policy.ctx.none",
            "version": "1",
            "title": "Ctx none guard",
            "description": "Ensure None context is safe.",
            "effective_date": None,
            "scope": {
                "domains": ["governance"],
                "routes": ["/api/decide"],
                "actors": ["planner"],
            },
            "conditions": [{"field": "risk.level", "operator": "eq", "value": "high"}],
            "requirements": {
                "required_evidence": [],
                "required_reviewers": [],
                "minimum_approval_count": 0,
            },
            "constraints": [],
            "outcome": {"decision": "deny", "reason": "High risk."},
            "obligations": [],
            "test_vectors": [],
            "source_refs": [],
            "metadata": {},
        },
        manifest={"schema_version": "0.1"},
    )
    # None context should be coerced to {} and not raise AttributeError
    result = evaluate_runtime_policies(bundle, None)  # type: ignore[arg-type]
    assert result.final_outcome == "allow"


def test_verify_manifest_signature_logs_warning_on_corrupt_manifest(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Corrupted manifest.json during algorithm detection emits WARNING log."""
    import logging
    from veritas_os.policy.runtime_adapter import verify_manifest_signature

    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text("NOT VALID JSON", encoding="utf-8")
    sig_path = tmp_path / "manifest.sig"
    sig_path.write_text("dummy", encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="veritas_os.policy.runtime_adapter"):
        verify_manifest_signature(tmp_path)

    assert "failed to parse manifest.json" in caplog.text


def test_verify_manifest_signature_returns_false_on_unreadable_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """verify_manifest_signature returns False (not crash) when file read fails."""
    import logging
    from veritas_os.policy.runtime_adapter import verify_manifest_signature

    manifest_path = tmp_path / "manifest.json"
    sig_path = tmp_path / "manifest.sig"
    manifest_path.write_text('{"signing":{"algorithm":"sha256"}}', encoding="utf-8")
    sig_path.write_text("dummy", encoding="utf-8")

    # Simulate file-system error after the existence check by patching read_bytes
    _orig_read_bytes = Path.read_bytes

    def _failing_read_bytes(self: Path) -> bytes:
        if self == manifest_path:
            raise OSError("simulated I/O failure")
        return _orig_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", _failing_read_bytes)

    with caplog.at_level(logging.WARNING, logger="veritas_os.policy.runtime_adapter"):
        result = verify_manifest_signature(tmp_path)

    assert result is False
    assert "failed to read manifest" in caplog.text


# --- NaN/Inf numeric comparison guard tests ---


@pytest.mark.parametrize(
    "operator, policy_value, ctx_value",
    [
        ("gt", 5, float("nan")),
        ("lt", 5, float("nan")),
        ("gte", 5, float("inf")),
        ("lte", 5, float("-inf")),
        ("gt", 5, "nan"),
        ("lt", 5, "inf"),
        # NaN/Inf in policy threshold value
        ("gt", float("nan"), 10),
        ("lt", float("inf"), 10),
    ],
)
def test_numeric_comparison_nan_inf_returns_false(
    operator: str,
    policy_value: object,
    ctx_value: object,
) -> None:
    """NaN and Inf values in numeric comparisons safely return False (no match)."""
    bundle = _make_numeric_test_bundle(operator, policy_value)
    context = {**BASE_NUMERIC_CONTEXT, "score": ctx_value}
    decision = evaluate_runtime_policies(bundle, context).to_dict()

    assert decision["final_outcome"] == "allow"


# --- contains operator type safety test ---


def test_contains_operator_non_string_expected_with_string_actual() -> None:
    """contains operator with a non-string expected value on a string actual safely returns False."""
    from veritas_os.policy.runtime_adapter import RuntimePolicy, RuntimePolicyBundle

    policy = RuntimePolicy(
        policy_id="policy.contains.type_safety",
        version="1",
        title="Contains type safety",
        description="Non-string expected in string actual should not raise TypeError.",
        effective_date=None,
        scope={
            "domains": ["governance"],
            "routes": ["/api/decide"],
            "actors": ["planner"],
        },
        conditions=[
            {"field": "label", "operator": "contains", "value": 42}
        ],
        constraints=[],
        requirements={
            "required_evidence": [],
            "required_reviewers": [],
            "minimum_approval_count": 0,
        },
        outcome={"decision": "deny", "reason": "Type mismatch test."},
        obligations=[],
        test_vectors=[],
        metadata={},
        source_refs=[],
    )
    bundle = RuntimePolicyBundle(
        schema_version="0.1",
        policy_id=policy.policy_id,
        version=policy.version,
        semantic_hash="sha256:test",
        compiler_version="0.1.0",
        compiled_at="2026-04-03T00:00:00Z",
        manifest={"schema_version": "0.1"},
        runtime_policies=[policy],
    )

    context = {
        "domain": "governance",
        "route": "/api/decide",
        "actor": "planner",
        "label": "hello world",
    }
    decision = evaluate_runtime_policies(bundle, context).to_dict()

    # Non-string expected on string actual → no match (previously raised TypeError)
    assert decision["final_outcome"] == "allow"


def test_outcome_missing_keys_does_not_raise_key_error() -> None:
    """Evaluator handles malformed outcome dict (missing 'decision'/'reason') gracefully."""
    from veritas_os.policy.runtime_adapter import RuntimePolicy, RuntimePolicyBundle

    policy = RuntimePolicy(
        policy_id="policy.malformed.outcome",
        version="1",
        title="Malformed outcome",
        description="Outcome dict intentionally missing keys.",
        effective_date=None,
        scope={
            "domains": ["governance"],
            "routes": ["/api/decide"],
            "actors": ["planner"],
        },
        conditions=[
            {"field": "risk.level", "operator": "eq", "value": "high"}
        ],
        constraints=[],
        requirements={
            "required_evidence": [],
            "required_reviewers": [],
            "minimum_approval_count": 0,
        },
        outcome={},  # intentionally empty — missing 'decision' and 'reason'
        obligations=[],
        test_vectors=[],
        metadata={},
        source_refs=[],
    )
    bundle = RuntimePolicyBundle(
        schema_version="0.1",
        policy_id=policy.policy_id,
        version=policy.version,
        semantic_hash="sha256:test",
        compiler_version="0.1.0",
        compiled_at="2026-04-05T00:00:00Z",
        manifest={"schema_version": "0.1"},
        runtime_policies=[policy],
    )

    context = {
        "domain": "governance",
        "route": "/api/decide",
        "actor": "planner",
        "risk": {"level": "high"},
    }
    # Should not raise KeyError; defaults to "allow" outcome
    decision = evaluate_runtime_policies(bundle, context).to_dict()
    assert decision["final_outcome"] == "allow"
    assert "policy.malformed.outcome" in decision["triggered_policies"]


def test_verify_manifest_signature_logs_warning_on_missing_files(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """verify_manifest_signature logs a warning when manifest/sig files are missing."""
    import logging
    from veritas_os.policy.runtime_adapter import verify_manifest_signature

    with caplog.at_level(logging.WARNING, logger="veritas_os.policy.runtime_adapter"):
        result = verify_manifest_signature(tmp_path)

    assert result is False
    assert "missing" in caplog.text
    assert "manifest.json" in caplog.text
