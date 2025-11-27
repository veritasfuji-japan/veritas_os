# veritas_os/core/fuji.py
# -*- coding: utf-8 -*-
"""
FUJI Gate v2 (Safety Head × Policy Engine × TrustLog)

- Safety Head:
    LLM もしくは専用安全モデルを叩き、
      risk_score ∈ [0,1], categories[], rationale
    を返す「統計的安全ヘッド」。

- Policy Engine:
    YAML / 内蔵ポリシー定義に基づき、
      risk_score × categories × stakes × telos_score
    から
      status: "allow" | "allow_with_warning" | "needs_human_review" | "deny"
    を決定する純粋ルール層（監査可能）。

- TrustLog:
    1 回の evaluate ごとに、
      safety_head 出力・policy_version・最終 status
    を JSONL + ハッシュチェーンに append する。

互換ポイント:
- kernel.decide からは fuji.evaluate(query, context=..., evidence=..., alternatives=...)
  の旧インターフェイスで呼べる。
- decision dict を渡す新インターフェイスにも対応。
- context["fuji_safe_applied"] or context["pii_already_masked"] が True の場合、
  PII 由来カテゴリーを弱めて risk を緩和する。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List
from pathlib import Path
from datetime import datetime, timezone
import time
import os
import re

# ---------------------------------------------------------
# 依存モジュール（存在しない場合はフォールバック）
# ---------------------------------------------------------
try:
    # env tools ラッパ（llm_safety など）
    from veritas_os.tools import call_tool
except Exception:  # pragma: no cover
    def call_tool(kind: str, **kwargs: Any) -> Dict[str, Any]:
        raise RuntimeError(
            f"env tool '{kind}' / veritas_os.tools.call_tool が利用できません"
        )


try:
    # TrustLog への append
    from veritas_os.logging.trust_log import append_trust_event
except Exception:  # pragma: no cover
    def append_trust_event(event: Dict[str, Any]) -> None:
        # 何もしないダミー（本番では veritas_os.logging.trust_log を使う）
        return


try:
    import yaml  # ポリシーファイル用
except Exception:  # pragma: no cover
    # PyYAML が無い場合は None。_load_policy が自動で DEFAULT にフォールバックする。
    yaml = None  # type: ignore


# =========================================================
# しきい値 & 簡易ヒューリスティック（フォールバック用）
# =========================================================
DEFAULT_MIN_EVIDENCE = 1
MAX_UNCERTAINTY = 0.60

# 危険・違法系の簡易ワード（Safety Head が落ちた時の fallback 用）
BANNED_KEYWORDS = {
    "harm", "kill", "exploit", "illegal", "weapon", "malware", "bomb", "doxx",
    "毒", "殺", "爆弾", "銃", "兵器", "ハッキング", "違法",
}
SENSITIVE_KEYWORDS = {
    "bio", "pathogen", "drug synthesis", "zero-day", "bypass", "unlock jail",
    "生物兵器", "毒物合成", "ゼロデイ", "脱獄", "暗号回避",
}

# ざっくり PII 検出（fallback 用）
_RE_PHONE  = re.compile(r'(0\d{1,4}[-―‐ｰ–—]?\d{1,4}[-―‐ｰ–—]?\d{3,4})')
_RE_EMAIL  = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')
_RE_ADDRJP = re.compile(r'(東京都|道府県|市|区|町|村).{0,20}\d')
# 人名っぽい漢字 2〜4 文字だが、日本語文では誤検出だらけになるので PII 判定には使わない
_RE_NAMEJP = re.compile(r'[\u4e00-\u9fff]{2,4}')


# =========================================================
# データ構造
# =========================================================
@dataclass
class SafetyHeadResult:
    risk_score: float
    categories: List[str]
    rationale: str
    model: str
    raw: Dict[str, Any]


# =========================================================
# ユーティリティ
# =========================================================
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def _to_text(x: Any) -> str:
    if x is None:
        return ""
    if isinstance(x, str):
        return x
    if isinstance(x, dict):
        for k in ("query", "title", "description", "text", "prompt"):
            v = x.get(k)
            if isinstance(v, str) and v:
                return v
    return str(x)


def _normalize_text(s: str) -> str:
    return (s or "").replace("　", " ").strip().lower()


def _policy_path() -> Path:
    """
    FUJI ポリシーファイルのパスを決定。
    - 環境変数 VERITAS_FUJI_POLICY が設定されていればそれを優先（相対パスはプロジェクトルート基準）
    - なければ <veritas_os>/policies/fuji_default.yaml
    """
    env_path = os.getenv("VERITAS_FUJI_POLICY")
    core_dir = Path(__file__).resolve().parent      # .../core
    root_dir = core_dir.parent                      # .../veritas_os

    if env_path:
        p = Path(env_path)
        if not p.is_absolute():
            p = root_dir / p
        return p

    return root_dir / "policies" / "fuji_default.yaml"


# ---------------------------------------------------------
# デフォルトポリシー（YAML がなくても動く）
# ---------------------------------------------------------
_DEFAULT_POLICY: Dict[str, Any] = {
    "version": "fuji_v2_default",
    "base_thresholds": {
        "default": 0.50,
        "high_stakes": 0.35,
        "low_stakes": 0.70,
    },
    "categories": {
        "PII": {
            "max_risk_allow": 0.20,
            "action_on_exceed": "human_review",
        },
        "self_harm": {
            "max_risk_allow": 0.05,
            "action_on_exceed": "deny",
        },
        "illicit": {
            "max_risk_allow": 0.10,
            "action_on_exceed": "deny",
        },
        "violence": {
            "max_risk_allow": 0.20,
            "action_on_exceed": "human_review",
        },
        "minors": {
            "max_risk_allow": 0.15,
            "action_on_exceed": "human_review",
        },
        "safety_head_error": {
            "max_risk_allow": 0.00,
            "action_on_exceed": "human_review",
        },
    },
    "actions": {
        "allow": {
            "risk_upper": 0.40,
        },
        "warn": {
            "risk_upper": 0.65,
        },
        "human_review": {
            "risk_upper": 0.85,
        },
        "deny": {
            "risk_upper": 1.00,
        },
    },
}


def _load_policy(path: Path | None) -> Dict[str, Any]:
    """
    FUJI ポリシーを YAML からロード。
    - 読み込みに失敗 / ファイルなし / PyYAMLなし の場合は _DEFAULT_POLICY を返す。
    - ここではログを出さず、静かにフォールバックする（上位で必要なら meta で確認）。
    """
    if yaml is None:
        return dict(_DEFAULT_POLICY)

    if path is None or not path.exists():
        return dict(_DEFAULT_POLICY)

    try:
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception:
        return dict(_DEFAULT_POLICY)

    if "version" not in data:
        data["version"] = f"fuji_file_{path.name}"

    return data


# グローバルに一度ロードして使い回し
_POLICY_PATH = _policy_path()
POLICY: Dict[str, Any] = _load_policy(_POLICY_PATH)


def reload_policy() -> Dict[str, Any]:
    """ポリシーファイルを再読込したい場合に使用（テスト用など）。"""
    global POLICY
    POLICY = _load_policy(_policy_path())
    return POLICY


# =========================================================
# 1) Safety Head（LLM もしくは fallback）
# =========================================================
def _fallback_safety_head(text: str) -> SafetyHeadResult:
    """
    env tool が使えない場合の簡易 fallback:
    - 危険キーワード / PII を簡易検査して risk / categories を推定。
    - 日本語文全体が「name_like」と誤検出されないように、
      人名パターン（_RE_NAMEJP）は PII 判定には使わない。
    """
    t = _normalize_text(text)
    categories: List[str] = []
    risk = 0.05
    rationale_parts: List[str] = []

    # ---------- 危険・違法系キーワード ----------
    hits = [w for w in BANNED_KEYWORDS if w in t] + [
        w for w in SENSITIVE_KEYWORDS if w in t
    ]
    if hits:
        categories.append("illicit")
        risk = max(risk, 0.8)
        rationale_parts.append(
            f"危険・違法系キーワード検出: {', '.join(sorted(set(hits)))}"
        )

    # ---------- PII（電話・メール・住所のみ） ----------
    pii_hits: List[str] = []
    if _RE_PHONE.search(text):
        pii_hits.append("phone")
    if _RE_EMAIL.search(text):
        pii_hits.append("email")
    if _RE_ADDRJP.search(text):
        pii_hits.append("address")

    # ※ _RE_NAMEJP（漢字2〜4文字）は、日本語文だと誤検出だらけになるので
    #    ここでは PII 判定に使わない。
    # if _RE_NAMEJP.search(text):
    #     pii_hits.append("name_like")

    if pii_hits:
        categories.append("PII")
        # PII のみなら中くらいのリスクにとどめる
        risk = max(risk, 0.35)
        rationale_parts.append(f"PII パターン検出: {', '.join(pii_hits)}")

    # ---------- 何もヒットしなかった場合 ----------
    if not categories:
        rationale_parts.append(
            "特段の危険キーワードや PII パターンは検出されませんでした。"
        )

    return SafetyHeadResult(
        risk_score=min(1.0, risk),
        categories=sorted(set(categories)),
        rationale=" / ".join(rationale_parts),
        model="heuristic_fallback",
        raw={
            "fallback": True,
            "hits": hits,
            "pii_hits": pii_hits,
        },
    )


def run_safety_head(
    text: str,
    context: Dict[str, Any] | None = None,
    alternatives: List[Dict[str, Any]] | None = None,
) -> SafetyHeadResult:
    """
    LLM もしくは専用 safety モデルを env_tool 経由で呼び出す。
    """
    ctx = context or {}

    try:
        res = call_tool(
            "llm_safety",
            text=text,
            context=ctx,
            alternatives=alternatives or [],
            max_categories=5,
        )

        if not isinstance(res, dict) or not res.get("ok"):
            raise RuntimeError(res.get("error") or "llm_safety returned ok=False")

        risk = _safe_float(res.get("risk_score"), 0.05)
        cats = res.get("categories") or []
        rat = res.get("rationale") or ""
        model = res.get("model") or "llm_safety_unknown"

        return SafetyHeadResult(
            risk_score=max(0.0, min(1.0, risk)),
            categories=[str(c) for c in cats],
            rationale=str(rat),
            model=str(model),
            raw=res,
        )

    except Exception as e:
        fb = _fallback_safety_head(text)
        fb.categories.append("safety_head_error")
        fb.rationale += f" / safety_head error: {repr(e)[:120]}"
        fb.raw.setdefault("safety_head_error", repr(e))
        return fb


# =========================================================
# 2) Policy Engine（監査可能ルール）
# =========================================================
def _apply_policy(
    *,
    risk: float,
    categories: List[str],
    stakes: float,
    telos_score: float,
    policy: Dict[str, Any],
) -> Dict[str, Any]:
    """
    risk / categories / stakes / telos_score と policy 設定から、
      status / decision_status / reasons / violations / risk / policy_version
    を決定する。

    互換性のため:
    - violations        : str（カテゴリ名）のリスト  ← 旧 pipeline 用
    - violation_details : dict のリスト              ← 新しい詳細情報はこちら
    """
    base = policy.get("base_thresholds") or {}

    if stakes >= 0.7:
        base_thr = _safe_float(base.get("high_stakes", base.get("default", 0.5)), 0.5)
    elif stakes <= 0.3:
        base_thr = _safe_float(base.get("low_stakes", base.get("default", 0.5)), 0.5)
    else:
        base_thr = _safe_float(base.get("default", 0.5), 0.5)

    cat_cfg = policy.get("categories") or {}
    actions = policy.get("actions") or {}

    # ここは「詳細」用
    violation_details: List[Dict[str, Any]] = []

    # カテゴリごとの違反チェック
    for c in categories:
        cfg = cat_cfg.get(str(c))
        if not cfg:
            continue
        max_allow = cfg.get("max_risk_allow")
        if max_allow is not None and risk > float(max_allow):
            violation_details.append(
                {
                    "category": str(c),
                    "max_risk_allow": float(max_allow),
                    "action_on_exceed": cfg.get("action_on_exceed", "human_review"),
                }
            )

    # カテゴリ違反がある場合は、そのアクションを「最も厳しいもの」に寄せる
    precedence = {"deny": 3, "human_review": 2, "warn": 1, "allow": 0}
    final_action = "allow"

    if violation_details:
        best = "allow"
        for v in violation_details:
            act = str(v.get("action_on_exceed", "human_review"))
            if precedence.get(act, 0) > precedence.get(best, 0):
                best = act
        final_action = best
    else:
        # 違反なしの場合は risk × actions で決定
        def _act_key(item: Any) -> float:
            _, conf = item
            return float(conf.get("risk_upper", 1.0))

        for act, conf in sorted(actions.items(), key=_act_key):
            upper = float(conf.get("risk_upper", 1.0))
            if risk <= upper:
                final_action = act
                break

    if final_action == "allow":
        status = "allow"
        decision_status = "allow"
    elif final_action == "warn":
        status = "allow_with_warning"
        decision_status = "allow"
    elif final_action == "human_review":
        status = "needs_human_review"
        decision_status = "hold"
    else:
        status = "deny"
        decision_status = "deny"

    reasons: List[str] = [
        f"policy_action={final_action},risk={risk:.3f},stakes={stakes:.2f},base_thr={base_thr:.2f}"
    ]
    if violation_details:
        reasons.append(
            "category_violations="
            + ",".join(
                sorted(
                    {v["category"] for v in violation_details if "category" in v}
                )
            )
        )

    # 旧 pipeline 互換用に「カテゴリ名だけ」のリストも出す
    violation_categories = sorted(
        {v["category"] for v in violation_details if "category" in v}
    )

    return {
        "status": status,
        "decision_status": decision_status,
        "reasons": reasons,
        "violations": violation_categories,      # ← ここは str のリスト
        "violation_details": violation_details,  # ← 詳細はこちら
        "risk": float(risk),
        "policy_version": policy.get("version", "fuji_v2_unknown"),
    }


# =========================================================
# 3) FUJI Gate 本体
# =========================================================
def fuji_gate(
    text: str,
    *,
    context: Dict[str, Any] | None = None,
    evidence: List[Dict[str, Any]] | None = None,
    alternatives: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    """
    単一テキスト（query 等）に対して、
      Safety Head → Policy Engine → TrustLog
    を通した最終ゲート判定を行う。
    """
    ctx = context or {}
    ev = evidence or []
    alts = alternatives or []

    stakes = _safe_float(ctx.get("stakes", 0.5), 0.5)
    telos_score = _safe_float(ctx.get("telos_score", ctx.get("value_ema", 0.5)), 0.5)
    safe_applied = bool(ctx.get("fuji_safe_applied") or ctx.get("pii_already_masked"))

    # ---------- 1) Safety Head ----------
    t0 = time.time()
    sh = run_safety_head(text, ctx, alts)
    latency_ms = int((time.time() - t0) * 1000)

    categories = list(sh.categories)
    risk = float(sh.risk_score)
    base_reasons: List[str] = []

    # --- heuristic_fallback の「name_like だけ PII」誤検出をここで潰す ---
    if sh.model == "heuristic_fallback":
        raw = sh.raw or {}
        pii_hits = raw.get("pii_hits") or []
        rationale_lower = (sh.rationale or "").lower()

        is_name_like_only = False

        # 1) pii_hits があるが phone/email/address が含まれないケース
        if pii_hits:
            safe_hits = [h for h in pii_hits if h in ("phone", "email", "address")]
            if not safe_hits:
                is_name_like_only = True

        # 2) それでも検出できない場合は rationale 文字列で "name_like" を見る
        if "name_like" in rationale_lower and not any(
            k in rationale_lower for k in ("phone", "email", "address", "電話", "メール", "住所")
        ):
            is_name_like_only = True

        if is_name_like_only and any(str(c).upper() == "PII" for c in categories):
            categories = [c for c in categories if str(c).upper() != "PII"]
            risk = max(risk, 0.05)
            risk = min(risk, 0.20)
            base_reasons.append("fallback_pii_ignored(name_like_only)")

            # ★ ここを追加
            sh.rationale = (
                "日本語テキスト中の人名らしき表現（name_like）は、"
                "この環境では PII として扱わないポリシーにより無視されました。"
            )

    if safe_applied:
        filtered = [c for c in categories if str(c).lower() not in ("pii", "pii_exposure")]
        if len(filtered) < len(categories):
            categories = filtered
            risk = min(risk, 0.40)
            base_reasons.append("pii_safe_applied")

    if len(ev) < DEFAULT_MIN_EVIDENCE:
        categories.append("low_evidence")
        risk = min(1.0, risk + 0.10)
        base_reasons.append(f"low_evidence({len(ev)}/{DEFAULT_MIN_EVIDENCE})")

    # telos_score による軽いスケーリング
    risk *= (1.0 + 0.10 * max(0.0, min(1.0, telos_score)))
    risk = min(1.0, max(0.0, risk))

    # ---------- 2) Policy Engine ----------
    policy = POLICY
    pol_res = _apply_policy(
        risk=risk,
        categories=categories,
        stakes=stakes,
        telos_score=telos_score,
        policy=policy,
    )

    status = pol_res["status"]
    decision_status = pol_res["decision_status"]
    violations = pol_res.get("violations", [])                # str のリスト
    violation_details = pol_res.get("violation_details", [])  # dict のリスト
    final_risk = pol_res["risk"]
    reasons = base_reasons + pol_res["reasons"]

    guidance = sh.rationale or ""
    if "low_evidence" in categories:
        guidance += (
            "\n\n補足: エビデンスが不足している可能性があります。"
            "出典や前提条件を明示すると、より安定した判断ができます。"
        )

    # ---------- 3) TrustLog への記録 ----------
    try:
        event = {
            "ts": _now_iso(),
            "event": "fuji_evaluate",
            "text_preview": text[:200],
            "risk_score": float(sh.risk_score),
            "risk_after_policy": float(final_risk),
            "categories": list(sh.categories),
            "categories_effective": categories,
            "stakes": stakes,
            "telos_score": telos_score,
            "status": status,
            "decision_status": decision_status,
            "policy_version": pol_res.get("policy_version"),
            "safe_applied": safe_applied,
            "latency_ms": latency_ms,
            "safety_head_model": sh.model,
            "violation_details": violation_details,
        }
        append_trust_event(event)
    except Exception as e:  # pragma: no cover
        reasons.append(f"trustlog_error:{repr(e)[:80]}")

    checks = [
        {
            "kind": "safety_head",
            "model": sh.model,
            "risk_score": sh.risk_score,
            "categories": sh.categories,
            "latency_ms": latency_ms,
        },
        {
            "kind": "policy_engine",
            "policy_version": pol_res.get("policy_version"),
        },
    ]

    return {
        "status": status,
        "decision_status": decision_status,
        "rejection_reason": None if status != "deny" else "policy_deny",
        "reasons": reasons,
        "violations": violations,
        "risk": round(float(final_risk), 3),
        "checks": checks,
        "guidance": guidance or None,
        "modifications": [],
        "redactions": [],
        "safe_instructions": [],
        "meta": {
            "policy_version": pol_res.get("policy_version"),
            "safety_head_model": sh.model,
            "safe_applied": safe_applied,
        },
    }


# =========================================================
# 4) 旧 API 互換ラッパ
# =========================================================
def validate_action(action_text: Any, context: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """
    v1 互換の簡易ラッパ。
    - 旧コードが validate_action を呼んでいても落ちないようにする。
    """
    res = fuji_gate(text=_to_text(action_text), context=context or {})
    st = res.get("status")

    if st == "allow":
        status = "ok"
    elif st == "deny":
        status = "rejected"
    else:
        status = "modify"

    return {
        "status": status,
        "reasons": res.get("reasons", []),
        "violations": res.get("violations", []),
        "risk": res.get("risk", 0.0),
        "modifications": [],
        "redactions": [],
        "safe_instructions": res.get("guidance") or "",
    }


def posthoc_check(
    decision: Dict[str, Any],
    evidence: List[Dict[str, Any]] | None = None,
    *,
    min_evidence: int = DEFAULT_MIN_EVIDENCE,
    max_uncertainty: float = MAX_UNCERTAINTY,
) -> Dict[str, Any]:
    """
    v1 互換のダミー実装。
    - いまは FUJI v2 に統合されているので、minimum な flag 判定のみ行う。
    """
    ev = evidence or []
    status = "ok"
    reasons: List[str] = []
    violations: List[str] = []
    violation_details: List[Dict[str, Any]] = []
    risk = 0.0

    chosen = (decision or {}).get("chosen") or {}
    unc = _safe_float(chosen.get("uncertainty", 0.0), 0.0)

    if unc >= max_uncertainty:
        status = "flag"
        reasons.append(f"high_uncertainty({unc:.2f})")
        risk = max(risk, 0.2)

    if len(ev) < int(min_evidence):
        status = "flag"
        reasons.append(f"insufficient_evidence({len(ev)}/{min_evidence})")
        risk = max(risk, 0.2)

    return {
        "status": status,
        "reasons": reasons,
        "violations": violations,
        "violation_details": violation_details,
        "risk": risk,
    }


# =========================================================
# 5) evaluate ラッパ（旧/新インターフェイス互換）
# =========================================================
def evaluate(
    decision_or_query: Any,
    context: Dict[str, Any] | None = None,
    evidence: List[Dict[str, Any]] | None = None,
    alternatives: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    """
    使い勝手ラッパ。

    1) dict が渡された場合（新仕様）:
        decision_snapshot を想定して、そこから query/context/evidence/alternatives を拾う。

    2) 文字列が渡された場合（旧仕様）:
        fuji.evaluate(query, context=..., evidence=..., alternatives=...)
    """
    if isinstance(decision_or_query, dict):
        dec = decision_or_query
        base_ctx = dec.get("context") or {}
        ctx = {**base_ctx, **(context or {})}

        q_text = dec.get("query")
        if not q_text:
            chosen = dec.get("chosen") or {}
            q_text = (
                chosen.get("query")
                or chosen.get("title")
                or chosen.get("description")
                or ""
            )

        alts = dec.get("alternatives") or dec.get("options") or alternatives or []
        ev = dec.get("evidence") or evidence or []

        res = fuji_gate(
            text=_to_text(q_text),
            context=ctx,
            evidence=ev,
            alternatives=alts,
        )
        if dec.get("request_id"):
            res.setdefault("decision_id", dec.get("request_id"))
        return res

    query_str = _to_text(decision_or_query)
    return fuji_gate(
        text=query_str,
        context=context or {},
        evidence=evidence or [],
        alternatives=alternatives or [],
    )


__all__ = [
    "DEFAULT_MIN_EVIDENCE",
    "MAX_UNCERTAINTY",
    "SafetyHeadResult",
    "run_safety_head",
    "fuji_gate",
    "evaluate",
    "validate_action",
    "posthoc_check",
    "reload_policy",
]

