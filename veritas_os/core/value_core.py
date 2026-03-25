# veritas/core/value_core.py
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

# 共通ユーティリティをインポート
from .utils import _to_float, _clip01
from .time_utils import utc_now_iso_z


def _normalize_weights(w: Dict[str, Any]) -> Dict[str, float]:
    """
    入力された weight を 0..1 にクリップし、最大値が1を超える場合は 1 に合わせてスケール。
    空なら DEFAULT_WEIGHTS を返す。
    """
    if not w:
        return DEFAULT_WEIGHTS.copy()
    # まず 0..1 に収める
    w2 = {k: _clip01(_to_float(v, 0.0)) for k, v in w.items()}
    mx = max(w2.values()) if w2 else 1.0
    if mx > 1.0 + 1e-9:  # 念のため
        w2 = {k: (v / mx) for k, v in w2.items()}
    return w2


# ==============================
#   設定・保存パス
# ==============================
# config.cfg から統一パスを取得（フォールバック: ~/.veritas）
try:
    from veritas_os.core.config import cfg as _cfg
    CFG_DIR = _cfg.log_dir or Path(os.path.expanduser("~/.veritas"))
except (ImportError, AttributeError):
    CFG_DIR = Path(os.path.expanduser("~/.veritas"))

CFG_PATH = CFG_DIR / "value_core.json"
TRUST_LOG_PATH = CFG_DIR / "trust_log.jsonl"

# デフォルトの価値重み（0.0〜1.0）
DEFAULT_WEIGHTS: Dict[str, float] = {
    "ethics": 0.95,        # 倫理
    "legality": 0.95,      # 合法性
    "harm_avoid": 0.95,    # 非加害
    "truthfulness": 0.85,  # 真実性／検証可能性
    "user_benefit": 0.85,  # 利益・便益
    "reversibility": 0.70, # 可逆性
    "accountability": 0.70,# 説明責任
    "efficiency": 0.60,    # 効率・コスト
    "autonomy": 0.60,      # 自律性
    # ↓日本語キー（行動方針）
    "最小ステップで前進する": 0.60,
    "mvpコードを進める": 0.60,
    "一次情報(公式/論文)を調べる": 0.70,
    "情報収集を優先する": 0.60,
    "サウナ控め": 0.30,
}

# ==============================
#   コンテキストプロファイル（domain 別の重み調整）
# ==============================
CONTEXT_PROFILES: Dict[str, Dict[str, float]] = {
    "medical": {
        "harm_avoid": 1.0,
        "truthfulness": 1.0,
        "accountability": 0.95,
        "ethics": 0.95,
    },
    "financial": {
        "legality": 1.0,
        "accountability": 0.95,
        "reversibility": 0.9,
        "truthfulness": 0.9,
    },
    "legal": {
        "legality": 1.0,
        "ethics": 1.0,
        "accountability": 0.95,
        "truthfulness": 0.9,
    },
    "safety": {
        "harm_avoid": 1.0,
        "ethics": 0.95,
        "reversibility": 0.9,
        "accountability": 0.9,
    },
}

# ==============================
#   ポリシープリセット（policy 別のスコア下限）
# ==============================
POLICY_PRESETS: Dict[str, Dict[str, float]] = {
    "strict": {
        "ethics": 0.9,
        "legality": 0.9,
        "harm_avoid": 0.9,
        "truthfulness": 0.85,
    },
    "balanced": {},
    "permissive": {},
}

