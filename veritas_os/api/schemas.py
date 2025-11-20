# veritas _os/api/schemas.py
from __future__ import annotations

from typing import Any, Dict, List, Optional, Literal, Union
from pydantic import BaseModel, Field, ConfigDict, model_validator



# =========================
# Core context / options
# =========================

class Context(BaseModel):
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
    id: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    score: Optional[float] = None
    text: Optional[str] = None        # 互換（title の別名）
    score_raw: Optional[float] = None


# =========================
# Evidence / critique / debate
# =========================
class ValuesOut(BaseModel):
    scores: Dict[str, float]
    total: float
    top_factors: List[str]
    rationale: str
    # value-learning で書き込んでいる EMA を受け取る用
    ema: Optional[float] = None

class EvidenceItem(BaseModel):
    source: str
    uri: Optional[str] = None
    snippet: str
    confidence: float = 0.7


class CritiqueItem(BaseModel):
    issue: str
    severity: Literal["low", "med", "high"] = "med"
    fix: Optional[str] = None


class DebateView(BaseModel):
    stance: str
    argument: str
    score: float


# =========================
# Safety / trust
# =========================

class FujiDecision(BaseModel):
    status: Literal["allow", "modify","rejected", "block", "abstain"]
    reasons: List[str] = Field(default_factory=list)
    violations: List[str] = Field(default_factory=list)


class TrustLog(BaseModel):
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
    id: Optional[str] = None
    title: Optional[str] = None
    text: Optional[str] = None        # 互換（title の別名）
    description: Optional[str] = None
    score: Optional[float] = None
    score_raw: Optional[float] = None


Alt = Union[AltItem, Option, Dict[str, Any]]
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
    id: str
    title: str
    description: str = ""
    score: float = 1.0
    score_raw: Optional[float] = None

    # WorldModel / Meta 情報を落とさないようにする
    world: Optional[Dict[str, Any]] = None
    meta: Optional[Dict[str, Any]] = None


class Gate(BaseModel):
    risk: float = 0.0
    telos_score: float = 0.0
    bias: Optional[float] = None
    decision_status: Literal["allow", "modify", "rejected"] = "allow"
    reason: Optional[str] = None
    modifications: List[Union[str, Dict[str, Any]]] = Field(default_factory=list)


class DecideResponse(BaseModel):
    # 追加フィールドを落とさないための保険
    model_config = ConfigDict(extra="allow")

    request_id: str
    chosen: Dict[str, Any] = Field(default_factory=dict)
    alternatives: List[Alt] = Field(default_factory=list)

    # 互換のために残すが、通常は alternatives と同じものを返す
    options: List[Alt] = Field(default_factory=list)

    values: Optional[ValuesOut] = None
    evidence: List[Any] = Field(default_factory=list)
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


DecideResponse.model_rebuild()


class EvoTips(BaseModel):
    insights: Dict[str, Any] = Field(default_factory=dict)
    actions: List[str] = Field(default_factory=list)
    next_prompts: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class PersonaState(BaseModel):
    name: str = "VERITAS"
    style: str = "direct, strategic, honest"
    tone: str = "warm"
    principles: List[str] = Field(
        default_factory=lambda: ["honesty", "dignity", "growth"]
    )
    last_updated: Optional[str] = None


# 対話用（SSEに使う）
class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    memory_auto_put: bool = True
    persona_evolve: bool = True
