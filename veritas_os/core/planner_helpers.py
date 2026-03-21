from __future__ import annotations

from typing import Dict, List, TypedDict

from .planner_normalization import normalize_float


class StepDict(TypedDict, total=False):
    """Planner step definition for normalized step payloads."""

    id: str
    title: str
    detail: str
    why: str
    eta_hours: float
    risk: float
    dependencies: List[str]


def wants_inventory_step(
    query: str, context: Dict[str, object] | None = None
) -> bool:
    """Return whether the query explicitly requests inventory-first planning."""
    _ = context or {}
    q = (query or "").strip()
    if not q:
        return False
    ql = q.lower()

    if "step1" in ql or "step 1" in ql:
        return True
    if "棚卸" in q or "棚おろし" in q:
        return True
    if ("現状" in q) and ("整理" in q or "把握" in q or "棚卸" in q):
        return True
    if "inventory" in ql:
        return True
    return False


def normalize_step(
    step: StepDict,
    default_eta_hours: float = 1.0,
    default_risk: float = 0.1,
) -> StepDict:
    """Normalize a planner step into safe scalar and dependency values."""
    normalized_step: StepDict = dict(step)

    eta_candidate = normalized_step.get("eta_hours", default_eta_hours)
    normalized_step["eta_hours"] = normalize_float(
        eta_candidate,
        field_name="eta_hours",
        default_override=default_eta_hours,
    )

    risk_candidate = normalized_step.get("risk", default_risk)
    normalized_step["risk"] = normalize_float(
        risk_candidate,
        field_name="risk",
        default_override=default_risk,
    )

    dependencies = normalized_step.get("dependencies")
    if not isinstance(dependencies, list):
        normalized_step["dependencies"] = []
    else:
        normalized_step["dependencies"] = [str(dep) for dep in dependencies]

    return normalized_step


def normalize_steps_list(
    steps: List[StepDict] | None,
    default_eta_hours: float = 1.0,
    default_risk: float = 0.1,
) -> List[StepDict]:
    """Normalize a step list while dropping malformed non-dict elements."""
    if not isinstance(steps, list):
        return []

    normalized_steps: List[StepDict] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        normalized_steps.append(
            normalize_step(
                step,
                default_eta_hours=default_eta_hours,
                default_risk=default_risk,
            )
        )
    return normalized_steps


def is_simple_qa(query: str, context: Dict[str, object] | None = None) -> bool:
    """Return whether a query should bypass heavy planning as simple QA."""
    ctx = context or {}

    if ctx.get("mode") == "simple_qa" or ctx.get("simple_qa"):
        return True

    q = (query or "").strip()
    if not q:
        return False

    q_lower = q.lower()
    agi_block_keywords = [
        "agi",
        "ＡＧＩ",
        "veritas",
        "ヴェリタス",
        "ベリタス",
        "proto-agi",
        "プロトagi",
    ]
    if any(keyword in q or keyword in q_lower for keyword in agi_block_keywords):
        return False

    question_prefixes = (
        "what",
        "why",
        "when",
        "where",
        "who",
        "which",
        "how",
        "can ",
        "could ",
        "should ",
        "is ",
        "are ",
        "do ",
        "does ",
        "did ",
    )
    question_endings = (
        "か",
        "かね",
        "かな",
        "でしょうか",
        "教えて",
        "を教えて",
        "知りたい",
    )
    looks_question = (
        ("?" in q)
        or ("？" in q)
        or q_lower.startswith(question_prefixes)
        or q.endswith(question_endings)
    )
    has_plan_words = any(
        keyword in q
        for keyword in [
            "どう進め",
            "進め方",
            "計画",
            "プラン",
            "ロードマップ",
            "タスク",
        ]
    ) or any(
        keyword in q_lower
        for keyword in [
            "roadmap",
            "plan",
            "strategy",
            "next step",
            "next steps",
            "implementation",
            "implement",
            "task",
            "tasks",
        ]
    )

    return len(q) <= 40 and looks_question and not has_plan_words
