# veritas_os/core/fuji_policy.py
# -*- coding: utf-8 -*-
"""
FUJI Gate: Policy engine — YAML loading, hot reload, pattern compilation,
default policies, and the rule-based ``_apply_policy`` evaluator.

Extracted from fuji.py.  This module has **no** dependency on fuji.py
and may be imported independently.
"""

from __future__ import annotations

import logging
import math
import os
import re
import threading
from pathlib import Path
from typing import Any, Dict, List

from ..config import capability_cfg
from ..utils import _safe_float
from .fuji_injection import _build_injection_patterns_from_policy

_logger = logging.getLogger(__name__)

# =========================================================
# Conditional YAML import (mirrors original fuji.py logic)
# =========================================================
_FUJI_YAML_EXPLICITLY_ENABLED = os.getenv("VERITAS_CAP_FUJI_YAML_POLICY") in {
    "1",
    "true",
    "TRUE",
    "yes",
    "on",
}

if capability_cfg.enable_fuji_yaml_policy:
    try:
        import yaml  # ポリシーファイル用
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
        yaml = None  # type: ignore
else:  # pragma: no cover - explicit capability-off path
    yaml = None  # type: ignore

# =========================================================
# PII regex patterns (fallback, overridable via policy YAML)
# =========================================================
_PII_RE: Dict[str, re.Pattern[str]] = {
    "phone":          re.compile(r'(0\d{1,4}[-―‐ｰ–—]?\d{1,4}[-―‐ｰ–—]?\d{3,4})'),
    "email":          re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'),
    "address_jp":     re.compile(r'(東京都|道府県|市|区|町|村).{0,20}\d'),
    "person_name_jp": re.compile(r'[\u4e00-\u9fff]{2,4}\s*(?:さん|様|氏|先生|殿)'),
}

# =========================================================
# Keyword sets (fallback for when YAML policy has none)
# =========================================================
BANNED_KEYWORDS_FALLBACK = {
    "harm",
    "kill",
    "exploit",
    "illegal",
    "weapon",
    "malware",
    "bomb",
    "doxx",
    "毒",
    "殺",
    "爆弾",
    "銃",
    "兵器",
    "ハッキング",
    "違法",
}
SENSITIVE_KEYWORDS_FALLBACK = {
    "bio",
    "pathogen",
    "drug synthesis",
    "zero-day",
    "bypass",
    "unlock jail",
    "生物兵器",
    "毒物合成",
    "ゼロデイ",
    "脱獄",
    "暗号回避",
}

# PoC向け：高リスクっぽい業務ドメイン判定（テキスト含意）
RISKY_KEYWORDS_POC = re.compile(
    r"(法務|契約|労働|規制|コンプライアンス|金融|融資|投資|医療|診断|個人情報|マイナンバー|"
    r"セキュリティ|脆弱性|攻撃|ハッキング|監査|不正|犯罪|詐欺)",
    re.IGNORECASE
)


# =========================================================
# Default / strict-deny policies
# =========================================================
_DEFAULT_POLICY: Dict[str, Any] = {
    "version": "fuji_v2_default",
    "base_thresholds": {
        "default": 0.50,
        "high_stakes": 0.35,
        "low_stakes": 0.70,
    },
    "categories": {
        "PII": {"max_risk_allow": 0.20, "action_on_exceed": "human_review"},
        "self_harm": {"max_risk_allow": 0.05, "action_on_exceed": "deny"},
        "illicit": {"max_risk_allow": 0.10, "action_on_exceed": "deny"},
        "violence": {"max_risk_allow": 0.20, "action_on_exceed": "human_review"},
        "minors": {"max_risk_allow": 0.15, "action_on_exceed": "human_review"},
        "safety_head_error": {"max_risk_allow": 0.00, "action_on_exceed": "human_review"},
    },
    "actions": {
        "allow": {"risk_upper": 0.40},
        "warn": {"risk_upper": 0.65},
        "human_review": {"risk_upper": 0.85},
        "deny": {"risk_upper": 1.00},
    },
}