# ==============================
#   プロファイル（学習する価値観）
# ==============================
@dataclass
class ValueProfile:
    weights: Dict[str, float]

    # ---- 読み込み ----
    @classmethod
    def load(cls) -> "ValueProfile":
        """
        ~/.veritas/value_core.json を読み込む。
        なければ DEFAULT_WEIGHTS を初期値として保存してから返す。
        """
        try:
            CFG_DIR.mkdir(parents=True, exist_ok=True)
            if CFG_PATH.exists():
                with CFG_PATH.open("r", encoding="utf-8") as f:
                    data = json.load(f)

                # {"weights": {...}} 形式 or そのまま dict の両方に対応
                if isinstance(data, dict):
                    loaded = data.get("weights", data)
                else:
                    loaded = {}

                merged = DEFAULT_WEIGHTS.copy()
                merged.update(
                    {
                        k: _clip01(_to_float(v, merged.get(k, 0.0)))
                        for k, v in (loaded or {}).items()
                    }
                )
                return cls(weights=_normalize_weights(merged))
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            logger.warning("load failed: %s", e)

        # 失敗したらデフォルトで作り直し
        prof = cls(weights=DEFAULT_WEIGHTS.copy())
        prof.save()
        return prof

    # ---- 保存 ----
    def save(self) -> None:
        CFG_DIR.mkdir(parents=True, exist_ok=True)
        data = {"weights": _normalize_weights(self.weights)}
        # ★ 修正: atomic_write_json を使用してクラッシュ時のファイル破損を防止
        from veritas_os.core.atomic_io import atomic_write_json
        atomic_write_json(CFG_PATH, data, indent=2)

    # ---- オンライン学習 ----
    def update_from_scores(self, scores: Dict[str, float], lr: float = 0.02) -> None:
        """
        直近の Value scores から weights を少しだけ更新する。
        w_new = (1 - lr) * w_old + lr * score
        """
        w = dict(self.weights)
        for k, s in scores.items():
            old = float(w.get(k, DEFAULT_WEIGHTS.get(k, 0.5)))
            w[k] = _clip01((1.0 - lr) * old + lr * float(s))

        self.weights = _normalize_weights(w)
        self.save()


# ==============================
#   評価用データ構造
# ==============================
@dataclass
class ValueResult:
    scores: Dict[str, float]
    total: float
    top_factors: List[str]
    rationale: str
    # --- 追加フィールド（後方互換: デフォルト値あり） ---
    contributions: Dict[str, float] = field(default_factory=dict)
    applied_context: str = ""
    applied_policy: str = ""
    audit_trail: List[Dict[str, Any]] = field(default_factory=list)


# ==============================
#   簡易ヒューリスティクス
# ==============================
NEG_WORDS = {"違法", "犯罪", "個人情報の晒し", "暴力", "武器", "差別", "誹謗中傷"}
RISKY_WORDS = {"投機", "ギャンブル", "損失", "ハッキング", "過度の自動化"}


def heuristic_value_scores(q: str, ctx: dict) -> Dict[str, float]:
    qn = (q or "").lower()

    # 初期値を DEFAULT_WEIGHTS から作る
    s = {k: float(DEFAULT_WEIGHTS.get(k, 0.5)) for k in DEFAULT_WEIGHTS}

    # ネガティブワード
    if any(w in qn for w in NEG_WORDS):
        s["ethics"] = 0.0
        s["legality"] = 0.0
        s["harm_avoid"] = 0.0

    # リスクワード
    if any(w in qn for w in RISKY_WORDS):
        s["reversibility"] = 0.4
        s["efficiency"] = 0.5

    # ポジティブなワード
    if "報告" in qn or "説明" in qn or "引用" in qn or "検証" in qn:
        s["truthfulness"] = 0.95
        s["accountability"] = 0.9

    if "自動" in qn or "自律" in qn:
        s["autonomy"] = 0.8

    if "安全" in qn or "危険" in qn or "リスク" in qn:
        s["harm_avoid"] = min(s["harm_avoid"], 0.85)

    if "改善" in qn or "最適" in qn or "短縮" in qn:
        s["efficiency"] = 0.9
        s["accountability"] = 0.8

    return {k: _clip01(v) for k, v in s.items()}


# ==============================
#   Rationale 生成（explainability 強化）
# ==============================
def _build_rationale(
    top: List[str],
    contribs: Dict[str, float],
    weights: Dict[str, float],
    scores: Dict[str, float],
    applied_context: str,
    applied_policy: str,
) -> str:
    """上位因子の数値寄与を含む詳細 rationale を生成する。"""
    parts: List[str] = []

    if applied_context:
        parts.append(f"[domain={applied_context}]")
    if applied_policy:
        parts.append(f"[policy={applied_policy}]")

    # 上位 3 因子の数値内訳
    factor_descs: List[str] = []
    for k in top[:3]:
        w = weights.get(k, 0.0)
        s = scores.get(k, 0.0)
        c = contribs.get(k, 0.0)
        factor_descs.append(f"{k}({s:.2f}×{w:.2f}={c:.2f})")
    if factor_descs:
        parts.append("主要因子: " + ", ".join(factor_descs))

    # 意味的な補足
    if "ethics" in top:
        parts.append("倫理面を重視しました")
    if "legality" in top:
        parts.append("法的な安全性を考慮しました")
    if "user_benefit" in top:
        parts.append("あなたの長期的な利益を優先しました")
    if not any(k in top for k in ("ethics", "legality", "user_benefit")):
        parts.append("全体のバランスを見て判断しました")

    return " / ".join(parts)


