# veritas_os/core/fuji.py
# -*- coding: utf-8 -*-
"""
FUJI Gate (安全・法・倫理ゲート)
- validate_action : 単体テキストの即時チェック（ok / modify / rejected）
- posthoc_check   : 決定＋証拠の健全性チェック（ok / flag / rejected）
- fuji_gate       : 最終ゲート判定（allow / modify / rejected）＋監査情報
- evaluate        : 使い勝手用ラッパ

重要なポイント:
- context["fuji_safe_applied"] == True の場合は、
  「PII 由来の modify / pii_* 理由」を無効化して allow 扱いにする。
"""

from __future__ import annotations
from typing import List, Dict, Any
import re
import os

# =========================
# 設定（しきい値・語彙）
# =========================
DEFAULT_MIN_EVIDENCE = 1
MAX_UNCERTAINTY = 0.60

BANNED_KEYWORDS = {
    "harm", "kill", "exploit", "illegal", "weapon", "malware", "bomb", "doxx",
    "毒", "殺", "爆弾", "銃", "兵器", "ハッキング", "違法"
}
SENSITIVE = {
    "bio", "pathogen", "drug synthesis", "zero-day", "bypass", "unlock jail",
    "生物兵器", "毒物合成", "ゼロデイ", "脱獄", "暗号回避"
}

# ざっくりPII検出（最低限）
_RE_PHONE  = re.compile(r'(0\d{1,4}[-―‐ｰ–—]?\d{1,4}[-―‐ｰ–—]?\d{3,4})')
_RE_EMAIL  = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')
_RE_ADDRJP = re.compile(r'(東京都|道府県|市|区|町|村).{0,20}\d')
_RE_NAMEJP = re.compile(r'[\u4e00-\u9fff]{2,4}')  # 人名っぽい漢字2〜4文字

# =========================
# ユーティリティ
# =========================
def _normalize_text(s: str) -> str:
    return (s or "").replace("　", " ").strip().lower()

def _to_text(x: Any) -> str:
    if x is None:
        return ""
    if isinstance(x, str):
        return x
    if isinstance(x, dict):
        for k in ("title", "description", "text", "prompt"):
            v = x.get(k)
            if isinstance(v, str) and v:
                return v
    return str(x)

def _is_masked_query(s: str) -> bool:
    """伏せ字が入っていれば True（安全化済み判定の一助）"""
    t = _to_text(s)
    return ("●" in t) or ("〇" in t) or ("[pii]" in t.lower()) or ("[redacted]" in t.lower())

def _filter_out_pii(reasons: List[str], violations: List[str]) -> tuple[list[str], list[str]]:
    """PII 由来の理由・違反を取り除く"""
    r = [x for x in reasons    if not x.startswith("pii_")]
    v = [x for x in violations if not x.startswith("pii")]
    return r, v

