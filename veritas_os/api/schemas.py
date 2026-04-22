# veritas_os/api/schemas.py
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Literal, Union, Iterable, Mapping
from uuid import uuid4

from pydantic import (
    BaseModel,
    Field,
    ConfigDict,
    model_validator,
    field_validator,
)
from veritas_os.policy.bind_artifacts import FinalOutcome
from veritas_os.core.decision_semantics import (
    COMPATIBLE_GATE_DECISION_VALUES,
    LEGACY_GATE_DECISION_ALIASES,
    CANONICAL_GATE_DECISION_VALUES,
    canonicalize_public_gate_decision,
    normalize_required_evidence_keys,
    unique_preserve_order,
    validate_gate_business_combination,
)

# =========================
# Input Length Constraints (Security)
# =========================
# These limits prevent DoS attacks via oversized payloads.
# Adjust as needed for your use case, but keep reasonable limits.

MAX_QUERY_LENGTH = 10000  # Max characters for query/message fields
MAX_SNIPPET_LENGTH = 50000  # Max characters for evidence snippets
MAX_DESCRIPTION_LENGTH = 20000  # Max characters for descriptions
MAX_TITLE_LENGTH = 1000  # Max characters for titles
MAX_LIST_ITEMS = 100  # Max items in lists (alternatives, evidence, etc.)
MAX_ID_LENGTH = 500  # Max characters for ID fields (user_id, session_id, etc.)
MAX_URI_LENGTH = 2000  # Max characters for URI fields
MAX_SOURCE_LENGTH = 500  # Max characters for source fields
MAX_ACTOR_LENGTH = 200  # Max characters for actor/source type fields
MAX_KIND_LENGTH = 50  # Max characters for kind/retention_class fields

# Shared decision status literal used across FujiDecision, Gate, DecideResponse
DecisionStatusLiteral = Literal["allow", "modify", "rejected", "block", "abstain"]
GateDecisionLiteral = Literal[
    "proceed",
    "hold",
    "block",
    "human_review_required",
    "allow",
    "deny",
    "modify",
    "rejected",
    "abstain",
    "unknown",
]
# NOTE:
# - Canonical public values are defined in decision_semantics.py:
#   CANONICAL_GATE_DECISION_VALUES.
# - Legacy aliases remain compatibility-only:
#   LEGACY_GATE_DECISION_ALIASES.
# - This Literal intentionally remains permissive for backward compatibility.
BusinessDecisionLiteral = Literal[
    "APPROVE",
    "DENY",
    "HOLD",
    "REVIEW_REQUIRED",
    "POLICY_DEFINITION_REQUIRED",
    "EVIDENCE_REQUIRED",
]

logger = logging.getLogger(__name__)

# =========================
# Helpers (robust coercion)
# =========================


def _is_mapping(x: Any) -> bool:
    return isinstance(x, Mapping)


def _as_list(v: Any) -> List[Any]:
    """
    Robustly coerce v into a Python list.
    - None -> []
    - dict -> [dict]
    - scalar -> [scalar]
    - iterable (tuple/set/generator) -> list(iterable)
    - list -> list
    """
    if v is None:
        return []
    if isinstance(v, list):
        return v
    if _is_mapping(v):
        return [v]
    if isinstance(v, (str, int, float, bool)):
        return [v]
    # other iterables: tuple/set/generator/etc
    if isinstance(v, Iterable):
        try:
            return list(v)
        except Exception:
            logger.debug("_as_list: failed to coerce iterable, wrapping as [v]")
            return [v]
    return [v]


def _coerce_context(v: Any) -> Dict[str, Any]:
    """
    Accept Context | dict | anything -> dict
    """
    if v is None:
        return {}
    if isinstance(v, Context):
        return v.model_dump()
    if _is_mapping(v):
        return dict(v)
    # last resort
    return {"raw": v}


# =========================
# Core context / options
# =========================


class Context(BaseModel):
    model_config = ConfigDict(extra="allow")

    user_id: str = Field(..., max_length=MAX_ID_LENGTH)
    session_id: Optional[str] = Field(default=None, max_length=MAX_ID_LENGTH)
    query: str = Field(..., max_length=MAX_QUERY_LENGTH)

    goals: Optional[List[str]] = Field(default=None)
    constraints: Optional[List[str]] = Field(default=None)

    # OpenAPI で定義されているツール許可リスト
    tools_allowed: Optional[List[str]] = Field(default=None)

    # 返答の時間軸（未指定可）
    time_horizon: Optional[Literal["short", "mid", "long"]] = None

    # 将来の好み/スタイル切替のフック
    preferences: Optional[List[str]] = Field(default=None)
    telos_weights: Optional[Dict[str, float]] = None
    affect_hint: Optional[Dict[str, str]] = None
    response_style: Optional[Literal["logic", "emotional", "business", "expert", "casual"]] = None

    @field_validator("goals", "constraints", "preferences", "tools_allowed", mode="before")
    @classmethod
    def _validate_list_size(cls, v: Any) -> Any:
        if v is not None and isinstance(v, (list, tuple, set)) and len(v) > MAX_LIST_ITEMS:
            raise ValueError(f"list exceeds maximum size of {MAX_LIST_ITEMS}")
        return v


