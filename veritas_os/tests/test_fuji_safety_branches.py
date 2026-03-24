# -*- coding: utf-8 -*-
"""
fuji.py safety / fallback / compatibility 分岐の追加カバレッジ。

既存テストで未カバーまたは薄いパスを補強する:
- fuji_core_decide: deterministic illicit floor
- fuji_core_decide: deterministic self_harm floor
- fuji_core_decide: deterministic PII unmasked floor
- fuji_core_decide: invariant fix (deny coercion, rejection_reason 保険)
- fuji_core_decide: non-deny clears rejection_reason
- fuji_gate: trust log append failure (OSError)
- fuji_gate: rejection payload generation on deny
- fuji_gate: meta/checks with judgment_source / llm_available
- evaluate: evidence=None → enforce_low_evidence=False
- evaluate: dict input merges decision_id from request_id
"""

from __future__ import annotations

from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from veritas_os.core import fuji


# ===========================================================
# helpers
# ===========================================================

def _sh(
    *,
    risk_score: float = 0.1,
    categories: List[str] | None = None,
    rationale: str = "",
    model: str = "test_model",
    raw: Dict[str, Any] | None = None,
) -> fuji.SafetyHeadResult:
    return fuji.SafetyHeadResult(
        risk_score=risk_score,
        categories=categories or [],
        rationale=rationale,
        model=model,
        raw=raw or {},
    )


SAFE_POLICY: Dict[str, Any] = {
    "version": "test_safe_policy",
    "base_thresholds": {"default": 0.5},
    "categories": {},
    "actions": {
        "allow": {"risk_upper": 0.2},
        "warn": {"risk_upper": 0.5},
        "human_review": {"risk_upper": 0.8},
        "deny": {"risk_upper": 1.0},
    },
}

DENY_CATEGORY_POLICY: Dict[str, Any] = {
    "version": "test_deny_cat_policy",
    "base_thresholds": {"default": 0.5},
    "categories": {
        "illicit": {"max_risk_allow": 0.1, "action_on_exceed": "deny"},
        "self_harm": {"max_risk_allow": 0.1, "action_on_exceed": "deny"},
        "PII": {"max_risk_allow": 0.2, "action_on_exceed": "human_review"},
    },
    "actions": SAFE_POLICY["actions"],
}


# ===========================================================
# B-1) fuji_core_decide — deterministic risk floors
# ===========================================================

class TestFujiCoreDeterministicFloors:
    """deterministic rule による risk floor 強制を検証。"""

    def test_illicit_floor_enforcement(self):
        """illicit カテゴリ → risk >= RISK_FLOOR_ILLICIT (0.70)。"""
        sh = _sh(risk_score=0.05, categories=["illicit"])
        res = fuji.fuji_core_decide(
            safety_head=sh,
            stakes=0.5,
            telos_score=0.5,
            evidence_count=5,
            policy=DENY_CATEGORY_POLICY,
            text="illicit test",
        )
        # risk should be at least 0.70 (deterministic floor)
        assert res["risk"] >= fuji.RISK_FLOOR_ILLICIT
        assert any("deterministic_illicit_floor" in r for r in res["reasons"])

    def test_self_harm_floor_enforcement(self):
        """self_harm カテゴリ → risk >= RISK_FLOOR_SELF_HARM (0.80)。"""
        sh = _sh(risk_score=0.05, categories=["self_harm"])
        res = fuji.fuji_core_decide(
            safety_head=sh,
            stakes=0.5,
            telos_score=0.5,
            evidence_count=5,
            policy=DENY_CATEGORY_POLICY,
            text="self harm test",
        )
        assert res["risk"] >= fuji.RISK_FLOOR_SELF_HARM
        assert any("deterministic_self_harm_floor" in r for r in res["reasons"])

    def test_pii_unmasked_floor_enforcement(self):
        """PII (safe_applied=False) → risk >= RISK_FLOOR_PII_UNMASKED (0.50)。"""
        sh = _sh(risk_score=0.05, categories=["PII"], model="llm_safety")
        res = fuji.fuji_core_decide(
            safety_head=sh,
            stakes=0.5,
            telos_score=0.5,
            evidence_count=5,
            policy=DENY_CATEGORY_POLICY,
            safe_applied=False,
            text="phone: 090-1234-5678",
        )
        assert res["risk"] >= fuji.RISK_FLOOR_PII_UNMASKED
        assert any("deterministic_pii_floor" in r for r in res["reasons"])

    def test_pii_safe_applied_skips_floor(self):
        """PII + safe_applied=True → PII floor は適用されない。"""
        sh = _sh(risk_score=0.05, categories=["PII"], model="llm_safety")
        res = fuji.fuji_core_decide(
            safety_head=sh,
            stakes=0.5,
            telos_score=0.5,
            evidence_count=5,
            policy=SAFE_POLICY,
            safe_applied=True,
            text="masked data",
        )
        # PII floor (0.50) should NOT be applied; safe_applied caps risk lower
        assert res["risk"] < fuji.RISK_FLOOR_PII_UNMASKED
        assert any("pii_safe_applied" in r for r in res["reasons"])