# ==============================
#   監査エントリ生成
# ==============================
def _audit_entry(
    action: str, key: str, old: float, new: float, **extra: Any,
) -> Dict[str, Any]:
    """audit_trail 用の統一エントリを生成する。"""
    entry: Dict[str, Any] = {
        "action": action,
        "key": key,
        "old": round(old, 4),
        "new": round(new, 4),
    }
    entry.update(extra)
    return entry


# ==============================
#   メイン評価関数（学習付き）
# ==============================
def evaluate(query: str, context: Dict[str, Any]) -> ValueResult:
    """
    - heuristic_value_scores で scores を出す
    - context["value_scores"] / ["value_weights"] で上書き可能
    - context["domain"] でコンテキストプロファイル適用
    - context["policy"] でポリシープリセット適用
    - ValueProfile を使って total を計算
    - ついでに weights を少しだけ学習して保存
    """
    ctx = context or {}
    q = query or ""
    qn = q.lower()
    audit: List[Dict[str, Any]] = []

    # 1) ヒューリスティクスで基本スコア
    scores = heuristic_value_scores(q, ctx)

    # 2) context からのスコア上書き（あれば優先）
    ctx_scores_raw: Dict[str, Any] = ctx.get("value_scores", {}) or {}
    for k, v in ctx_scores_raw.items():
        scores[k] = _clip01(_to_float(v, scores.get(k, 0.0)))

    # 3) 行動系（日本語キー）ヒント
    def _hint(tf: bool, base: float) -> float:
        return _clip01(base if tf else scores.get("最小ステップで前進する", 0.0))

    scores.setdefault("最小ステップで前進する", _hint(True, 0.7))
    scores.setdefault("mvpコードを進める", _clip01(0.6 if ("code" in qn or "実装" in qn) else 0.3))
    scores.setdefault(
        "一次情報(公式/論文)を調べる",
        _clip01(0.6 if ("論文" in qn or "paper" in qn or "rfc" in qn) else 0.3),
    )
    scores.setdefault(
        "情報収集を優先する",
        _clip01(0.5 if ("調査" in qn or "リサーチ" in qn) else 0.3),
    )
    scores.setdefault("サウナ控め", _clip01(scores.get("サウナ控め", 0.3)))

    # 3.5) ポリシープリセットによるスコア下限適用
    applied_policy = ""
    policy_name = str(ctx.get("policy", ""))
    if policy_name and policy_name in POLICY_PRESETS:
        applied_policy = policy_name
        floors = POLICY_PRESETS[policy_name]
        for k, floor_val in floors.items():
            old = scores.get(k, 0.0)
            if old < floor_val:
                scores[k] = floor_val
                audit.append(_audit_entry(
                    "policy_floor", k, old, floor_val, policy=policy_name,
                ))

    # 4) 重みの決定（保存 > context 上書き）
    prof = ValueProfile.load()
    merged_w = prof.weights.copy()
    ctx_weights = ctx.get("value_weights", {}) or {}
    for k, v in ctx_weights.items():
        merged_w[k] = _clip01(_to_float(v, merged_w.get(k, 0.0)))

    # 4.5) コンテキストプロファイルによる重み調整
    applied_context = ""
    domain = str(ctx.get("domain", ""))
    if domain and domain in CONTEXT_PROFILES:
        applied_context = domain
        profile_weights = CONTEXT_PROFILES[domain]
        for k, target_w in profile_weights.items():
            old_w = merged_w.get(k, 0.0)
            if old_w < target_w:
                merged_w[k] = target_w
                audit.append(_audit_entry(
                    "context_weight", k, old_w, target_w, domain=domain,
                ))

    weights = _normalize_weights(merged_w)

    # 5) 加重平均で total（sum→クリップではなく平均にするので 1.0 固定を防ぐ）
    contribs: Dict[str, float] = {}
    if scores:
        contribs = {
            k: round(float(scores[k]) * float(weights.get(k, 1.0)), 4)
            for k in scores.keys()
        }
        total_raw = sum(contribs.values()) / max(len(contribs), 1)
    else:
        total_raw = 0.5
    total = _clip01(total_raw)

    # 6) 上位要素（weight * score でソート）
    factors_sorted = sorted(
        scores.items(),
        key=lambda kv: float(kv[1]) * float(weights.get(kv[0], 1.0)),
        reverse=True,
    )
    top = [k for k, _ in factors_sorted[:5]]

    # 7) 詳細 rationale（explainability 強化）
    rationale = _build_rationale(
        top, contribs, weights, scores, applied_context, applied_policy,
    )

    # 8) オンライン学習（禁止フラグが立っていなければ）
    if not ctx.get("no_learn_values", False):
        lr = float(ctx.get("value_lr", 0.02))
        prof.update_from_scores(scores, lr=lr)

    return ValueResult(
        scores=scores,
        total=total,
        top_factors=top,
        rationale=rationale,
        contributions=contribs,
        applied_context=applied_context,
        applied_policy=applied_policy,
        audit_trail=audit,
    )


