# veritas_os/api/schemas.py
from __future__ import annotations

from typing import Any, Dict, List, Optional, Literal, Union
from pydantic import BaseModel, Field, ConfigDict, model_validator


# =========================
# Core context / options
# =========================

class Context(BaseModel):
    model_config = ConfigDict(extra="allow")

    user_id: str
    session_id: Optional[str] = None
    query: str

    goals: Optional[List[str]] = None
    constraints: Optional[List[str]] = None

    # 返答の時間軸（未指定可）
    time_horizon: Optional[Literal["short", "mid", "long"]] = None

    # 将来の好み/スタイル切替のフック
    preferences: Optional[List[str]] = None
    telos_weights: Optional[Dict[str, float]] = None
    affect_hint: Optional[Dict[str, str]] = None
    response_style: Optional[
        Literal["logic", "emotional", "business", "expert", "casual"]
    ] = None


class Option(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    score: Optional[float] = None
    text: Optional[str] = None        # 互換（title の別名）
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

    source: str = "unknown"
    uri: Optional[str] = None
    title: Optional[str] = None
    snippet: str = ""
    confidence: float = 0.7

    @model_validator(mode="after")
    def _coerce_minimum_contract(self) -> "EvidenceItem":
        # source
        if not self.source:
            self.source = "unknown"

        # uri: url/link/href 互換
        if self.uri is None:
            u = None
            if isinstance(getattr(self, "__pydantic_extra__", None), dict):
                ex = self.__pydantic_extra__ or {}
                u = ex.get("url") or ex.get("link") or ex.get("href") or ex.get("URI")
            if u:
                self.uri = str(u)

        # snippet: 無ければ title -> uri -> "" の順で埋める
        if not self.snippet:
            if self.title:
                self.snippet = str(self.title)
            elif self.uri:
                self.snippet = str(self.uri)
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
    approver: str
    sha256_prev: Optional[str] = None


# =========================
# API I/O（Request）
# =========================

class AltItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: Optional[str] = None
    title: Optional[str] = None
    text: Optional[str] = None        # 互換（title の別名）
    description: Optional[str] = None
    score: Optional[float] = None
    score_raw: Optional[float] = None

    @model_validator(mode="after")
    def _unify_text(self) -> "AltItem":
        if (not self.title) and self.text:
            self.title = self.text
        return self


AltIn = Union[AltItem, Option, Dict[str, Any]]


class DecideRequest(BaseModel):
    # 未知フィールドも保持（将来拡張・Swagger差異に強い）
    model_config = ConfigDict(extra="allow")

    query: str = ""
    context: Dict[str, Any] = Field(default_factory=dict)

    # ★ 新旧どちらでも受けられるよう両方定義
    alternatives: Optional[List[AltItem]] = None
    options: Optional[List[AltItem]] = None

    min_evidence: int = 1
    memory_auto_put: bool = True
    persona_evolve: bool = True

    # 受信後に options -> alternatives へ片寄せ（alternatives 優先）
    @model_validator(mode="after")
    def _unify_options(self) -> "DecideRequest":
        if (self.alternatives is None or len(self.alternatives) == 0) and self.options:
            self.alternatives = self.options
        return self


# =========================
# API I/O（Response）
# =========================

class Alt(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    title: str
    description: str = ""
    score: float = 1.0
    score_raw: Optional[float] = None

    # WorldModel / Meta 情報を落とさないようにする
    world: Optional[Dict[str, Any]] = None
    meta: Optional[Dict[str, Any]] = None


class Gate(BaseModel):
    model_config = ConfigDict(extra="allow")

    risk: float = 0.0
    telos_score: float = 0.0
    bias: Optional[float] = None
    decision_status: Literal["allow", "modify", "rejected"] = "allow"
    reason: Optional[str] = None
    modifications: List[Union[str, Dict[str, Any]]] = Field(default_factory=list)


class DecideResponse(BaseModel):
    """
    ★狙い：
    - pipeline が model_validate → model_dump を挟んでも evidence(特に source="web") が消えない
    - evidence が str/dict/BaseModel 混在でも受け取って正規化する
    """
    model_config = ConfigDict(extra="allow")

    request_id: str
    chosen: Dict[str, Any] = Field(default_factory=dict)
    alternatives: List[Alt] = Field(default_factory=list)

    # 互換のために残すが、通常は alternatives と同じものを返す
    options: List[Alt] = Field(default_factory=list)

    values: Optional[ValuesOut] = None

    # ★ここが重要：Any ではなく EvidenceItem で受ける（落ちにくい）
    evidence: List[EvidenceItem] = Field(default_factory=list)

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

    # ここから下が /v1/decide 側に合わせた拡張分
    decision_status: Literal["allow", "modify", "rejected"] = "allow"
    rejection_reason: Optional[str] = None

    # MemoryOS メタ
    memory_citations: List[Any] = Field(default_factory=list)
    memory_used_count: int = 0

    # PlannerOS / ReasonOS
    plan: Optional[Dict[str, Any]] = None
    planner: Optional[Dict[str, Any]] = None
    reason: Optional[Any] = None

    # persist 用に付けている meta（memory_evidence_count など）
    meta: Dict[str, Any] = Field(default_factory=dict)

    # ★ 監査用 TrustLog（必須ではないので Optional）
    trust_log: Optional[Dict[str, Any]] = None

    @model_validator(mode="after")
    def _unify_and_sanitize(self) -> "DecideResponse":
        # alternatives があって options が空ならミラー（互換）
        if self.alternatives and not self.options:
            self.options = list(self.alternatives)

        # evidence が壊れて/混在して来ても必ず EvidenceItem に寄せる
        fixed: List[EvidenceItem] = []
        raw_list: List[Any] = list(self.evidence or [])

        for ev in raw_list:
            if isinstance(ev, EvidenceItem):
                fixed.append(ev)
                continue

            # str -> EvidenceItem
            if isinstance(ev, str):
                fixed.append(EvidenceItem(source="text", snippet=ev, confidence=0.5))
                continue

            # dict -> EvidenceItem
            if isinstance(ev, dict):
                d = dict(ev)

                # source を必ず埋める（テスト契約: web ソース evidence の存在）
                if not d.get("source"):
                    d["source"] = "unknown"

                # uri 互換
                if d.get("uri") is None:
                    u = d.get("url") or d.get("link") or d.get("href")
                    if u:
                        d["uri"] = str(u)

                # snippet 互換
                if not d.get("snippet"):
                    if d.get("text"):
                        d["snippet"] = str(d.get("text"))
                    elif d.get("title"):
                        d["snippet"] = str(d.get("title"))
                    elif d.get("uri"):
                        d["snippet"] = str(d.get("uri"))
                    else:
                        d["snippet"] = ""

                fixed.append(EvidenceItem.model_validate(d))
                continue

            # その他 -> stringify
            fixed.append(EvidenceItem(source="unknown", snippet=str(ev), confidence=0.3))

        self.evidence = fixed
        return self


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

    message: str
    session_id: Optional[str] = None
    memory_auto_put: bool = True
    persona_evolve: bool = True