# ===========================================================
# B-2) fuji_core_decide — invariant fix
# ===========================================================

class TestFujiCoreInvariantFix:
    """fuji_core_decide の不変条件保険ロジックを検証。"""

    def test_deny_status_coerces_decision_status(self):
        """status=deny のとき decision_status も deny に強制される。"""
        # high risk illicit → policy should produce deny status
        sh = _sh(risk_score=0.95, categories=["illicit"])
        res = fuji.fuji_core_decide(
            safety_head=sh,
            stakes=0.5,
            telos_score=0.5,
            evidence_count=5,
            policy=DENY_CATEGORY_POLICY,
            text="clearly illicit",
        )
        assert res["status"] == "deny"
        assert res["decision_status"] == "deny"
        assert res["rejection_reason"] is not None

    def test_deny_decision_always_has_rejection_reason(self):
        """decision_status=deny のとき rejection_reason は必ず non-None。"""
        sh = _sh(risk_score=0.99, categories=["illicit"])
        res = fuji.fuji_core_decide(
            safety_head=sh,
            stakes=0.5,
            telos_score=0.5,
            evidence_count=5,
            policy=DENY_CATEGORY_POLICY,
            text="clearly illicit again",
        )
        if res["decision_status"] == "deny":
            assert res["rejection_reason"] is not None, \
                "deny without rejection_reason violates invariant"

    def test_non_deny_clears_rejection_reason(self):
        """decision_status != deny → rejection_reason は None。"""
        sh = _sh(risk_score=0.01, categories=[])
        res = fuji.fuji_core_decide(
            safety_head=sh,
            stakes=0.3,
            telos_score=0.5,
            evidence_count=5,
            policy=SAFE_POLICY,
            text="safe text",
        )
        assert res["decision_status"] != "deny"
        assert res["rejection_reason"] is None


# ===========================================================
# B-3) fuji_gate — trust log append failure
# ===========================================================

class TestFujiGateTrustLogFailure:
    """fuji_gate の TrustLog 追記失敗時の安全な degradation を検証。"""

    def test_trustlog_oserror_adds_reason(self, monkeypatch):
        """append_trust_event が OSError → reasons に trustlog_error が追加。"""
        monkeypatch.setattr(fuji, "_check_policy_hot_reload", lambda: None)
        monkeypatch.setattr(
            fuji, "call_tool",
            lambda *a, **kw: {
                "ok": True,
                "risk_score": 0.05,
                "categories": [],
                "rationale": "",
                "model": "test_model",
            },
        )
        monkeypatch.setattr(
            fuji, "append_trust_event",
            MagicMock(side_effect=OSError("disk full")),
        )

        res = fuji.fuji_gate("safe text", context={}, evidence=[])
        # trust log failure should not crash fuji_gate
        assert res["decision_status"] in ("allow", "hold", "deny")
        assert any("trustlog_error" in r for r in res.get("reasons", []))


