# tests/test_kernel_post_choice.py
# -*- coding: utf-8 -*-
"""Unit tests for kernel_post_choice.py — post-choice enrichment helpers."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, Dict

import pytest

from veritas_os.core.kernel_post_choice import (
    enrich_affect,
    enrich_reason,
    enrich_reflection,
)


# ============================================================
# Helpers
# ============================================================

def _run(coro):
    """Run an async coroutine synchronously."""
    return asyncio.run(coro)


def _mk_extras() -> Dict[str, Any]:
    return {}


def _mk_chosen() -> Dict[str, Any]:
    return {"id": "c1", "title": "Test choice", "description": "", "score": 1.0}


def _mk_fuji() -> Dict[str, Any]:
    return {"risk": 0.1, "decision_status": "allow", "modifications": []}


# ============================================================
# enrich_affect
# ============================================================

class TestEnrichAffect:
    def test_success(self):
        class FakeAffect:
            def reflect(self, data):
                return {"boost": 0.05, "tips": []}

        extras = _mk_extras()
        _run(enrich_affect(
            query="test query",
            chosen=_mk_chosen(),
            fuji_result=_mk_fuji(),
            telos_score=0.5,
            affect_core=FakeAffect(),
            extras=extras,
        ))
        assert extras["affect"]["meta"] == {"boost": 0.05, "tips": []}

    def test_error_captured(self):
        class BrokenAffect:
            def reflect(self, data):
                raise RuntimeError("boom")

        extras = _mk_extras()
        _run(enrich_affect(
            query="test",
            chosen=_mk_chosen(),
            fuji_result=_mk_fuji(),
            telos_score=0.5,
            affect_core=BrokenAffect(),
            extras=extras,
        ))
        assert "meta_error" in extras["affect"]
        assert "boom" in extras["affect"]["meta_error"]


# ============================================================
# enrich_reason
# ============================================================

class TestEnrichReason:
    def test_success_sync(self):
        class FakeReason:
            def generate_reason(self, **kwargs):
                return {"text": "because reasons"}

        extras = _mk_extras()
        _run(enrich_reason(
            query="q",
            telos_score=0.5,
            fuji_result=_mk_fuji(),
            reason_core=FakeReason(),
            user_id="cli",
            mode="",
            intent="plan",
            planner=None,
            extras=extras,
        ))
        assert extras["affect"]["natural"] == {"text": "because reasons"}

    def test_success_async(self):
        class AsyncReason:
            async def generate_reason(self, **kwargs):
                return {"text": "async reasons"}

        extras = _mk_extras()
        _run(enrich_reason(
            query="q",
            telos_score=0.5,
            fuji_result=_mk_fuji(),
            reason_core=AsyncReason(),
            user_id="cli",
            mode="",
            intent="plan",
            planner=None,
            extras=extras,
        ))
        assert extras["affect"]["natural"] == {"text": "async reasons"}

    def test_reason_core_none(self):
        extras = _mk_extras()
        _run(enrich_reason(
            query="q",
            telos_score=0.5,
            fuji_result=_mk_fuji(),
            reason_core=None,
            user_id="cli",
            mode="",
            intent="plan",
            planner=None,
            extras=extras,
        ))
        assert "natural_error" in extras["affect"]

    def test_error_captured(self):
        class BadReason:
            def generate_reason(self, **kwargs):
                raise ValueError("bad")

        extras = _mk_extras()
        _run(enrich_reason(
            query="q",
            telos_score=0.5,
            fuji_result=_mk_fuji(),
            reason_core=BadReason(),
            user_id="cli",
            mode="",
            intent="plan",
            planner=None,
            extras=extras,
        ))
        assert "bad" in extras["affect"]["natural_error"]


# ============================================================
# enrich_reflection
# ============================================================

class TestEnrichReflection:
    def test_skipped_in_fast_mode(self):
        class FakeReason:
            def generate_reflection_template(self, **kwargs):
                return {"template": "reflect"}

        extras = _mk_extras()
        _run(enrich_reflection(
            query="q",
            chosen=_mk_chosen(),
            fuji_result={"risk": 0.9},
            telos_score=0.5,
            reason_core=FakeReason(),
            planner=None,
            stakes=0.9,
            fast_mode=True,
            extras=extras,
        ))
        # Should not produce any affect key since fast_mode skips
        assert "affect" not in extras or "reflection_template" not in extras.get("affect", {})

    def test_skipped_low_stakes_low_risk(self):
        class FakeReason:
            def generate_reflection_template(self, **kwargs):
                return {"template": "reflect"}

        extras = _mk_extras()
        _run(enrich_reflection(
            query="q",
            chosen=_mk_chosen(),
            fuji_result={"risk": 0.1},
            telos_score=0.5,
            reason_core=FakeReason(),
            planner=None,
            stakes=0.3,
            fast_mode=False,
            extras=extras,
        ))
        assert "affect" not in extras or "reflection_template" not in extras.get("affect", {})

    def test_runs_on_high_stakes(self):
        class FakeReason:
            def generate_reflection_template(self, **kwargs):
                return {"template": "reflect on this"}

        extras = _mk_extras()
        _run(enrich_reflection(
            query="q",
            chosen=_mk_chosen(),
            fuji_result={"risk": 0.1},
            telos_score=0.5,
            reason_core=FakeReason(),
            planner=None,
            stakes=0.8,
            fast_mode=False,
            extras=extras,
        ))
        assert extras["affect"]["reflection_template"] == {"template": "reflect on this"}

    def test_runs_on_high_risk(self):
        class AsyncReason:
            async def generate_reflection_template(self, **kwargs):
                return {"template": "high risk"}

        extras = _mk_extras()
        _run(enrich_reflection(
            query="q",
            chosen=_mk_chosen(),
            fuji_result={"risk": 0.7},
            telos_score=0.5,
            reason_core=AsyncReason(),
            planner=None,
            stakes=0.3,
            fast_mode=False,
            extras=extras,
        ))
        assert extras["affect"]["reflection_template"] == {"template": "high risk"}

    def test_reason_core_none(self):
        extras = _mk_extras()
        _run(enrich_reflection(
            query="q",
            chosen=_mk_chosen(),
            fuji_result={"risk": 0.9},
            telos_score=0.5,
            reason_core=None,
            planner=None,
            stakes=0.9,
            fast_mode=False,
            extras=extras,
        ))
        # No error, just no template produced
        assert "affect" not in extras or "reflection_template" not in extras.get("affect", {})

    def test_error_captured(self):
        class BadReason:
            def generate_reflection_template(self, **kwargs):
                raise TypeError("type err")

        extras = _mk_extras()
        _run(enrich_reflection(
            query="q",
            chosen=_mk_chosen(),
            fuji_result={"risk": 0.9},
            telos_score=0.5,
            reason_core=BadReason(),
            planner=None,
            stakes=0.9,
            fast_mode=False,
            extras=extras,
        ))
        assert "type err" in extras["affect"]["reflection_template_error"]