class Option(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: Optional[str] = Field(default=None, max_length=MAX_ID_LENGTH)
    title: Optional[str] = Field(default=None, max_length=MAX_TITLE_LENGTH)
    description: Optional[str] = Field(default=None, max_length=MAX_DESCRIPTION_LENGTH)
    score: Optional[float] = None
    text: Optional[str] = Field(default=None, max_length=MAX_TITLE_LENGTH)  # 互換（title の別名）
    score_raw: Optional[float] = None

    @model_validator(mode="after")
    def _unify_text(self) -> "Option":
        # title が無ければ text を title に寄せる
        if (not self.title) and self.text:
            self.title = self.text
        return self


# =========================
# Evidence / critique / debate
# =========================


class ValuesOut(BaseModel):
    model_config = ConfigDict(extra="allow")

    scores: Dict[str, float]
    total: float
    top_factors: List[str]
    rationale: str
    # value-learning で書き込んでいる EMA を受け取る用
    ema: Optional[float] = None


class EvidenceItem(BaseModel):
    """
    evidence はパイプライン / tool / web_search / memory など多経路で混在しがち。
    - extra="allow" で未知キーを落とさない
    - snippet/title/uri/source の最小契約を必ず満たす
    """
    model_config = ConfigDict(extra="allow")

    source: str = Field(default="unknown", max_length=MAX_SOURCE_LENGTH)
    uri: Optional[str] = Field(default=None, max_length=MAX_URI_LENGTH)
    title: Optional[str] = Field(default=None, max_length=MAX_TITLE_LENGTH)
    snippet: str = Field(default="", max_length=MAX_SNIPPET_LENGTH)
    confidence: float = 0.7

    @model_validator(mode="after")
    def _coerce_minimum_contract(self) -> "EvidenceItem":
        # source
        if not self.source:
            self.source = "unknown"

        # uri: url/link/href/URI 互換
        if self.uri is None:
            u = None
            ex = getattr(self, "__pydantic_extra__", None)
            if isinstance(ex, dict):
                u = ex.get("url") or ex.get("link") or ex.get("href") or ex.get("URI")
            if u:
                self.uri = str(u)[:2000]  # Truncate to max length

        # snippet: 無ければ title -> uri -> "" の順で埋める
        if not self.snippet:
            if self.title:
                self.snippet = str(self.title)[:MAX_SNIPPET_LENGTH]
            elif self.uri:
                self.snippet = str(self.uri)[:MAX_SNIPPET_LENGTH]
            else:
                self.snippet = ""

        # confidence
        try:
            self.confidence = float(self.confidence if self.confidence is not None else 0.7)
        except (TypeError, ValueError):
            self.confidence = 0.7
        self.confidence = max(0.0, min(1.0, self.confidence))
        return self


class CritiqueItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    issue: str
    severity: Literal["low", "med", "high"] = "med"
    fix: Optional[str] = None


class DebateView(BaseModel):
    model_config = ConfigDict(extra="allow")

    stance: str
    argument: str
    score: float


# =========================
# Safety / trust
# =========================


class FujiDecision(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: DecisionStatusLiteral
    reasons: List[str] = Field(default_factory=list, max_length=MAX_LIST_ITEMS)
    violations: List[str] = Field(default_factory=list, max_length=MAX_LIST_ITEMS)

    # Diagnostic fields consumed by the frontend FujiGateView adapter.
    # rule_hit: the specific policy rule or keyword that triggered the gate.
    rule_hit: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Policy rule or keyword that triggered the FUJI gate.",
    )
    # severity: qualitative risk level ("low" | "medium" | "high" | "critical").
    severity: Optional[str] = Field(
        default=None,
        max_length=50,
        description="Qualitative risk severity level produced by the safety head.",
    )
    # remediation_hint: suggested action for the operator or user.
    remediation_hint: Optional[str] = Field(
        default=None,
        max_length=1000,
        description="Suggested remediation action for operators when gate fires.",
    )
    # risky_text_fragment: short excerpt from the input that triggered the rule.
    risky_text_fragment: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Short excerpt from the input that triggered the policy rule.",
    )


class TrustLog(BaseModel):
    model_config = ConfigDict(extra="allow")

    request_id: str
    created_at: str
    sources: List[str] = Field(default_factory=list, max_length=MAX_LIST_ITEMS)
    critics: List[str] = Field(default_factory=list, max_length=MAX_LIST_ITEMS)
    checks: List[str] = Field(default_factory=list, max_length=MAX_LIST_ITEMS)

    # 実運用の落下を避けるため、デフォルトを持たせる（必須思想なら外してOK）
    approver: str = "system"

    # FUJI Gateの判定結果（openapi.yaml では任意フィールド）
    fuji: Optional[Dict[str, Any]] = None

    # ハッシュチェーン: trust_log.py の append_trust_log で付与される
    sha256: Optional[str] = None
    sha256_prev: Optional[str] = None

    # パイプラインが付与する追加フィールド（pipeline.py の audit entry から）
    query: Optional[str] = None
    gate_status: Optional[str] = None
    gate_risk: Optional[float] = None

    # ハッシュチェーン検証結果（/v1/trust/verify 経由で付与される）
    chain_verification: Optional[
        Literal["verified", "degraded", "broken", "unknown"]
    ] = None
    chain_verification_reason: Optional[str] = None


class ExecutionIntent(BaseModel):
    """Decision-linked execution attempt descriptor (schema-first contract)."""

    model_config = ConfigDict(extra="allow")

    execution_intent_id: str = Field(default_factory=lambda: uuid4().hex, max_length=MAX_ID_LENGTH)
    decision_id: str = Field(default="", max_length=MAX_ID_LENGTH)
    request_id: str = Field(default="", max_length=MAX_ID_LENGTH)
    policy_snapshot_id: str = Field(default="", max_length=MAX_ID_LENGTH)
    actor_identity: str = Field(default="", max_length=MAX_ACTOR_LENGTH)
    target_system: str = Field(default="", max_length=MAX_TITLE_LENGTH)
    target_resource: str = Field(default="", max_length=MAX_URI_LENGTH)
    intended_action: str = Field(default="", max_length=MAX_TITLE_LENGTH)
    evidence_refs: List[str] = Field(default_factory=list, max_length=MAX_LIST_ITEMS)
    decision_hash: str = Field(default="", max_length=128)
    decision_ts: str = ""
    ttl_seconds: Optional[int] = Field(default=None, ge=0)
    expected_state_fingerprint: Optional[str] = Field(default=None, max_length=256)
    approval_context: Optional[Dict[str, Any]] = None
    policy_lineage: Optional[Dict[str, Any]] = None


class BindReceipt(BaseModel):
    """Bind-time governance artifact linked to decision lineage."""

    model_config = ConfigDict(extra="allow")

    bind_receipt_id: str = Field(default_factory=lambda: uuid4().hex, max_length=MAX_ID_LENGTH)
    execution_intent_id: str = Field(default="", max_length=MAX_ID_LENGTH)
    decision_id: str = Field(default="", max_length=MAX_ID_LENGTH)
    bind_ts: str = ""
    live_state_fingerprint_before: str = Field(default="", max_length=256)
    live_state_fingerprint_after: str = Field(default="", max_length=256)
    authority_check_result: Dict[str, Any] = Field(default_factory=dict)
    constraint_check_result: Dict[str, Any] = Field(default_factory=dict)
    drift_check_result: Dict[str, Any] = Field(default_factory=dict)
    risk_check_result: Dict[str, Any] = Field(default_factory=dict)
    admissibility_result: Dict[str, Any] = Field(default_factory=dict)
    final_outcome: FinalOutcome = FinalOutcome.BLOCKED
    rollback_reason: Optional[str] = Field(default=None, max_length=MAX_DESCRIPTION_LENGTH)
    escalation_reason: Optional[str] = Field(default=None, max_length=MAX_DESCRIPTION_LENGTH)
    trustlog_hash: str = Field(default="", max_length=128)
    prev_bind_hash: Optional[str] = Field(default=None, max_length=128)