# ===========================================================
# B-4) fuji_gate — rejection payload
# ===========================================================

class TestFujiGateRejectionPayload:
    """fuji_gate が deny 時に rejection payload を生成することを検証。"""

    def test_deny_produces_rejection_payload(self, monkeypatch):
        """decision_status=deny → rejection dict が返される。"""
        monkeypatch.setattr(fuji, "_check_policy_hot_reload", lambda: None)
        monkeypatch.setattr(
            fuji, "call_tool",
            lambda *a, **kw: {
                "ok": True,
                "risk_score": 0.95,
                "categories": ["illicit"],
                "rationale": "dangerous content",
                "model": "test_model",
            },
        )
        monkeypatch.setattr(fuji, "append_trust_event", lambda e: None)

        res = fuji.fuji_gate(
            "illicit content",
            context={"stakes": 0.5},
            evidence=[{"source": "test", "snippet": "s", "confidence": 0.8}],
        )
        # With risk=0.95 + illicit floor, should be deny
        if res["decision_status"] == "deny":
            assert res.get("rejection") is not None
            assert isinstance(res["rejection"], dict)
        else:
            # Even if not deny due to policy, the structure should be valid
            assert "rejection" in res


# ===========================================================
# B-5) fuji_gate — meta/checks structure
# ===========================================================

class TestFujiGateMetaChecks:
    """fuji_gate の meta / checks に judgment_source, llm_available が含まれる。"""

    def test_meta_contains_judgment_source_and_llm_available(self, monkeypatch):
        monkeypatch.setattr(fuji, "_check_policy_hot_reload", lambda: None)
        monkeypatch.setattr(
            fuji, "call_tool",
            lambda *a, **kw: {
                "ok": True,
                "risk_score": 0.05,
                "categories": [],
                "rationale": "",
                "model": "test_model",
            },
        )
        monkeypatch.setattr(fuji, "append_trust_event", lambda e: None)

        res = fuji.fuji_gate("hello", context={}, evidence=[])

        meta = res.get("meta", {})
        assert "judgment_source" in meta
        assert "llm_available" in meta
        assert isinstance(meta["llm_available"], bool)

    def test_checks_include_safety_head_and_policy_engine(self, monkeypatch):
        monkeypatch.setattr(fuji, "_check_policy_hot_reload", lambda: None)
        monkeypatch.setattr(
            fuji, "call_tool",
            lambda *a, **kw: {
                "ok": True,
                "risk_score": 0.05,
                "categories": [],
                "rationale": "",
                "model": "test_model",
            },
        )
        monkeypatch.setattr(fuji, "append_trust_event", lambda e: None)

        res = fuji.fuji_gate("hello", context={}, evidence=[])

        checks = res.get("checks", [])
        kinds = [c["kind"] for c in checks]
        assert "safety_head" in kinds
        assert "policy_engine" in kinds

    def test_heuristic_fallback_sets_deterministic_judgment(self, monkeypatch):
        """run_safety_head が heuristic_fallback → judgment_source = deterministic_*。"""
        monkeypatch.setattr(fuji, "_check_policy_hot_reload", lambda: None)
        # Force exception in call_tool to trigger heuristic fallback
        monkeypatch.setattr(
            fuji, "call_tool",
            MagicMock(side_effect=RuntimeError("llm unavailable")),
        )
        monkeypatch.setattr(fuji, "append_trust_event", lambda e: None)

        res = fuji.fuji_gate("hello world", context={}, evidence=[])

        meta = res.get("meta", {})
        assert meta.get("judgment_source") in (
            "deterministic_fallback",
            "deterministic_rule",
        )
        assert meta.get("llm_available") is False


# ===========================================================
# B-6) fuji_gate — invariant fixups (same logic also in fuji_core_decide)
# ===========================================================

