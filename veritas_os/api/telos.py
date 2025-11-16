# telos.py
# VERITAS: Value/Telos layer
# -------------------------------------------
# 目的:
#  - 価値関数にもとづくスコア (0..1) を算出
#  - 時間地平/安全性/重みの正規化に対応
#  - ログ/監査のための内訳(debug)を返せる

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Mapping, Tuple


@dataclass(frozen=True)
class TelosConfig:
    # 重みデフォルト（合計1.0推奨）
    W_Transcendence: float = 0.60   # 理想追求
    W_Struggle: float      = 0.40   # 現実対処

    # 時間地平ごとの係数
    horizon_factor: Mapping[str, float] | None = None  # type: ignore

    # 安全性の寄与（FUJIの risk:0..1 を想定。0=安全,1=危険）
    safety_weight: float = 0.20  # 安全が高いほど加点(-0.2..+0.2)
    safety_floor: float  = 0.50  # 最低保証(危険でも0に落とさない)

    # 基本点 (重みを掛ける前の素点係数)
    base_transcendence: float = 1.00
    base_struggle: float      = 0.70

    def __post_init__(self):
        if self.horizon_factor is None:
            object.__setattr__(self, "horizon_factor", {
                "short": 0.85,
                "mid":   1.00,
                "long":  1.05,
            })


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _weights(context: Dict, cfg: TelosConfig) -> Tuple[float, float]:
    """contextから重みを安全に取得し、合計1.0へ正規化して返す"""
    w = (context.get("telos_weights") or {})
    # 大小文字や別表記も許容
    wt = float(w.get("W_Transcendence", w.get("w_transcendence", cfg.W_Transcendence)))
    ws = float(w.get("W_Struggle",      w.get("w_struggle",      cfg.W_Struggle)))
    tot = max(1e-9, wt + ws)
    return wt / tot, ws / tot


def _horizon_factor(context: Dict, cfg: TelosConfig) -> float:
    horizon = str(context.get("time_horizon", "mid")).lower()
    return cfg.horizon_factor.get(horizon, cfg.horizon_factor["mid"])  # type: ignore


def _safety_boost(context: Dict, cfg: TelosConfig) -> Tuple[float, float]:
    """FUJIのリスク(0..1)から安全ブーストとリスクを返す"""
    fuji = context.get("fuji_status") or {}
    risk = float(fuji.get("risk", 0.0))  # 0 安全 ←→ 1 危険
    safety = _clamp(1.0 - risk)          # 1.0が安全
    boost = cfg.safety_weight * (safety - 0.5) * 2.0  # -0.2..+0.2
    return boost, _clamp(risk)


def telos_score(context: Dict) -> float:
    """
    context 例:
    {
      "telos_weights": {"W_Transcendence":0.6, "W_Struggle":0.4},
      "time_horizon": "mid",  # "short"|"mid"|"long"
      "fuji_status": {"risk":0.1}
    }
    """
    cfg = TelosConfig()

    wt, ws = _weights(context, cfg)
    h  = _horizon_factor(context, cfg)
    boost, risk = _safety_boost(context, cfg)

    # 素点（理想をやや重視）
    base = wt * cfg.base_transcendence + ws * cfg.base_struggle

    score = base * h + boost

    # 危険時でも完全0に張り付かない最低保証
    score = max(cfg.safety_floor * (1.0 - risk), score)

    return _clamp(score)


def telos_debug(context: Dict) -> Dict:
    """
    監査/ログ用の内訳を返す。
    decide() 側の shadow_log にそのまま入れてOK。
    """
    cfg = TelosConfig()
    wt, ws = _weights(context, cfg)
    h  = _horizon_factor(context, cfg)
    boost, risk = _safety_boost(context, cfg)
    base = wt * cfg.base_transcendence + ws * cfg.base_struggle
    raw  = base * h + boost
    floor = cfg.safety_floor * (1.0 - risk)
    final = _clamp(max(floor, raw))

    return {
        "input": {
            "telos_weights": {"W_Transcendence": wt, "W_Struggle": ws},
            "time_horizon": str(context.get("time_horizon", "mid")).lower(),
            "fuji_risk": risk,
        },
        "factors": {
            "horizon_factor": h,
            "base_transcendence": cfg.base_transcendence,
            "base_struggle": cfg.base_struggle,
            "safety_weight": cfg.safety_weight,
            "safety_floor": cfg.safety_floor,
            "safety_boost": boost,
        },
        "scores": {
            "base": base,
            "raw": raw,
            "floor": floor,
            "final": final,
        },
    }


__all__ = ["TelosConfig", "telos_score", "telos_debug"]