# =========================
# 1) 事前チェック（単体）
# =========================
def validate_action(action_text: Any, context: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """
    単体テキストに対する即時チェック。
    戻り値: {
      "status": "ok" | "modify" | "rejected",
      "reasons":[], "violations":[], "risk":float,
      "modifications":[], "redactions":[], "safe_instructions":[]
    }
    """
    raw = _to_text(action_text)
    t = _normalize_text(raw)
    ctx = context or {}

    # テスト用：環境変数で強制 modify
    if os.getenv("VERITAS_FORCE_MODIFY", "").strip() == "1":
        return {
            "status": "modify",
            "reasons": ["forced_by_env"],
            "violations": [],
            "risk": 0.15,
            "modifications": ["mask_pii"],
            "redactions": ["個人名", "住所", "電話", "メール"],
            "safe_instructions": ["氏名・住所・電話・メールは ● で伏せ字にしてください。"]
        }

    status = "ok"
    reasons: List[str] = []
    violations: List[str] = []
    risk = 0.05
    modifications: List[str] = []
    redactions: List[str] = []
    safe_instructions: List[str] = []

    # 1) 危険・違法ワード → 即 rejected
    hits: List[str] = []
    for w in BANNED_KEYWORDS:
        if w in t:
            hits.append(w)
    for w in SENSITIVE:
        if w in t:
            hits.append(w)
    if hits:
        status = "rejected"
        reasons.append("policy_violation:keyword")
        violations.extend(sorted(set(hits)))
        risk = 0.95
        return {
            "status": status,
            "reasons": reasons,
            "violations": violations,
            "risk": risk,
            "modifications": modifications,
            "redactions": redactions,
            "safe_instructions": safe_instructions,
        }

    # 1.5) fuji_safe_applied → PII 由来 modify を完全スキップ
    # 内部ベンチや、すでに匿名化済みのテキストを扱うケースでは、
    # PII 検出ロジックは走らせずに OK 扱いにする。
    if ctx.get("fuji_safe_applied") or ctx.get("pii_already_masked"):
        return {
            "status": status,          # "ok"
            "reasons": reasons,        # []
            "violations": violations,  # []
            "risk": risk,              # 0.05
            "modifications": modifications,
            "redactions": redactions,
            "safe_instructions": safe_instructions,
        }

    # 2) PII×伏せ字意図 → modify
    intent_mask = (
        ("伏せ" in raw) or ("匿名" in raw) or ("マスク" in raw) or ("隠" in raw) or ("黒塗り" in raw)
        or ("redact" in t) or ("mask" in t) or ("anonym" in t)
    )

    if intent_mask:
        if _RE_PHONE.search(raw):  redactions.append("電話")
        if _RE_EMAIL.search(raw):  redactions.append("メール")
        if _RE_ADDRJP.search(raw): redactions.append("住所")
        # 人名は誤検出が多いので意図がある時のみ
        if _RE_NAMEJP.search(raw): redactions.append("個人名")

        if redactions:
            status = "modify"
            reasons.append("pii_redaction_required")
            violations.append("pii_exposure")
            risk = max(risk, 0.35)
            modifications.append("mask_pii")
            safe_instructions.extend([
                "氏名・住所・電話・メールなどの個人情報は ● で伏せ字にしてください。",
                "固有名詞はイニシャル化（例：山田太郎→山田●●）。"
            ])

    return {
        "status": status,
        "reasons": reasons,
        "violations": sorted(set(violations)),
        "risk": risk,
        "modifications": modifications,
        "redactions": sorted(set(redactions)),
        "safe_instructions": safe_instructions,
    }

# =========================
# 2) 事後チェック（監査）
# =========================
def posthoc_check(
    decision: Dict[str, Any],
    evidence: List[Dict[str, Any]] | None = None,
    *,
    min_evidence: int = DEFAULT_MIN_EVIDENCE,
    max_uncertainty: float = MAX_UNCERTAINTY,
) -> Dict[str, Any]:
    ev = evidence or []
    status = "ok"
    reasons: List[str] = []
    violations: List[str] = []
    risk = 0.0

    chosen = (decision or {}).get("chosen") or {}
    try:
        unc = float(chosen.get("uncertainty", 0.0) or 0.0)
    except Exception:
        unc = 0.0

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
        "risk": risk,
    }

