# veritas/core/strategy.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict, Any, Optional

# 同じパッケージ内の WorldModel / ValueCore を利用する
try:
    from . import world_model as wm
    from . import value_core
except ImportError:
    # パッケージ名が veritas_os の場合など、必要に応じてここを書き換え
    from veritas.core import world_model as wm  # type: ignore
    from veritas.core import value_core        # type: ignore


# =========================================
# ユーティリティ
# =========================================

def _clip01(x: Any, default: float = 0.0) -> float:
    try:
        v = float(x)
    except Exception:
        v = float(default)
    return max(0.0, min(1.0, v))


# =========================================
# オプション定義
# =========================================

DEFAULT_OPTIONS: List[Dict[str, Any]] = [
    {
        "id": "A",
        "title": "Conservative Plan",
        "description": "安全・根拠重視で段階導入（安全/再現性優先）",
        "base_score": 0.70,
    },
    {
        "id": "B",
        "title": "Balanced Plan",
        "description": "価値 / 速度 / 安全のバランスを取る（デフォルト推奨）",
        "base_score": 0.80,
    },
    {
        "id": "C",
        "title": "Aggressive Plan",
        "description": "高リスク高リターン（AGI化・自動化を最優先）",
        "base_score": 0.60,
    },
]


@dataclass
class OptionScore:
    option_id: str
    fusion_score: float      # 最終スコア（0〜1）
    base_score: float        # オプションのベース
    value_total: float       # ValueCore total（0〜1）
    world_utility: float     # world_model.simulate().utility（0〜1）
    world_confidence: float  # world_model.simulate().confidence（0〜1）
    risk: float              # FUJI risk（0〜1）
    rationale: str           # 簡易の理由テキスト


# =========================================
# オプション生成
# =========================================

def generate_options(
    state: Dict[str, Any] | None,
    ctx: Dict[str, Any] | None,
    base: List[Dict[str, Any]] | None = None,
) -> List[Dict[str, Any]]:
    """
    A/B/C などの「候補オプション」を返す。

    - base が渡されていれば、それを優先（pydantic 等の model_dump にも対応）
    - 何もなければ DEFAULT_OPTIONS を返す
    - ここではまだスコアリングはしない（純粋な候補生成）
    """
    if base and len(base) > 0:
        normalized: List[Dict[str, Any]] = []
        for o in base:
            if hasattr(o, "model_dump"):
                normalized.append(o.model_dump())  # type: ignore
            else:
                normalized.append(dict(o))
        return normalized

    # state / ctx は将来の拡張用（ここでは使わなくてもOK）
    _ = state, ctx
    return [dict(o) for o in DEFAULT_OPTIONS]


# =========================================
# スコアリング
# =========================================