# ==============================
#   外部APIからの重み更新
# ==============================
def update_weights(new_weights: Dict[str, Any]) -> Dict[str, float]:
    prof = ValueProfile.load()
    for k, v in (new_weights or {}).items():
        prof.weights[k] = _clip01(_to_float(v, prof.weights.get(k, 0.0)))
    prof.weights = _normalize_weights(prof.weights)
    prof.save()
    return prof.weights


# ==============================
#   🔁 Meta-Learning: 信頼ログから自己適応
# ==============================
def rebalance_from_trust_log(log_path: str = str(TRUST_LOG_PATH)) -> None:
    """trust_log.jsonl の内容から ValueCore を自動調整"""
    log_file = Path(log_path)
    if not log_file.exists():
        logger.warning("trust_log.jsonl not found")
        return

    scores: List[float] = []
    with log_file.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                j = json.loads(line)
                if "score" in j:
                    scores.append(float(j["score"]))
            except (json.JSONDecodeError, TypeError, ValueError):
                continue

    if not scores:
        logger.warning("No scores found in trust log.")
        return

    # --- EMA ---
    ema, alpha = 0.0, 0.2
    for v in scores:
        ema = alpha * v + (1.0 - alpha) * ema
    logger.info("Trust EMA: %.3f", ema)

    prof = ValueProfile.load()
    w = prof.weights.copy()

    # --- 自己適応ロジック（例） ---
    if ema < 0.7:
        w["truthfulness"] = _clip01(_to_float(w.get("truthfulness", 0.8)) + 0.05)
        w["accountability"] = _clip01(_to_float(w.get("accountability", 0.7)) + 0.05)
    elif ema > 0.9:
        w["efficiency"] = _clip01(_to_float(w.get("efficiency", 0.6)) + 0.05)

    prof.weights = _normalize_weights(w)
    prof.save()
    logger.info(
        "ValueCore rebalanced successfully at %s",
        utc_now_iso_z(timespec="seconds"),
    )

# ==============================
#   Trust Log への1行追記
# ==============================
def append_trust_log(
    user_id: str,
    score: float,
    note: str = "",
    source: str = "manual",
    extra: Dict[str, Any] | None = None,
) -> None:
    """
    trust_log に 1 行追記するユーティリティ（ユーザーフィードバック用）。
    - score: 0.0〜1.0 を想定（範囲外ならクリップ）
    - note : 簡単なメモ（「今日の決定はかなり良い」など）
    - source: "manual" / "auto" など

    ★ 修正: 正規の logging.trust_log.append_trust_log に委譲することで
      ハッシュチェーンの整合性を維持する。
    """
    try:
        s = _clip01(score)
        rec: Dict[str, Any] = {
            "type": "trust_feedback",
            "user_id": user_id,
            "score": s,
            "note": note,
            "source": source,
        }
        if extra:
            rec["extra"] = extra

        from veritas_os.logging.trust_log import append_trust_log as _canonical_append
        _canonical_append(rec)

        logger.debug("trust_log appended: user=%s, score=%s", user_id, s)
    except Exception as e:
        logger.warning("append_trust_log failed: %s", e)