# =========================
# 3) FUJI 最終ゲート
# =========================
def fuji_gate(
    context: Dict[str, Any] | None = None,
    query: str | Dict[str, Any] | None = None,
    alternatives: List[Dict[str, Any]] | None = None,
    evidence: List[Dict[str, Any]] | None = None,
    *,
    min_evidence: int = DEFAULT_MIN_EVIDENCE,
    max_uncertainty: float = MAX_UNCERTAINTY,
) -> Dict[str, Any]:
    """
    allow / modify / rejected を返す。modify時は redactions 等も添付。
    """
    ctx = context or {}
    q_text = _to_text(query)
    alts = alternatives or []
    ev = evidence or []

    reasons: List[str] = []
    violations: List[str] = []
    checks: List[Dict[str, Any]] = []
    risk: float = 0.0
    guidance: str | None = None

    # modify 用の集約
    wants_modify = False
    mods: List[str] = []
    reds: List[str] = []
    safe_instr: List[str] = []

    # 「安全化済み」シグナル（UIやサーバが立てる）、または伏せ字痕跡を検知
    safe_applied = bool(ctx.get("fuji_safe_applied") or ctx.get("pii_already_masked")) or _is_masked_query(q_text)

    # 3-1) クエリ
    vq = validate_action(q_text, ctx)
    checks.append({"name": "validate_action(query)", **{k: vq[k] for k in ("status", "reasons", "violations")}})
    risk = max(risk, float(vq.get("risk", 0.0)))
    reasons.extend(vq.get("reasons", []))
    violations.extend(vq.get("violations", []))
    if vq["status"] == "modify":
        wants_modify = True
        mods += vq.get("modifications", [])
        reds += vq.get("redactions", [])
        safe_instr += vq.get("safe_instructions", [])

    # 3-2) 代替案
    for a in alts:
        va = validate_action(a, ctx)
        checks.append({"name": "validate_action(alt)", **{k: va[k] for k in ("status", "reasons", "violations")}})
        risk = max(risk, float(va.get("risk", 0.0)))
        reasons.extend(va.get("reasons", []))
        violations.extend(va.get("violations", []))
        if va["status"] == "modify":
            wants_modify = True
            mods += va.get("modifications", [])
            reds += va.get("redactions", [])
            safe_instr += va.get("safe_instructions", [])

    # 3-3) 事後チェック（監査）
    ph = posthoc_check(decision={"chosen": {}}, evidence=ev,
                       min_evidence=min_evidence, max_uncertainty=max_uncertainty)
    checks.append({"name": "posthoc_check", **{k: ph[k] for k in ("status", "reasons", "violations")}})
    risk = max(risk, float(ph.get("risk", 0.0)))

    # --- 安全化後の緩和（ここがポイント）---
    if safe_applied:
        # PII 由来の “modify” 要因を除去
        reasons, violations = _filter_out_pii(reasons, violations)
        wants_modify = False
        # PII マスク系の修正要求も削除
        mods = [m for m in mods if not m.startswith("mask_pii")]
        reds = []
        safe_instr = []
        risk = min(risk, 0.35)

    # 3-4) 最終判定
    if violations and ("policy_violation" in reasons or any(r.startswith("policy_") for r in reasons)):
        decision_status = "rejected"
        rejection_reason = "policy_violation"
        risk = max(risk, 0.95)
        guidance = (
            "その依頼には対応できません。合法・安全・教育的な範囲なら、"
            "例えば『危険物の歴史的背景』や『安全規格の仕組み』の解説は可能です。"
        )
        mods, reds, safe_instr = [], [], []

    elif wants_modify:
        if safe_applied:
            # ここには基本来ない想定だが、念のため allow に昇格
            decision_status = "allow"
            rejection_reason = None
        else:
            decision_status = "modify"
            rejection_reason = None
            guidance = "個人情報を伏せ字にした上で、要約/処理を続行してください。"
    else:
        decision_status = "allow"
        rejection_reason = None
        if ph["status"] == "flag":
            guidance = (
                "根拠が不足/不確実性が高い可能性があります。"
                "出典URLや前提条件を指定すると精度が上がります。"
            )

    return {
        "status": decision_status,          # ← ここがベンチで見るフィールド
        "decision_status": decision_status, # 互換用
        "rejection_reason": rejection_reason,
        "reasons": list(dict.fromkeys(reasons)),
        "violations": sorted(set(violations)),
        "risk": round(float(risk), 3),
        "checks": checks,
        "guidance": guidance,
        # modify用フィールド（server.py が extras/gate に流用）
        "modifications": list(dict.fromkeys(mods)),
        "redactions": sorted(set(reds)),
        "safe_instructions": safe_instr,
    }

# =========================
# 4) ラッパ
# =========================
def evaluate(
    query: str,
    context: Dict[str, Any] | None = None,
    evidence: List[Dict[str, Any]] | None = None,
    alternatives: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    return fuji_gate(
        context=context or {},
        query=query,
        alternatives=alternatives or [],
        evidence=evidence or [],
        min_evidence=DEFAULT_MIN_EVIDENCE,
        max_uncertainty=MAX_UNCERTAINTY,
    )

__all__ = [
    "DEFAULT_MIN_EVIDENCE", "MAX_UNCERTAINTY",
    "validate_action", "posthoc_check", "fuji_gate", "evaluate"
]