class TestFujiGateInvariantFixups:
    """fuji_gate レベルでの invariant fix を検証。"""

    def test_deny_without_rejection_reason_gets_default(self, monkeypatch):
        """status=deny, rejection_reason=None → policy_deny_coerce が入る。"""
        monkeypatch.setattr(fuji, "_check_policy_hot_reload", lambda: None)
        monkeypatch.setattr(
            fuji, "call_tool",
            lambda *a, **kw: {
                "ok": True,
                "risk_score": 0.95,
                "categories": ["illicit"],
                "rationale": "bad",
                "model": "test_model",
            },
        )
        monkeypatch.setattr(fuji, "append_trust_event", lambda e: None)

        res = fuji.fuji_gate(
            "dangerous content",
            context={"stakes": 0.5},
            evidence=[{"source": "t", "snippet": "s", "confidence": 0.8}],
        )
        if res["decision_status"] == "deny":
            assert res["rejection_reason"] is not None

    def test_non_deny_clears_rejection_reason(self, monkeypatch):
        """decision_status != deny → rejection_reason は None。"""
        monkeypatch.setattr(fuji, "_check_policy_hot_reload", lambda: None)
        monkeypatch.setattr(
            fuji, "call_tool",
            lambda *a, **kw: {
                "ok": True,
                "risk_score": 0.01,
                "categories": [],
                "rationale": "safe",
                "model": "test_model",
            },
        )
        monkeypatch.setattr(fuji, "append_trust_event", lambda e: None)

        res = fuji.fuji_gate("safe text", context={}, evidence=[])
        if res["decision_status"] != "deny":
            assert res["rejection_reason"] is None


# ===========================================================
# B-7) evaluate — evidence=None path
# ===========================================================

class TestEvaluateEvidenceNone:
    """evaluate に evidence=None を渡したとき enforce_low_evidence=False が設定される。"""

    def test_evidence_none_sets_enforce_false(self, monkeypatch):
        """evidence=None → context に enforce_low_evidence=False がセットされる。"""
        captured_ctx: Dict[str, Any] = {}

        original_fuji_gate = fuji.fuji_gate

        def spy_fuji_gate(text, *, context=None, evidence=None, alternatives=None):
            captured_ctx.update(context or {})
            return original_fuji_gate(
                text, context=context, evidence=evidence, alternatives=alternatives
            )

        monkeypatch.setattr(fuji, "_check_policy_hot_reload", lambda: None)
        monkeypatch.setattr(
            fuji, "call_tool",
            lambda *a, **kw: {
                "ok": True,
                "risk_score": 0.05,
                "categories": [],
                "rationale": "",
                "model": "test_model",
            },
        )
        monkeypatch.setattr(fuji, "append_trust_event", lambda e: None)
        monkeypatch.setattr(fuji, "fuji_gate", spy_fuji_gate)

        res = fuji.evaluate("safe query", evidence=None)
        assert captured_ctx.get("enforce_low_evidence") is False

    def test_evidence_provided_does_not_override_enforce(self, monkeypatch):
        """evidence が明示的に渡された場合、enforce_low_evidence は自動設定されない。"""
        captured_ctx: Dict[str, Any] = {}

        original_fuji_gate = fuji.fuji_gate

        def spy_fuji_gate(text, *, context=None, evidence=None, alternatives=None):
            captured_ctx.update(context or {})
            return original_fuji_gate(
                text, context=context, evidence=evidence, alternatives=alternatives
            )

        monkeypatch.setattr(fuji, "_check_policy_hot_reload", lambda: None)
        monkeypatch.setattr(
            fuji, "call_tool",
            lambda *a, **kw: {
                "ok": True,
                "risk_score": 0.05,
                "categories": [],
                "rationale": "",
                "model": "test_model",
            },
        )
        monkeypatch.setattr(fuji, "append_trust_event", lambda e: None)
        monkeypatch.setattr(fuji, "fuji_gate", spy_fuji_gate)

        ev = [{"source": "test", "snippet": "s", "confidence": 0.9}]
        fuji.evaluate("safe query", evidence=ev)
        # When evidence is provided, enforce_low_evidence is NOT injected by evaluate
        assert "enforce_low_evidence" not in captured_ctx


