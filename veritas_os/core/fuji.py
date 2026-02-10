# veritas_os/core/fuji.py
# -*- coding: utf-8 -*-
"""
FUJI Gate v2 (Safety Head × Policy Engine × TrustLog)

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
from datetime import datetime, timezone
import logging
import threading
import time
import os
import re

_logger = logging.getLogger(__name__)

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

# ---------------------------------------------------------
# 依存モジュール（存在しない場合はフォールバック）
# ---------------------------------------------------------
try:
    from veritas_os.tools import call_tool
except Exception:  # pragma: no cover
    def call_tool(kind: str, **kwargs: Any) -> Dict[str, Any]:
        raise RuntimeError(
            f"env tool '{kind}' / veritas_os.tools.call_tool が利用できません"
        )


try:
    from veritas_os.logging.trust_log import append_trust_event
except Exception:  # pragma: no cover
    def append_trust_event(event: Dict[str, Any]) -> None:
        return


try:
    import yaml  # ポリシーファイル用
except Exception:  # pragma: no cover
    yaml = None  # type: ignore


# =========================================================
# しきい値 & 簡易ヒューリスティック（フォールバック用）
# ★ リファクタリング: config.fuji_cfg から設定を取得
# =========================================================
try:
    from .config import fuji_cfg as _fuji_cfg
    DEFAULT_MIN_EVIDENCE = _fuji_cfg.default_min_evidence
    MAX_UNCERTAINTY = _fuji_cfg.max_uncertainty
    _ENV_POC_MODE = _fuji_cfg.poc_mode
except Exception:
    # フォールバック: config が壊れていてもfuji.pyは動作する
    DEFAULT_MIN_EVIDENCE = 1
    MAX_UNCERTAINTY = 0.60
    _ENV_POC_MODE = os.getenv("VERITAS_POC_MODE", "0") == "1"

# 危険・違法系の簡易ワード（Safety Head が落ちた時の fallback 用）
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

# ざっくり PII 検出（fallback 用）
_RE_PHONE  = re.compile(r'(0\d{1,4}[-―‐ｰ–—]?\d{1,4}[-―‐ｰ–—]?\d{3,4})')
_RE_EMAIL  = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')
_RE_ADDRJP = re.compile(r'(東京都|道府県|市|区|町|村).{0,20}\d')
_RE_NAMEJP = re.compile(r'[\u4e00-\u9fff]{2,4}\s*(?:さん|様|氏|先生|殿)')


# PoC向け：高リスクっぽい業務ドメイン判定（テキスト含意）
RISKY_KEYWORDS_POC = re.compile(
    r"(法務|契約|労働|規制|コンプライアンス|金融|融資|投資|医療|診断|個人情報|マイナンバー|"
    r"セキュリティ|脆弱性|攻撃|ハッキング|監査|不正|犯罪|詐欺)",
    re.IGNORECASE
)

_PROMPT_INJECTION_PATTERNS: List[tuple[re.Pattern[str], float, str]] = [
    (
        re.compile(
            r"(ignore|disregard|override).{0,40}"
            r"(system|previous|developer|safety|policy)",
            re.IGNORECASE,
        ),
        0.4,
        "override_instructions",
    ),
    (
        re.compile(
            r"(reveal|show|leak).{0,40}"
            r"(system prompt|developer message|policy)",
            re.IGNORECASE,
        ),
        0.4,
        "reveal_system",
    ),
    (
        re.compile(r"\b(jailbreak|dan|prompt injection)\b", re.IGNORECASE),
        0.5,
        "jailbreak_keyword",
    ),
    (
        re.compile(
            r"(bypass|disable).{0,30}(safety|guard|policy|filter)",
            re.IGNORECASE,
        ),
        0.5,
        "bypass_safety",
    ),
    (
        re.compile(r"(act as|roleplay).{0,30}(system|developer|root)", re.IGNORECASE),
        0.2,
        "role_override",
    ),
]


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


def _safe_int(x: Any, default: int) -> int:
    try:
        v = int(x)
        return v if v >= 0 else default
    except Exception:
        return default


# _to_text は utils.py から統合インポート済み


def _normalize_text(s: str) -> str:
    return (s or "").replace("　", " ").strip().lower()


def _resolve_trust_log_id(context: Dict[str, Any]) -> str:
    """
    Resolve a trust_log_id from context without altering existing TrustLog behavior.
    """
    if context.get("trust_log_id"):
        return str(context["trust_log_id"])
    if context.get("request_id"):
        return str(context["request_id"])
    return "TL-UNKNOWN"


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


def _redact_text_for_trust_log(text: str, policy: Dict[str, Any]) -> str:
    """
    Redact PII in TrustLog text previews based on policy settings.

    This keeps FUJI's responsibility (safety gate + audit logging) while
    honoring the policy's redaction requirement before writing TrustLog.
    """
    audit_cfg = policy.get("audit") or {}
    if not audit_cfg.get("redact_before_log", False):
        return text

    pii_cfg = policy.get("pii") or {}
    if not pii_cfg.get("enabled", True):
        return text

    masked_markers = pii_cfg.get("masked_markers") or ["●"]
    mask_token = str(masked_markers[0]) if masked_markers else "●"
    text_value = text or ""

    redact_kinds = pii_cfg.get("redact_kinds") or {}
    if redact_kinds.get("phone", True):
        text_value = _RE_PHONE.sub(mask_token * 4, text_value)
    if redact_kinds.get("email", True):
        text_value = _RE_EMAIL.sub(mask_token * 4, text_value)
    if redact_kinds.get("address_jp", True):
        text_value = _RE_ADDRJP.sub(mask_token * 4, text_value)
    if redact_kinds.get("person_name_jp", False):
        text_value = _RE_NAMEJP.sub(mask_token * 2, text_value)

    return text_value


def _select_fuji_code(
    *,
    violations: List[str],
    meta: Dict[str, Any],
) -> str:
    """
    Select a FUJI standard code based on FUJI gate signals.
    """
    prompt_injection = meta.get("prompt_injection") or {}
    if prompt_injection.get("score", 0.0) >= 0.4 or prompt_injection.get("signals"):
        return "F-4001"

    if "PII" in violations:
        return "F-4003"

    if meta.get("low_evidence"):
        return "F-1002"

    if any(v in {"illicit", "self_harm", "violence", "minors"} for v in violations):
        return "F-3008"

    return "F-3008"


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
        # ★ セキュリティ修正: 絶対パスがプロジェクトルート外の場合は警告を記録
        resolved = p.resolve()
        try:
            resolved.relative_to(root_dir.resolve())
        except ValueError:
            _logger.warning("VERITAS_FUJI_POLICY points outside project root: %s", env_path)
        return resolved

    return root_dir / "policies" / "fuji_default.yaml"


def _ctx_bool(ctx: Dict[str, Any], key: str, default: bool) -> bool:
    v = ctx.get(key, default)
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "y", "on")
    return default


def _is_high_risk_context(*, risk: float, stakes: float, categories: List[str], text: str) -> bool:
    """
    PoC用：low_evidence 時に deny へ寄せるかどうかの判定。
    """
    if stakes >= 0.7:
        return True
    if risk >= 0.7:
        return True

    cats = {str(c).strip().lower() for c in (categories or [])}
    if any(c in cats for c in ("self_harm", "illicit", "violence", "minors", "pii")):
        return True

    if RISKY_KEYWORDS_POC.search(text or ""):
        return True

    return False


def _build_followups(text: str, context: Dict[str, Any]) -> List[FujiFollowup]:
    """
    PoCで「止める/補う」がレスポンスに必ず出るようにする。
    """
    q = (text or "").strip()
    scope_hint = str(context.get("scope", "") or "").strip()
    return [
        {
            "type": "web_search",
            "title": "一次ソースで裏取り（独立ソース2件以上）",
            "query": q,
            "acceptance": "公式/一次情報 + 信頼できる独立ソースの2件以上",
        },
        {
            "type": "clarify",
            "title": "前提条件の確認（PoC要件）",
            "questions": [
                "PoCのゴール（監査ログ/意思決定支援/安全ゲート）の最優先は？",
                "評価指標（正確性/再現性/説明可能性/速度）の優先順位は？",
                f"この判断のスコープ（対象業務・対象期間・制約）は？{(' / hint: ' + scope_hint) if scope_hint else ''}",
            ],
        },
        {
            "type": "evidence_request",
            "title": "追加エビデンス投入（社内ルール/要件）",
            "items": [
                "PoC要件定義（対象業務、判断ポイント、想定入力/出力）",
                "セキュリティ/法務制約（禁止事項・承認フロー・保管要件）",
                "成功条件（KPI、合格ライン、評価手順）",
            ],
        },
    ]


def _detect_prompt_injection(text: str) -> Dict[str, Any]:
    """
    FUJI Gate に対するプロンプトインジェクションの兆候を検出する。

    安全ヘッド自体をハックしようとする試行に対する防御層として、
    ルールベースでシグナルを抽出しスコア化する。
    """
    score = 0.0
    signals: List[str] = []
    if not text:
        return {"score": 0.0, "signals": signals}

    for pattern, weight, label in _PROMPT_INJECTION_PATTERNS:
        if pattern.search(text):
            score += weight
            signals.append(label)

    return {"score": min(1.0, score), "signals": signals}


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


def _load_policy(path: Path | None) -> Dict[str, Any]:
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


def _load_policy_from_str(content: str, path: Path) -> Dict[str, Any]:
    """文字列からポリシーをパースする（TOCTOU 回避用）。"""
    if yaml is None:
        return dict(_DEFAULT_POLICY)
    try:
        data = yaml.safe_load(content) or {}
    except Exception:
        return dict(_DEFAULT_POLICY)
    if "version" not in data:
        data["version"] = f"fuji_file_{path.name}"
    return data


_POLICY_PATH = _policy_path()
POLICY: Dict[str, Any] = _load_policy(_POLICY_PATH)
_POLICY_MTIME: float = _POLICY_PATH.stat().st_mtime if _POLICY_PATH.exists() else 0.0

# ★ 修正 (H-9): ポリシーリロード時の TOCTOU 競合状態を防止するためのロック
_policy_reload_lock = threading.Lock()


def reload_policy() -> Dict[str, Any]:
    """ポリシーを強制的にリロードする"""
    global POLICY, _POLICY_MTIME
    with _policy_reload_lock:
        path = _policy_path()
        POLICY = _load_policy(path)
        _POLICY_MTIME = path.stat().st_mtime if path.exists() else 0.0
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
                    _POLICY_MTIME = current_mtime
            finally:
                if fd >= 0:
                    os.close(fd)
    except OSError as exc:
        _logger.debug("policy hot reload skipped: %s", exc)


# =========================================================
# 1) Safety Head（LLM もしくは fallback）
# =========================================================
def _fallback_safety_head(text: str) -> SafetyHeadResult:
    t = _normalize_text(text)
    categories: List[str] = []
    risk = 0.05
    rationale_parts: List[str] = []

    hard_block, sensitive = _policy_blocked_keywords(POLICY)
    hits = [w for w in hard_block if w in t] + [w for w in sensitive if w in t]
    if hits:
        categories.append("illicit")
        risk = max(risk, 0.8)
        rationale_parts.append(f"危険・違法系キーワード検出: {', '.join(sorted(set(hits)))}")

    pii_hits: List[str] = []
    if _RE_PHONE.search(text):
        pii_hits.append("phone")
    if _RE_EMAIL.search(text):
        pii_hits.append("email")
    if _RE_ADDRJP.search(text):
        pii_hits.append("address")

    # _RE_NAMEJP は誤検出が多いので PII 判定に使わない
    if pii_hits:
        categories.append("PII")
        risk = max(risk, 0.35)
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
        # ★ 不確実性を反映: LLM エラー時はベースリスクを 0.30 に引き上げ
        # 理由: LLM が評価できなかった = 安全性を確認できていない
        fb.risk_score = max(fb.risk_score, 0.30)
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
    監査可能ルール層（pure rule）。
    - status: allow|allow_with_warning|needs_human_review|deny
    - decision_status: allow|hold|deny   （テスト期待値に準拠）
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

    violation_details: List[Dict[str, Any]] = []

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
        def _act_key(item: Any) -> float:
            _, conf = item
            return float(conf.get("risk_upper", 1.0))

        for act, conf in sorted(actions.items(), key=_act_key):
            upper = float(conf.get("risk_upper", 1.0))
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
        risk = float(safety_head.risk_score) if safety_head.risk_score is not None else 0.05
    except (TypeError, ValueError):
        risk = 0.05
    base_reasons: List[str] = []
    guidance = safety_head.rationale or ""

    injection = _detect_prompt_injection(text)
    injection_score = float(injection.get("score", 0.0) or 0.0)
    injection_signals = list(injection.get("signals") or [])
    if injection_score > 0.0:
        categories.append("prompt_injection")
        risk = min(1.0, risk + (0.15 * injection_score))
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
            risk = min(float(risk), 0.20)
            base_reasons.append("fallback_pii_ignored(name_like_only)")
            guidance = (
                "heuristic_fallback の name_like 検出は日本語テキストで誤検出が多いため、"
                "name_like-only の場合は PII として扱わずリスクを抑制しました。"
            )

    # --- 既に PII セーフ化済みの場合の緩和 ---
    # ★ リファクタリング: 設定値から取得
    try:
        pii_safe_cap = _fuji_cfg.pii_safe_risk_cap
    except Exception:
        pii_safe_cap = 0.40

    if safe_applied:
        filtered = [c for c in categories if str(c).lower() not in ("pii", "pii_exposure")]
        if len(filtered) < len(categories):
            categories = filtered
            risk = min(risk, pii_safe_cap)
            base_reasons.append("pii_safe_applied")

    # --- evidence 不足ペナルティ（テスト要件：guidance に文言を入れる） ---
    # ★ リファクタリング: 設定値から取得
    try:
        low_ev_penalty = _fuji_cfg.low_evidence_risk_penalty
    except Exception:
        low_ev_penalty = 0.10

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
    # ★ リファクタリング: 設定値から取得
    try:
        telos_risk_scale = _fuji_cfg.telos_risk_scale_factor
    except Exception:
        telos_risk_scale = 0.10

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

    min_evidence = _safe_int(
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
    except Exception as e:  # pragma: no cover
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

