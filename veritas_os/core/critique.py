# veritas_os/core/critique.py
# -*- coding: utf-8 -*-
"""
VERITAS Critique Module - Critical Analysis of Decision Options

このモジュールは、意思決定オプションを静的に批判的分析し、
潜在的な問題点を特定するための軽量ルールベース評価ロジックを提供する。

設計方針（重要）:
- analyze() は「生データ（list）」を返す（互換維持）
- パイプライン側で dict 契約に正規化するのが基本
- ただし事故防止のため、dict 契約を返す analyze_dict() を併設（推奨）
  -> response["critique"] に入れるのは analyze_dict() または pipeline 正規化後の dict

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
- 監査/UI都合で最低件数パッド（ensure_min_items）
- dict 契約へ整形（analyze_dict）

使用例:
    >>> from veritas_os.core.critique import analyze_dict
    >>> option = {"title":"Test", "risk":0.9, "value":0.8}
    >>> evidence = [{"source":"test", "confidence":0.7}]
    >>> ctx = {"min_evidence":2, "risk_threshold":0.7}
    >>> critique = analyze_dict(option, evidence, ctx, min_items=3)
    >>> assert isinstance(critique, dict)
    >>> assert "findings" in critique and len(critique["findings"]) >= 3
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Iterable
from datetime import datetime, timezone


Severity = str  # "high" | "med" | "low"

# NOTE:
# score が大きいほど重要度が高い
_SEVERITY_SCORE: Dict[str, int] = {
    "low": 0,
    "med": 1,
    "high": 2,
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm_severity(x: Any) -> Severity:
    """
    Critique item 側の severity は、安全側（med）へ正規化する。
    ただし filter_by_severity の「未知指定」は別扱い（=0扱い）なので、
    そちらは _severity_rank() を使用すること。
    """
    try:
        s = str(x).lower().strip()
    except (TypeError, ValueError):
        return "med"
    if s in ("high", "h", "critical", "crit"):
        return "high"
    if s in ("low", "l"):
        return "low"
    return "med"


def _severity_rank(x: Any, *, unknown_rank: int = 0) -> int:
    """
    重要度指定の rank 化。
    - Critique item の severity だけでなく、filter の min_severity にも使う。
    - filter の min_severity で未知値が来た場合、テスト契約上は 0 扱い（=全件通る）。
    """
    if x is None:
        return int(unknown_rank)
    try:
        s = str(x).lower().strip()
    except (TypeError, ValueError):
        return int(unknown_rank)

    if s in ("high", "h", "critical", "crit"):
        return _SEVERITY_SCORE["high"]
    if s in ("med", "m", "medium"):
        return _SEVERITY_SCORE["med"]
    if s in ("low", "l"):
        return _SEVERITY_SCORE["low"]
    # unknown => 0 扱い（=全件通る）などに使う
    return int(unknown_rank)


def _as_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return float(default)


def _crit(
    issue: str,
    severity: Severity,
    details: Optional[Dict[str, Any]] = None,
    fix: Optional[str] = None,
    code: Optional[str] = None,
) -> Dict[str, Any]:
    """クリティーク 1 件分の標準フォーマットを生成。"""
    return {
        "issue": str(issue),
        "severity": _norm_severity(severity),
        "details": details or {},
        "fix": fix,
        "code": code or "CRITIQUE_RULE",
    }


def analyze(
    option: Dict[str, Any],
    evidence: Optional[Iterable[Dict[str, Any]]] = None,
    context: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    決定オプションを批判的に分析する（生データ list を返す）。

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
            "issue": str,
            "severity": "high"|"med"|"low",
            "fix": str|None,
            "details": dict,
            "code": str,
        }
    """
    ctx = context or {}
    ev_list = list(evidence or [])

    critiques: List[Dict[str, Any]] = []

    # ==== 閾値（context から取得 / デフォルト付き） ====
    min_evidence: int = int(ctx.get("min_evidence", 2))
    risk_threshold: float = _as_float(ctx.get("risk_threshold", 0.7), 0.7)
    complexity_threshold: float = _as_float(ctx.get("complexity_threshold", 5.0), 5.0)
    value_threshold: float = _as_float(ctx.get("value_threshold", 0.3), 0.3)
    feasibility_threshold: float = _as_float(ctx.get("feasibility_threshold", 0.4), 0.4)
    timeline_threshold: float = _as_float(ctx.get("timeline_threshold", 180.0), 180.0)

    confidence_threshold: float = _as_float(ctx.get("confidence_threshold", 0.6), 0.6)
    risk_value_ratio_threshold: float = _as_float(ctx.get("risk_value_ratio_threshold", 2.0), 2.0)

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
                code="CRITIQUE_EVIDENCE_COUNT",
            )
        )

    # ==== 2. 根拠の信頼性チェック ====
    confidences = [
        _as_float(e.get("confidence", 0.5), 0.5)
        for e in ev_list
        if isinstance(e, dict)
    ]

    # 「件数条件は満たしているが、平均 confidence が低い」ケースを検出
    if evidence_count > 0 and evidence_count >= min_evidence and confidences:
        avg_confidence = sum(confidences) / max(len(confidences), 1)
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
                    code="CRITIQUE_EVIDENCE_CONFIDENCE",
                )
            )

    # ==== 3. リスクチェック ====
    risk = option.get("risk")
    if isinstance(risk, (int, float)) and not isinstance(risk, bool) and float(risk) >= risk_threshold:
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
                code="CRITIQUE_RISK_HIGH",
            )
        )

    # ==== 4. 複雑度（スコープ）チェック ====
    complexity = option.get("complexity")
    if isinstance(complexity, (int, float)) and not isinstance(complexity, bool) and float(complexity) > complexity_threshold:
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
                code="CRITIQUE_SCOPE_TOO_LARGE",
            )
        )

    # ==== 5. 価値チェック ====
    value = option.get("value")
    if isinstance(value, (int, float)) and not isinstance(value, bool) and float(value) < value_threshold:
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
                code="CRITIQUE_VALUE_LOW",
            )
        )

    # ==== 6. 実現可能性チェック ====
    feasibility = option.get("feasibility")
    if isinstance(feasibility, (int, float)) and not isinstance(feasibility, bool) and float(feasibility) < feasibility_threshold:
        sev: Severity = "high" if float(feasibility) < 0.2 else "med"
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
                code="CRITIQUE_FEASIBILITY_LOW",
            )
        )

    # ==== 7. タイムラインチェック ====
    timeline = option.get("timeline")
    if isinstance(timeline, (int, float)) and not isinstance(timeline, bool) and float(timeline) > timeline_threshold:
        critiques.append(
            _crit(
                issue="長期タイムライン",
                severity="med",
                details={
                    "timeline_days": float(timeline),
                    "threshold": timeline_threshold,
                    "excess": float(timeline) - timeline_threshold,
                },
                fix="短期的な成果が見えるマイルストーン設計やフェーズ分割を検討してください。",
                code="CRITIQUE_TIMELINE_LONG",
            )
        )

    # ==== 8. リスク・価値バランスチェック ====
    if isinstance(risk, (int, float)) and not isinstance(risk, bool) and isinstance(value, (int, float)) and not isinstance(value, bool):
        rv = float(value)
        # Use bounded value instead of float("inf") to avoid infinity propagation
        ratio = float(risk) / rv if rv > 0 else float(risk) * 100.0
        if ratio > risk_value_ratio_threshold and float(risk) > 0.6 and float(value) < 0.5:
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
                    code="CRITIQUE_RISK_VALUE_IMBALANCE",
                )
            )

    return critiques