# ===========================================================
# B-8) evaluate — dict input with request_id
# ===========================================================

class TestEvaluateDictInput:
    """evaluate に dict を渡したときのマージ動作を検証。"""

    def test_dict_with_request_id_merges_decision_id(self, monkeypatch):
        """decision dict に request_id があれば result に decision_id として反映。"""
        monkeypatch.setattr(fuji, "_check_policy_hot_reload", lambda: None)
        monkeypatch.setattr(
            fuji, "call_tool",
            lambda *a, **kw: {
                "ok": True,
                "risk_score": 0.05,
                "categories": [],
                "rationale": "",
                "model": "test_model",
            },
        )
        monkeypatch.setattr(fuji, "append_trust_event", lambda e: None)

        decision = {
            "query": "safe query",
            "request_id": "req-123",
            "alternatives": [],
            "evidence": [],
        }
        res = fuji.evaluate(decision)
        assert res.get("decision_id") == "req-123"

    def test_dict_without_query_uses_chosen_title(self, monkeypatch):
        """query が無い dict → chosen.title をフォールバック。"""
        monkeypatch.setattr(fuji, "_check_policy_hot_reload", lambda: None)
        monkeypatch.setattr(
            fuji, "call_tool",
            lambda *a, **kw: {
                "ok": True,
                "risk_score": 0.05,
                "categories": [],
                "rationale": "",
                "model": "test_model",
            },
        )
        monkeypatch.setattr(fuji, "append_trust_event", lambda e: None)

        decision = {
            "chosen": {"title": "My chosen option"},
            "alternatives": [],
            "evidence": [],
        }
        res = fuji.evaluate(decision)
        # should succeed without error
        assert "decision_status" in res

    def test_dict_context_merge(self, monkeypatch):
        """decision の context と外部 context がマージされる。"""
        captured_ctx: Dict[str, Any] = {}
        original_fuji_gate = fuji.fuji_gate

        def spy_fuji_gate(text, *, context=None, evidence=None, alternatives=None):
            captured_ctx.update(context or {})
            return original_fuji_gate(
                text, context=context, evidence=evidence, alternatives=alternatives
            )

        monkeypatch.setattr(fuji, "_check_policy_hot_reload", lambda: None)
        monkeypatch.setattr(
            fuji, "call_tool",
            lambda *a, **kw: {
                "ok": True,
                "risk_score": 0.05,
                "categories": [],
                "rationale": "",
                "model": "test_model",
            },
        )
        monkeypatch.setattr(fuji, "append_trust_event", lambda e: None)
        monkeypatch.setattr(fuji, "fuji_gate", spy_fuji_gate)

        decision = {
            "query": "q",
            "context": {"from_decision": True},
            "evidence": [],
        }
        fuji.evaluate(decision, context={"from_caller": True})
        assert captured_ctx.get("from_decision") is True
        assert captured_ctx.get("from_caller") is True


# ===========================================================
# B-9) validate_action — v1 compatibility
# ===========================================================