# =========================
# Response envelope — Trust Log
# =========================

VerificationResultLiteral = Literal["ok", "broken", "not_found"]


class TrustLogsResponse(BaseModel):
    """Paginated response envelope for GET /v1/trust/logs."""

    items: List[Dict[str, Any]] = Field(default_factory=list)
    cursor: Optional[str] = None
    next_cursor: Optional[str] = None
    limit: int = 50
    has_more: bool = False


class RequestLogResponse(BaseModel):
    """Response envelope for GET /v1/trust/{request_id}."""

    request_id: str = ""
    items: List[Dict[str, Any]] = Field(default_factory=list)
    count: int = 0
    chain_ok: bool = False
    verification_result: str = "not_found"


# =========================
# API I/O（Request）
# =========================


class AltItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: Optional[str] = Field(default=None, max_length=MAX_ID_LENGTH)
    title: Optional[str] = Field(default=None, max_length=MAX_TITLE_LENGTH)
    text: Optional[str] = Field(default=None, max_length=MAX_TITLE_LENGTH)  # 互換（title の別名）
    description: Optional[str] = Field(default=None, max_length=MAX_DESCRIPTION_LENGTH)
    score: Optional[float] = None
    score_raw: Optional[float] = None

    @model_validator(mode="after")
    def _unify_text(self) -> "AltItem":
        if (not self.title) and self.text:
            self.title = self.text
        return self


AltIn = Union[AltItem, Option, Dict[str, Any]]


def _altin_to_altitem(x: Any) -> AltItem:
    """
    Accept AltItem | Option | dict | scalar and normalize to AltItem.
    """
    if x is None:
        return AltItem()
    if isinstance(x, AltItem):
        return x
    if isinstance(x, Option):
        d = x.model_dump()
        # Option.text/title unify already, but keep it safe
        return AltItem.model_validate(d)
    if _is_mapping(x):
        return AltItem.model_validate(dict(x))
    # scalar fallback
    return AltItem(title=str(x))


class DecideRequest(BaseModel):
    """
    完全互換の受け口（落ちない）:
    - context: Context/dict/anything -> dict に正規化
    - alternatives/options: list/dict/Option/AltItem/scalar 混在OK
    - options -> alternatives 片寄せ（alternatives 優先）
    """
    model_config = ConfigDict(extra="allow")

    query: str = Field(default="", max_length=MAX_QUERY_LENGTH)
    context: Dict[str, Any] = Field(default_factory=dict)

    # ★ 受け口は AltIn にする（dict/Option/AltItem 全受け）
    # Note: max_length is for strings; Pydantic v2 doesn't have max_items for Lists in Field
    # List size validation is done in the field_validator below
    alternatives: Optional[List[AltIn]] = None
    options: Optional[List[AltIn]] = None

    min_evidence: int = Field(default=1, ge=0, le=100)
    memory_auto_put: bool = True
    persona_evolve: bool = True
    coercion_events: List[str] = Field(default_factory=list, exclude=True)

    @field_validator("context", mode="before")
    @classmethod
    def _coerce_context_before(cls, v: Any) -> Dict[str, Any]:
        return _coerce_context(v)

    @field_validator("alternatives", mode="before")
    @classmethod
    def _coerce_alternatives_before(cls, v: Any) -> List[AltItem]:
        # None -> []
        if v is None:
            return []
        # dict/scalar/iterable -> list
        items = _as_list(v)
        # Enforce list size limit
        if len(items) > MAX_LIST_ITEMS:
            raise ValueError(f"alternatives list exceeds maximum size of {MAX_LIST_ITEMS}")
        return [_altin_to_altitem(x) for x in items]

    @field_validator("options", mode="before")
    @classmethod
    def _coerce_options_before(cls, v: Any) -> List[AltItem]:
        if v is None:
            return []
        items = _as_list(v)
        # Enforce list size limit
        if len(items) > MAX_LIST_ITEMS:
            raise ValueError(f"options list exceeds maximum size of {MAX_LIST_ITEMS}")
        return [_altin_to_altitem(x) for x in items]

    @model_validator(mode="after")
    def _unify_options(self) -> "DecideRequest":
        """Unify compatibility fields and record coercion/deprecation events.

        The API keeps accepting both ``alternatives`` and legacy ``options`` to
        preserve backward compatibility. Internally, ``alternatives`` is treated
        as canonical and ``options`` is synchronized to the canonical value so
        downstream components see a stable shape.
        """
        events: List[str] = []

        if "raw" in self.context:
            events.append("coercion.context_non_mapping")

        if "options" in self.model_fields_set:
            events.append("deprecation.options_field_used")
            logger.warning(
                "DecideRequest received deprecated field 'options'; prefer 'alternatives'",
            )

        # alternatives 優先。無ければ options を採用
        alts = list(self.alternatives or [])
        opts = list(self.options or [])
        if (not alts) and opts:
            self.alternatives = opts
            alts = opts
            events.append("coercion.options_to_alternatives")

        # 互換で options も同値に揃える（クライアント期待がある場合）
        if alts and (not opts):
            self.options = list(alts)
            events.append("coercion.alternatives_to_options")

        if alts and opts:
            canonical_alts = [alt.model_dump() for alt in alts]
            canonical_opts = [opt.model_dump() for opt in opts]
            if canonical_alts != canonical_opts:
                self.options = list(alts)
                events.append("coercion.options_overridden_by_alternatives")
                logger.warning(
                    "DecideRequest received conflicting alternatives/options;"
                    " options were normalized to alternatives",
                )

        # ここで型を AltItem に確定（field_validator で済んでいる想定だが保険）
        self.alternatives = [x if isinstance(x, AltItem) else _altin_to_altitem(x) for x in (self.alternatives or [])]
        self.options = [x if isinstance(x, AltItem) else _altin_to_altitem(x) for x in (self.options or [])]

        extras = getattr(self, "__pydantic_extra__", None)
        if isinstance(extras, dict) and extras:
            events.append("coercion.request_extra_keys_allowed")
            logger.warning(
                "DecideRequest accepted %d extra keys: %s",
                len(extras),
                sorted(extras.keys()),
            )

        if events:
            self.coercion_events = sorted(set(events))
        return self


