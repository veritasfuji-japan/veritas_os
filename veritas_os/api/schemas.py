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

    user_id: str = Field(..., max_length=500)
    session_id: Optional[str] = Field(default=None, max_length=500)
    query: str = Field(..., max_length=MAX_QUERY_LENGTH)

    goals: Optional[List[str]] = None
    constraints: Optional[List[str]] = None

    # 返答の時間軸（未指定可）
    time_horizon: Optional[Literal["short", "mid", "long"]] = None

    # 将来の好み/スタイル切替のフック
    preferences: Optional[List[str]] = None
    telos_weights: Optional[Dict[str, float]] = None
    affect_hint: Optional[Dict[str, str]] = None
    response_style: Optional[Literal["logic", "emotional", "business", "expert", "casual"]] = None


class Option(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: Optional[str] = Field(default=None, max_length=500)
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

    source: str = Field(default="unknown", max_length=500)
    uri: Optional[str] = Field(default=None, max_length=2000)
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
        except Exception:
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

    status: Literal["allow", "modify", "rejected", "block", "abstain"]
    reasons: List[str] = Field(default_factory=list)
    violations: List[str] = Field(default_factory=list)


class TrustLog(BaseModel):
    model_config = ConfigDict(extra="allow")

    request_id: str
    created_at: str
    sources: List[str] = Field(default_factory=list)
    critics: List[str] = Field(default_factory=list)
    checks: List[str] = Field(default_factory=list)

    # 実運用の落下を避けるため、デフォルトを持たせる（必須思想なら外してOK）
    approver: str = "system"

    sha256_prev: Optional[str] = None


# =========================
# API I/O（Request）
# =========================


class AltItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: Optional[str] = Field(default=None, max_length=500)
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
    decision_status: Literal["allow", "modify", "rejected", "block", "abstain"] = "allow"
    reason: Optional[str] = None
    modifications: List[Union[str, Dict[str, Any]]] = Field(default_factory=list)


class DecideResponse(BaseModel):
    """
    ★狙い（完全版）：
    - model_validate → model_dump を挟んでも evidence が消えない
    - evidence / critique / debate / alternatives が dict / str / BaseModel 混在でも落ちない
    - list_type エラーの根絶（dict/tuple/set/generator も安全に list 化）
    - alternatives/options のミラー互換
    """
    model_config = ConfigDict(extra="allow")

    request_id: str = ""
    chosen: Dict[str, Any] = Field(default_factory=dict)

    alternatives: List[Alt] = Field(default_factory=list)
    # 互換のために残す（通常は alternatives と同じ）
    options: List[Alt] = Field(default_factory=list)

    values: Optional[ValuesOut] = None

    evidence: List[EvidenceItem] = Field(default_factory=list)

    # critique/debate は “何が来ても落とさない” を最優先
    critique: List[Any] = Field(default_factory=list)
    debate: List[Any] = Field(default_factory=list)

    telos_score: float = 0.0
    fuji: Dict[str, Any] = Field(default_factory=dict)
    rsi_note: Optional[Dict[str, Any]] = None
    extras: Dict[str, Any] = Field(default_factory=dict)
    gate: Gate = Field(default_factory=Gate)
    persona: Dict[str, Any] = Field(default_factory=dict)
    version: str = "veritas-api 1.x"
    evo: Optional[Dict[str, Any]] = None

    # /v1/decide 側に合わせた拡張分
    decision_status: Literal["allow", "modify", "rejected", "block", "abstain"] = "allow"
    rejection_reason: Optional[str] = None

    # MemoryOS メタ
    memory_citations: List[Any] = Field(default_factory=list)
    memory_used_count: int = 0

    # PlannerOS / ReasonOS
    plan: Optional[Dict[str, Any]] = None
    planner: Optional[Dict[str, Any]] = None
    reason: Optional[Any] = None

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
        """Normalize response payload and expose coercion metadata for audits.

        ``alternatives`` is the canonical response contract. Legacy ``options``
        remains available for compatibility, but is kept synchronized so that
        clients can migrate without semantic drift.
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
    session_id: Optional[str] = Field(default=None, max_length=500)
    memory_auto_put: bool = True
    persona_evolve: bool = True
