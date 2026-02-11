# veritas/core/adapt.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import logging
import os
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

from .config import cfg  # VERITAS の設定オブジェクト
from .atomic_io import atomic_write_json
from .utils import _safe_float

logger = logging.getLogger(__name__)


# ==== NEW: プロジェクト内に保存するパス ============================
# 例: .../veritas_clean_test2/veritas_os/scripts/logs
VERITAS_DIR = cfg.log_dir  # = Path(.../veritas_os/scripts/logs)
PERSONA_JSON = str(VERITAS_DIR / "persona.json")
TRUST_JSONL = str(VERITAS_DIR / "trust_log.jsonl")


# =====================================
#  persona のデフォルト定義 & ヘルパ
# =====================================
def _default_persona() -> Dict[str, Any]:
    """常に同じ shape を返すデフォルト persona."""
    return {
        "name": "VERITAS",
        "style": "direct, strategic, honest",
        "bias_weights": {},
    }


def _ensure_persona(obj: Any) -> Dict[str, Any]:
    """
    ロード結果 obj を「安全な persona dict」に矯正する。

    - dict 以外 → デフォルト persona
    - dict の場合も name/style/bias_weights が欠けていれば補完
    """
    if not isinstance(obj, dict):
        persona = _default_persona()
    else:
        base = _default_persona()
        name = obj.get("name")
        style = obj.get("style")
        bias = obj.get("bias_weights")

        if isinstance(name, str) and name.strip():
            base["name"] = name
        if isinstance(style, str) and style.strip():
            base["style"] = style
        if isinstance(bias, dict):
            base["bias_weights"] = bias

        persona = base

    # bias_weights は必ずクリーンにして返す
    persona["bias_weights"] = clean_bias_weights(
        dict(persona.get("bias_weights") or {})
    )
    return persona


# =====================================
#  bias_weights のクリーニングユーティリティ
# =====================================
def clean_bias_weights(
    bias: Dict[str, float] | None,
    zero_eps: float = 1e-4,
) -> Dict[str, float]:
    """
    persona.bias_weights をクリーンアップする。

    - すべて float 化
    - 0.0〜1.0 にクリップ
    - きわめて小さい値( |v| < zero_eps )は 0 扱い
    - 最大値で正規化して、最大でも 1.0 にする
    """
    if not bias:
        return {}

    tmp: Dict[str, float] = {}
    for k, v in bias.items():
        x = _safe_float(v, default=0.0)

        # 0..1 にクリップ
        if x < 0.0:
            x = 0.0
        if x > 1.0:
            x = 1.0

        # ごく小さい値は 0 扱い
        if abs(x) < zero_eps:
            x = 0.0

        tmp[k] = x

    # 最大値でスケーリング（分布の形は保ちつつ極小値を防ぐ）
    mx = max(tmp.values()) if tmp else 1.0
    if mx <= 0.0:
        return {k: 0.0 for k in tmp.keys()}

    cleaned: Dict[str, float] = {}
    for k, v in tmp.items():
        nv = v / mx
        # 再度クリップ＆丸め（見やすさ用）
        if abs(nv) < zero_eps:
            nv = 0.0
        if nv > 1.0:
            nv = 1.0
        cleaned[k] = float(f"{nv:.3f}")

    return cleaned


# =====================================
#  persona のロード／セーブ
# =====================================
def load_persona(path: str = PERSONA_JSON) -> Dict[str, Any]:
    """
    persona.json をロードして安全な dict にして返す。

    - ファイルなし / 壊れた JSON / list など dict 以外 → デフォルト
    - dict でも name/style/bias_weights が欠けていれば補完
    """
    raw: Any
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError, ValueError):
        raw = None

    persona = _ensure_persona(raw)
    return persona