# =========================
# Pipeline stage metrics (extras["stage_metrics"])
# =========================


class StageMetrics(BaseModel):
    """
    Per-stage execution metrics written into DecideResponse.extras["stage_metrics"].

    Each pipeline stage (Input, Evidence, Critique, Debate, Plan, Value, FUJI,
    TrustLog) may publish a StageMetrics entry keyed by its lowercase name.

    Frontend adapter contract (decision-view.ts):
    - Key aliases: Input→"input", Evidence→"evidence", Critique→"critique",
      Debate→"debate", Plan→"plan"/"planner", Value→"value"/"values",
      FUJI→"fuji"/"gate", TrustLog→"trustlog"/"trust_log"
    - latency_ms: stage wall-clock time in milliseconds
    - health: "ok" | "warning" | "failed" | "unknown"
    - summary: one-line human-readable result description
    - detail: extended diagnostic text (shown on hover / expanded view)
    """
    model_config = ConfigDict(extra="allow")

    latency_ms: Optional[float] = Field(
        default=None,
        description="Stage wall-clock execution time in milliseconds.",
    )
    health: Literal["ok", "warning", "failed", "unknown"] = Field(
        default="unknown",
        description="Stage health status consumed by the pipeline visualizer.",
    )
    summary: Optional[str] = Field(
        default=None,
        max_length=500,
        description="One-line human-readable description of stage outcome.",
    )
    detail: Optional[str] = Field(
        default=None,
        max_length=5000,
        description="Extended diagnostic text for the stage (shown in expanded UI view).",
    )
    reason: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="Fallback for detail when detail is absent (e.g. gate rejection reason).",
    )


# =========================
# API I/O（Response）
# =========================


class Alt(BaseModel):
    model_config = ConfigDict(extra="allow")

    # 実運用で id 欠落が起きやすいのでデフォルトを持たせ、後段で補完
    id: str = ""
    title: str = ""
    description: str = ""
    score: float = 1.0
    score_raw: Optional[float] = None

    # WorldModel / Meta 情報を落とさないようにする
    world: Optional[Dict[str, Any]] = None
    meta: Optional[Dict[str, Any]] = None

    @model_validator(mode="after")
    def _ensure_id_title(self) -> "Alt":
        if not self.id:
            self.id = uuid4().hex
        if not self.title:
            # title 空は最悪 "option-<id>" に寄せる
            self.title = f"option-{self.id[:8]}"
        return self


class Gate(BaseModel):
    model_config = ConfigDict(extra="allow")

    risk: float = 0.0
    telos_score: float = 0.0
    bias: Optional[float] = None
    decision_status: DecisionStatusLiteral = "allow"
    reason: Optional[str] = None
    modifications: List[Union[str, Dict[str, Any]]] = Field(default_factory=list, max_length=MAX_LIST_ITEMS)

    # Diagnostic fields consumed by the frontend FujiGateView adapter.
    # Mirrors the same fields on FujiDecision so the adapter's merged lookup works
    # regardless of which object carries the value.
    rule_hit: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Policy rule or keyword that triggered the gate (mirrors FujiDecision.rule_hit).",
    )
    severity: Optional[str] = Field(
        default=None,
        max_length=50,
        description="Qualitative risk severity level (mirrors FujiDecision.severity).",
    )
    remediation_hint: Optional[str] = Field(
        default=None,
        max_length=1000,
        description="Suggested remediation action (mirrors FujiDecision.remediation_hint).",
    )
    risky_text_fragment: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Short excerpt triggering the rule (mirrors FujiDecision.risky_text_fragment).",
    )