_STRICT_DENY_POLICY: Dict[str, Any] = {
    "version": "fuji_v2_strict_deny",
    "base_thresholds": {
        "default": 0.0,
        "high_stakes": 0.0,
        "low_stakes": 0.0,
    },
    "categories": {},
    "actions": {
        "deny": {"risk_upper": 1.0},
    },
}


# =========================================================
# Policy path resolution
# =========================================================
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
            # ★ セキュリティ修正: 相対パスは resolve() してプロジェクト内に収まることを確認
            resolved = p.resolve()
            try:
                resolved.relative_to(root_dir.resolve())
            except ValueError:
                _logger.warning("VERITAS_FUJI_POLICY relative path escapes project root, ignoring: %s", env_path)
                return root_dir / "policies" / "fuji_default.yaml"
            return resolved
        # ★ セキュリティ修正: 絶対パスがプロジェクトルート外の場合はデフォルトにフォールバック
        resolved = p.resolve()
        try:
            resolved.relative_to(root_dir.resolve())
        except ValueError:
            _logger.warning("VERITAS_FUJI_POLICY points outside project root, ignoring: %s", env_path)
            return root_dir / "policies" / "fuji_default.yaml"
        return resolved

    return root_dir / "policies" / "fuji_default.yaml"


# =========================================================
# Strict policy mode
# =========================================================
def _strict_policy_load_enabled() -> bool:
    """Return True when strict policy-load mode is enabled via env var."""
    raw = os.getenv("VERITAS_FUJI_STRICT_POLICY_LOAD", "0")
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _fallback_policy(*, path: Path | None, reason: str, exc: Exception | None = None) -> Dict[str, Any]:
    """Return fallback policy and emit an operation-visible warning/error log."""
    path_label = str(path) if path is not None else "<none>"
    strict_mode = _strict_policy_load_enabled()

    if exc is None:
        _logger.warning(
            "FUJI policy fallback triggered: reason=%s path=%s strict=%s",
            reason,
            path_label,
            strict_mode,
        )
    else:
        _logger.warning(
            "FUJI policy fallback triggered: reason=%s path=%s exc_type=%s strict=%s",
            reason,
            path_label,
            type(exc).__name__,
            strict_mode,
            exc_info=True,
        )

    if strict_mode:
        _logger.error(
            "FUJI strict policy-load mode active. Deny policy is enforced due to policy load failure. "
            "path=%s reason=%s",
            path_label,
            reason,
        )
        return dict(_STRICT_DENY_POLICY)

    return dict(_DEFAULT_POLICY)


# =========================================================
# Policy loading
# =========================================================
def _load_policy(path: Path | None) -> Dict[str, Any]:
    if not capability_cfg.enable_fuji_yaml_policy or yaml is None:
        return dict(_DEFAULT_POLICY)

    if path is None or not path.exists():
        return _fallback_policy(path=path, reason="missing_policy_file")

    yaml_error = getattr(yaml, "YAMLError", None)
    yaml_errors = (yaml_error,) if isinstance(yaml_error, type) else ()
    handled_errors = (TypeError, ValueError, OSError) + yaml_errors

    try:
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except handled_errors as exc:
        return _fallback_policy(path=path, reason="yaml_load_error", exc=exc)

    if "version" not in data:
        data["version"] = f"fuji_file_{path.name}"

    return data


def _load_policy_from_str(content: str, path: Path) -> Dict[str, Any]:
    """文字列からポリシーをパースする（TOCTOU 回避用）。"""
    if not capability_cfg.enable_fuji_yaml_policy or yaml is None:
        return dict(_DEFAULT_POLICY)
    yaml_error = getattr(yaml, "YAMLError", None)
    yaml_errors = (yaml_error,) if isinstance(yaml_error, type) else ()
    handled_errors = (TypeError, ValueError) + yaml_errors

    try:
        data = yaml.safe_load(content) or {}
    except handled_errors as exc:
        return _fallback_policy(path=path, reason="yaml_parse_error", exc=exc)
    if "version" not in data:
        data["version"] = f"fuji_file_{path.name}"
    return data


