# veritas_os/core/fuji.py
# -*- coding: utf-8 -*-
"""
FUJI Gate v2 (Safety Head × Policy Engine × TrustLog)

Public contract:
- ``fuji_gate()`` and the v1-compatible validation helpers provide the stable
  policy/safety gate consumed by Kernel and API layers.
- This module coordinates final gate decisions and audit-facing status only;
  detailed policy loading and safety-head behavior belong in helper modules.

Preferred extension points:
- ``fuji_policy.py`` / ``fuji_policy_rollout.py`` for policy loading and rollout
- ``fuji_helpers.py`` for normalization and compatibility helpers
- ``fuji_safety_head.py`` for deterministic / LLM safety-head behavior

Compatibility guidance:
- This file still contains compatibility shims for older validation paths.
  Preserve those adapters, but add new fallback, rollout, or safety logic to
  the helper modules above so FUJI responsibility does not sprawl further.

PoC仕様：
- low_evidence のときは allow に倒さず、必ず「補う/止める」へ寄せる
  - 高リスク/高ステークス => deny
  - それ以外              => needs_human_review
- low_evidence のときは必ず followups（追加調査アクション）を返す

重要（矛盾を100%潰すための不変条件）:
- status は内部状態: allow | allow_with_warning | needs_human_review | deny
- decision_status は外部API向け: allow | hold | deny
- status == "deny"              => decision_status == "deny" かつ rejection_reason != None
- decision_status == "deny"     => rejection_reason != None
- decision_status != "deny"     => rejection_reason == None
- validate_action（v1互換）では deny => rejected へマッピングする
- validate_action（pre-check）では evidence が無いことが多いので、
  デフォルトで low_evidence を強制しない（= enforce_low_evidence は evidence が渡された時のみON）

Safety / Policy / TrustLog は監査可能な形で残す。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence
from pathlib import Path
import logging
import math
import threading
import time
import os
import re

_logger = logging.getLogger(__name__)

# =========================================================
# リスク閾値定数（FujiConfig で一元管理）
# =========================================================
RISK_BASELINE = 0.05  # 安全テキストのベースラインリスク
RISK_FLOOR_PII = 0.35  # PII 検出時の最低リスク
RISK_FLOOR_PII_UNMASKED = 0.50  # PII 未マスク時の最低リスク
RISK_FLOOR_ILLICIT = 0.70  # illicit 検出時の最低リスク (deny 閾値)
RISK_FLOOR_ILLICIT_HEURISTIC = 0.80  # illicit キーワードヒューリスティクス検出時
RISK_FLOOR_SELF_HARM = 0.80  # self_harm 検出時の最低リスク
RISK_FLOOR_FLAG = 0.20  # uncertainty/evidence 不足時のフラグリスク
RISK_DENY_THRESHOLD = 0.70  # deny 判定の閾値

from .types import (
    FujiInternalStatus,
    FujiDecisionStatus,
    FujiV1Status,
    FujiViolation,
    FujiFollowup,
    FujiDecisionDict,
    FujiV1Result,
    SafetyHeadResultDict,
    EvidenceDict,
    ISOTimestamp,
)
from .utils import _safe_float, _to_text
from .fuji_codes import build_fuji_rejection
from .fuji_injection import _detect_prompt_injection as _detect_prompt_injection_impl
from .fuji_helpers import (
    build_followups,
    ctx_bool,
    is_high_risk_context,
    normalize_injection_text,
    normalize_text,
    now_iso,
    redact_text_for_trust_log,
    resolve_trust_log_id,
    safe_nonneg_int,
    select_fuji_code,
)
from . import fuji_policy as _fuji_policy
from .fuji_policy import (
    POLICY,
    BANNED_KEYWORDS_FALLBACK,
    RISKY_KEYWORDS_POC,
    SENSITIVE_KEYWORDS_FALLBACK,
    _DEFAULT_POLICY,
    _PII_RE,
    _STRICT_DENY_POLICY,
    _apply_policy,
    _build_runtime_patterns_from_policy,
    _policy_blocked_keywords,
    _policy_path,
    _strict_policy_load_enabled,
)
from .config import capability_cfg, emit_capability_manifest
from veritas_os.logging.trust_log import append_trust_event as _append_trust_event
from veritas_os.tools import call_tool as _call_tool

_FUJI_YAML_EXPLICITLY_ENABLED = os.getenv("VERITAS_CAP_FUJI_YAML_POLICY") in {
    "1",
    "true",
    "TRUE",
    "yes",
    "on",
}

if capability_cfg.enable_fuji_yaml_policy:
    try:
        import yaml  # type: ignore
    except (ImportError, ModuleNotFoundError) as exc:  # pragma: no cover
        if _FUJI_YAML_EXPLICITLY_ENABLED:
            raise RuntimeError(
                "YAML policy is enabled by VERITAS_CAP_FUJI_YAML_POLICY=1, "
                "but PyYAML is not installed"
            ) from exc
        _logger.warning(
            "[CONFIG_MISMATCH] PyYAML is unavailable while YAML policy default is "
            "enabled; falling back to built-in policy. To enforce strict mode, "
            "set VERITAS_CAP_FUJI_YAML_POLICY=1 explicitly."
        )
        yaml = None
else:  # pragma: no cover - explicit capability-off path
    yaml = getattr(_fuji_policy, "yaml", None)


_POLICY_MTIME = getattr(_fuji_policy, "_POLICY_MTIME", 0.0)


def call_tool(kind: str, **kwargs: Any) -> Dict[str, Any]:
    """Call external tool bridge only when explicitly enabled by capability flag."""
    if not capability_cfg.enable_fuji_tool_bridge:
        raise RuntimeError(
            "fuji tool bridge is disabled by VERITAS_CAP_FUJI_TOOL_BRIDGE"
        )
    return _call_tool(kind, **kwargs)


def append_trust_event(event: Dict[str, Any]) -> None:
    """Append trust events only when explicitly enabled by capability flag."""
    if not capability_cfg.enable_fuji_trust_log:
        return
    _append_trust_event(event)


# =========================================================
# しきい値 & 簡易ヒューリスティック（フォールバック用）
# ★ リファクタリング: config.fuji_cfg から設定を取得
# =========================================================
try:
    from .config import fuji_cfg as _fuji_cfg
    DEFAULT_MIN_EVIDENCE = _fuji_cfg.default_min_evidence
    MAX_UNCERTAINTY = _fuji_cfg.max_uncertainty
    _ENV_POC_MODE = _fuji_cfg.poc_mode
except (ImportError, ModuleNotFoundError, AttributeError, TypeError, ValueError) as _cfg_err:
    # フォールバック: config が壊れていてもfuji.pyは動作する
    _logger.warning("Failed to load fuji_cfg, using defaults: %s", _cfg_err)
    DEFAULT_MIN_EVIDENCE = 1
    MAX_UNCERTAINTY = 0.60
    _ENV_POC_MODE = os.getenv("VERITAS_POC_MODE", "0") == "1"

# よく使われる同形異体文字（Cyrillic / Greek）の最小マップ。
# すべてを網羅するものではないが、悪用されやすい文字を優先的に吸収する。
if capability_cfg.emit_manifest_on_import:
    emit_capability_manifest(
        component="fuji",
        manifest={
            "tool_bridge": capability_cfg.enable_fuji_tool_bridge,
            "trust_log": capability_cfg.enable_fuji_trust_log,
            "yaml_policy": capability_cfg.enable_fuji_yaml_policy,
        },
    )

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
_now_iso = now_iso
_safe_nonneg_int = safe_nonneg_int


# _to_text は utils.py から統合インポート済み


_normalize_text = normalize_text
_resolve_trust_log_id = resolve_trust_log_id


_ctx_bool = ctx_bool
_is_high_risk_context = is_high_risk_context
_build_followups = build_followups
_redact_text_for_trust_log = redact_text_for_trust_log
_select_fuji_code = select_fuji_code
_normalize_injection_text = normalize_injection_text


def _detect_prompt_injection(text: str) -> Dict[str, Any]:
    """Detect prompt-injection signals via the shared injection helper."""
    return _detect_prompt_injection_impl(text)


def _sync_fuji_policy_runtime() -> None:
    """Keep shared policy helpers aligned with fuji.py capability aliases."""
    _fuji_policy.yaml = yaml
    _fuji_policy.capability_cfg = capability_cfg


def _fallback_policy(
    *,
    path: Path | None,
    reason: str,
    exc: Exception | None = None,
) -> Dict[str, Any]:
    """Delegate fallback-policy handling to fuji_policy helpers."""
    _sync_fuji_policy_runtime()
    return _fuji_policy._fallback_policy(path=path, reason=reason, exc=exc)



def _load_policy(path: Path | None) -> Dict[str, Any]:
    """Backward-compatible FUJI policy loader via the shared policy module."""
    _sync_fuji_policy_runtime()
    return _fuji_policy._load_policy(path)



def _load_policy_from_str(content: str, path: Path) -> Dict[str, Any]:
    """Parse FUJI policy content via the shared policy module."""
    _sync_fuji_policy_runtime()
    return _fuji_policy._load_policy_from_str(content, path)



def reload_policy() -> Dict[str, Any]:
    """Reload the shared FUJI policy state and keep module aliases synchronized."""
    global POLICY, _POLICY_MTIME
    _sync_fuji_policy_runtime()
    POLICY = _fuji_policy.reload_policy()
    _POLICY_MTIME = getattr(_fuji_policy, "_POLICY_MTIME", _POLICY_MTIME)
    return POLICY



def _check_policy_hot_reload() -> None:
    """Delegate FUJI policy hot reload to the shared policy helper."""
    global POLICY, _POLICY_MTIME
    _sync_fuji_policy_runtime()
    _fuji_policy._check_policy_hot_reload()
    POLICY = _fuji_policy.POLICY
    _POLICY_MTIME = getattr(_fuji_policy, "_POLICY_MTIME", _POLICY_MTIME)


# =========================================================
# 1) Safety Head（LLM もしくは fallback）
# =========================================================
def _fallback_safety_head(text: str) -> SafetyHeadResult:
    t = _normalize_text(text)
    categories: List[str] = []
    risk = RISK_BASELINE
    rationale_parts: List[str] = []

    hard_block, sensitive = _policy_blocked_keywords(POLICY)
    hits = [w for w in hard_block if w in t] + [w for w in sensitive if w in t]
    if hits:
        categories.append("illicit")
        risk = max(risk, RISK_FLOOR_ILLICIT_HEURISTIC)
        rationale_parts.append(f"危険・違法系キーワード検出: {', '.join(sorted(set(hits)))}")

    pii_hits: List[str] = []
    if _PII_RE["phone"].search(text):
        pii_hits.append("phone")
    if _PII_RE["email"].search(text):
        pii_hits.append("email")
    if _PII_RE["address_jp"].search(text):
        pii_hits.append("address")

    # person_name_jp は誤検出が多いので PII 判定に使わない
    if pii_hits:
        categories.append("PII")
        risk = max(risk, RISK_FLOOR_PII)
        rationale_parts.append(f"PII パターン検出: {', '.join(pii_hits)}")

    if not categories:
        rationale_parts.append("特段の危険キーワードや PII パターンは検出されませんでした。")

    return SafetyHeadResult(
        risk_score=min(1.0, risk),
        categories=sorted(set(categories)),
        rationale=" / ".join(rationale_parts),
        model="heuristic_fallback",
        raw={"fallback": True, "hits": hits, "pii_hits": pii_hits},
    )


def _apply_llm_fallback_penalty(
    result: "SafetyHeadResult",
    ctx: Dict[str, Any],
    *,
    label: str = "LLM unavailable",
) -> None:
    """Apply risk floor penalty when LLM safety head is unavailable.

    セキュリティ監査 F-03/F-04 対応:
    - deterministic layer がリスクありと判定した場合 → stakes に応じたリスクフロア
    - リスク検出なし → 不確実性ベースライン 0.30
    """
    _has_risk_cats = any(
        c for c in result.categories
        if c not in ("safety_head_error",)
    )
    stakes = _safe_float(ctx.get("stakes", 0.5), 0.5)
    if _has_risk_cats:
        if stakes >= 0.7:
            result.risk_score = max(result.risk_score, 0.70)
            result.rationale += f" / [deterministic_layer] {label} + high stakes → risk floor 0.70"
        else:
            result.risk_score = max(result.risk_score, 0.50)
            result.rationale += f" / [deterministic_layer] {label} → risk floor 0.50"
    else:
        result.risk_score = max(result.risk_score, 0.30)
        result.rationale += f" / [deterministic_layer] {label} → baseline risk floor 0.30"


def run_safety_head(
    text: str,
    context: Dict[str, Any] | None = None,
    alternatives: List[Dict[str, Any]] | None = None,
) -> SafetyHeadResult:
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

        # セキュリティ監査 F-01 対応: LLM fallback 検出時の追加ペナルティ
        llm_fallback = bool(res.get("llm_fallback"))

        result = SafetyHeadResult(
            risk_score=max(0.0, min(1.0, risk)),
            categories=[str(c) for c in cats],
            rationale=str(rat),
            model=str(model),
            raw=res,
        )

        if llm_fallback:
            result.raw["llm_fallback"] = True
            _apply_llm_fallback_penalty(result, ctx, label="LLM unavailable")

        return result

    except (TypeError, ValueError, RuntimeError, OSError) as e:
        _logger.error(
            "[FUJI] Safety head LLM evaluation failed; falling back to heuristics: %s",
            repr(e),
            exc_info=True,
        )
        fb = _fallback_safety_head(text)
        fb.categories.append("safety_head_error")
        fb.rationale += f" / safety_head error: {repr(e)[:120]}"
        fb.raw.setdefault("safety_head_error", repr(e))
        fb.raw["llm_fallback"] = True
        _apply_llm_fallback_penalty(fb, ctx, label="LLM error")
        return fb




# =========================================================
# 3) FUJI コア判定（純粋ロジック）
# =========================================================
def fuji_core_decide(
    *,
    safety_head: SafetyHeadResult | None,
    stakes: float,
    telos_score: float,
    evidence_count: int,
    policy: Dict[str, Any] | None = None,
    safe_applied: bool = False,
    min_evidence: int = DEFAULT_MIN_EVIDENCE,
    text: str = "",
    poc_mode: bool = False,
) -> Dict[str, Any]:
    """
    ★ セキュリティ修正: 入力パラメータのnullチェック強化
    """
    policy = policy or POLICY

    # ★ safety_head が None の場合のフォールバック
    if safety_head is None:
        safety_head = _fallback_safety_head(text or "")

    # ★ 安全なアクセス: categories と risk_score
    categories = list(safety_head.categories or []) if safety_head.categories else []
    try:
        risk = float(safety_head.risk_score) if safety_head.risk_score is not None else RISK_BASELINE
        if not math.isfinite(risk):
            risk = 1.0  # fail-closed: NaN/Inf は最大リスクとして扱う
    except (TypeError, ValueError):
        risk = RISK_BASELINE
    base_reasons: List[str] = []
    guidance = safety_head.rationale or ""

    injection = _detect_prompt_injection(text)
    injection_score = float(injection.get("score", 0.0) or 0.0)
    injection_signals = list(injection.get("signals") or [])
    if injection_score > 0.0:
        categories.append("prompt_injection")
        # injection_weight: YAML risk_adjustments > hardcoded default 0.15
        _inj_weight = _safe_float(
            (policy.get("risk_adjustments") or {}).get("injection_weight"), 0.15
        )
        risk = min(1.0, risk + (_inj_weight * injection_score))
        base_reasons.append(f"prompt_injection_score={injection_score:.2f}")
        if injection_signals:
            base_reasons.append(
                "prompt_injection_signals=" + ",".join(sorted(injection_signals))
            )

    def _extract_policy_action(pol_res: Dict[str, Any], reasons: List[str]) -> str | None:
        pa = pol_res.get("policy_action")
        if isinstance(pa, str) and pa:
            return pa
        for r in reasons:
            if r.startswith("policy_action="):
                tail = r.split("=", 1)[1]
                return tail.split(",", 1)[0].strip()
        return None

    def _mark_policy_pre_and_final_gate(
        reasons: List[str],
        *,
        policy_action: str | None,
        final_gate: str,
    ) -> None:
        pre = policy_action or "unknown"

        replaced = False
        for i, r in enumerate(reasons):
            if r.startswith("policy_action="):
                reasons[i] = f"policy_action_pre_poc={pre}"
                replaced = True
                break
        if not replaced:
            reasons.append(f"policy_action_pre_poc={pre}")

        reasons.append(f"final_gate={final_gate}")

    # --- Deterministic Safety Layer: LLM非依存のリスクフロア ---
    # セキュリティ監査 2026-03-12 §3.3.1 対応:
    # deterministicルール検出時にLLMスコアに関係なく最低リスクを保証する
    _det_raw = safety_head.raw or {}
    _is_llm_fallback = bool(_det_raw.get("llm_fallback") or _det_raw.get("fallback"))
    _det_reasons: List[str] = []

    if "illicit" in categories:
        # deterministic rule で illicit 検出 → risk >= RISK_FLOOR_ILLICIT (deny 閾値到達)
        if risk < RISK_FLOOR_ILLICIT:
            risk = RISK_FLOOR_ILLICIT
            _det_reasons.append(f"deterministic_illicit_floor={RISK_FLOOR_ILLICIT}")

    if "self_harm" in categories:
        # self_harm 検出 → risk >= RISK_FLOOR_SELF_HARM
        if risk < RISK_FLOOR_SELF_HARM:
            risk = RISK_FLOOR_SELF_HARM
            _det_reasons.append(f"deterministic_self_harm_floor={RISK_FLOOR_SELF_HARM}")

    if "PII" in categories and not safe_applied:
        # PII 検出 (未マスク時) → risk >= RISK_FLOOR_PII_UNMASKED
        if risk < RISK_FLOOR_PII_UNMASKED:
            risk = RISK_FLOOR_PII_UNMASKED
            _det_reasons.append(f"deterministic_pii_floor={RISK_FLOOR_PII_UNMASKED}")

    # LLM unavailable penalty: only when deterministic layer detected risk signals
    # (categories present besides safety_head_error/low_evidence).
    # If the heuristic confirms text is clean, no penalty needed.
    _risk_categories = [c for c in categories if c not in ("safety_head_error", "low_evidence")]
    if _is_llm_fallback and _risk_categories:
        # LLM unavailable + risk signals detected → risk += 0.20 ペナルティ
        risk = min(1.0, risk + 0.20)
        _det_reasons.append("deterministic_llm_unavailable_penalty")

    if _det_reasons:
        base_reasons.extend(_det_reasons)
        guidance = (guidance or "").rstrip()
        guidance += (
            "\n\n[Deterministic Safety Layer] "
            + "; ".join(_det_reasons)
        )

    # --- heuristic_fallback の name_like-only PII を無害化（テスト要件保険） ---
    if safety_head.model == "heuristic_fallback":
        raw = safety_head.raw or {}
        pii_hits_raw = raw.get("pii_hits")

        norm_hits: List[str] = []
        if isinstance(pii_hits_raw, list):
            for h in pii_hits_raw:
                if isinstance(h, str):
                    norm_hits.append(h.strip().lower())
                elif isinstance(h, dict):
                    for k in ("kind", "type", "name"):
                        v = h.get(k)
                        if isinstance(v, str) and v.strip():
                            norm_hits.append(v.strip().lower())
                            break
        elif isinstance(pii_hits_raw, str) and pii_hits_raw.strip():
            norm_hits = [pii_hits_raw.strip().lower()]

        rationale_lower = (safety_head.rationale or "").lower()

        strong_pii_hit = any(h in ("phone", "email", "address") for h in norm_hits)
        strong_pii_text = any(
            k in rationale_lower
            for k in ("phone", "email", "address", "電話", "メール", "住所", "@")
        )

        is_name_like_only = False
        if norm_hits:
            if all(h == "name_like" for h in norm_hits) and not (strong_pii_hit or strong_pii_text):
                is_name_like_only = True
        if ("name_like" in rationale_lower) and not (strong_pii_hit or strong_pii_text):
            is_name_like_only = True

        if is_name_like_only:
            if any(str(c).upper() == "PII" for c in categories):
                categories = [c for c in categories if str(c).upper() != "PII"]
            # name_like_only_cap: YAML risk_adjustments > hardcoded default 0.20
            _name_like_cap = _safe_float(
                (policy.get("risk_adjustments") or {}).get("name_like_only_cap"), 0.20
            )
            risk = min(float(risk), _name_like_cap)
            base_reasons.append("fallback_pii_ignored(name_like_only)")
            guidance = (
                "heuristic_fallback の name_like 検出は日本語テキストで誤検出が多いため、"
                "name_like-only の場合は PII として扱わずリスクを抑制しました。"
            )

    # --- 既に PII セーフ化済みの場合の緩和 ---
    # ★ リファクタリング: env config > YAML risk_adjustments > hardcoded default
    try:
        pii_safe_cap = _fuji_cfg.pii_safe_risk_cap
    except (AttributeError, TypeError, ValueError):
        pii_safe_cap = _safe_float(
            (policy.get("risk_adjustments") or {}).get("pii_safe_cap"), 0.40
        )

    if safe_applied:
        filtered = [c for c in categories if str(c).lower() not in ("pii", "pii_exposure")]
        if len(filtered) < len(categories):
            categories = filtered
            risk = min(risk, pii_safe_cap)
            base_reasons.append("pii_safe_applied")

    # --- evidence 不足ペナルティ（テスト要件：guidance に文言を入れる） ---
    # ★ リファクタリング: env config > YAML risk_adjustments > hardcoded default
    try:
        low_ev_penalty = _fuji_cfg.low_evidence_risk_penalty
    except (AttributeError, TypeError, ValueError):
        low_ev_penalty = _safe_float(
            (policy.get("risk_adjustments") or {}).get("low_evidence_penalty"), 0.10
        )

    low_ev = evidence_count < int(min_evidence)
    if low_ev:
        categories.append("low_evidence")
        risk = min(1.0, risk + low_ev_penalty)
        base_reasons.append(f"low_evidence({evidence_count}/{min_evidence})")

        # ★ テスト期待：この文字列を guidance に含める
        add_msg = "エビデンスが不足している可能性があります"
        if add_msg not in (guidance or ""):
            guidance = (guidance or "").rstrip()
            guidance = (guidance + ("\n\n" if guidance else "") + add_msg)

    # --- telos_score による軽いスケーリング ---
    # ★ リファクタリング: env config > YAML risk_adjustments > hardcoded default
    try:
        telos_risk_scale = _fuji_cfg.telos_risk_scale_factor
    except (AttributeError, TypeError, ValueError):
        telos_risk_scale = _safe_float(
            (policy.get("risk_adjustments") or {}).get("telos_scale_factor"), 0.10
        )

    telos_clamped = max(0.0, min(1.0, telos_score))
    risk *= (1.0 + telos_risk_scale * telos_clamped)
    risk = min(1.0, max(0.0, risk))

    # --- Policy Engine 適用 ---
    pol_res = _apply_policy(
        risk=risk,
        categories=categories,
        stakes=stakes,
        telos_score=telos_score,
        policy=policy,
    )

    status = pol_res["status"]
    decision_status = pol_res["decision_status"]
    violations = pol_res.get("violations", [])
    violation_details = pol_res.get("violation_details", [])
    final_risk = float(pol_res["risk"])
    reasons = base_reasons + pol_res["reasons"]
    policy_version = pol_res.get("policy_version")

    policy_action_pre = _extract_policy_action(pol_res, reasons)

    rejection_reason: str | None = None
    followups: List[Dict[str, Any]] = []
    final_gate: str | None = None

    # -------------------------------
    # PoC強制ルール：low_evidence は allow にしない（PoCモード時）
    # -------------------------------
    if poc_mode and low_ev:
        hi = _is_high_risk_context(
            risk=final_risk,
            stakes=stakes,
            categories=list(set(list(categories) + list(safety_head.categories or []))),
            text=text,
        )

        followups = _build_followups(
            text,
            {
                "stakes": stakes,
                "telos_score": telos_score,
                "min_evidence": int(min_evidence),
                "evidence_count": int(evidence_count),
            },
        )

        if hi:
            status = "deny"
            decision_status = "deny"
            rejection_reason = "poc_low_evidence_high_risk"
            reasons.append("poc_low_evidence_high_risk -> deny")

            final_gate = "poc_low_evidence_high_risk_deny"
            _mark_policy_pre_and_final_gate(
                reasons,
                policy_action=policy_action_pre,
                final_gate=final_gate,
            )
        else:
            status = "needs_human_review"
            decision_status = "hold"
            reasons.append("poc_low_evidence -> hold")

            final_gate = "poc_low_evidence_hold"
            _mark_policy_pre_and_final_gate(
                reasons,
                policy_action=policy_action_pre,
                final_gate=final_gate,
            )

        guidance = (guidance or "").rstrip()
        guidance += (
            "\n\n[PoC Gate] エビデンス不足のため、判断を確定せず「追加調査/前提確認」を要求します。"
            "（監査上、“止める/補う”を優先）"
        )

    # -------------------------------
    # 不変条件の最後の保険（deny/hold/allow をテスト準拠で固定）
    # -------------------------------
    if status == "deny" and decision_status != "deny":
        decision_status = "deny"
        rejection_reason = rejection_reason or "policy_deny_coerce"
        reasons.append("invariant_fix: deny=>deny")

    if decision_status == "deny" and not rejection_reason:
        rejection_reason = "policy_or_poc_gate_deny"
        reasons.append("invariant_fix: deny needs rejection_reason")

    if decision_status != "deny":
        rejection_reason = None

    return {
        "status": status,
        "decision_status": decision_status,
        "rejection_reason": rejection_reason,
        "reasons": reasons,
        "violations": violations,
        "violation_details": violation_details,
        "risk": float(final_risk),
        "guidance": guidance or None,
        "policy_version": policy_version,
        "followups": followups,
        "meta": {
            "policy_version": policy_version,
            "safety_head_model": safety_head.model,
            "safe_applied": safe_applied,
            "poc_mode": bool(poc_mode),
            "low_evidence": bool(low_ev),
            "evidence_count": int(evidence_count),
            "min_evidence": int(min_evidence),
            "policy_action_pre_poc": policy_action_pre,
            "final_gate": final_gate,
            "prompt_injection": {
                "score": float(injection_score),
                "signals": sorted(injection_signals),
            },
        },
    }


# =========================================================
# 4) FUJI Gate 本体（SafetyHead + TrustLog ラッパ）
# =========================================================
def fuji_gate(
    text: str,
    *,
    context: Dict[str, Any] | None = None,
    evidence: List[Dict[str, Any]] | None = None,
    alternatives: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    # ポリシーファイルのホットリロードチェック
    _check_policy_hot_reload()

    ctx = context or {}
    alts = alternatives or []

    evidence_provided = evidence is not None
    ev = evidence or []

    stakes = _safe_float(ctx.get("stakes", 0.5), 0.5)
    telos_score = _safe_float(ctx.get("telos_score", ctx.get("value_ema", 0.5)), 0.5)
    safe_applied = bool(ctx.get("fuji_safe_applied") or ctx.get("pii_already_masked"))

    min_evidence = _safe_nonneg_int(
        ctx.get("min_evidence")
        or ctx.get("fuji_min_evidence")
        or os.getenv("VERITAS_MIN_EVIDENCE", DEFAULT_MIN_EVIDENCE),
        DEFAULT_MIN_EVIDENCE
    )

    poc_mode = _ctx_bool(ctx, "poc_mode", _ENV_POC_MODE)

    # pre-check（validate_action）では low_evidence を強制しないデフォルト
    enforce_low_evidence = _ctx_bool(ctx, "enforce_low_evidence", evidence_provided)
    evidence_count_for_gate = len(ev) if enforce_low_evidence else int(min_evidence)

    # ---------- 1) Safety Head ----------
    t0 = time.time()
    sh = run_safety_head(text, ctx, alts)
    latency_ms = int((time.time() - t0) * 1000)

    # ---------- 2) コア判定 ----------
    core_res = fuji_core_decide(
        safety_head=sh,
        stakes=stakes,
        telos_score=telos_score,
        evidence_count=evidence_count_for_gate,
        policy=POLICY,
        safe_applied=safe_applied,
        min_evidence=min_evidence,
        text=text,
        poc_mode=poc_mode,
    )

    status = core_res["status"]
    decision_status = core_res["decision_status"]
    rejection_reason = core_res.get("rejection_reason")
    violations = core_res.get("violations", [])
    violation_details = core_res.get("violation_details", [])
    final_risk = core_res["risk"]
    reasons = list(core_res.get("reasons", []))
    guidance = core_res.get("guidance") or ""
    policy_version = core_res.get("policy_version")
    meta = dict(core_res.get("meta") or {})
    followups = list(core_res.get("followups") or [])

    if poc_mode and bool(meta.get("low_evidence")) and not followups:
        followups = _build_followups(text, ctx)

    # ---------- 3) TrustLog ----------
    # セキュリティ監査 §3.3.3 対応: judgment_source / llm_available フィールド追加
    _sh_raw = sh.raw or {}
    _is_llm_fallback = bool(
        _sh_raw.get("llm_fallback")
        or _sh_raw.get("fallback")
        or _sh_raw.get("safety_head_error")
    )
    if sh.model and sh.model not in ("heuristic_fallback", "llm_safety_unknown"):
        _judgment_source = "llm"
    elif _sh_raw.get("safety_head_error"):
        _judgment_source = "deterministic_fallback"
    else:
        _judgment_source = "deterministic_rule"
    _llm_available = not _is_llm_fallback

    try:
        redacted_preview = _redact_text_for_trust_log(text, POLICY)
        event = {
            "ts": _now_iso(),
            "event": "fuji_evaluate",
            "text_preview": (redacted_preview or "")[:200],
            "risk_score": float(sh.risk_score),
            "risk_after_policy": float(final_risk),
            "categories": list(sh.categories),
            "categories_effective": violations or list(sh.categories),
            "stakes": stakes,
            "telos_score": telos_score,
            "status": status,
            "decision_status": decision_status,
            "rejection_reason": rejection_reason,
            "policy_version": policy_version,
            "safe_applied": safe_applied,
            "latency_ms": latency_ms,
            "safety_head_model": sh.model,
            "judgment_source": _judgment_source,
            "llm_available": _llm_available,
            "violation_details": violation_details,
            "followups_count": len(followups),
            "meta": {
                "poc_mode": bool(poc_mode),
                "enforce_low_evidence": bool(enforce_low_evidence),
                "low_evidence": bool(meta.get("low_evidence")),
                "evidence_count": int(meta.get("evidence_count", evidence_count_for_gate)),
                "min_evidence": int(meta.get("min_evidence", min_evidence)),
            },
        }
        append_trust_event(event)
    except (TypeError, ValueError, OSError, RuntimeError) as e:  # pragma: no cover
        reasons.append(f"trustlog_error:{repr(e)[:80]}")

    checks: List[Dict[str, Any]] = [
        {
            "kind": "safety_head",
            "model": sh.model,
            "risk_score": sh.risk_score,
            "categories": sh.categories,
            "latency_ms": latency_ms,
        },
        {"kind": "policy_engine", "policy_version": policy_version},
    ]
    if poc_mode:
        checks.append(
            {
                "kind": "poc_low_evidence_gate",
                "enabled": True,
                "enforce_low_evidence": bool(enforce_low_evidence),
                "min_evidence": int(min_evidence),
                "evidence_count": int(len(ev)),
                "evidence_count_effective": int(evidence_count_for_gate),
                "low_evidence": bool(meta.get("low_evidence")),
            }
        )

    meta.setdefault("policy_version", policy_version)
    meta.setdefault("safety_head_model", sh.model)
    meta.setdefault("safe_applied", safe_applied)
    meta.setdefault("poc_mode", bool(poc_mode))
    meta.setdefault("enforce_low_evidence", bool(enforce_low_evidence))
    meta["latency_ms"] = latency_ms
    # セキュリティ監査 §3.3.3 対応
    meta["judgment_source"] = _judgment_source
    meta["llm_available"] = _llm_available

    # 不変条件（ここでも固定）
    if status == "deny" and decision_status != "deny":
        decision_status = "deny"
        rejection_reason = rejection_reason or "policy_deny_coerce"
        reasons.append("invariant_fix@fuji_gate: deny=>deny")
    if decision_status == "deny" and not rejection_reason:
        rejection_reason = "policy_or_poc_gate_deny"
        reasons.append("invariant_fix@fuji_gate: deny needs rejection_reason")
    if decision_status != "deny":
        rejection_reason = None

    rejection_payload = None
    if decision_status == "deny":
        code = _select_fuji_code(violations=violations, meta=meta)
        rejection_payload = build_fuji_rejection(
            code=code,
            trust_log_id=_resolve_trust_log_id(ctx),
        )

    return {
        "status": status,                    # 内部状態
        "decision_status": decision_status,  # 外部API向け（allow/hold/deny）
        "rejection_reason": rejection_reason,
        "rejection": rejection_payload,
        "reasons": reasons,
        "violations": violations,
        "risk": round(float(final_risk), 3),
        "checks": checks,
        "guidance": guidance or None,
        "followups": followups,
        "modifications": followups,  # 既存UI互換
        "redactions": [],
        "safe_instructions": [],
        "meta": meta,
    }


# =========================================================
# 5) 旧 API 互換ラッパ
# =========================================================
def validate_action(action_text: Any, context: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """
    v1互換：status を ok/modify/rejected に寄せる。

    テスト要件:
    - fuji_gate が (status="deny", decision_status="deny") を返したら rejected にマッピングする
    """
    res = fuji_gate(text=_to_text(action_text), context=context or {}, evidence=None)
    ds = res.get("decision_status")
    st = res.get("status")

    if ds == "allow":
        status = "ok"
    elif ds == "deny" or st == "deny":
        status = "rejected"
    else:
        status = "modify"

    return {
        "status": status,
        "reasons": res.get("reasons", []),
        "violations": res.get("violations", []),
        "risk": res.get("risk", 0.0),
        "modifications": res.get("followups") or res.get("modifications") or [],
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
        risk = max(risk, RISK_FLOOR_FLAG)

    if len(ev) < int(min_evidence):
        status = "flag"
        reasons.append(f"insufficient_evidence({len(ev)}/{min_evidence})")
        risk = max(risk, RISK_FLOOR_FLAG)

    return {
        "status": status,
        "reasons": reasons,
        "violations": violations,
        "violation_details": violation_details,
        "risk": risk,
    }


# =========================================================
# 6) evaluate ラッパ（旧/新インターフェイス互換）
# =========================================================
def evaluate(
    decision_or_query: Any,
    context: Dict[str, Any] | None = None,
    evidence: List[Dict[str, Any]] | None = None,
    alternatives: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    """
    1) dict: decision_snapshot
    2) str : 旧 query

    テスト要件:
    - 文字列クエリの場合、fuji_gate には evidence=[] を渡す（None ではない）
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

    # ★ テストに合わせて evidence は [] を渡す
    #   ただし、元々 evidence が省略（None）なら enforce_low_evidence は False を保つ。
    ctx = dict(context or {})
    if evidence is None and "enforce_low_evidence" not in ctx:
        ctx["enforce_low_evidence"] = False

    return fuji_gate(
        text=query_str,
        context=ctx,
        evidence=[] if evidence is None else evidence,
        alternatives=alternatives or [],
    )


__all__ = [
    "DEFAULT_MIN_EVIDENCE",
    "MAX_UNCERTAINTY",
    "SafetyHeadResult",
    "run_safety_head",
    "fuji_core_decide",
    "fuji_gate",
    "evaluate",
    "validate_action",
    "posthoc_check",
    "reload_policy",
]