class DecideResponse(BaseModel):
    """
    ★狙い（完全版）：
    - model_validate → model_dump を挟んでも evidence が消えない
    - evidence / critique / debate / alternatives が dict / str / BaseModel 混在でも落ちない
    - list_type エラーの根絶（dict/tuple/set/generator も安全に list 化）
    - alternatives/options のミラー互換

    Response layers (for readability, payload shape stays flat):
    1) Core decision contract fields
    2) Audit / debug / internal fields
    3) Backward-compatible legacy fields
    """
    model_config = ConfigDict(extra="allow")

    # レスポンス成否フラグ（サーバーが常に付与）
    ok: bool = True
    error: Optional[str] = None

    request_id: str = ""
    chosen: Dict[str, Any] = Field(default_factory=dict)

    alternatives: List[Alt] = Field(default_factory=list, max_length=MAX_LIST_ITEMS)
    # 互換/レガシー用途のエイリアス（通常は alternatives と同じ）
    options: List[Alt] = Field(default_factory=list, max_length=MAX_LIST_ITEMS)

    values: Optional[ValuesOut] = None

    evidence: List[EvidenceItem] = Field(default_factory=list, max_length=MAX_LIST_ITEMS)

    # critique/debate は “何が来ても落とさない” を最優先
    critique: List[Any] = Field(default_factory=list, max_length=MAX_LIST_ITEMS)
    debate: List[Any] = Field(default_factory=list, max_length=MAX_LIST_ITEMS)

    telos_score: float = 0.0
    fuji: Dict[str, Any] = Field(default_factory=dict)
    rsi_note: Optional[Dict[str, Any]] = None
    extras: Dict[str, Any] = Field(default_factory=dict)
    gate: Gate = Field(default_factory=Gate)
    persona: Dict[str, Any] = Field(default_factory=dict)
    version: str = "veritas-api 1.x"
    evo: Optional[Dict[str, Any]] = None

    # /v1/decide 側に合わせた拡張分
    decision_status: DecisionStatusLiteral = "allow"
    rejection_reason: Optional[str] = None
    gate_decision: GateDecisionLiteral = Field(
        default="unknown",
        description=(
            "Canonical public values: "
            f"{', '.join(CANONICAL_GATE_DECISION_VALUES)}. "
            "`proceed` is a gate pass-through state and is not business approval. "
            "Legacy aliases are compatibility-only and normalized at runtime: "
            f"{', '.join(LEGACY_GATE_DECISION_ALIASES)}. "
            "Accepted compatibility surface: "
            f"{', '.join(COMPATIBLE_GATE_DECISION_VALUES)}."
        ),
    )
    business_decision: BusinessDecisionLiteral = "HOLD"
    next_action: str = "REVISE_AND_RESUBMIT"
    required_evidence: List[str] = Field(default_factory=list, max_length=MAX_LIST_ITEMS)
    missing_evidence: List[str] = Field(default_factory=list, max_length=MAX_LIST_ITEMS)
    satisfied_evidence: List[str] = Field(default_factory=list, max_length=MAX_LIST_ITEMS)
    human_review_required: bool = False
    rationale: Optional[str] = None
    refusal_reason: Optional[str] = None

    # P1-4: Art. 50 — AI interaction mandatory disclosure fields
    ai_disclosure: str = "This response was generated by an AI system (VERITAS OS)."
    regulation_notice: str = "Subject to EU AI Act Regulation (EU) 2024/1689."

    # P3-4: Art. 13 — Third-party notification for high-risk decisions (GAP-17)
    affected_parties_notice: Optional[Dict[str, Any]] = Field(
        default=None,
        description=(
            "When a high-risk AI decision affects third parties (employment, "
            "credit, insurance, etc.), this field contains the notification "
            "record with affected-party rights information."
        ),
    )

    # Audit / debug / internal: MemoryOS メタ
    memory_citations: List[Any] = Field(default_factory=list, max_length=MAX_LIST_ITEMS)
    memory_used_count: int = 0

    # Audit / debug / internal: PlannerOS / ReasonOS
    plan: Optional[Dict[str, Any]] = None
    planner: Optional[Dict[str, Any]] = None
    reason: Optional[Any] = None

    # パイプラインが付与する追加フィールド（正式 schema 昇格）
    # query: 元のユーザー入力。監査・再現・UI 表示で使用。
    query: Optional[str] = Field(
        default=None,
        description="Original user query text, attached by pipeline for audit and replay.",
    )
    # pipeline_steps: EU AI Act 動的コンプライアンスステップ一覧。
    pipeline_steps: Optional[List[str]] = Field(
        default=None,
        description="Dynamic pipeline steps resolved by the orchestrator (EU AI Act compliance).",
    )
    # deterministic_replay: 決定論的再現に必要なスナップショット。
    deterministic_replay: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Snapshot for deterministic replay of this decision.",
    )

    # Governance identity: which governance artifact was in force for this decision.
    governance_identity: Optional[Dict[str, Any]] = Field(
        default=None,
        description=(
            "Identity of the governance artifact in force when this decision "
            "was made.  Includes policy version, digest, signature verification "
            "status, and signer identity."
        ),
    )
    bind_outcome: Optional[FinalOutcome] = Field(
        default=None,
        description="Bind-phase governance outcome linked to this decision when available.",
    )
    bind_failure_reason: Optional[str] = Field(
        default=None,
        max_length=MAX_DESCRIPTION_LENGTH,
        description="Operator-facing reason when bind phase was blocked/escalated/rolled back.",
    )
    bind_reason_code: Optional[str] = Field(
        default=None,
        max_length=MAX_TITLE_LENGTH,
        description="Machine-readable bind reason code for compact governance filtering.",
    )
    bind_receipt_id: Optional[str] = Field(
        default=None,
        max_length=MAX_ID_LENGTH,
        description="Lineage pointer to the bind receipt artifact.",
    )
    execution_intent_id: Optional[str] = Field(
        default=None,
        max_length=MAX_ID_LENGTH,
        description="Lineage pointer to the execution intent linked to bind phase.",
    )
    authority_check_result: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Authority check summary from bind-phase adjudication.",
    )
    constraint_check_result: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Constraint check summary from bind-phase adjudication.",
    )
    drift_check_result: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Drift check summary from bind-phase adjudication.",
    )
    risk_check_result: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Runtime risk check summary from bind-phase adjudication.",
    )
    wat_integrity: Optional[Dict[str, Any]] = Field(
        default=None,
        description=(
            "Canonical additive WAT integrity summary for UI consumers. "
            "Top-level contract mirrors shadow validation outputs while "
            "legacy meta.wat_shadow remains available for compatibility."
        ),
    )
    wat_drift_vector: Optional[Dict[str, float]] = Field(
        default=None,
        description=(
            "Canonical additive WAT drift vector using normalized keys: "
            "policy, signature, observable, temporal."
        ),
    )

    # User-facing summary for simple_qa mode.
    # When present, frontends should display this instead of raw chosen/meta fields.
    user_summary: Optional[str] = Field(
        default=None,
        description=(
            "Polished natural-language answer for user-facing display. "
            "Present in simple_qa and knowledge_qa modes. Frontends should "
            "prefer this over raw chosen/meta fields when available."
        ),
    )

    # persist 用 meta
    meta: Dict[str, Any] = Field(default_factory=dict)
    coercion_events: List[str] = Field(default_factory=list, exclude=True)

    # 監査用 TrustLog（入ってくる形が dict/TrustLog どちらでも OK にしたい）
    trust_log: Optional[Union[TrustLog, Dict[str, Any]]] = None

    # -------------------------
    # BEFORE validators（落ちる前に整形）
    # -------------------------

    @field_validator("request_id", mode="before")
    @classmethod
    def _coerce_request_id(cls, v: Any) -> str:
        if v is None or v == "":
            return uuid4().hex
        return str(v)

    @field_validator("critique", mode="before")
    @classmethod
    def _coerce_critique_to_list(cls, v: Any) -> List[Any]:
        return _as_list(v)

    @field_validator("debate", mode="before")
    @classmethod
    def _coerce_debate_to_list(cls, v: Any) -> List[Any]:
        return _as_list(v)

    @field_validator("alternatives", mode="before")
    @classmethod
    def _coerce_alts(cls, v: Any) -> List[Any]:
        # dict/scalar/list/iterable すべて list 化
        return _as_list(v)

    @field_validator("options", mode="before")
    @classmethod
    def _coerce_opts(cls, v: Any) -> List[Any]:
        return _as_list(v)

    @field_validator("evidence", mode="before")
    @classmethod
    def _coerce_evidence_to_list_of_dicts(cls, v: Any) -> List[Any]:
        """
        evidence が
          - dict 単体
          - str 単体
          - list の中に str / dict / BaseModel / その他
        で来ても “EvidenceItem が食える形” に寄せてから型解決させる。
        """
        if v is None:
            return []

        # dict 単体 → list 化
        if _is_mapping(v):
            v = [dict(v)]

        # str 単体 → list 化（テキスト証拠）
        if isinstance(v, str):
            return [{"source": "text", "snippet": v, "confidence": 0.5}]

        # list/iterable 化
        items = _as_list(v)

        out: List[Any] = []
        for ev in items:
            # EvidenceItem はそのまま
            if isinstance(ev, EvidenceItem):
                out.append(ev)
                continue

            # Pydantic BaseModel は dict 化して情報保持
            if isinstance(ev, BaseModel):
                out.append(ev.model_dump())
                continue

            # dict
            if _is_mapping(ev):
                d = dict(ev)
                if not d.get("source"):
                    d["source"] = "unknown"
                if d.get("uri") is None:
                    u = d.get("url") or d.get("link") or d.get("href") or d.get("URI")
                    if u:
                        d["uri"] = str(u)
                if not d.get("snippet"):
                    if d.get("text"):
                        d["snippet"] = str(d.get("text"))
                    elif d.get("title"):
                        d["snippet"] = str(d.get("title"))
                    elif d.get("uri"):
                        d["snippet"] = str(d.get("uri"))
                    else:
                        d["snippet"] = ""
                out.append(d)
                continue

            # str
            if isinstance(ev, str):
                out.append({"source": "text", "snippet": ev, "confidence": 0.5})
                continue

            # その他
            out.append({"source": "unknown", "snippet": str(ev), "confidence": 0.3})

        return out

    @field_validator("trust_log", mode="before")
    @classmethod
    def _coerce_trust_log(cls, v: Any) -> Any:
        if v is None:
            return None
        if isinstance(v, TrustLog):
            return v
        if _is_mapping(v):
            # dict ならそのまま。後段で TrustLog に寄せる
            return dict(v)
        # 変な型は raw として保持
        return {"raw": str(v)}

    # -------------------------
    # AFTER validator（互換・最終整形）
    # -------------------------

    @model_validator(mode="after")
    def _unify_and_sanitize(self) -> "DecideResponse":
        """Normalize response payload and enforce canonical decision semantics.

        ``alternatives`` is the canonical response contract. Legacy ``options``
        remains available for compatibility, but is kept synchronized so that
        clients can migrate without semantic drift.

        Decision hardening rules:
        - ``gate_decision`` is canonicalized to public values first.
        - Legacy aliases are accepted as compatibility-only inputs.
        - Forbidden ``gate_decision``/``business_decision``/``human_review_required``
          combinations are rejected (no silent correction).
        """
        events: List[str] = []

        # alternatives があって options が空ならミラー（互換）
        if self.alternatives and not self.options:
            self.options = list(self.alternatives)
            events.append("coercion.alternatives_to_options")

        # options があって alternatives が空なら寄せる（逆互換も強化）
        if self.options and not self.alternatives:
            self.alternatives = list(self.options)
            events.append("coercion.options_to_alternatives")

        if self.alternatives and self.options:
            canonical_alts = [alt.model_dump() for alt in self.alternatives]
            canonical_opts = [opt.model_dump() for opt in self.options]
            if canonical_alts != canonical_opts:
                self.options = list(self.alternatives)
                events.append("coercion.response_options_overridden_by_alternatives")
                logger.warning(
                    "DecideResponse had conflicting alternatives/options;"
                    " options were normalized to alternatives",
                )

        # alternatives/options を “必ず Alt” に寄せ切る
        fixed_alts: List[Alt] = []
        for a in list(self.alternatives or []):
            if isinstance(a, Alt):
                fixed_alts.append(a)
            elif isinstance(a, BaseModel):
                fixed_alts.append(Alt.model_validate(a.model_dump()))
            elif _is_mapping(a):
                fixed_alts.append(Alt.model_validate(dict(a)))
            elif isinstance(a, str):
                fixed_alts.append(Alt(title=a))
            else:
                fixed_alts.append(Alt(title=str(a)))
        self.alternatives = fixed_alts

        fixed_opts: List[Alt] = []
        for o in list(self.options or []):
            if isinstance(o, Alt):
                fixed_opts.append(o)
            elif isinstance(o, BaseModel):
                fixed_opts.append(Alt.model_validate(o.model_dump()))
            elif _is_mapping(o):
                fixed_opts.append(Alt.model_validate(dict(o)))
            elif isinstance(o, str):
                fixed_opts.append(Alt(title=o))
            else:
                fixed_opts.append(Alt(title=str(o)))
        self.options = fixed_opts

        # critique/debate は “必ず list” を最終保証
        self.critique = _as_list(self.critique)
        self.debate = _as_list(self.debate)

        # evidence は BEFORE でほぼ正規化済みだが、最後に “必ず EvidenceItem” に寄せ切る
        fixed_ev: List[EvidenceItem] = []
        for ev in list(self.evidence or []):
            if isinstance(ev, EvidenceItem):
                fixed_ev.append(ev)
            elif isinstance(ev, BaseModel):
                fixed_ev.append(EvidenceItem.model_validate(ev.model_dump()))
            elif _is_mapping(ev):
                fixed_ev.append(EvidenceItem.model_validate(dict(ev)))
            elif isinstance(ev, str):
                fixed_ev.append(EvidenceItem(source="text", snippet=ev, confidence=0.5))
            else:
                fixed_ev.append(EvidenceItem(source="unknown", snippet=str(ev), confidence=0.3))
        self.evidence = fixed_ev

        # trust_log を “可能なら TrustLog” に寄せる（落とさない）
        if self.trust_log is not None and not isinstance(self.trust_log, TrustLog):
            if _is_mapping(self.trust_log):
                try:
                    self.trust_log = TrustLog.model_validate(dict(self.trust_log))
                except Exception:
                    # 壊れてても残す（監査上、消すよりマシ）
                    logger.warning("DecideResponse trust_log promotion failed; preserving raw mapping")
                    events.append("coercion.trust_log_promotion_failed")
                    self.trust_log = dict(self.trust_log)

        extras = getattr(self, "__pydantic_extra__", None)
        if isinstance(extras, dict) and extras:
            events.append("coercion.response_extra_keys_allowed")
            logger.warning(
                "DecideResponse accepted %d extra keys: %s",
                len(extras),
                sorted(extras.keys()),
            )

        canonical_gate_decision = canonicalize_public_gate_decision(self.gate_decision)
        if canonical_gate_decision != self.gate_decision:
            self.gate_decision = canonical_gate_decision
            events.append("coercion.gate_decision_canonicalized")

        if self.required_evidence:
            self.required_evidence = unique_preserve_order(
                normalize_required_evidence_keys(self.required_evidence)
            )
            self.satisfied_evidence = unique_preserve_order(
                normalize_required_evidence_keys(self.satisfied_evidence)
            )
            required_set = set(self.required_evidence)
            self.missing_evidence = [
                item
                for item in self.missing_evidence
                if (
                    normalized := normalize_required_evidence_keys([item])
                ) and normalized[0] in required_set
            ]
            self.missing_evidence = unique_preserve_order(self.missing_evidence)

        validate_gate_business_combination(
            gate_decision=self.gate_decision,
            business_decision=self.business_decision,
            human_review_required=self.human_review_required,
        )

        if events:
            unique_events = sorted(set(events))
            self.coercion_events = unique_events
            self.meta.setdefault("x_coerced_fields", unique_events)

        return self


