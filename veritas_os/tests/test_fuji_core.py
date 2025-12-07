# -*- coding: utf-8 -*-
"""
FUJI Gate v2 / fuji_core_decide のテスト

- heuristic_fallback の name_like 誤検出の無視
- PII マスク済み (safe_applied) 緩和
- evidence 不足ペナルティ
- illicit 高リスク → deny
- fuji_gate 経由での TrustLog イベント
- validate_action / evaluate ラッパの互換性
"""

import pytest

from veritas_os.core import fuji


# ---------------------------------------------------------
# ユーティリティ
# ---------------------------------------------------------


def _sh(
    *,
    risk_score: float = 0.1,
    categories=None,
    rationale: str = "",
    model: str = "heuristic_fallback",
    raw=None,
) -> fuji.SafetyHeadResult:
    """SafetyHeadResult を簡単に作るヘルパー"""
    return fuji.SafetyHeadResult(
        risk_score=risk_score,
        categories=categories or [],
        rationale=rationale,
        model=model,
        raw=raw or {},
    )


# ---------------------------------------------------------
# fuji_core_decide のテスト
# ---------------------------------------------------------


def test_fuji_core_ignores_name_like_only_pii():
    """
    heuristic_fallback で「name_like だけ PII」になっているケースを
    ちゃんと無視して risk を下げているか。
    """
    sh = _sh(
        risk_score=0.6,
        categories=["PII"],
        rationale="PII パターン検出: name_like",
        model="heuristic_fallback",
        raw={"fallback": True, "pii_hits": ["name_like"]},
    )

    res = fuji.fuji_core_decide(
        safety_head=sh,
        stakes=0.5,
        telos_score=0.0,
        evidence_count=1,
        policy=fuji.POLICY,
        safe_applied=False,
    )

    # PII カテゴリは有効な違反としては出てこないはず
    assert "PII" not in res["violations"]
    # リスクが 0.2 以下まで抑えられている（実装上の上限）
    assert res["risk"] <= 0.20
    # 理由に fallback_pii_ignored が入っている
    assert any("fallback_pii_ignored" in r for r in res["reasons"])


def test_fuji_core_pii_safe_applied_relaxes_category():
    """
    context で fuji_safe_applied / pii_already_masked が True のとき、
    PII カテゴリが弱まり、risk が 0.40 以下に抑えられるか。
    """
    sh = _sh(
        risk_score=0.8,
        categories=["PII"],
        rationale="電話番号が含まれています",
        raw={"fallback": True, "pii_hits": ["phone"]},
    )

    res = fuji.fuji_core_decide(
        safety_head=sh,
        stakes=0.5,
        telos_score=0.0,
        evidence_count=1,
        policy=fuji.POLICY,
        safe_applied=True,  # ← マスク済みフラグ
    )

    # PII は violations には出てこない（緩和されている）
    assert "PII" not in res["violations"]
    # リスクは 0.40 以下にクリップされる
    assert res["risk"] <= 0.40
    # 理由に pii_safe_applied が入っている
    assert any("pii_safe_applied" in r for r in res["reasons"])


def test_fuji_core_low_evidence_penalty():
    """
    evidence_count < min_evidence の場合に low_evidence が付与され、
    guidance に補足メッセージが入るか。
    """
    sh = _sh(
        risk_score=0.1,
        categories=[],
        rationale="特段の危険は検出されませんでした。",
        raw={"fallback": True, "hits": [], "pii_hits": []},
    )

    res = fuji.fuji_core_decide(
        safety_head=sh,
        stakes=0.5,
        telos_score=0.0,
        evidence_count=0,  # ← エビデンス不足
        policy=fuji.POLICY,
        safe_applied=False,
        min_evidence=1,
    )

    # 少しだけリスクが増える
    assert res["risk"] >= 0.1
    # 理由に low_evidence が含まれている
    assert any("low_evidence" in r for r in res["reasons"])
    # guidance にエビデンス不足の補足が入る
    assert "エビデンスが不足している可能性があります" in (res["guidance"] 
or "")


def test_fuji_core_illicit_high_risk_denied():
    """
    illicit カテゴリ × high risk の場合に policy によって deny になるか。
    """
    sh = _sh(
        risk_score=0.9,
        categories=["illicit"],
        rationale="危険・違法系キーワード検出: weapon",
        raw={"fallback": True, "hits": ["weapon"], "pii_hits": []},
    )

    res = fuji.fuji_core_decide(
        safety_head=sh,
        stakes=0.8,   # high_stakes
        telos_score=0.0,
        evidence_count=3,
        policy=fuji.POLICY,
        safe_applied=False,
    )

    assert res["status"] == "deny"
    assert res["decision_status"] == "deny"
    assert "illicit" in res["violations"]


# ---------------------------------------------------------
# fuji_gate / ラッパのテスト
# ---------------------------------------------------------


def test_fuji_gate_trustlog_append(monkeypatch):
    """
    fuji_gate が TrustLog の append_trust_event を 1 回呼ぶか。
    """
    events = []

    def fake_append(event):
        events.append(event)

    # trust_log だけ差し替え（safety_head は本物のままでも fallback で動く）
    monkeypatch.setattr(fuji, "append_trust_event", fake_append)

    res = fuji.fuji_gate(
        text="これは安全なテストクエリです。",
        context={"stakes": 0.5},
        evidence=[],
        alternatives=[],
    )

    # FUJI の最終ステータス
    assert res["status"] in ("allow", "allow_with_warning", "needs_human_review")

    # TrustLog イベントが 1 件飛んでいる
    assert len(events) == 1
    ev = events[0]
    assert ev["event"] == "fuji_evaluate"
    assert "risk_score" in ev
    assert "policy_version" in ev
    assert "latency_ms" in ev


def test_validate_action_ok_flow():
    """
    validate_action(v1 互換ラッパ) が少なくとも rejected にはならない
    普通メッセージで通ることを確認。
    """
    res = fuji.validate_action(
        "これは普通の雑談メッセージです。", context={"stakes": 0.3},
    )

    assert res["status"] in ("ok", "modify")
    assert "risk" in res


def test_evaluate_with_decision_dict():
    """
    decision dict を渡したときに、decision_id を維持したまま
    fuji_gate を通って結果が返ってくるか。
    """
    decision = {
        "query": "This is a sample decision query.",
        "context": {"stakes": 0.5},
        "evidence": [],
        "alternatives": [],
        "request_id": "req-123",
    }

    res = fuji.evaluate(decision)
    assert res["status"] in (
        "allow",
        "allow_with_warning",
        "needs_human_review",
        "deny",
    )
    assert res.get("decision_id") == "req-123"

