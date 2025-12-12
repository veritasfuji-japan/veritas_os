# veritas_os/core/critique.py
# -*- coding: utf-8 -*-
"""
VERITAS Critique Module - Critical Analysis of Decision Options

このモジュールは、意思決定オプションを静的に批判的分析し、
潜在的な問題点を特定するための軽量ルールベース評価ロジックを提供する。

主な機能:
- 根拠不足の検出（件数）
- 根拠の信頼性チェック（平均 confidence）
- リスク評価
- 複雑度（スコープ）チェック
- 価値評価
- リスク・価値のバランス評価
- 実現可能性チェック
- タイムライン（期間）チェック
- クリティークの要約 / 重要度フィルタリング

使用例:
    >>> from veritas_os.core.critique import analyze
    >>>
    >>> option = {
    ...     "title": "新機能実装",
    ...     "risk": 0.3,
    ...     "complexity": 4,
    ...     "value": 0.8,
    ... }
    >>> evidence = [
    ...     {"source": "user_research", "confidence": 0.9},
    ...     {"source": "market_analysis", "confidence": 0.8},
    ... ]
    >>> context = {
    ...     "min_evidence": 2,
    ...     "risk_threshold": 0.7,
    ...     "complexity_threshold": 5,
    ... }
    >>>
    >>> critiques = analyze(option, evidence, context)
    >>> for c in critiques:
    ...     print(f"{c['severity'].upper()}: {c['issue']}")
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Iterable


Severity = str  # "high" | "med" | "low"

_SEVERITY_SCORE: Dict[str, int] = {
    "low": 0,
    "med": 1,
    "high": 2,
}


def _crit(
    issue: str,
    severity: Severity,
    details: Optional[Dict[str, Any]] = None,
    fix: Optional[str] = None,
) -> Dict[str, Any]:
    """クリティーク 1 件分の標準フォーマットを生成。"""
    return {
        "issue": issue,
        "severity": severity,
        "details": details or {},
        "fix": fix,
    }


def analyze(
    option: Dict[str, Any],
    evidence: Optional[Iterable[Dict[str, Any]]] = None,
    context: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    決定オプションを批判的に分析する。

    Args:
        option:
            評価対象のオプション dict。
            想定フィールド:
                - title (str)
                - risk (float)
                - complexity (int or float)
                - value (float)
                - feasibility (float)
                - timeline (int or float, 日数)
        evidence:
            根拠リスト。
            各要素は {"source": str, "confidence": float, ...} 形式を想定。
        context:
            閾値などの設定。
            - min_evidence (int)             : 最小根拠数（デフォルト: 2）
            - risk_threshold (float)         : リスク閾値（デフォルト: 0.7）
            - complexity_threshold (float)   : 複雑度閾値（デフォルト: 5）
            - value_threshold (float)        : 価値閾値（デフォルト: 0.3）
            - feasibility_threshold (float)  : 実現可能性閾値（デフォルト: 0.4）
            - timeline_threshold (float)     : タイムライン閾値（日）（デフォルト: 180）
            - confidence_threshold (float)   : 平均 confidence 閾値（デフォルト: 0.6）
            - risk_value_ratio_threshold(float): リスク/価値比の閾値（デフォルト: 2.0）

    Returns:
        クリティークのリスト。各要素は:
        {
            "issue": str,           # 問題名
            "severity": str,        # "high" | "med" | "low"
            "fix": str | None,      # 修正提案（任意）
            "details": dict,        # 詳細情報
        }

    Examples:
        >>> option = {"title": "Test", "risk": 0.9, "value": 0.8}
        >>> evidence = [{"source": "test"}]
        >>> context = {"min_evidence": 2, "risk_threshold": 0.7}
        >>> result = analyze(option, evidence, context)
        >>> len(result) >= 2  # 根拠不足 + 高リスク
        True
        >>> any(c["issue"] == "根拠不足" for c in result)
        True
    """
    ctx = context or {}
    ev_list = list(evidence or [])

    critiques: List[Dict[str, Any]] = []

    # ==== 閾値（context から取得 / デフォルト付き） ====
    min_evidence: int = int(ctx.get("min_evidence", 2))
    risk_threshold: float = float(ctx.get("risk_threshold", 0.7))
    complexity_threshold: float = float(ctx.get("complexity_threshold", 5.0))
    value_threshold: float = float(ctx.get("value_threshold", 0.3))
    feasibility_threshold: float = float(ctx.get("feasibility_threshold", 0.4))
    timeline_threshold: float = float(ctx.get("timeline_threshold", 180.0))

    confidence_threshold: float = float(ctx.get("confidence_threshold", 0.6))
    risk_value_ratio_threshold: float = float(
        ctx.get("risk_value_ratio_threshold", 2.0)
    )

    # ==== 1. 根拠不足チェック ====
    evidence_count = len(ev_list)
    if evidence_count < min_evidence:
        severity = "high" if evidence_count == 0 else "med"
        critiques.append(
            _crit(
                issue="根拠不足",
                severity=severity,
                details={
                    "evidence_count": evidence_count,
                    "min_required": min_evidence,
                    "gap": max(min_evidence - evidence_count, 0),
                },
                fix=f"最低 {min_evidence} 件の根拠が必要です。現在 {evidence_count} 件のみです。",
            )
        )

    # ==== 2. 根拠の信頼性チェック ====
    confidences = [
        float(e.get("confidence", 0.5))
        for e in ev_list
        if isinstance(e.get("confidence"), (int, float))
    ]

    # 「件数条件は満たしているが、平均 confidence が低い」ケースを検出
    if evidence_count > 0 and evidence_count >= min_evidence and confidences:
        avg_confidence = sum(confidences) / len(confidences)
        if avg_confidence < confidence_threshold:
            critiques.append(
                _crit(
                    issue="低信頼性の根拠",
                    severity="med",
                    details={
                        "avg_confidence": avg_confidence,
                        "confidence_threshold": confidence_threshold,
                        "evidence_confidences": confidences,
                    },
                    fix=(
                        "根拠の平均信頼度が十分ではありません。"
                        "より信頼性の高い情報源（一次データ・レビュー・監査済みレポートなど）を追加してください。"
                    ),
                )
            )

    # ==== 3. リスクチェック ====
    risk = option.get("risk")
    if isinstance(risk, (int, float)) and risk >= risk_threshold:
        critiques.append(
            _crit(
                issue="高リスク",
                severity="high",
                details={
                    "risk_score": float(risk),
                    "threshold": risk_threshold,
                    "excess": float(risk) - risk_threshold,
                },
                fix="リスク軽減策（スコープ縮小・段階導入・追加ガードなど）を検討してください。",
            )
        )

    # ==== 4. 複雑度（スコープ）チェック ====
    complexity = option.get("complexity")
    if isinstance(complexity, (int, float)) and complexity > complexity_threshold:
        critiques.append(
            _crit(
                issue="過大スコープ",
                severity="med",
                details={
                    "complexity": float(complexity),
                    "threshold": complexity_threshold,
                    "excess": float(complexity) - complexity_threshold,
                },
                fix=(
                    "スコープが大きすぎます。PoC 分割・フェーズ分割・"
                    "MVP 化などにより、段階的な導入を検討してください。"
                ),
            )
        )

    # ==== 5. 価値チェック ====
    value = option.get("value")
    if isinstance(value, (int, float)) and value < value_threshold:
        critiques.append(
            _crit(
                issue="低価値",
                severity="low",
                details={
                    "value": float(value),
                    "threshold": value_threshold,
                    "gap": value_threshold - float(value),
                },
                fix="期待される価値が低いです。代替案やよりインパクトの大きい施策を検討してください。",
            )
        )

    # ==== 6. 実現可能性チェック ====
    feasibility = option.get("feasibility")
    if isinstance(feasibility, (int, float)) and feasibility < feasibility_threshold:
        sev: Severity = "high" if feasibility < 0.2 else "med"
        critiques.append(
            _crit(
                issue="低実現可能性",
                severity=sev,
                details={
                    "feasibility": float(feasibility),
                    "threshold": feasibility_threshold,
                    "gap": feasibility_threshold - float(feasibility),
                },
                fix="リソース・スキル・依存関係・外部要因を見直し、実現性を高める前提条件を特定してください。",
            )
        )

    # ==== 7. タイムラインチェック ====
    timeline = option.get("timeline")
    if isinstance(timeline, (int, float)) and timeline > timeline_threshold:
        critiques.append(
            _crit(
                issue="長期タイムライン",
                severity="med",  # テストでは severity は参照されないが、中程度の問題として扱う
                details={
                    "timeline_days": float(timeline),
                    "threshold": timeline_threshold,
                    "excess": float(timeline) - timeline_threshold,
                },
                fix="短期的な成果が見えるマイルストーン設計やフェーズ分割を検討してください。",
            )
        )

    # ==== 8. リスク・価値バランスチェック ====
    if isinstance(risk, (int, float)) and isinstance(value, (int, float)):
        if value > 0:
            ratio = float(risk) / float(value)
        else:
            ratio = float("inf")

        # 「リスクが高く、価値が低い」ケースを重点的に警告
        # デフォルトでは ratio > 2.0 を「不均衡」とみなす
        if ratio > risk_value_ratio_threshold and risk > 0.6 and value < 0.5:
            critiques.append(
                _crit(
                    issue="リスク・価値の不均衡",
                    severity="high",
                    details={
                        "risk": float(risk),
                        "value": float(value),
                        "risk_value_ratio": ratio,
                        "ratio_threshold": risk_value_ratio_threshold,
                    },
                    fix="価値向上（スコープ調整）かリスク低減策を講じるまで、実行を保留することを検討してください。",
                )
            )

    return critiques


