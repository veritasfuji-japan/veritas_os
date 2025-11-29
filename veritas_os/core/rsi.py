# veritas_os/core/rsi.py
from __future__ import annotations
from typing import Any, Dict

# ---- チューニング対象のデフォルト & 上下限 ----
DEFAULT_MIN_EVIDENCE = 2
MIN_MIN_EVIDENCE = 1
MAX_MIN_EVIDENCE = 5

DEFAULT_CRITIQUE_WEIGHT = 1.0
MIN_CRITIQUE_WEIGHT = 0.5
MAX_CRITIQUE_WEIGHT = 3.0


def propose_patch(last_outcome: Dict[str, Any]) -> Dict[str, float]:
    """
    直近の decide 結果（アウトカム）から、
    kernel パラメータに対する「差分パッチ」を提案する。

    いまはサンプルとして:
    - min_evidence を +1 だけ増やす
    - critique_weight を +0.1 だけ増やす
    """
    return {
        "min_evidence_delta": +1,
        "critique_weight_delta": +0.1,
    }


def validate_and_apply(patch: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    """
    propose_patch が返したパッチを、現在の state に安全に反映する。

    - 不正な値は無視
    - 事前に決めたレンジ内にクリップする
    """
    state.setdefault("kernel", {})
    k = state["kernel"]

    # ---- min_evidence の更新 ----
    try:
        delta_me = float(patch.get("min_evidence_delta", 0.0))
    except Exception:
        delta_me = 0.0

    cur_me = int(k.get("min_evidence", DEFAULT_MIN_EVIDENCE))
    new_me = cur_me + int(delta_me)
    new_me = max(MIN_MIN_EVIDENCE, min(MAX_MIN_EVIDENCE, new_me))
    k["min_evidence"] = new_me

    # ---- critique_weight の更新 ----
    try:
        delta_cw = float(patch.get("critique_weight_delta", 0.0))
    except Exception:
        delta_cw = 0.0

    cur_cw = float(k.get("critique_weight", DEFAULT_CRITIQUE_WEIGHT))
    new_cw = cur_cw + delta_cw
    new_cw = max(MIN_CRITIQUE_WEIGHT, min(MAX_CRITIQUE_WEIGHT, new_cw))
    k["critique_weight"] = round(new_cw, 2)

    return state
