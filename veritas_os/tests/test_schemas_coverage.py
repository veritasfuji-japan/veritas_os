# veritas_os/tests/test_schemas_coverage.py
"""
Coverage-boost tests for veritas_os/api/schemas.py.
Focus on validators, coercion functions, and edge cases.
"""
from __future__ import annotations

from collections import OrderedDict
from typing import Any, Dict, List

import pytest
from pydantic import ValidationError

from veritas_os.api.governance import LogRetention, GovernancePolicy
from veritas_os.api.schemas import (
    _as_list,
    _coerce_context,
    Alt,
    AltItem,
    Context,
    DecideRequest,
    DecideResponse,
    EvidenceItem,
    FujiDecision,
    Gate,
    Option,
    StageMetrics,
    TrustLog,
    ValuesOut,
    _altin_to_altitem,
    _is_mapping,
)


# =========================================================
# 1. _as_list edge cases
# =========================================================


class TestAsListExtended:
    def test_none(self):
        assert _as_list(None) == []

    def test_list_passthrough(self):
        assert _as_list([1, 2]) == [1, 2]

    def test_dict_wraps(self):
        assert _as_list({"a": 1}) == [{"a": 1}]

    def test_ordered_dict(self):
        od = OrderedDict([("x", 1)])
        result = _as_list(od)
        assert len(result) == 1
        assert result[0] == {"x": 1}

    def test_string_wraps(self):
        assert _as_list("hello") == ["hello"]

    def test_int_wraps(self):
        assert _as_list(42) == [42]

    def test_float_wraps(self):
        assert _as_list(3.14) == [3.14]

    def test_bool_wraps(self):
        assert _as_list(True) == [True]

    def test_tuple_converts(self):
        assert _as_list((1, 2, 3)) == [1, 2, 3]

    def test_set_converts(self):
        result = _as_list({1, 2})
        assert sorted(result) == [1, 2]

    def test_generator_converts(self):
        gen = (x * 2 for x in [1, 2, 3])
        assert _as_list(gen) == [2, 4, 6]

    def test_non_iterable_wraps(self):
        class Opaque:
            pass
        obj = Opaque()
        result = _as_list(obj)
        assert result == [obj]


# =========================================================
# 2. _coerce_context
# =========================================================


class TestCoerceContext:
    def test_none_returns_empty(self):
        assert _coerce_context(None) == {}

    def test_dict_passthrough(self):
        d = {"user_id": "u1", "query": "q"}
        assert _coerce_context(d) == d

    def test_context_object(self):
        ctx = Context(user_id="u1", query="q")
        result = _coerce_context(ctx)
        assert isinstance(result, dict)
        assert result["user_id"] == "u1"

    def test_mapping_like(self):
        od = OrderedDict([("a", 1)])
        result = _coerce_context(od)
        assert result == {"a": 1}

    def test_scalar_wraps_as_raw(self):
        result = _coerce_context(42)
        assert result == {"raw": 42}

    def test_string_wraps_as_raw(self):
        result = _coerce_context("some string")
        assert result == {"raw": "some string"}


# =========================================================
# 3. EvidenceItem validator
# =========================================================


class TestEvidenceItemValidator:
    def test_default_source(self):
        ev = EvidenceItem()
        assert ev.source == "unknown"

    def test_empty_source_coerced(self):
        ev = EvidenceItem(source="")
        assert ev.source == "unknown"

    def test_uri_from_url_extra(self):
        ev = EvidenceItem.model_validate({"url": "http://example.com", "snippet": "s"})
        assert ev.uri == "http://example.com"

    def test_uri_from_link_extra(self):
        ev = EvidenceItem.model_validate({"link": "http://link.com", "snippet": "s"})
        assert ev.uri == "http://link.com"

    def test_snippet_fallback_to_title(self):
        ev = EvidenceItem(title="My Title", snippet="")
        assert ev.snippet == "My Title"

    def test_snippet_fallback_to_uri(self):
        ev = EvidenceItem(uri="http://example.com", snippet="", title=None)
        assert ev.snippet == "http://example.com"

    def test_confidence_clamped(self):
        ev = EvidenceItem(confidence=2.0)
        assert ev.confidence == 1.0

    def test_confidence_negative_clamped(self):
        ev = EvidenceItem(confidence=-0.5)
        assert ev.confidence == 0.0

    def test_confidence_default_value(self):
        ev = EvidenceItem()
        assert ev.confidence == 0.7


# =========================================================
# 4. DecideRequest validators
# =========================================================


class TestDecideRequestValidators:
    def test_context_from_none(self):
        req = DecideRequest(query="test", context=None)
        assert req.context == {}

    def test_context_from_dict(self):
        req = DecideRequest(query="q", context={"user_id": "u1", "query": "q"})
        assert req.context["user_id"] == "u1"

    def test_alternatives_from_none(self):
        req = DecideRequest(query="q")
        assert req.alternatives is not None

    def test_alternatives_from_dict(self):
        req = DecideRequest(query="q", alternatives={"title": "opt1"})
        assert len(req.alternatives) == 1
        assert req.alternatives[0].title == "opt1"

    def test_options_mirror_to_alternatives(self):
        req = DecideRequest(query="q", options=[{"title": "A"}])
        assert len(req.alternatives) >= 1

    def test_alternatives_priority_over_options(self):
        req = DecideRequest(
            query="q",
            alternatives=[{"title": "A"}],
            options=[{"title": "B"}],
        )
        assert req.alternatives[0].title == "A"

    def test_scalar_alternative(self):
        req = DecideRequest(query="q", alternatives=["option_text"])
        assert req.alternatives[0].title == "option_text"