def summarize_critiques(critiques: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    クリティークのリストを要約する。

    Args:
        critiques: `analyze()` の出力リスト。

    Returns:
        {
          "total": int,
          "by_severity": {"high": int, "med": int, "low": int},
          "issues": List[str],      # issue 名の一覧（重複は除外）
          "has_blockers": bool,     # high severity が 1 つでもあれば True
        }

    Examples:
        >>> critiques = [
        ...     {"issue": "根拠不足", "severity": "high", "fix": "..."},
        ...     {"issue": "低価値", "severity": "low", "fix": "..."},
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
    issues_set = set()
    has_blockers = False

    for c in critiques:
        sev: Severity = c.get("severity", "low")
        issue = c.get("issue")

        if issue:
            issues_set.add(issue)

        if sev not in by_severity:
            sev_key = "low"
        else:
            sev_key = sev

        by_severity[sev_key] += 1

        if sev_key == "high":
            has_blockers = True

    return {
        "total": len(critiques),
        "by_severity": by_severity,
        "issues": list(issues_set),
        "has_blockers": has_blockers,
    }


def filter_by_severity(
    critiques: List[Dict[str, Any]],
    min_severity: str = "low",
) -> List[Dict[str, Any]]:
    """
    重要度でクリティークをフィルタリングする。

    Args:
        critiques:
            `analyze()` の出力リスト。
        min_severity:
            最小重要度。"high" | "med" | "low" | その他。
            未知の値の場合は閾値 0 扱い（＝全件通す）。

    Returns:
        フィルタ済みクリティークのリスト。

    Examples:
        >>> critiques = [
        ...     {"issue": "高リスク", "severity": "high", "fix": "..."},
        ...     {"issue": "過大スコープ", "severity": "med", "fix": "..."},
        ...     {"issue": "低価値", "severity": "low", "fix": "..."},
        ... ]
        >>> high_only = filter_by_severity(critiques, "high")
        >>> [c["issue"] for c in high_only]
        ['高リスク']
    """
    threshold = _SEVERITY_SCORE.get(min_severity, 0)
    filtered: List[Dict[str, Any]] = []

    for c in critiques:
        sev: Severity = c.get("severity", "low")
        score = _SEVERITY_SCORE.get(sev, 0)
        if score >= threshold:
            filtered.append(c)

    return filtered


__version__ = "2.0.0"
__author__ = "VERITAS Development Team"
__all__ = ["analyze", "summarize_critiques", "filter_by_severity"]


if __name__ == "__main__":
    # 簡易動作チェック用（pytest からは呼ばれない）
    print("=== VERITAS Critique Module Self-Test ===\n")

    option1 = {
        "title": "新機能実装",
        "risk": 0.9,
        "complexity": 3,
        "value": 0.8,
    }
    evidence1: List[Dict[str, Any]] = []
    context1 = {
        "min_evidence": 2,
        "risk_threshold": 0.7,
    }

    print("[Test 1] 根拠不足 + 高リスク")
    result1 = analyze(option1, evidence1, context1)
    for c in result1:
        print(f"  [{c['severity'].upper()}] {c['issue']}: {c['details']}")
    print()

    option2 = {
        "title": "小さな改善",
        "risk": 0.1,
        "complexity": 2,
        "value": 0.9,
        "feasibility": 0.9,
        "timeline": 30,
    }
    evidence2 = [
        {"source": "user_feedback", "confidence": 0.9},
        {"source": "analytics", "confidence": 0.8},
    ]
    context2 = {
        "min_evidence": 2,
        "risk_threshold": 0.7,
        "complexity_threshold": 5,
        "value_threshold": 0.3,
        "feasibility_threshold": 0.4,
        "timeline_threshold": 180,
    }

    print("[Test 2] 問題の少ないオプション")
    result2 = analyze(option2, evidence2, context2)
    if not result2:
        print("  ✅ 問題なし")
    else:
        for c in result2:
            print(f"  [{c['severity'].upper()}] {c['issue']}: {c['details']}")
    print()

    print("[Test 3] 要約")
    summary = summarize_critiques(result1)
    print(summary)
    print("\n=== Self-Test Finished ===")