def summarize_critiques(critiques: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    クリティークのリストを要約する。
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
        if not isinstance(c, dict):
            continue
        sev: Severity = _norm_severity(c.get("severity", "low"))
        issue = c.get("issue")

        if issue:
            issues_set.add(issue)

        sev_key = sev if sev in by_severity else "low"
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

    重要: テスト契約
      - min_severity="low"  => 全件
      - min_severity="med"  => high + med
      - min_severity="high" => high のみ
      - min_severity が未知値 => デフォルト 0 扱いで全件通る
        （ここで _norm_severity(min_severity) を使うと "med" に落ちてしまうので禁止）
    """
    threshold = _severity_rank(min_severity, unknown_rank=0)

    filtered: List[Dict[str, Any]] = []
    for c in critiques or []:
        if not isinstance(c, dict):
            continue
        sev: Severity = _norm_severity(c.get("severity", "low"))
        score = _SEVERITY_SCORE.get(sev, 0)
        if score >= threshold:
            filtered.append(c)

    return filtered


def ensure_min_items(
    critiques: List[Dict[str, Any]],
    *,
    min_items: int = 3,
    context: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    監査/UI都合で Critique を最低件数までパッドする。
    analyze() の意味（問題が無ければ空）を壊さないため、別関数で提供する。
    """
    _ = context or {}

    defaults = [
        _crit(
            issue="根拠の一次性・独立性が未検証",
            severity="med",
            details={"hint": "一次ソース/独立ソース2件/引用箇所紐付け"},
            fix="一次ソース + 独立ソース2件以上で裏取りし、根拠を決定ログに紐付けてください。",
            code="CRITIQUE_EVIDENCE_PRIMARY",
        ),
        _crit(
            issue="前提条件・スコープが未固定",
            severity="med",
            details={"hint": "ゴール/KPI/制約/禁止事項/対象範囲"},
            fix="目的・KPI・スコープ・制約・禁止事項を明文化し、contextに固定してください。",
            code="CRITIQUE_SCOPE_UNSPECIFIED",
        ),
        _crit(
            issue="代替案の比較が不足",
            severity="med",
            details={"hint": "少なくとも2案比較/トレードオフ"},
            fix="少なくとも2つの代替案を比較し、採用/不採用理由を明示してください。",
            code="CRITIQUE_ALTERNATIVES_WEAK",
        ),
    ]

    out = list(critiques or [])
    i = 0
    while len(out) < int(min_items):
        out.append(dict(defaults[i % len(defaults)]))
        i += 1
    return out


def _to_findings(critiques: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    analyze() 出力（issue/severity/details/fix）を
    pipeline の findings（message/code/details/fix）へ変換する。
    """
    findings: List[Dict[str, Any]] = []
    for c in critiques or []:
        if not isinstance(c, dict):
            continue
        findings.append(
            {
                "severity": _norm_severity(c.get("severity", "med")),
                "message": str(c.get("issue") or "Critique finding"),
                "code": str(c.get("code") or "CRITIQUE_RULE"),
                "details": c.get("details") if isinstance(c.get("details"), dict) else {},
                "fix": c.get("fix"),
            }
        )
    return findings


def analyze_dict(
    option: Dict[str, Any],
    evidence: Optional[Iterable[Dict[str, Any]]] = None,
    context: Optional[Dict[str, Any]] = None,
    *,
    min_items: int = 3,
    mode: str = "rules",
) -> Dict[str, Any]:
    """
    dict 契約（pipeline向け）で Critique を返す “安全API”。

    - analyze() の list を内部で取得
    - ensure_min_items() で最低件数を保証（UI/監査用）
    - findings 形式へ変換
    - response["critique"] にそのまま格納できる dict を返す

    NOTE:
      pipeline 側でも最終的に _ensure_critique_required() を通すのが理想。
      ただし、呼び出し側のミス（list のまま格納）を防ぐためにこの関数を提供する。
    """
    critiques = analyze(option, evidence, context)

    # 監査/UI都合で最低件数までパッド（意味は analyze() のまま維持）
    padded = ensure_min_items(critiques, min_items=min_items, context=context)

    findings = _to_findings(padded)

    # ok 判定: analyze() が空でも “生成成功” とみなす（問題なし）
    return {
        "ok": True,
        "mode": str(mode or "rules"),
        "summary": "Critique generated (rule-based).",
        "findings": findings,
        "recommendations": [],
        "ts": _now_iso(),
        # raw を残すとデバッグに強い（必要なければ pipeline で落としてOK）
        "raw": critiques,
    }


__version__ = "2.1.1"
__author__ = "VERITAS Development Team"
__all__ = [
    "analyze",
    "analyze_dict",
    "ensure_min_items",
    "summarize_critiques",
    "filter_by_severity",
]


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