# =========================================================
# 5. DecideResponse validators
# =========================================================


class TestDecideResponseValidators:
    def test_request_id_generated_when_none(self):
        resp = DecideResponse(request_id=None)
        assert len(resp.request_id) > 0

    def test_evidence_from_string(self):
        resp = DecideResponse(evidence="some text evidence")
        assert len(resp.evidence) == 1
        assert resp.evidence[0].source == "text"
        assert resp.evidence[0].snippet == "some text evidence"

    def test_evidence_from_dict(self):
        resp = DecideResponse(evidence={"source": "web", "snippet": "info"})
        assert len(resp.evidence) == 1
        assert resp.evidence[0].source == "web"

    def test_evidence_from_list_of_strings(self):
        resp = DecideResponse(evidence=["ev1", "ev2"])
        assert len(resp.evidence) == 2
        assert all(e.source == "text" for e in resp.evidence)

    def test_evidence_dict_url_to_uri(self):
        resp = DecideResponse(evidence=[{"url": "http://a.com", "snippet": "s"}])
        assert resp.evidence[0].uri == "http://a.com"

    def test_evidence_dict_snippet_from_text(self):
        resp = DecideResponse(evidence=[{"text": "my text"}])
        assert resp.evidence[0].snippet == "my text"

    def test_alternatives_mirror_to_options(self):
        resp = DecideResponse(alternatives=[{"title": "A"}])
        assert len(resp.options) > 0

    def test_options_mirror_to_alternatives(self):
        resp = DecideResponse(options=[{"title": "B"}])
        assert len(resp.alternatives) > 0

    def test_critique_from_string(self):
        resp = DecideResponse(critique="issue found")
        assert resp.critique == ["issue found"]

    def test_debate_from_dict(self):
        resp = DecideResponse(debate={"stance": "for", "argument": "good"})
        assert len(resp.debate) == 1

    def test_trust_log_from_dict(self):
        tl_data = {
            "request_id": "r1",
            "created_at": "2024-01-01T00:00:00Z",
            "sources": [],
            "critics": [],
            "checks": [],
        }
        resp = DecideResponse(trust_log=tl_data)
        assert isinstance(resp.trust_log, TrustLog)

    def test_trust_log_with_pipeline_fields(self):
        """TrustLog accepts pipeline-provided fields (gate_status, gate_risk, query)."""
        tl = TrustLog(
            request_id="r2",
            created_at="2024-01-01T00:00:00Z",
            query="test query",
            gate_status="allow",
            gate_risk=0.15,
        )
        assert tl.query == "test query"
        assert tl.gate_status == "allow"
        assert tl.gate_risk == 0.15

    def test_trust_log_from_invalid_type(self):
        resp = DecideResponse(trust_log=12345)
        assert resp.trust_log is not None

    def test_evidence_unknown_type(self):
        resp = DecideResponse(evidence=[42])
        assert len(resp.evidence) == 1
        assert resp.evidence[0].source == "unknown"

    def test_alt_from_dict_list(self):
        resp = DecideResponse(alternatives=[{"title": "opt1"}, {"title": "opt2"}])
        assert len(resp.alternatives) == 2
        assert resp.alternatives[0].title == "opt1"


# =========================================================
# 6. Alt model
# =========================================================


class TestAltModel:
    def test_auto_id(self):
        alt = Alt()
        assert len(alt.id) > 0

    def test_auto_title(self):
        alt = Alt(id="", title="")
        assert alt.title.startswith("option-")

    def test_explicit_values(self):
        alt = Alt(id="a1", title="My Option", score=0.9)
        assert alt.id == "a1"
        assert alt.title == "My Option"


# =========================================================
# 7. Option model
# =========================================================


class TestOptionModel:
    def test_text_to_title(self):
        opt = Option(text="from text")
        assert opt.title == "from text"

    def test_title_preserved(self):
        opt = Option(title="explicit", text="fallback")
        assert opt.title == "explicit"


# =========================================================
# 8. _altin_to_altitem
# =========================================================


class TestAltinToAltitem:
    def test_none(self):
        result = _altin_to_altitem(None)
        assert isinstance(result, AltItem)

    def test_altitem_passthrough(self):
        ai = AltItem(title="test")
        assert _altin_to_altitem(ai) is ai

    def test_option_converts(self):
        opt = Option(title="opt")
        result = _altin_to_altitem(opt)
        assert isinstance(result, AltItem)
        assert result.title == "opt"

    def test_dict_converts(self):
        result = _altin_to_altitem({"title": "dict opt"})
        assert result.title == "dict opt"

    def test_scalar_converts(self):
        result = _altin_to_altitem(42)
        assert result.title == "42"


