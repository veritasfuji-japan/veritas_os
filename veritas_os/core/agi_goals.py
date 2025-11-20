# veritas_os/core/agi_goals.py
# -*- coding: utf-8 -*-
"""
AGI ゴール管理モジュール: auto_adjust_goals

- bias_weights: persona.bias_weights （タイトル/タスク名ごとの重み）
- world_snap  : world.simulate() の結果（predicted_progress / predicted_risk / base_* など）
- value_ema   : Telos由来の「価値 EMA」（0〜1）
- fuji_risk   : FUJI Gate 由来のリスク推定（0〜1）

ここでは「簡易強化学習 / メタ学習っぽい」ロジックとして、
各ゴールの重みを progress / risk / value_ema に応じて少しずつ増減させる。
"""

from __future__ import annotations

from typing import Any, Dict


# ============================================================
# ユーティリティ
# ============================================================

def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def _clip01(x: float) -> float:
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


# ============================================================
# ゴールのグループ分類
# ============================================================

# key（= bias_weights のキー。多くは日本語タイトル）を
# 「どの種類のゴールか」に雑にマッピングする。
GOAL_GROUP_PATTERNS: Dict[str, tuple] = {
    # AGIコア開発系
    "agi_core": (
        "agiゴール管理",
        "agiゴール",
        "agi化",
        "veritasのagi化",
        "自己調整",
        "value ema",
        "world model",
        "世界モデル",
        "推論モジュール",
    ),

    # 安全 / FUJI / リスク低減
    "safety": (
        "fuji",
        "安全",
        "安全・倫理",
        "リスク",
        "risk",
        "gate",
    ),

    # 現状分析・要件定義・世界の把握
    "analysis": (
        "現状分析",
        "要件定義",
        "自己診断",
        "自己診断レポート",
        "診断レポート",
        "価値の評価",
        "世界モデルと安全境界",
        "世界モデルと安全境界の文書化",
        "世界モデルと安全境界の言語化",
    ),

    # 情報収集 / 論文リサーチ
    "research": (
        "一次情報",
        "論文",
        "research",
        "agi論文",
        "agiリサーチ",
        "研究論文",
    ),

    # 実装 / MVP / API / CLI / Github など
    "impl": (
        "mvp",
        "最小実装",
        "api実装",
        "api",
        "cli",
        "github",
        "リポジトリ",
        "統合テスト",
        "デモ",
    ),

    # その他（分類不能）
    "other": tuple(),
}


def _classify_goal(key: str) -> str:
    """
    bias_weights のキー（多くは「◯◯をする」みたいな日本語文字列）を
    簡易にグループ分類する。
    """
    k = (key or "").lower()
    if not k:
        return "other"

    for group, pats in GOAL_GROUP_PATTERNS.items():
        if not pats:
            continue
        for p in pats:
            if p and p.lower() in k:
                return group

    return "other"


# ============================================================
# 簡易「強化学習 / メタ学習」っぽいゴール自己調整
# ============================================================