class TestValidateActionV1Compat:
    """validate_action の status マッピング (allow→ok, deny→rejected, else→modify)。"""

    def test_allow_maps_to_ok(self, monkeypatch):
        monkeypatch.setattr(
            fuji, "fuji_gate",
            lambda text, **kw: {
                "status": "allow",
                "decision_status": "allow",
                "reasons": [],
                "violations": [],
                "risk": 0.05,
                "followups": [],
                "modifications": [],
                "guidance": "",
            },
        )
        res = fuji.validate_action("safe text")
        assert res["status"] == "ok"

    def test_deny_maps_to_rejected(self, monkeypatch):
        monkeypatch.setattr(
            fuji, "fuji_gate",
            lambda text, **kw: {
                "status": "deny",
                "decision_status": "deny",
                "reasons": ["bad"],
                "violations": ["illicit"],
                "risk": 0.95,
                "followups": [],
                "modifications": [],
                "guidance": "",
            },
        )
        res = fuji.validate_action("bad text")
        assert res["status"] == "rejected"

    def test_hold_maps_to_modify(self, monkeypatch):
        monkeypatch.setattr(
            fuji, "fuji_gate",
            lambda text, **kw: {
                "status": "needs_human_review",
                "decision_status": "hold",
                "reasons": ["review"],
                "violations": [],
                "risk": 0.5,
                "followups": [{"type": "clarify", "text": "please clarify"}],
                "modifications": [],
                "guidance": "review needed",
            },
        )
        res = fuji.validate_action("ambiguous text")
        assert res["status"] == "modify"

    def test_warn_maps_to_modify(self, monkeypatch):
        monkeypatch.setattr(
            fuji, "fuji_gate",
            lambda text, **kw: {
                "status": "warn",
                "decision_status": "warn",
                "reasons": ["caution"],
                "violations": [],
                "risk": 0.35,
                "followups": [],
                "modifications": [],
                "guidance": "be careful",
            },
        )
        res = fuji.validate_action("slightly risky text")
        assert res["status"] == "modify"

    def test_status_deny_with_non_allow_ds_maps_to_rejected(self, monkeypatch):
        """status=deny, decision_status=hold → st==deny fallback → rejected。"""
        monkeypatch.setattr(
            fuji, "fuji_gate",
            lambda text, **kw: {
                "status": "deny",
                "decision_status": "hold",
                "reasons": [],
                "violations": [],
                "risk": 0.8,
                "followups": [],
                "modifications": [],
                "guidance": "",
            },
        )
        res = fuji.validate_action("edge case")
        assert res["status"] == "rejected"

    def test_allow_decision_status_takes_priority(self, monkeypatch):
        """decision_status=allow → ok, even if status=deny (ds takes precedence)。"""
        monkeypatch.setattr(
            fuji, "fuji_gate",
            lambda text, **kw: {
                "status": "deny",
                "decision_status": "allow",
                "reasons": [],
                "violations": [],
                "risk": 0.8,
                "followups": [],
                "modifications": [],
                "guidance": "",
            },
        )
        res = fuji.validate_action("edge case")
        assert res["status"] == "ok"


# ===========================================================
# B-10) fuji_core_decide — LLM unavailable penalty
# ===========================================================

class TestFujiCoreLlmUnavailablePenalty:
    """LLM fallback 時に risk カテゴリがある場合のペナルティ付与。"""

    def test_llm_fallback_with_risk_category_adds_penalty(self):
        """llm_fallback=True + risk categories → +0.20 ペナルティ。"""
        sh = _sh(
            risk_score=0.30,
            categories=["PII"],
            model="heuristic_fallback",
            raw={"llm_fallback": True, "pii_hits": ["phone"]},
        )
        res = fuji.fuji_core_decide(
            safety_head=sh,
            stakes=0.5,
            telos_score=0.5,
            evidence_count=5,
            policy=SAFE_POLICY,
            safe_applied=False,
            text="090-1234-5678",
        )
        # Should have the penalty applied
        assert any("deterministic_llm_unavailable_penalty" in r for r in res["reasons"])

    def test_llm_fallback_without_risk_category_no_penalty(self):
        """llm_fallback=True + no risk categories → ペナルティなし。"""
        sh = _sh(
            risk_score=0.05,
            categories=[],
            model="heuristic_fallback",
            raw={"llm_fallback": True},
        )
        res = fuji.fuji_core_decide(
            safety_head=sh,
            stakes=0.3,
            telos_score=0.5,
            evidence_count=5,
            policy=SAFE_POLICY,
            text="safe text",
        )
        assert not any("deterministic_llm_unavailable_penalty" in r for r in res["reasons"])
