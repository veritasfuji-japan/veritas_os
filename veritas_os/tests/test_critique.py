# tests/test_critique.py
from veritas_os.core.critique import (
    analyze,
    summarize_critiques,
    filter_by_severity,
)


def _issues_set(critiques):
    return {c.get("issue") for c in critiques}


def test_analyze_detects_evidence_shortage_and_high_risk():
    option = {
        "title": "新機能実装",
        "risk": 0.9,
        "complexity": 3,
        "value": 0.8,
    }
    evidence = []  # 根拠ゼロ
    context = {
        "min_evidence": 2,
        "risk_threshold": 0.7,
    }

    critiques = analyze(option, evidence, context)
    issues = _issues_set(critiques)

    assert "根拠不足" in issues
    assert "高リスク" in issues

    lack = next(c for c in critiques if c["issue"] == "根拠不足")
    assert lack["severity"] == "high"
    assert lack["details"]["evidence_count"] == 0
    assert lack["details"]["min_required"] == 2

    high_risk = next(c for c in critiques if c["issue"] == "高リスク")
    assert high_risk["severity"] == "high"
    assert high_risk["details"]["risk_score"] == 0.9
    assert high_risk["details"]["threshold"] == 0.7


def test_analyze_detects_low_confidence_evidence():
    option = {"title": "テスト", "risk": 0.1, "value": 0.8}
    evidence = [
        {"source": "a", "confidence": 0.4},
        {"source": "b", "confidence": 0.5},
    ]
    context = {
        "min_evidence": 1,  # 件数は足りている状態にする
    }

    critiques = analyze(option, evidence, context)
    issues = _issues_set(critiques)

    assert "低信頼性の根拠" in issues
    low_conf = next(c for c in critiques if c["issue"] == 
"低信頼性の根拠")
    assert low_conf["details"]["avg_confidence"] < 0.6
    assert low_conf["details"]["confidence_threshold"] == 0.6
    assert low_conf["details"]["evidence_confidences"] == [0.4, 0.5]


def test_analyze_detects_complexity_and_timeline_and_feasibility():
    option = {
        "title": "大規模リプレイス",
        "risk": 0.2,
        "complexity": 10,     # → 過大スコープ
        "value": 0.9,
        "feasibility": 0.3,   # → 低実現可能性
        "timeline": 365,      # → 長期タイムライン
    }
    evidence = [
        {"source": "design_doc", "confidence": 0.9},
        {"source": "review", "confidence": 0.9},
    ]
    context = {
        "min_evidence": 2,
        "complexity_threshold": 5,
        "feasibility_threshold": 0.4,
        "timeline_threshold": 180,
    }

    critiques = analyze(option, evidence, context)
    issues = _issues_set(critiques)

    assert "過大スコープ" in issues
    assert "低実現可能性" in issues
    assert "長期タイムライン" in issues

    scope = next(c for c in critiques if c["issue"] == "過大スコープ")
    assert scope["details"]["complexity"] == 10
    assert scope["details"]["threshold"] == 5

    feas = next(c for c in critiques if c["issue"] == "低実現可能性")
    assert feas["severity"] == "med"  # 0.3 は 0.2 以上なので med
    assert feas["details"]["feasibility"] == 0.3

    tl = next(c for c in critiques if c["issue"] == "長期タイムライン")
    assert tl["details"]["timeline_days"] == 365
    assert tl["details"]["threshold"] == 180


def test_analyze_detects_low_value_and_risk_value_imbalance():
    option = {
        "title": "微妙な施策",
        "risk": 0.8,   # 高い
        "value": 0.2,  # 低い
    }
    evidence = [
        {"source": "memo", "confidence": 0.7},
        {"source": "chat", "confidence": 0.7},
    ]
    context = {
        "min_evidence": 1,       # 根拠不足は出さない
        "value_threshold": 0.3,
    }

    critiques = analyze(option, evidence, context)
    issues = _issues_set(critiques)

    assert "低価値" in issues
    assert "リスク・価値の不均衡" in issues

    low_v = next(c for c in critiques if c["issue"] == "低価値")
    assert low_v["severity"] == "low"
    assert low_v["details"]["value"] == 0.2
    assert low_v["details"]["threshold"] == 0.3

    imbalance = next(c for c in critiques if c["issue"] == 
"リスク・価値の不均衡")
    assert imbalance["severity"] == "high"
    # value > 0 なので ratio は有限になるはず
    assert imbalance["details"]["risk_value_ratio"] == 0.8 / 0.2


def test_analyze_returns_empty_list_for_good_option():
    option = {
        "title": "小さな改善",
        "risk": 0.1,
        "complexity": 2,
        "value": 0.9,
        "feasibility": 0.9,
        "timeline": 30,
    }
    evidence = [
        {"source": "user_feedback", "confidence": 0.9},
        {"source": "analytics", "confidence": 0.8},
    ]
    context = {
        "min_evidence": 2,
        "risk_threshold": 0.7,
        "complexity_threshold": 5,
        "value_threshold": 0.3,
        "feasibility_threshold": 0.4,
        "timeline_threshold": 180,
    }

    critiques = analyze(option, evidence, context)
    assert critiques == []


def test_summarize_critiques_empty_and_non_empty():
    # 空ケース
    empty_summary = summarize_critiques([])
    assert empty_summary["total"] == 0
    assert empty_summary["by_severity"] == {"high": 0, "med": 0, "low": 0}
    assert empty_summary["issues"] == []
    assert empty_summary["has_blockers"] is False

    # 非空ケース
    critiques = [
        {"issue": "根拠不足", "severity": "high", "fix": "..."},
        {"issue": "低価値", "severity": "low", "fix": "..."},
        {"issue": "過大スコープ", "severity": "med", "fix": "..."},
    ]
    summary = summarize_critiques(critiques)

    assert summary["total"] == 3
    assert summary["by_severity"]["high"] == 1
    assert summary["by_severity"]["med"] == 1
    assert summary["by_severity"]["low"] == 1
    assert set(summary["issues"]) == {"根拠不足", "低価値", 
"過大スコープ"}
    assert summary["has_blockers"] is True


def test_filter_by_severity_levels():
    critiques = [
        {"issue": "高リスク", "severity": "high", "fix": "..."},
        {"issue": "過大スコープ", "severity": "med", "fix": "..."},
        {"issue": "低価値", "severity": "low", "fix": "..."},
    ]

    # low 以上 → 全部
    low_plus = filter_by_severity(critiques, "low")
    assert _issues_set(low_plus) == {"高リスク", "過大スコープ", "低価値"}

    # med 以上 → high + med
    med_plus = filter_by_severity(critiques, "med")
    assert _issues_set(med_plus) == {"高リスク", "過大スコープ"}

    # high のみ
    high_only = filter_by_severity(critiques, "high")
    assert _issues_set(high_only) == {"高リスク"}

    # 未知の重要度指定 → デフォルト 0 扱いで全件通る想定
    unknown = filter_by_severity(critiques, "unknown")
    assert _issues_set(unknown) == {"高リスク", "過大スコープ", "低価値"}