def auto_adjust_goals(
    bias_weights: Dict[str, float],
    world_snap: Dict[str, Any] | None = None,
    value_ema: float = 0.5,
    fuji_risk: float = 0.05,
) -> Dict[str, float]:
    """
    AGI ゴール管理モジュールの「自己調整ロジック拡張」本体。

    イメージ:
      - world_snap(= world.simulate()) と value_ema を見て「今回の一手の報酬」を決める
      - その報酬に応じて、各ゴールグループ(agi_core / safety / analysis / research / impl)
        の重みを少しだけ増減させる（マルチアームドバンディット風）
      - 最後に全体を正規化して 0〜1 に収める

    ※ 本格的な RL ではなく「RL 風のヒューリスティック」だが、
       少なくとも progress / risk / telos に応じてゴール重みが変動する。
    """
    if not bias_weights:
        return bias_weights

    ws: Dict[str, float] = dict(bias_weights)

    # ---- world_snap から progress / risk を抽出 ----
    world_snap = dict(world_snap or {})
    # world.simulate の出力をある程度想定:
    # { predicted_progress, predicted_risk, base_progress, base_risk, ... }
    progress = _safe_float(
        world_snap.get("predicted_progress")
        or world_snap.get("progress")
        or world_snap.get("base_progress"),
        default=1.0,
    )
    risk = _safe_float(
        world_snap.get("predicted_risk")
        or world_snap.get("last_risk")
        or world_snap.get("base_risk")
        or fuji_risk,
        default=fuji_risk,
    )

    # 0〜1 に軽くクリップ
    progress = _clip01(progress)
    risk = _clip01(risk)
    value_ema = _clip01(value_ema)
    fuji_risk = _clip01(fuji_risk)

    # ---- 簡易「報酬」: progress + value_ema が高く、安全(risk低)なら高報酬 ----
    # reward ~= 0〜1 を想定
    reward = (
        0.4 * progress
        + 0.4 * value_ema
        + 0.2 * (1.0 - max(risk, fuji_risk))
    )
    reward = _clip01(reward)

    # baseline 0.5 を中心に、上なら「うまくいってる」、下なら「改善が必要」とみなす
    reward_delta = reward - 0.5  # -0.5〜+0.5

    # 学習率: 1回あたりどれくらい重みを動かすか（小さめ）
    base_lr = 0.20  # 20% くらいまでしかスケールさせない

    # ---- グループごとのスケーリングファクタを決める ----
    # ここに「メタ戦略」を埋め込む。
    #
    # ・reward が高い = いまの戦略がうまく行ってる:
    #     - agi_core / impl を少し強化（攻め継続）
    #     - analysis / research はやや抑えめ（調査フェーズから実装フェーズへ）
    #
    # ・reward が低い = いまの戦略で伸びてない:
    #     - analysis / research / safety を強化（状況把握と安全側へのシフト）
    #     - impl / agi_core は少し抑えめ（闇雲な実装を緩める）
    group_scale: Dict[str, float] = {}

    if reward_delta >= 0:
        # うまく行っているとき: exploitation モード寄り
        group_scale["agi_core"] = 1.0 + base_lr * (reward_delta * 1.2)
        group_scale["impl"]     = 1.0 + base_lr * (reward_delta * 1.0)
        group_scale["analysis"] = 1.0 - base_lr * (reward_delta * 0.6)
        group_scale["research"] = 1.0 - base_lr * (reward_delta * 0.5)
        # 安全は基本維持だが、危険度が高い時だけ少し上げる
        safety_boost = (0.5 - min(risk, fuji_risk)) * 0.4  # 安全ならプラス、危険ならマイナス
        group_scale["safety"]   = 1.0 + base_lr * safety_boost
    else:
        # うまく行っていないとき: exploration & safety モード寄り
        group_scale["agi_core"] = 1.0 + base_lr * (reward_delta * 0.6)  # ちょい下げ
        group_scale["impl"]     = 1.0 + base_lr * (reward_delta * 0.8)  # もう少し下げ
        group_scale["analysis"] = 1.0 - base_lr * (reward_delta * 1.2)  # 上げる（deltaは負なので-×-でプラス）
        group_scale["research"] = 1.0 - base_lr * (reward_delta * 1.0)
        group_scale["safety"]   = 1.0 - base_lr * (reward_delta * 1.3)

    # other は常に 1.0 付近（あまり動かさない）
    group_scale.setdefault("other", 1.0)

    # ---- 各ゴール重みを RL 風にアップデート ----
    new_ws: Dict[str, float] = {}
    for key, w in ws.items():
        g = _classify_goal(key)
        scale = group_scale.get(g, 1.0)

        # スケール適用（0未満にはしない）
        new_w = max(w * scale, 0.0)
        new_ws[key] = new_w

    # ---- 正規化（合計1.0 に揃える） ----
    total = sum(new_ws.values())
    if total <= 0:
        # すべて 0 になってしまった場合は、元に近い形でリセット
        n = len(new_ws) or 1
        return {k: 1.0 / n for k in new_ws.keys()}

    normalized = {k: v / total for k, v in new_ws.items()}

    return normalized