def save_persona(persona: Dict[str, Any], path: str = PERSONA_JSON) -> None:
    """
    persona をクリーンアップして JSON で保存（アトミック書き込み）。
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)

    persona = _ensure_persona(persona)
    atomic_write_json(path, persona, indent=2)


# =====================================
#  trust_log から履歴を読む
# =====================================
def read_recent_decisions(
    jsonl_path: str = TRUST_JSONL,
    window: int = 50,
) -> List[Dict[str, Any]]:
    """trust_log.jsonl から直近 window 件の chosen を抽出（なければ空）"""
    items: List[Dict[str, Any]] = []
    try:
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    # 決定ログを想定：shadow_decide書式 or append_trust_log派生
                    chosen = obj.get("chosen") or {}
                    if chosen:
                        items.append(
                            {
                                "id": chosen.get("id"),
                                "title": chosen.get("title"),
                            }
                        )
                except Exception:
                    # 1行壊れていても全体は止めない
                    logger.debug("Skipping malformed JSONL line in %s", jsonl_path)
    except FileNotFoundError:
        return []

    # 後ろ（新しい）から window 件
    return items[-window:]


def compute_bias_from_history(decisions: List[Dict[str, Any]]) -> Dict[str, float]:
    """
    頻度→確率（weight）。title 優先、なければ id で集計。

    テスト仕様に合わせて：
    - title が存在していて非空 → title.lower() で集計
    - title が存在していて空/None → id で集計
    - title キー自体が存在しない場合も → id で集計
    """
    keys: List[str] = []

    for d in decisions:
        if not isinstance(d, dict):
            continue

        has_title_key = "title" in d
        raw_title = d.get("title") if has_title_key else None
        title_str = (raw_title or "").strip() if isinstance(raw_title, str) else ""

        if has_title_key and title_str:
            # 1) title が非空 → title 優先
            keys.append(title_str.lower())
        else:
            # 2) title なし or 空 → id で集計
            if d.get("id"):
                keys.append(f"@id:{d['id']}")

    if not keys:
        return {}

    cnt = Counter(keys)
    total = float(sum(cnt.values()))
    if total <= 0.0:
        return {k: 0.0 for k in cnt.keys()}

    return {k: v / total for k, v in cnt.items()}


def merge_bias_to_persona(
    persona: Dict[str, Any],
    new_bias: Dict[str, float],
    alpha: float = 0.25,
) -> Dict[str, Any]:
    """
    単純 EMA マージ：new = (1-alpha)*old + alpha*new

    （途中で clean_bias_weights を挟んで、値の暴走を防ぐ）
    """
    persona = _ensure_persona(persona)
    old = clean_bias_weights(dict(persona.get("bias_weights") or {}))
    nb = clean_bias_weights(dict(new_bias or {}))

    merged: Dict[str, float] = {}
    keys = set(old.keys()) | set(nb.keys())
    for k in keys:
        merged[k] = (1.0 - alpha) * float(old.get(k, 0.0)) + alpha * float(
            nb.get(k, 0.0)
        )

    persona["bias_weights"] = clean_bias_weights(merged)
    return persona


def fuzzy_bias_lookup(bias_weights: Dict[str, float], title: str) -> float:
    """
    title に対して bias_weights のキー（lower title or @id:...）を緩めに照合。
    キーワード部分一致（3文字以上）で最大重みを返す。
    """
    if not bias_weights or not title:
        return 0.0

    t = title.lower()
    best = 0.0

    for k, w in bias_weights.items():
        if k.startswith("@id:"):
            # id一致は kernel 側で処理するのでここはスキップ
            continue

        # 3文字以上のトークンで部分一致
        toks = [x for x in k.split() if len(x) >= 3] or [k]
        if any(tok in t for tok in toks) or k == t:
            best = max(best, float(w))

    return best


def update_persona_bias_from_history(window: int = 50) -> Dict[str, Any]:
    """
    trust_log 履歴 → バイアス計算 → persona.json に反映して返す。
    """
    persona = load_persona()
    recent = read_recent_decisions(TRUST_JSONL, window=window)
    bias = compute_bias_from_history(recent)
    if not bias:
        return persona

    persona = merge_bias_to_persona(persona, bias, alpha=0.25)
    save_persona(persona)
    return persona


__all__ = [
    "clean_bias_weights",
    "load_persona",
    "save_persona",
    "read_recent_decisions",
    "compute_bias_from_history",
    "merge_bias_to_persona",
    "fuzzy_bias_lookup",
    "update_persona_bias_from_history",
]