# forward refs を確実に解決
DecideResponse.model_rebuild()


class EvoTips(BaseModel):
    model_config = ConfigDict(extra="allow")

    insights: Dict[str, Any] = Field(default_factory=dict)
    actions: List[str] = Field(default_factory=list)
    next_prompts: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class PersonaState(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str = "VERITAS"
    style: str = "direct, strategic, honest"
    tone: str = "warm"
    principles: List[str] = Field(default_factory=lambda: ["honesty", "dignity", "growth"])
    last_updated: Optional[str] = None


# 対話用（SSEに使う）
class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    message: str = Field(..., max_length=MAX_QUERY_LENGTH)
    session_id: Optional[str] = Field(default=None, max_length=MAX_ID_LENGTH)
    memory_auto_put: bool = True
    persona_evolve: bool = True


# =========================
# Memory API Request Models
# =========================

MAX_MEMORY_TEXT_LENGTH = 100_000  # Max characters for memory text field
MAX_MEMORY_TAGS = 100  # Max tags per memory item
MAX_NOTE_LENGTH = 10_000  # Max characters for feedback notes
ALLOWED_RETENTION_CLASSES = {"short", "standard", "long", "regulated"}


class MemoryPutRequest(BaseModel):
    """Typed request body for POST /v1/memory/put."""

    model_config = ConfigDict(extra="allow")

    user_id: Optional[str] = Field(default=None, max_length=MAX_ID_LENGTH)
    key: Optional[str] = Field(default=None, max_length=MAX_ID_LENGTH)
    text: str = Field(default="", max_length=MAX_MEMORY_TEXT_LENGTH)
    tags: List[str] = Field(default_factory=list)
    value: Any = Field(default_factory=dict)
    kind: str = Field(default="semantic", max_length=MAX_KIND_LENGTH)
    retention_class: Optional[str] = Field(default=None, max_length=MAX_KIND_LENGTH)
    meta: Dict[str, Any] = Field(default_factory=dict)
    expires_at: Optional[int] = None
    legal_hold: bool = False

    @field_validator("tags", mode="before")
    @classmethod
    def _validate_tags(cls, v: Any) -> List[str]:
        if v is None:
            return []
        if not isinstance(v, list):
            v = [v]
        if len(v) > MAX_MEMORY_TAGS:
            raise ValueError(f"too many tags (max {MAX_MEMORY_TAGS})")
        return [str(t) for t in v]

    @field_validator("text", mode="before")
    @classmethod
    def _coerce_text(cls, v: Any) -> str:
        if v is None:
            return ""
        return str(v)

    @field_validator("kind", mode="before")
    @classmethod
    def _coerce_kind(cls, v: Any) -> str:
        if v is None:
            return "semantic"
        return str(v).strip().lower()

    @field_validator("retention_class", mode="before")
    @classmethod
    def _coerce_retention_class(cls, v: Any) -> Optional[str]:
        if v is None:
            return None
        normalized = str(v).strip().lower()
        if normalized not in ALLOWED_RETENTION_CLASSES:
            return None
        return normalized


class MemoryGetRequest(BaseModel):
    """Typed request body for POST /v1/memory/get."""

    user_id: Optional[str] = Field(default=None, max_length=MAX_ID_LENGTH)
    key: str = Field(..., max_length=MAX_ID_LENGTH)


class MemorySearchRequest(BaseModel):
    """Typed request body for POST /v1/memory/search."""

    model_config = ConfigDict(extra="allow")

    user_id: Optional[str] = Field(default=None, max_length=MAX_ID_LENGTH)
    query: str = Field(default="", max_length=MAX_QUERY_LENGTH)
    k: int = Field(default=8, ge=1, le=100)
    min_sim: float = Field(default=0.25, ge=0.0, le=1.0)
    # Use Any so that server-side _validate_memory_kinds() can enforce
    # type checking (rejecting non-string items with a domain error).
    kinds: Any = None

    @field_validator("kinds", mode="before")
    @classmethod
    def _coerce_kinds(cls, v: Any) -> Any:
        if v is None:
            return None
        if isinstance(v, str):
            return [v]
        if isinstance(v, list):
            return v
        return v

    @field_validator("query", mode="before")
    @classmethod
    def _coerce_query(cls, v: Any) -> str:
        if v is None:
            return ""
        return str(v)

    @field_validator("k", mode="before")
    @classmethod
    def _coerce_k(cls, v: Any) -> int:
        try:
            return max(1, min(int(v), 100))
        except (ValueError, TypeError):
            return 8

    @field_validator("min_sim", mode="before")
    @classmethod
    def _coerce_min_sim(cls, v: Any) -> float:
        try:
            return max(0.0, min(float(v), 1.0))
        except (ValueError, TypeError):
            return 0.25


class MemoryEraseRequest(BaseModel):
    """Typed request body for POST /v1/memory/erase."""

    user_id: Optional[str] = Field(default=None, max_length=MAX_ID_LENGTH)
    reason: str = Field(default="user_request", max_length=MAX_SOURCE_LENGTH)
    actor: str = Field(default="api", max_length=MAX_ACTOR_LENGTH)


class TrustFeedbackRequest(BaseModel):
    """Typed request body for POST /v1/trust/feedback."""

    user_id: Optional[str] = Field(default=None, max_length=MAX_ID_LENGTH)
    score: float = Field(default=0.5, ge=0.0, le=1.0)
    note: str = Field(default="", max_length=MAX_NOTE_LENGTH)
    source: str = Field(default="manual", max_length=MAX_ACTOR_LENGTH)

    @field_validator("score", mode="before")
    @classmethod
    def _coerce_score(cls, v: Any) -> float:
        if v is None:
            return 0.5
        try:
            return max(0.0, min(1.0, float(v)))
        except (TypeError, ValueError):
            return 0.5


class TrustFeedbackResponse(BaseModel):
    """Response envelope for POST /v1/trust/feedback."""

    ok: bool = True
    user_id: Optional[str] = None
    error: Optional[str] = None


class GovernancePolicyResponse(BaseModel):
    """Response envelope for GET/PUT /v1/governance/policy."""

    ok: bool = True
    policy: Optional[Dict[str, Any]] = None
    bind_receipt: Optional[BindReceipt] = None
    bind_outcome: Optional[FinalOutcome] = None
    bind_failure_reason: Optional[str] = Field(default=None, max_length=MAX_DESCRIPTION_LENGTH)
    bind_reason_code: Optional[str] = Field(default=None, max_length=MAX_TITLE_LENGTH)
    bind_receipt_id: Optional[str] = Field(default=None, max_length=MAX_ID_LENGTH)
    execution_intent_id: Optional[str] = Field(default=None, max_length=MAX_ID_LENGTH)
    error: Optional[str] = None


class GovernancePolicyHistoryResponse(BaseModel):
    """Response envelope for GET /v1/governance/policy/history."""

    ok: bool = True
    count: int = 0
    history: List[Dict[str, Any]] = Field(default_factory=list)
    error: Optional[str] = None


class GovernanceDecisionExportItem(BaseModel):
    """Public governance decision export record with bind summary fields."""

    request_id: str = ""
    decision_id: str = ""
    decision_status: str = "unknown"
    risk: Optional[float] = None
    created_at: str = ""
    approver: str = "system"
    trace_sha256: Optional[str] = None
    bind_outcome: Optional[FinalOutcome] = None
    bind_failure_reason: Optional[str] = Field(default=None, max_length=MAX_DESCRIPTION_LENGTH)
    bind_reason_code: Optional[str] = Field(default=None, max_length=MAX_TITLE_LENGTH)
    bind_receipt_id: Optional[str] = Field(default=None, max_length=MAX_ID_LENGTH)
    execution_intent_id: Optional[str] = Field(default=None, max_length=MAX_ID_LENGTH)
    authority_check_result: Optional[Dict[str, Any]] = None
    constraint_check_result: Optional[Dict[str, Any]] = None
    drift_check_result: Optional[Dict[str, Any]] = None
    risk_check_result: Optional[Dict[str, Any]] = None


class GovernanceDecisionExportResponse(BaseModel):
    """Response envelope for GET /v1/governance/decisions/export."""

    ok: bool = True
    count: int = 0
    items: List[GovernanceDecisionExportItem] = Field(default_factory=list)
    error: Optional[str] = None


class GovernanceBindReceiptResponse(BaseModel):
    """Response envelope for GET /v1/governance/bind-receipts/{bind_receipt_id}."""

    ok: bool = True
    bind_receipt: Optional[BindReceipt] = None
    bind_outcome: Optional[FinalOutcome] = None
    bind_failure_reason: Optional[str] = Field(default=None, max_length=MAX_DESCRIPTION_LENGTH)
    bind_reason_code: Optional[str] = Field(default=None, max_length=MAX_TITLE_LENGTH)
    bind_receipt_id: Optional[str] = Field(default=None, max_length=MAX_ID_LENGTH)
    execution_intent_id: Optional[str] = Field(default=None, max_length=MAX_ID_LENGTH)
    authority_check_result: Optional[Dict[str, Any]] = None
    constraint_check_result: Optional[Dict[str, Any]] = None
    drift_check_result: Optional[Dict[str, Any]] = None
    risk_check_result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class GovernancePolicyBundlePromoteRequest(BaseModel):
    """Request body for POST /v1/governance/policy-bundles/promote."""

    model_config = ConfigDict(extra="forbid")

    bundle_id: Optional[str] = Field(default=None, max_length=MAX_ID_LENGTH)
    bundle_dir_name: Optional[str] = Field(default=None, max_length=MAX_ID_LENGTH)
    decision_id: str = Field(..., max_length=MAX_ID_LENGTH)
    request_id: str = Field(..., max_length=MAX_ID_LENGTH)
    policy_snapshot_id: str = Field(..., max_length=MAX_ID_LENGTH)
    decision_hash: str = Field(..., max_length=MAX_ID_LENGTH)
    approval_context: Optional[Dict[str, Any]] = None

    @model_validator(mode="after")
    def _validate_bundle_selector(self) -> "GovernancePolicyBundlePromoteRequest":
        """Require exactly one bundle selector and reject traversal patterns."""
        selector_count = int(bool(self.bundle_id)) + int(bool(self.bundle_dir_name))
        if selector_count != 1:
            raise ValueError("exactly one of bundle_id or bundle_dir_name must be provided")
        candidate = (self.bundle_id or self.bundle_dir_name or "").strip()
        if not candidate:
            raise ValueError("bundle selector cannot be empty")
        if any(sep in candidate for sep in ("/", "\\")) or candidate in {".", ".."}:
            raise ValueError("invalid bundle selector")
        return self


class GovernancePolicyBundlePromoteResponse(BaseModel):
    """Response envelope for POST /v1/governance/policy-bundles/promote."""

    ok: bool = True
    bind_receipt: Optional[BindReceipt] = None
    bind_outcome: Optional[FinalOutcome] = None
    bind_failure_reason: Optional[str] = Field(default=None, max_length=MAX_DESCRIPTION_LENGTH)
    bind_reason_code: Optional[str] = Field(default=None, max_length=MAX_TITLE_LENGTH)
    bind_receipt_id: Optional[str] = Field(default=None, max_length=MAX_ID_LENGTH)
    execution_intent_id: Optional[str] = Field(default=None, max_length=MAX_ID_LENGTH)
    error: Optional[str] = None


class GovernanceBindReceiptListResponse(BaseModel):
    """Response envelope for GET /v1/governance/bind-receipts."""

    ok: bool = True
    count: int = 0
    items: List[BindReceipt] = Field(default_factory=list)
    error: Optional[str] = None
