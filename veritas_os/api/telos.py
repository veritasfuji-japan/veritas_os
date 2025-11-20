# telos.py
# VERITAS: Value/Telos layer
# -------------------------------------------
# 目的:
#  - 価値関数にもとづくスコア (0..1) を算出
#  - 時間地平/安全性/進捗指標/重みの正規化に対応
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
    # 安全が高いほど加点(-0.2..+0.2)
    safety_weight: float = 0.20
    # 危険時でもスコアが完全 0 にならない最低保証
    safety_floor: float  = 0.50

    # 基本点 (重みを掛ける前の素点係数)
    base_transcendence: float = 1.00
    base_struggle: float      = 0.70

    # world_progress / value_ema の影響度（0なら無効化）
    # pv_mix が 0.0〜1.0 のとき、factor は
    #   1.0 + progress_gain * (pv_mix - 0.5) * 2.0
    # となる（例: gain=0.1 → 0.9〜1.1）
    progress_gain: float = 0.10

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
    """
    FUJIのリスク(0..1)から安全ブーストとリスクを返す。

    risk: 0 安全 ←→ 1 危険
    safety: 1.0 が完全安全
    boost: safety_weight に応じて -0.2..+0.2 程度の補正
    """
    fuji = context.get("fuji_status") or {}
    risk = float(fuji.get("risk", 0.0))          # 0 安全 ←→ 1 危険
    risk = _clamp(risk)
    safety = 1.0 - risk                          # 1.0 が安全
    boost = cfg.safety_weight * (safety - 0.5) * 2.0  # -w..+w
    return boost, risk


def _progress_factor(context: Dict, cfg: TelosConfig) -> Tuple[float, float, float]:
    """
    world.predicted_progress と value_ema から進捗係数を算出。

    - world.predicted_progress: 0..1（world.simulate() の予測進捗）
    - value_ema: 0..1（ValueEMA: 過去 decision の平均的な価値スコア）

    どちらも指定がない場合は 0.5 とみなし、factor=1.0 となる。
    """
    world = context.get("world") or {}
    world_progress = float(world.get("predicted_progress", 0.5))
    value_ema = float(context.get("value_ema", 0.5))

    world_progress = _clamp(world_progress)
    value_ema = _clamp(value_ema)

    pv_mix = 0.5 * (world_progress + value_ema)  # 0..1 の平均
    # progress_gain=0.1 のとき 0.9〜1.1 のレンジ
    pv_factor = 1.0 + cfg.progress_gain * (pv_mix - 0.5) * 2.0

    return pv_factor, world_progress, value_ema


def telos_score(context: Dict) -> float:
    """
    Telosスコアのメイン関数。

    context 例:
    {
      "telos_weights": {
        "W_Transcendence": 0.6,
        "W_Struggle": 0.4
      },
      "time_horizon": "mid",  # "short"|"mid"|"long"
      "fuji_status": {"risk": 0.1},
      "world": {"predicted_progress": 0.8},
      "value_ema": 0.55
    }
    """
    cfg = TelosConfig()

    wt, ws = _weights(context, cfg)
    h  = _horizon_factor(context, cfg)
    boost, risk = _safety_boost(context, cfg)
    pv_factor, _, _ = _progress_factor(context, cfg)

    # 素点（理想をやや重視）
    base = wt * cfg.base_transcendence + ws * cfg.base_struggle

    # 時間地平と進捗係数を掛けた後に安全ブーストを加算
    score = base * h * pv_factor + boost

    # 危険時でも完全0に張り付かない最低保証
    floor = cfg.safety_floor * (1.0 - risk)
    score = max(floor, score)

    return _clamp(score)


def telos_debug(context: Dict) -> Dict:
    """
    監査/ログ用の内訳を返す。
    decide() 側の shadow_log にそのまま入れてOK。

    戻り値:
    {
      "input": {...},
      "factors": {...},
      "scores": {...}
    }
    """
    cfg = TelosConfig()
    wt, ws = _weights(context, cfg)
    h  = _horizon_factor(context, cfg)
    boost, risk = _safety_boost(context, cfg)
    pv_factor, world_progress, value_ema = _progress_factor(context, cfg)

    base = wt * cfg.base_transcendence + ws * cfg.base_struggle
    raw  = base * h * pv_factor + boost
    floor = cfg.safety_floor * (1.0 - risk)
    final = _clamp(max(floor, raw))

    return {
        "input": {
            "telos_weights": {
                "W_Transcendence": wt,
                "W_Struggle": ws,
            },
            "time_horizon": str(context.get("time_horizon", "mid")).lower(),
            "fuji_risk": risk,
            "world_predicted_progress": world_progress,
            "value_ema": value_ema,
        },
        "factors": {
            "horizon_factor": h,
            "base_transcendence": cfg.base_transcendence,
            "base_struggle": cfg.base_struggle,
            "safety_weight": cfg.safety_weight,
            "safety_floor": cfg.safety_floor,
            "safety_boost": boost,
            "progress_gain": cfg.progress_gain,
            "progress_factor": pv_factor,
        },
        "scores": {
            "base": base,
            "raw": raw,
            "floor": floor,
            "final": final,
        },
    }


__all__ = ["TelosConfig", "telos_score", "telos_debug"]