def _ensure_values(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """
    ctx に values がなければ、ValueCore.evaluate を使って最小限の values を作る。
    すでに ctx["values"] があればそれを優先。
    """
    ctx = ctx or {}
    values = ctx.get("values") or {}

    if isinstance(values, dict) and "total" in values:
        return values

    # ない場合のみ評価（2重実行を避ける）
    try:
        query = ctx.get("query") or ctx.get("original_query") or ""
        vr = value_core.evaluate(str(query), ctx)
        values = {
            "total": float(vr.total),
            "scores": vr.scores,
            "top_factors": vr.top_factors,
            "rationale": vr.rationale,
        }
        ctx["values"] = values
        return values
    except Exception:
        # 失敗したらデフォルト
        return {"total": 0.5}


def score_options(
    options: List[Dict[str, Any]],
    ctx: Dict[str, Any],
) -> List[OptionScore]:
    """
    各オプションに対して
      - base_score
      - ValueCore total
      - WorldModel utility / confidence
      - FUJI risk
    を組み合わせて 0〜1 のスコアを計算する。

    戻り値は OptionScore のリスト。
    """
    ctx = ctx or {}
    state = ctx.get("world_state") or {}

    # values (0〜1)
    values = _ensure_values(ctx)
    value_total = _clip01(values.get("total", 0.5), 0.5)

    # FUJI risk (0〜1)
    fuji = ctx.get("fuji") or {}
    risk = _clip01(fuji.get("risk", 0.0), 0.0)

    scores: List[OptionScore] = []

    for opt in options:
        opt_id = str(opt.get("id") or "")
        base_score = _clip01(opt.get("base_score", 0.7), 0.7)

        # WorldModel によるユーティリティ予測
        try:
            sim = wm.simulate(opt, {"world_state": state})
            world_util = _clip01(sim.get("utility", sim.get("predicted_progress", 0.5)), 0.5)
            world_conf = _clip01(sim.get("confidence", 0.5), 0.5)
        except Exception:
            world_util = 0.5
            world_conf = 0.5

        # ===== フュージョンスコア =====
        # ざっくり:
        #   - base_score を 40%
        #   - value_total を 25%
        #   - world_util を 25%
        #   - risk の高さを -10% 分だけマイナス
        fusion = (
            0.40 * base_score +
            0.25 * value_total +
            0.25 * world_util +
            0.10 * world_conf -
            0.10 * risk
        )
        fusion = _clip01(fusion, 0.0)

        # rationale を簡易に作る
        rationale_parts: List[str] = []
        if fusion >= 0.8:
            rationale_parts.append("総合的にかなり有望なプランです")
        elif fusion >= 0.6:
            rationale_parts.append("総合的にバランスが良いプランです")
        else:
            rationale_parts.append("現時点では他のプランより優先度はやや低めです")

        if risk > 0.5:
            rationale_parts.append("FUJIリスクが高めなので慎重な検討が必要です")
        elif risk < 0.2:
            rationale_parts.append("FUJIリスクが比較的低く、安全寄りです")

        if world_util > 0.6:
            rationale_parts.append("WorldModel 上は進捗への寄与が大きそうです")

        rationale = " / ".join(rationale_parts)

        scores.append(
            OptionScore(
                option_id=opt_id,
                fusion_score=fusion,
                base_score=base_score,
                value_total=value_total,
                world_utility=world_util,
                world_confidence=world_conf,
                risk=risk,
                rationale=rationale,
            )
        )

    return scores


# =========================================
# ランキング（ベストオプションを 1 つ選ぶ）
# =========================================

def rank(
    options: List[Dict[str, Any]],
    ctx: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    options の中から「最も良い」ものを 1 つ返す。

    - ctx があれば ValueCore / WorldModel / FUJI を使ってスコアリング
    - ctx が None / 壊れている場合は、従来どおり B を優先する単純ロジックにフォールバック
    """
    if not options:
        return {}

    ctx = ctx or {}

    try:
        scores = score_options(options, ctx)
        # fusion_score 最大のオプションを選ぶ
        best_score = max(scores, key=lambda s: s.fusion_score)
        best_id = best_score.option_id
        best_opt = None
        for o in options:
            if str(o.get("id") or "") == best_id:
                best_opt = dict(o)
                break
        if best_opt is None:
            best_opt = dict(options[0])

        # スコア情報を option に埋め込んで返す
        best_opt["_veritas_scores"] = {
            "option_id": best_score.option_id,
            "fusion_score": best_score.fusion_score,
            "base_score": best_score.base_score,
            "value_total": best_score.value_total,
            "world_utility": best_score.world_utility,
            "world_confidence": best_score.world_confidence,
            "risk": best_score.risk,
            "rationale": best_score.rationale,
        }
        return best_opt

    except Exception:
        # フォールバック：従来の「Bを推し」ロジック
        fallback_score = {"A": 0.78, "B": 0.82, "C": 0.60}
        best = max(
            options,
            key=lambda o: fallback_score.get(str(o.get("id") or ""), 0.5),
        )
        return dict(best)

