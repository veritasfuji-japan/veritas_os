# veritas_os/core/reflection.py
from __future__ import annotations

from typing import Any, Dict, List

from .utils import _clip01

# trust_log / value_core は他モジュールに依存するので、
# 失敗しても落ちないように try-import しておく。
try:  # pragma: no cover - インポート失敗パスは通常は通らないので除外
    from ..logging import trust_log  # type: ignore
except Exception:  # pragma: no cover
    trust_log = None  # type: ignore[assignment]

try:  # pragma: no cover
    from . import value_core  # type: ignore
except Exception:  # pragma: no cover
    value_core = None  # type: ignore[assignment]


# _clip01 は utils.py からインポート


def _get_decision_id(decision: Any) -> str:
    """
    decision から ID をいい感じに取り出す。

    - .id 属性を優先
    - dict の場合は ["id"]
    - それも無ければ str() にフォールバック
    """
    if decision is None:
        return ""

    if hasattr(decision, "id"):
        try:
            return str(getattr(decision, "id"))
        except Exception:
            pass

    if isinstance(decision, dict) and "id" in decision:
        try:
            return str(decision["id"])
        except Exception:
            pass

    return str(decision)


def _compute_score(decision: Any, outcome: Dict[str, Any] | None) -> float:
    """
    trust_log.evaluate があればそれを使い、
    無ければ outcome["score"]、それも無ければ 0.5 を返す。
    """
    outcome = outcome or {}

    # 1) trust_log.evaluate が定義されていればそれを使う
    if trust_log is not None and hasattr(trust_log, "evaluate"):
        try:
            raw = trust_log.evaluate(decision, outcome)  # type: ignore[call-arg]
            return _clip01(raw, 0.5)
        except Exception:
            # 評価失敗時は下のフォールバックへ
            pass

    # 2) outcome に score が載っていればそれを使う
    if isinstance(outcome, dict) and "score" in outcome:
        return _clip01(outcome["score"], 0.5)

    # 3) 何もなければニュートラル 0.5
    return 0.5


def evaluate_decision(
    decision: Any,
    outcome: Dict[str, Any] | None,
    memory: List[Dict[str, Any]],
) -> float:
    """
    1回の decide 結果に対して「軽い振り返り」を行う。

    - trust_log.evaluate(decision, outcome) で score を算出（あれば）
    - score < 0.5 なら value_core.adjust_weights("prudence", +0.1) を呼ぶ（あれば）
    - memory に {decision_id, score} を append する
    - 最終的な score を返す
    """
    if memory is None:
        raise ValueError("memory は list である必要があります（None は不可）")

    score = _compute_score(decision, outcome)

    # スコアが低い場合は「慎重さ」を少しだけ強める
    if score < 0.5 and value_core is not None and hasattr(value_core, "adjust_weights"):
        try:
            # 元コードのイメージ: ValueCore.adjust_weights("prudence", +0.1)
            value_core.adjust_weights("prudence", +0.1)  # type: ignore[attr-defined]
        except Exception:
            # 調整に失敗しても core ロジックは壊さない
            pass

    memory.append(
        {
            "decision_id": _get_decision_id(decision),
            "score": score,
        }
    )
    return score

