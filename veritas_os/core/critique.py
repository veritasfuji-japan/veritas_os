# veritas_os/core/critique.py
# -*- coding: utf-8 -*-
"""
VERITAS Critique Module - Critical Analysis of Decision Options

このモジュールは、意思決定オプションを批判的に分析し、
潜在的な問題点を特定します。

機能:
- 根拠不足の検出
- リスク評価
- 複雑度チェック
- 価値評価
- 設定可能な閾値

使用例:
    >>> from veritas_os.core.critique import analyze
    >>> 
    >>> option = {
    ...     "title": "新機能実装",
    ...     "risk": 0.3,
    ...     "complexity": 4,
    ...     "value": 0.8
    ... }
    >>> evidence = [
    ...     {"source": "user_research", "confidence": 0.9},
    ...     {"source": "market_analysis", "confidence": 0.8}
    ... ]
    >>> context = {
    ...     "min_evidence": 2,
    ...     "risk_threshold": 0.7,
    ...     "complexity_threshold": 5
    ... }
    >>> 
    >>> critiques = analyze(option, evidence, context)
    >>> for c in critiques:
    ...     print(f"{c['severity'].upper()}: {c['issue']}")
"""

from typing import List, Dict, Any, Optional


def analyze(
    option: Dict[str, Any],
    evidence: List[Dict[str, Any]],
    context: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    決定オプションを批判的に分析
    
    この関数は、提供された選択肢に対して複数の観点から批判的分析を行い、
    潜在的な問題点をリスト化します。
    
    Args:
        option: 評価する選択肢
            必須フィールド: title (str)
            オプション: risk (float), complexity (int), value (float), 
                       feasibility (float), timeline (int)
        
        evidence: 根拠のリスト
            各要素は {"source": str, "confidence": float, ...} の形式
        
        context: 分析のコンテキストと閾値
            min_evidence (int): 最小根拠数（デフォルト: 2）
            risk_threshold (float): リスク閾値（デフォルト: 0.7）
            complexity_threshold (int): 複雑度閾値（デフォルト: 5）
            value_threshold (float): 価値閾値（デフォルト: 0.3）
            feasibility_threshold (float): 実現可能性閾値（デフォルト: 0.4）
            timeline_threshold (int): タイムライン閾値（デフォルト: 180日）
    
    Returns:
        批判のリスト。各要素は以下の形式:
        {
            "issue": str,           # 問題の名前
            "severity": str,        # "high" | "med" | "low"
            "fix": str,             # 修正案
            "details": dict,        # 詳細情報
        }
    
    Examples:
        >>> option = {"title": "Test", "risk": 0.9, "value": 0.8}
        >>> evidence = [{"source": "test"}]
        >>> context = {"min_evidence": 2, "risk_threshold": 0.7}
        >>> result = analyze(option, evidence, context)
        >>> len(result) >= 2  # 根拠不足 + 高リスク
        True
        >>> result[0]["issue"]
        '根拠不足'
    """
    crit = []
    
    # ==== 設定可能な閾値（contextから取得） ====
    min_evidence = context.get("min_evidence", 2)
    risk_threshold = context.get("risk_threshold", 0.7)
    complexity_threshold = context.get("complexity_threshold", 5)
    value_threshold = context.get("value_threshold", 0.3)
    feasibility_threshold = context.get("feasibility_threshold", 0.4)
    timeline_threshold = context.get("timeline_threshold", 180)  # days
    
    # ==== 1. 根拠不足チェック ====
    evidence_count = len(evidence)
    if evidence_count < min_evidence:
        severity = "high" if evidence_count == 0 else "med"
        crit.append({
            "issue": "根拠不足",
            "severity": severity,
            "fix": f"最低{min_evidence}件の根拠が必要です。現在{evidence_count}件のみ。追加の情報収集を推奨。",
            "details": {
                "evidence_count": evidence_count,
                "min_required": min_evidence,
                "gap": min_evidence - evidence_count,
            },
        })
    
    # ==== 2. 根拠の信頼性チェック ====
    if evidence:
        confidences = [
            e.get("confidence", 0.5) 
            for e in evidence 
            if isinstance(e.get("confidence"), (int, float))
        ]
        if confidences:
            avg_confidence = sum(confidences) / len(confidences)
            if avg_confidence < 0.6:
                crit.append({
                    "issue": "低信頼性の根拠",
                    "severity": "med",
                    "fix": f"根拠の平均信頼度が{avg_confidence:.2f}と低いです。より信頼性の高い情報源を追加してください。",
                    "details": {
                        "avg_confidence": avg_confidence,
                        "confidence_threshold": 0.6,
                        "evidence_confidences": confidences,
                    },
                })
    
    # ==== 3. リスクチェック ====
    risk = option.get("risk", 0.0)
    if isinstance(risk, (int, float)) and risk > risk_threshold:
        crit.append({
            "issue": "高リスク",
            "severity": "high",
            "fix": f"リスクスコアが{risk:.2f}と高いです。リスク軽減策の検討が必要です。",
            "details": {
                "risk_score": risk,
                "threshold": risk_threshold,
                "excess": risk - risk_threshold,
            },
        })
    
    # ==== 4. 複雑度チェック（条件付き） ====
    complexity = option.get("complexity", 0)
    if isinstance(complexity, (int, float)) and complexity > complexity_threshold:
        crit.append({
            "issue": "過大スコープ",
            "severity": "med",
            "fix": f"複雑度が{complexity}と高いです。「1価値 = 1画面」の原則でPoCを分割することを推奨。",
            "details": {
                "complexity": complexity,
                "threshold": complexity_threshold,
                "excess": complexity - complexity_threshold,
            },
        })
    
    # ==== 5. 価値チェック ====
    value = option.get("value", 0.0)
    if isinstance(value, (int, float)) and value < value_threshold:
        crit.append({
            "issue": "低価値",
            "severity": "low",
            "fix": f"期待価値が{value:.2f}と低いです。より価値の高い選択肢を検討してください。",
            "details": {
                "value": value,
                "threshold": value_threshold,
                "gap": value_threshold - value,
            },
        })
    
    # ==== 6. 実現可能性チェック ====
    feasibility = option.get("feasibility")
    if isinstance(feasibility, (int, float)) and feasibility < feasibility_threshold:
        crit.append({
            "issue": "低実現可能性",
            "severity": "high" if feasibility < 0.2 else "med",
            "fix": f"実現可能性が{feasibility:.2f}と低いです。技術的制約や前提条件を再検討してください。",
            "details": {
                "feasibility": feasibility,
                "threshold": feasibility_threshold,
                "gap": feasibility_threshold - feasibility,
            },
        })
    
    # ==== 7. タイムラインチェック ====
    timeline = option.get("timeline")
    if isinstance(timeline, (int, float)) and timeline > timeline_threshold:
        crit.append({
            "issue": "長期タイムライン",
            "severity": "low",
            "fix": f"予定期間が{timeline}日と長いです。短期的な成果を示せるマイルストーンの設定を推奨。",
            "details": {
                "timeline_days": timeline,
                "threshold": timeline_threshold,
                "excess": timeline - timeline_threshold,
            },
        })
    
    # ==== 8. リスク・価値バランスチェック ====
    if isinstance(risk, (int, float)) and isinstance(value, (int, float)):
        # ハイリスク・ローリターン は問題
        if risk > 0.6 and value < 0.5:
            crit.append({
                "issue": "リスク・価値の不均衡",
                "severity": "high",
                "fix": f"リスク{risk:.2f}に対して価値{value:.2f}が低すぎます。価値を高めるか、リスクを下げる施策を検討してください。",
                "details": {
                    "risk": risk,
                    "value": value,
                    "risk_value_ratio": risk / value if value > 0 else float('inf'),
                },
            })
    
    return crit


def summarize_critiques(critiques: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    批判のリストを要約
    
    Args:
        critiques: analyze()の出力
    
    Returns:
        要約情報:
        {
            "total": int,
            "by_severity": {"high": int, "med": int, "low": int},
            "issues": List[str],
            "has_blockers": bool,
        }
    
    Examples:
        >>> critiques = [
        ...     {"issue": "根拠不足", "severity": "high", "fix": "..."},
        ...     {"issue": "低価値", "severity": "low", "fix": "..."}
        ... ]
        >>> summary = summarize_critiques(critiques)
        >>> summary["total"]
        2
        >>> summary["has_blockers"]
        True
    """
    if not critiques:
        return {
            "total": 0,
            "by_severity": {"high": 0, "med": 0, "low": 0},
            "issues": [],
            "has_blockers": False,
        }
    
    by_severity = {"high": 0, "med": 0, "low": 0}
    issues = []
    
    for c in critiques:
        severity = c.get("severity", "med")
        if severity in by_severity:
            by_severity[severity] += 1
        issues.append(c.get("issue", "Unknown"))
    
    return {
        "total": len(critiques),
        "by_severity": by_severity,
        "issues": issues,
        "has_blockers": by_severity["high"] > 0,
    }


def filter_by_severity(
    critiques: List[Dict[str, Any]],
    min_severity: str = "low",
) -> List[Dict[str, Any]]:
    """
    重要度でフィルタリング
    
    Args:
        critiques: analyze()の出力
        min_severity: 最小重要度（"high" | "med" | "low"）
    
    Returns:
        フィルタされた批判リスト
    
    Examples:
        >>> critiques = [
        ...     {"issue": "高リスク", "severity": "high", "fix": "..."},
        ...     {"issue": "低価値", "severity": "low", "fix": "..."}
        ... ]
        >>> high_only = filter_by_severity(critiques, "high")
        >>> len(high_only)
        1
    """
    severity_order = {"high": 2, "med": 1, "low": 0}
    min_level = severity_order.get(min_severity, 0)
    
    return [
        c for c in critiques
        if severity_order.get(c.get("severity", "low"), 0) >= min_level
    ]


# ==== モジュールレベルのメタデータ ====

__version__ = "2.0.0"
__author__ = "VERITAS Development Team"
__all__ = ["analyze", "summarize_critiques", "filter_by_severity"]


if __name__ == "__main__":
    # 簡易テスト
    print("=== VERITAS Critique Module Test ===\n")
    
    # テストケース1: 根拠不足 + 高リスク
    print("Test 1: 根拠不足 + 高リスク")
    option1 = {
        "title": "新機能実装",
        "risk": 0.9,
        "complexity": 3,
        "value": 0.8,
    }
    evidence1 = []  # 根拠なし
    context1 = {
        "min_evidence": 2,
        "risk_threshold": 0.7,
    }
    
    result1 = analyze(option1, evidence1, context1)
    print(f"批判数: {len(result1)}")
    for c in result1:
        print(f"  [{c['severity'].upper()}] {c['issue']}: {c['fix']}")
    print()
    
    # テストケース2: 完璧な選択肢
    print("Test 2: 完璧な選択肢")
    option2 = {
        "title": "小さな改善",
        "risk": 0.2,
        "complexity": 2,
        "value": 0.9,
        "feasibility": 0.9,
        "timeline": 30,
    }
    evidence2 = [
        {"source": "user_feedback", "confidence": 0.9},
        {"source": "analytics", "confidence": 0.8},
        {"source": "expert_review", "confidence": 0.85},
    ]
    context2 = {
        "min_evidence": 2,
        "risk_threshold": 0.7,
        "complexity_threshold": 5,
        "value_threshold": 0.3,
    }
    
    result2 = analyze(option2, evidence2, context2)
    print(f"批判数: {len(result2)}")
    if result2:
        for c in result2:
            print(f"  [{c['severity'].upper()}] {c['issue']}: {c['fix']}")
    else:
        print("  ✅ 問題なし！")
    print()
    
    # テストケース3: 要約機能
    print("Test 3: 要約機能")
    summary = summarize_critiques(result1)
    print(f"  Total: {summary['total']}")
    print(f"  High: {summary['by_severity']['high']}")
    print(f"  Med: {summary['by_severity']['med']}")
    print(f"  Low: {summary['by_severity']['low']}")
    print(f"  Has Blockers: {summary['has_blockers']}")
    print()
    
    print("=== All Tests Completed ===")
