# tests/test_kernel_episode.py
# -*- coding: utf-8 -*-
"""Unit tests for kernel_episode.py — episode logging side-effects."""
from __future__ import annotations

from typing import Any, Dict, List

import pytest

from veritas_os.core.kernel_episode import save_episode


# ============================================================
# Helpers
# ============================================================

class FakeMemStore:
    """In-memory stub for mem_core.MEM."""
    def __init__(self, *, use_3arg: bool = False):
        self.calls: List[tuple] = []
        self._use_3arg = use_3arg

    def put(self, *args, **kwargs):
        if self._use_3arg and len(args) == 2:
            # Simulate TypeError for 2-arg call → trigger 3-arg fallback
            raise TypeError("requires 3 args")
        self.calls.append((args, kwargs))


class FakeMemCore:
    def __init__(self, *, use_3arg: bool = False):
        self.MEM = FakeMemStore(use_3arg=use_3arg)


def _noop_redact(payload):
    return payload


def _redact_with_change(payload):
    """Simulate PII detection by returning a different object."""
    import copy
    result = copy.deepcopy(payload)
    result["_redacted"] = True
    return result


# ============================================================
# Tests
# ============================================================

class TestSaveEpisode:
    def test_basic_save(self):
        mem = FakeMemCore()
        extras: Dict[str, Any] = {}

        save_episode(
            query="what to do",
            chosen={"title": "rest", "id": "c1"},
            ctx={"user_id": "u1", "request_id": "r1"},
            intent="health",
            mode="normal",
            telos_score=0.5,
            req_id="r1",
            mem_core=mem,
            redact_payload_fn=_noop_redact,
            extras=extras,
        )

        assert len(mem.MEM.calls) == 1
        args = mem.MEM.calls[0][0]
        assert args[0] == "episodic"
        record = args[1]
        assert "rest" in record["text"]
        assert "episode" in record["tags"]

    def test_skipped_when_pipeline_saved(self):
        mem = FakeMemCore()
        extras: Dict[str, Any] = {}

        save_episode(
            query="q",
            chosen={"title": "x"},
            ctx={"_episode_saved_by_pipeline": True},
            intent="plan",
            mode="",
            telos_score=0.5,
            req_id="r1",
            mem_core=mem,
            redact_payload_fn=_noop_redact,
            extras=extras,
        )

        assert len(mem.MEM.calls) == 0

    def test_pii_redaction_warning(self):
        mem = FakeMemCore()
        extras: Dict[str, Any] = {}

        save_episode(
            query="q",
            chosen={"title": "x"},
            ctx={"user_id": "u1"},
            intent="plan",
            mode="",
            telos_score=0.5,
            req_id="r1",
            mem_core=mem,
            redact_payload_fn=_redact_with_change,
            extras=extras,
        )

        assert extras["memory_log"]["warning"] == (
            "PII detected in episode log; masked before persistence."
        )

    def test_3arg_fallback(self):
        mem = FakeMemCore(use_3arg=True)
        extras: Dict[str, Any] = {}

        save_episode(
            query="q",
            chosen={"title": "x"},
            ctx={"user_id": "u1"},
            intent="plan",
            mode="",
            telos_score=0.5,
            req_id="r1",
            mem_core=mem,
            redact_payload_fn=_noop_redact,
            extras=extras,
        )

        # Should have used 3-arg fallback
        assert len(mem.MEM.calls) == 1
        args = mem.MEM.calls[0][0]
        assert args[0] == "u1"
        assert args[1].startswith("decision:")

    def test_error_captured(self):
        class BadMem:
            class MEM:
                @staticmethod
                def put(*args, **kwargs):
                    raise OSError("disk full")

        extras: Dict[str, Any] = {}

        save_episode(
            query="q",
            chosen={"title": "x"},
            ctx={},
            intent="plan",
            mode="",
            telos_score=0.5,
            req_id="r1",
            mem_core=BadMem(),
            redact_payload_fn=_noop_redact,
            extras=extras,
        )

        assert "error" in extras["memory_log"]
        assert "disk full" in extras["memory_log"]["error"]