# =========================================================
# Runtime pattern rebuild (PII patterns part)
# =========================================================
def _build_pii_patterns_from_policy(policy: Dict[str, Any]) -> None:
    """Rebuild PII regex patterns from YAML policy."""
    pii_pats = (policy.get("pii") or {}).get("patterns") or {}
    if not isinstance(pii_pats, dict):
        return

    for key in ("phone", "email", "address_jp", "person_name_jp"):
        pattern_str = pii_pats.get(key)
        if pattern_str and isinstance(pattern_str, str):
            try:
                _PII_RE[key] = re.compile(pattern_str)
            except re.error as exc:
                _logger.warning("[FUJI] pii.patterns.%s invalid regex: %s", key, exc)


def _build_runtime_patterns_from_policy(policy: Dict[str, Any]) -> None:
    """YAML ポリシーからランタイム用コンパイル済みパターンを再構築する。

    ポリシーロード時・リロード時に呼び出すことで、
    モジュールトップレベルのハードコード変数をポリシー定義で上書きする。

    - _PROMPT_INJECTION_PATTERNS: プロンプトインジェクション検出パターン
    - _CONFUSABLE_ASCII_MAP: Unicode 同形異体文字の正規化マップ
    - _PII_RE: PII 検出パターン辞書（phone, email, address_jp, person_name_jp）
    """
    # Injection patterns & confusable map (in fuji_injection module)
    _build_injection_patterns_from_policy(policy)
    # PII patterns (local to this module)
    _build_pii_patterns_from_policy(policy)


# =========================================================
# Module-level policy state
# =========================================================
_POLICY_PATH = _policy_path()
POLICY: Dict[str, Any] = _load_policy(_POLICY_PATH)
# ★ YAML からランタイムパターンを初期構築（ハードコードフォールバックを上書き）
_build_runtime_patterns_from_policy(POLICY)
try:
    _POLICY_MTIME: float = _POLICY_PATH.stat().st_mtime
except OSError:
    _POLICY_MTIME: float = 0.0

# ★ 修正 (H-9): ポリシーリロード時の TOCTOU 競合状態を防止するためのロック
_policy_reload_lock = threading.Lock()


def reload_policy() -> Dict[str, Any]:
    """ポリシーを強制的にリロードする"""
    global POLICY, _POLICY_MTIME
    with _policy_reload_lock:
        path = _policy_path()
        POLICY = _load_policy(path)
        # ★ リロード後もランタイムパターンを再構築する
        _build_runtime_patterns_from_policy(POLICY)
        try:
            _POLICY_MTIME = path.stat().st_mtime
        except OSError:
            _POLICY_MTIME = 0.0
    return POLICY


def _check_policy_hot_reload() -> None:
    """
    ポリシーファイルの変更を検知して自動リロードする。
    validate() / validate_action() 呼び出し時に実行される。

    ★ 修正 (H-9): ファイルディスクリプタ経由で mtime 取得と読み込みを
      同一 fd で行い、TOCTOU 競合状態を排除。さらに _policy_reload_lock で
      複数スレッドからの同時リロードを防止する。
    """
    global POLICY, _POLICY_MTIME
    path = _policy_path()
    if not path.exists():
        return
    try:
        with _policy_reload_lock:
            fd = os.open(str(path), os.O_RDONLY)
            try:
                current_mtime = os.fstat(fd).st_mtime
                if current_mtime > _POLICY_MTIME:
                    with os.fdopen(fd, "r", encoding="utf-8") as f:
                        content = f.read()
                    # fd is now owned and closed by os.fdopen
                    fd = -1
                    POLICY = _load_policy_from_str(content, path)
                    _build_runtime_patterns_from_policy(POLICY)
                    _POLICY_MTIME = current_mtime
            finally:
                if fd >= 0:
                    os.close(fd)
    except OSError as exc:
        _logger.debug("policy hot reload skipped: %s", exc)


# =========================================================
# Keyword extraction helpers
# =========================================================
def _policy_blocked_keywords(policy: Dict[str, Any]) -> tuple[set[str], set[str]]:
    """
    Extract blocked keywords from the active policy.

    Returns:
        (hard_block_keywords, sensitive_keywords)
    """
    blocked = policy.get("blocked_keywords") or {}
    hard_block = blocked.get("hard_block") or []
    sensitive = blocked.get("sensitive") or []
    hard_set = {str(word).lower() for word in hard_block if word}
    sensitive_set = {str(word).lower() for word in sensitive if word}

    if not hard_set:
        hard_set = {str(word).lower() for word in BANNED_KEYWORDS_FALLBACK}
    if not sensitive_set:
        sensitive_set = {str(word).lower() for word in SENSITIVE_KEYWORDS_FALLBACK}

    return hard_set, sensitive_set


