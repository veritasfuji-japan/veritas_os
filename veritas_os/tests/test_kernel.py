"""Regression tests for ``veritas_os.core.kernel`` (C-5 hardening).

This suite adds focused coverage for the main ``decide`` flow so that
core decision behavior remains stable across refactors.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict

from veritas_os.core import kernel


class _DummyMemoryStore:
    """Minimal in-memory sink used to stub ``mem_core.MEM`` in tests."""

    def put(self, *args: Any, **kwargs: Any) -> None:
        return None


def _patch_minimal_decide_dependencies(monkeypatch) -> None:
    """Patch heavyweight dependencies so ``kernel.decide`` can run deterministically."""

    monkeypatch.setattr(
        kernel.world_model,
        "inject_state_into_context",
        lambda context, user_id: dict(context),
    )
    monkeypatch.setattr(
        kernel.mem_core,
        "summarize_for_planner",
        lambda user_id, query, limit: "summary",
    )
    monkeypatch.setattr(
        kernel.adapt,
        "load_persona",
        lambda: {"bias_weights": {}},
    )
    monkeypatch.setattr(kernel.adapt, "clean_bias_weights", lambda weights: {})
    monkeypatch.setattr(kernel.adapt, "save_persona", lambda persona: None)
    monkeypatch.setattr(
        kernel.planner_core,
        "plan_for_veritas_agi",
        lambda context, query: {
            "steps": [{"id": "s1", "title": "Collect facts", "detail": "A"}]
        },
    )
    monkeypatch.setattr(kernel, "_score_alternatives", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        kernel.fuji_core,
        "evaluate",
        lambda *args, **kwargs: {
            "status": "allow",
            "decision_status": "allow",
            "risk": 0.1,
            "modifications": [],
        },
    )
    monkeypatch.setattr(kernel.mem_core, "get_evidence_for_decision", lambda *args, **kwargs: [])
    monkeypatch.setattr(kernel.mem_core, "MEM", _DummyMemoryStore())
    monkeypatch.setattr(kernel.world_model, "update_from_decision", lambda **kwargs: None)


def test_decide_fast_mode_returns_structured_response(monkeypatch) -> None:
    """Fast mode returns core response fields and records stage skip reasons."""

    _patch_minimal_decide_dependencies(monkeypatch)

    context: Dict[str, Any] = {
        "user_id": "u-1",
        "fast": True,
        "_episode_saved_by_pipeline": True,
        "_world_state_updated_by_pipeline": True,
        "_daily_plans_generated_by_pipeline": True,
    }

    result = asyncio.run(kernel.decide(context, "今日は何を進めるべき？", alternatives=None))

    assert result["decision_status"] == "allow"
    assert result["chosen"]["title"] == "Collect facts"
    assert result["gate"]["decision_status"] == "allow"
    assert result["extras"]["_skip_reasons"]["env_tools"] == "fast_mode"


def test_decide_uses_pipeline_evidence_and_skips_memory_search(monkeypatch) -> None:
    """When pipeline evidence is injected, memory search stage is skipped."""

    _patch_minimal_decide_dependencies(monkeypatch)

    monkeypatch.setattr(
        kernel.mem_core,
        "summarize_for_planner",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("unexpected call")),
    )

    pipeline_evidence = [
        {
            "source": "pipeline",
            "uri": "memory://1",
            "snippet": "cached",
            "confidence": 0.9,
        }
    ]
    context: Dict[str, Any] = {
        "user_id": "u-2",
        "fast": True,
        "_pipeline_evidence": pipeline_evidence,
        "_episode_saved_by_pipeline": True,
        "_world_state_updated_by_pipeline": True,
        "_daily_plans_generated_by_pipeline": True,
    }

    result = asyncio.run(kernel.decide(context, "query", alternatives=None))

    assert result["memory_evidence_count"] == 1
    assert result["extras"]["memory"]["source"] == "pipeline_provided"
    assert result["extras"]["_skip_reasons"]["memory_search"] == "provided_by_pipeline"


def test_decide_auto_doctor_warns_without_confinement(monkeypatch) -> None:
    """Auto-doctor must warn and skip when confinement profile is unavailable."""

    _patch_minimal_decide_dependencies(monkeypatch)
    monkeypatch.setattr(kernel, "_is_doctor_confinement_profile_active", lambda: False)

    context: Dict[str, Any] = {
        "user_id": "u-3",
        "fast": True,
        "auto_doctor": True,
        "_episode_saved_by_pipeline": True,
        "_world_state_updated_by_pipeline": True,
        "_daily_plans_generated_by_pipeline": True,
    }

    result = asyncio.run(kernel.decide(context, "query", alternatives=None))

    assert result["extras"]["doctor"]["skipped"] == "confinement_required"
    assert "security_warning" in result["extras"]["doctor"]