# =========================================================
# 9. _is_mapping
# =========================================================


class TestIsMapping:
    def test_dict(self):
        assert _is_mapping({}) is True

    def test_ordered_dict(self):
        assert _is_mapping(OrderedDict()) is True

    def test_list(self):
        assert _is_mapping([]) is False

    def test_string(self):
        assert _is_mapping("hello") is False


# =========================================================
# 10. StageMetrics
# =========================================================


class TestStageMetrics:
    def test_defaults(self):
        m = StageMetrics()
        assert m.health == "unknown"
        assert m.latency_ms is None
        assert m.summary is None
        assert m.detail is None
        assert m.reason is None

    def test_all_fields(self):
        m = StageMetrics(
            latency_ms=42.5,
            health="ok",
            summary="Gate passed",
            detail="No violations found.",
            reason="telos score within threshold",
        )
        assert m.health == "ok"
        assert m.latency_ms == 42.5

    def test_health_warning(self):
        m = StageMetrics(health="warning")
        assert m.health == "warning"

    def test_health_failed(self):
        m = StageMetrics(health="failed", summary="Blocked by FUJI gate")
        assert m.health == "failed"
        assert m.summary == "Blocked by FUJI gate"

    def test_health_invalid(self):
        with pytest.raises(ValidationError):
            StageMetrics(health="invalid_value")

    def test_extra_fields_allowed(self):
        m = StageMetrics(health="ok", custom_counter=99)
        assert m.model_extra.get("custom_counter") == 99

    def test_roundtrip(self):
        data = {"health": "ok", "latency_ms": 10.0, "summary": "done"}
        m = StageMetrics.model_validate(data)
        dumped = m.model_dump(exclude_none=True)
        assert dumped["health"] == "ok"
        assert dumped["latency_ms"] == 10.0


# =========================================================
# 11. FujiDecision and Gate diagnostic fields
# =========================================================


class TestFujiDecisionDiagnosticFields:
    def test_defaults_absent(self):
        fd = FujiDecision(status="allow")
        assert fd.rule_hit is None
        assert fd.severity is None
        assert fd.remediation_hint is None
        assert fd.risky_text_fragment is None

    def test_all_diagnostic_fields(self):
        fd = FujiDecision(
            status="block",
            reasons=["profanity detected"],
            violations=["content_policy"],
            rule_hit="profanity_v2",
            severity="high",
            remediation_hint="Remove offensive language before resubmitting.",
            risky_text_fragment="offensive snippet",
        )
        assert fd.rule_hit == "profanity_v2"
        assert fd.severity == "high"
        assert fd.remediation_hint == "Remove offensive language before resubmitting."
        assert fd.risky_text_fragment == "offensive snippet"

    def test_roundtrip(self):
        fd = FujiDecision(status="modify", rule_hit="bias_v1", severity="medium")
        d = fd.model_dump()
        fd2 = FujiDecision.model_validate(d)
        assert fd2.rule_hit == "bias_v1"
        assert fd2.severity == "medium"


class TestGateDiagnosticFields:
    def test_defaults_absent(self):
        g = Gate(risk=0.1, decision_status="allow")
        assert g.rule_hit is None
        assert g.severity is None
        assert g.remediation_hint is None
        assert g.risky_text_fragment is None

    def test_all_diagnostic_fields(self):
        g = Gate(
            risk=0.9,
            telos_score=0.3,
            decision_status="block",
            rule_hit="keyword_block",
            severity="critical",
            remediation_hint="Contact admin.",
            risky_text_fragment="dangerous term",
        )
        assert g.rule_hit == "keyword_block"
        assert g.severity == "critical"

    def test_roundtrip(self):
        g = Gate(risk=0.5, decision_status="modify", rule_hit="pii_v1")
        d = g.model_dump()
        g2 = Gate.model_validate(d)
        assert g2.rule_hit == "pii_v1"


# =========================================================
# 12. LogRetention audit_level validation
# =========================================================


class TestLogRetentionAuditLevel:
    @pytest.mark.parametrize("level", ["none", "minimal", "summary", "standard", "full", "strict"])
    def test_valid_levels(self, level: str):
        lr = LogRetention(audit_level=level)
        assert lr.audit_level == level

    def test_default_is_full(self):
        lr = LogRetention()
        assert lr.audit_level == "full"

    def test_invalid_level_raises(self):
        with pytest.raises(ValidationError):
            LogRetention(audit_level="verbose")

    def test_invalid_level_debug_raises(self):
        with pytest.raises(ValidationError):
            LogRetention(audit_level="debug")

    def test_governance_policy_default(self):
        gp = GovernancePolicy()
        assert gp.log_retention.audit_level == "full"

    def test_governance_policy_summary_level(self):
        gp = GovernancePolicy(
            log_retention=LogRetention(audit_level="summary", retention_days=180)
        )
        assert gp.log_retention.audit_level == "summary"
        assert gp.log_retention.retention_days == 180