# =========================================================
# Policy rule evaluator (_apply_policy)
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
    監査可能ルール層（pure rule）。
    - status: allow|allow_with_warning|needs_human_review|deny
    - decision_status: allow|hold|deny   （テスト期待値に準拠）
    """
    base = policy.get("base_thresholds") or {}

    # Stakes thresholds: read from policy overrides, fall back to 0.7/0.3
    overrides = policy.get("overrides") or {}
    high_stakes_cfg = overrides.get("high_stakes") or {}
    low_stakes_cfg = overrides.get("low_stakes") or {}
    high_stakes_gte = _safe_float(high_stakes_cfg.get("when_stakes_gte"), 0.7)
    low_stakes_lte = _safe_float(low_stakes_cfg.get("when_stakes_lte"), 0.3)

    if stakes >= high_stakes_gte:
        base_thr = _safe_float(base.get("high_stakes", base.get("default", 0.5)), 0.5)
    elif stakes <= low_stakes_lte:
        base_thr = _safe_float(base.get("low_stakes", base.get("default", 0.5)), 0.5)
    else:
        base_thr = _safe_float(base.get("default", 0.5), 0.5)

    cat_cfg = policy.get("categories") or {}
    actions = policy.get("actions") or {}

    violation_details: List[Dict[str, Any]] = []

    for c in categories:
        cfg = cat_cfg.get(str(c))
        if not cfg:
            continue
        max_allow = cfg.get("max_risk_allow")
        if max_allow is not None:
            try:
                max_allow_f = float(max_allow)
            except (ValueError, TypeError):
                continue
            if risk > max_allow_f:
                violation_details.append(
                    {
                        "category": str(c),
                        "max_risk_allow": max_allow_f,
                        "action_on_exceed": cfg.get("action_on_exceed", "human_review"),
                    }
                )

    # Action precedence: read from YAML policy, fall back to hardcoded defaults
    _default_precedence = {"deny": 3, "human_review": 2, "warn": 1, "allow": 0}
    raw_prec = policy.get("action_precedence") or {}
    precedence: Dict[str, int] = {}
    for _act, _default_val in _default_precedence.items():
        try:
            precedence[_act] = int(raw_prec.get(_act, _default_val))
        except (TypeError, ValueError):
            precedence[_act] = _default_val
    final_action = "allow"

    allowed_actions = {"allow", "warn", "human_review", "deny"}

    if violation_details:
        best = "allow"
        for v in violation_details:
            act = str(v.get("action_on_exceed", "human_review"))
            if act not in allowed_actions:
                # Fail-closed: invalid category action should never widen access.
                act = "deny"
            if precedence.get(act, 0) > precedence.get(best, 0):
                best = act
        final_action = best
    else:
        def _act_key(item: Any) -> float:
            _, conf = item
            val = float(conf.get("risk_upper", 1.0))
            return val if math.isfinite(val) else 1.0

        for act, conf in sorted(actions.items(), key=_act_key):
            upper = float(conf.get("risk_upper", 1.0))
            if not math.isfinite(upper):
                upper = 1.0  # fail-closed: NaN/Inf → 最大閾値
            if risk <= upper:
                final_action = act
                break

    # 正規化（テストが要求する decision_status=allow/hold/deny）
    if final_action == "allow":
        status = "allow"
        decision_status = "allow"
    elif final_action == "warn":
        status = "allow_with_warning"
        decision_status = "hold"
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
            "category_violations=" + ",".join(sorted({v["category"] for v in violation_details if "category" in v}))
        )

    violation_categories = sorted({v["category"] for v in violation_details if "category" in v})

    return {
        "policy_action": final_action,
        "status": status,
        "decision_status": decision_status,
        "reasons": reasons,
        "violations": violation_categories,
        "violation_details": violation_details,
        "risk": float(risk),
        "policy_version": policy.get("version", "fuji_v2_unknown"),
    }
