# -*- coding: utf-8 -*-
"""Kernel 単体テスト

DecisionKernel / scoring / episode / doctor / stages の統合テスト。"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


# ============================================================
# Source: test_kernel_post_choice.py
# ============================================================

# tests/test_kernel_post_choice.py
# -*- coding: utf-8 -*-
"""Unit tests for kernel_post_choice.py — post-choice enrichment helpers."""

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


# ============================================================
# Source: test_kernel_episode.py
# ============================================================

# tests/test_kernel_episode.py
# -*- coding: utf-8 -*-
"""Unit tests for kernel_episode.py — episode logging side-effects."""

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


# ============================================================
# Source: test_kernel_doctor.py
# ============================================================

# tests/test_kernel_doctor.py
# -*- coding: utf-8 -*-
"""Unit tests for kernel_doctor.py — doctor/security utilities.

These tests verify that the functions extracted from kernel.py into
kernel_doctor.py behave identically. They also confirm backward-compatible
access via ``kernel._is_doctor_confinement_profile_active`` etc.
"""

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from veritas_os.core.kernel_doctor import (
    _read_proc_self_status_seccomp,
    _read_apparmor_profile,
    _is_doctor_confinement_profile_active,
    _is_safe_python_executable,
    _open_doctor_log_fd,
)


# ============================================================
# _read_proc_self_status_seccomp
# ============================================================

class TestReadSeccomp:
    def test_returns_none_when_missing(self, tmp_path):
        with patch("pathlib.Path.exists", return_value=False):
            assert _read_proc_self_status_seccomp() is None

    def test_returns_int_or_none(self):
        result = _read_proc_self_status_seccomp()
        assert result is None or isinstance(result, int)

    def test_handles_os_error(self, tmp_path):
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.read_text", side_effect=OSError("perm")):
                assert _read_proc_self_status_seccomp() is None


# ============================================================
# _read_apparmor_profile
# ============================================================

class TestReadApparmor:
    def test_returns_none_when_missing(self):
        with patch("pathlib.Path.exists", return_value=False):
            assert _read_apparmor_profile() is None


# ============================================================
# _is_doctor_confinement_profile_active
# ============================================================

class TestConfinement:
    def test_active_with_seccomp(self, monkeypatch):
        import veritas_os.core.kernel_doctor as kd
        monkeypatch.setattr(kd, "_read_proc_self_status_seccomp", lambda: 2)
        monkeypatch.setattr(kd, "_read_apparmor_profile", lambda: None)
        assert _is_doctor_confinement_profile_active() is True

    def test_inactive_unconfined(self, monkeypatch):
        import veritas_os.core.kernel_doctor as kd
        monkeypatch.setattr(kd, "_read_proc_self_status_seccomp", lambda: 0)
        monkeypatch.setattr(kd, "_read_apparmor_profile", lambda: "unconfined")
        assert _is_doctor_confinement_profile_active() is False

    def test_active_with_custom_profile(self, monkeypatch):
        import veritas_os.core.kernel_doctor as kd
        monkeypatch.setattr(kd, "_read_proc_self_status_seccomp", lambda: None)
        monkeypatch.setattr(kd, "_read_apparmor_profile", lambda: "my_custom")
        assert _is_doctor_confinement_profile_active() is True

    def test_inactive_no_confinement(self, monkeypatch):
        import veritas_os.core.kernel_doctor as kd
        monkeypatch.setattr(kd, "_read_proc_self_status_seccomp", lambda: None)
        monkeypatch.setattr(kd, "_read_apparmor_profile", lambda: None)
        assert _is_doctor_confinement_profile_active() is False


# ============================================================
# _is_safe_python_executable
# ============================================================

class TestSafePython:
    def test_none_rejected(self):
        assert _is_safe_python_executable(None) is False

    def test_relative_rejected(self):
        assert _is_safe_python_executable("python3") is False

    def test_nonexistent_rejected(self):
        assert _is_safe_python_executable("/nonexistent/python3") is False

    def test_valid_executable(self):
        result = _is_safe_python_executable(sys.executable)
        # sys.executable should be valid in test environments
        assert isinstance(result, bool)

    def test_non_python_name_rejected(self, tmp_path):
        bad = tmp_path / "notpython"
        bad.write_text("#!/bin/sh\n")
        bad.chmod(0o755)
        assert _is_safe_python_executable(str(bad)) is False


# ============================================================
# _open_doctor_log_fd
# ============================================================

class TestOpenDoctorLog:
    def test_creates_regular_file(self, tmp_path):
        log_path = tmp_path / "doc.log"
        fd = _open_doctor_log_fd(str(log_path))
        try:
            assert log_path.exists()
            st = os.fstat(fd)
            # Permissions should be 0o600
            assert (st.st_mode & 0o777) == 0o600
        finally:
            os.close(fd)

    def test_rejects_non_regular(self, tmp_path):
        with pytest.raises((ValueError, OSError)):
            _open_doctor_log_fd(str(tmp_path))


# ============================================================
# Backward compat: accessible via kernel module
# ============================================================

class TestBackwardCompat:
    def test_accessible_from_kernel(self):
        """Verify re-exports exist (kernel import may fail in minimal envs)."""
        try:
            from veritas_os.core import kernel
        except BaseException:
            pytest.skip("kernel import requires full dependency set")
        assert hasattr(kernel, "_is_doctor_confinement_profile_active")
        assert hasattr(kernel, "_is_safe_python_executable")
        assert hasattr(kernel, "_open_doctor_log_fd")
        assert hasattr(kernel, "_read_proc_self_status_seccomp")
        assert hasattr(kernel, "_read_apparmor_profile")


# ============================================================
# Source: test_kernel_stages.py
# ============================================================

# -*- coding: utf-8 -*-
"""
kernel_stages モジュールのユニットテスト

各ステージ関数の詳細なテスト
"""
import pytest
import uuid
from unittest.mock import patch, MagicMock
from typing import Dict, Any, List


# =============================================================================
# Test: prepare_context
# =============================================================================

class TestPrepareContext:
    """prepare_context 関数のテスト"""

    def test_sets_default_user_id(self):
        """デフォルトの user_id が設定されるか"""
        from veritas_os.core.kernel_stages import prepare_context

        ctx = prepare_context({}, "query")
        assert ctx["user_id"] == "cli"

    def test_preserves_existing_user_id(self):
        """既存の user_id が保持されるか"""
        from veritas_os.core.kernel_stages import prepare_context

        ctx = prepare_context({"user_id": "custom_user"}, "query")
        assert ctx["user_id"] == "custom_user"

    def test_generates_request_id(self):
        """request_id が生成されるか"""
        from veritas_os.core.kernel_stages import prepare_context

        ctx = prepare_context({}, "query")
        assert "request_id" in ctx
        assert len(ctx["request_id"]) > 0

    def test_sets_query(self):
        """query が正しく設定されるか"""
        from veritas_os.core.kernel_stages import prepare_context

        ctx = prepare_context({}, "my query")
        assert ctx["query"] == "my query"

    def test_sets_default_stakes(self):
        """デフォルトの stakes が設定されるか"""
        from veritas_os.core.kernel_stages import prepare_context

        ctx = prepare_context({}, "query")
        assert ctx["stakes"] == 0.5

    def test_computes_telos_score(self):
        """_computed_telos_score が計算されるか"""
        from veritas_os.core.kernel_stages import prepare_context

        ctx = prepare_context({}, "query")
        assert "_computed_telos_score" in ctx
        assert isinstance(ctx["_computed_telos_score"], float)

    def test_computes_telos_score_with_custom_weights(self):
        """カスタム weights で telos_score が計算されるか"""
        from veritas_os.core.kernel_stages import prepare_context

        ctx = prepare_context({
            "telos_weights": {
                "W_Transcendence": 0.8,
                "W_Struggle": 0.2,
            }
        }, "query")

        expected = round(0.5 * 0.8 + 0.5 * 0.2, 3)
        assert ctx["_computed_telos_score"] == expected


# =============================================================================
# Test: collect_memory_evidence
# =============================================================================

class TestCollectMemoryEvidence:
    """collect_memory_evidence 関数のテスト"""

    def test_fast_mode_skips_collection(self):
        """fast_mode で収集がスキップされるか"""
        from veritas_os.core.kernel_stages import collect_memory_evidence

        result = collect_memory_evidence(
            user_id="test",
            query="query",
            context={},
            fast_mode=True,
        )

        assert result["source"] == "skipped_fast_mode"
        assert result["evidence"] == []
        assert result["evidence_count"] == 0

    def test_uses_pipeline_provided_evidence(self):
        """パイプライン提供のエビデンスが使用されるか"""
        from veritas_os.core.kernel_stages import collect_memory_evidence

        provided_evidence = [
            {"source": "test", "text": "evidence 1", "score": 0.9},
            {"source": "test", "text": "evidence 2", "score": 0.8},
        ]

        result = collect_memory_evidence(
            user_id="test",
            query="query",
            context={"_pipeline_evidence": provided_evidence},
            fast_mode=False,
        )

        assert result["source"] == "pipeline_provided"
        assert result["evidence"] == provided_evidence
        assert result["evidence_count"] == 2


# =============================================================================
# Test: run_world_simulation
# =============================================================================

class TestRunWorldSimulation:
    """run_world_simulation 関数のテスト"""

    def test_fast_mode_skips_simulation(self):
        """fast_mode でシミュレーションがスキップされるか"""
        from veritas_os.core.kernel_stages import run_world_simulation

        result = run_world_simulation(
            user_id="test",
            query="query",
            context={},
            fast_mode=True,
        )

        assert result["source"] == "skipped_fast_mode"
        assert result["simulation"] is None

    def test_uses_pipeline_provided_simulation(self):
        """パイプライン提供のシミュレーション結果が使用されるか"""
        from veritas_os.core.kernel_stages import run_world_simulation

        sim_result = {"state": "test_state"}

        result = run_world_simulation(
            user_id="test",
            query="query",
            context={
                "_world_sim_done": True,
                "_world_sim_result": sim_result,
            },
            fast_mode=False,
        )

        assert result["source"] == "pipeline_provided"
        assert result["simulation"] == sim_result


# =============================================================================
# Test: run_environment_tools
# =============================================================================

class TestRunEnvironmentTools:
    """run_environment_tools 関数のテスト"""

    def test_fast_mode_skips_tools(self):
        """fast_mode でツールがスキップされるか"""
        from veritas_os.core.kernel_stages import run_environment_tools

        result = run_environment_tools(
            query="query",
            context={},
            fast_mode=True,
        )

        assert "skipped" in result
        assert result["skipped"]["reason"] == "fast_mode"

    def test_uses_pipeline_provided_tools(self):
        """パイプライン提供のツール結果が使用されるか"""
        from veritas_os.core.kernel_stages import run_environment_tools

        provided_tools = {"web_search": {"results": []}}

        result = run_environment_tools(
            query="query",
            context={"_pipeline_env_tools": provided_tools},
            fast_mode=False,
        )

        assert result == provided_tools


# =============================================================================
# Test: score_alternatives (詳細)
# =============================================================================

class TestScoreAlternativesDetailed:
    """score_alternatives 関数の詳細テスト"""

    def test_logs_when_value_core_api_is_unavailable(self, caplog):
        """value_core API 不足時に debug ログを残すか"""
        from veritas_os.core.kernel_stages import score_alternatives

        with caplog.at_level("DEBUG", logger="veritas_os.core.kernel_stages"):
            score_alternatives(
                intent="plan",
                query="test",
                alternatives=[{"id": "1", "title": "test", "score": 1.0}],
                telos_score=0.5,
                stakes=0.5,
                persona_bias=None,
            )

        assert "value_core API unavailable in score_alternatives" in caplog.text

    def test_logs_when_value_core_scoring_fails(self, caplog):
        """value_core スコア計算失敗時に debug ログを残すか"""
        from veritas_os.core.kernel_stages import score_alternatives
        import veritas_os.core.value_core as value_core

        class DummyOptionScore:
            """テスト用 OptionScore 互換オブジェクト。"""

            def __init__(self, **kwargs):
                self.payload = kwargs

        def broken_value_score(_):
            raise RuntimeError("simulated value scoring failure")

        with patch.object(
            value_core,
            "compute_value_score",
            broken_value_score,
            create=True,
        ), patch.object(value_core, "OptionScore", DummyOptionScore, create=True):
            with caplog.at_level("DEBUG", logger="veritas_os.core.kernel_stages"):
                score_alternatives(
                    intent="plan",
                    query="test",
                    alternatives=[{"id": "opt-1", "title": "test", "score": 1.0}],
                    telos_score=0.5,
                    stakes=0.5,
                    persona_bias=None,
                )

        assert "value_core scoring failed for alternative id=opt-1" in caplog.text

    def test_weather_intent_bonus(self):
        """weather intent のボーナスが適用されるか"""
        from veritas_os.core.kernel_stages import score_alternatives
        from veritas_os.core.config import scoring_cfg

        alts = [
            {"id": "1", "title": "天気予報を確認", "score": 1.0},
            {"id": "2", "title": "別のオプション", "score": 1.0},
        ]

        score_alternatives(
            intent="weather",
            query="天気",
            alternatives=alts,
            telos_score=0.5,
            stakes=0.5,
            persona_bias=None,
        )

        weather_score = next(a["score"] for a in alts if a["id"] == "1")
        other_score = next(a["score"] for a in alts if a["id"] == "2")

        # weather オプションがより高いスコアを持つ
        assert weather_score > other_score

    def test_health_intent_bonus(self):
        """health intent のボーナスが適用されるか"""
        from veritas_os.core.kernel_stages import score_alternatives

        alts = [
            {"id": "1", "title": "休息を取る", "score": 1.0},
            {"id": "2", "title": "作業を続ける", "score": 1.0},
        ]

        score_alternatives(
            intent="health",
            query="疲れた",
            alternatives=alts,
            telos_score=0.5,
            stakes=0.5,
            persona_bias=None,
        )

        rest_score = next(a["score"] for a in alts if a["id"] == "1")
        work_score = next(a["score"] for a in alts if a["id"] == "2")

        assert rest_score > work_score

    def test_learn_intent_bonus(self):
        """learn intent のボーナスが適用されるか"""
        from veritas_os.core.kernel_stages import score_alternatives

        alts = [
            {"id": "1", "title": "一次情報を確認", "score": 1.0},
            {"id": "2", "title": "推測する", "score": 1.0},
        ]

        score_alternatives(
            intent="learn",
            query="学習",
            alternatives=alts,
            telos_score=0.5,
            stakes=0.5,
            persona_bias=None,
        )

        primary_score = next(a["score"] for a in alts if a["id"] == "1")
        guess_score = next(a["score"] for a in alts if a["id"] == "2")

        assert primary_score > guess_score

    def test_plan_intent_bonus(self):
        """plan intent のボーナスが適用されるか"""
        from veritas_os.core.kernel_stages import score_alternatives

        alts = [
            {"id": "1", "title": "最小限の変更でテスト", "score": 1.0},
            {"id": "2", "title": "完全に新規実装", "score": 1.0},
        ]

        score_alternatives(
            intent="plan",
            query="計画",
            alternatives=alts,
            telos_score=0.5,
            stakes=0.5,
            persona_bias=None,
        )

        minimal_score = next(a["score"] for a in alts if a["id"] == "1")
        large_score = next(a["score"] for a in alts if a["id"] == "2")

        # plan intent では「最小」「テスト」などのキーワードにボーナス
        assert minimal_score > large_score

    def test_query_match_umbrella_bonus(self):
        """雨/傘のクエリマッチボーナスが適用されるか"""
        from veritas_os.core.kernel_stages import score_alternatives

        alts = [
            {"id": "1", "title": "傘を持っていく", "score": 1.0},
            {"id": "2", "title": "そのまま出かける", "score": 1.0},
        ]

        score_alternatives(
            intent="weather",
            query="今日は雨が降りそう",
            alternatives=alts,
            telos_score=0.5,
            stakes=0.5,
            persona_bias=None,
        )

        umbrella_score = next(a["score"] for a in alts if a["id"] == "1")
        no_umbrella_score = next(a["score"] for a in alts if a["id"] == "2")

        assert umbrella_score > no_umbrella_score

    def test_high_stakes_rest_bonus(self):
        """高 stakes 時の休息ボーナスが適用されるか"""
        from veritas_os.core.kernel_stages import score_alternatives
        from veritas_os.core.config import scoring_cfg

        alts = [
            {"id": "1", "title": "休息を取る", "score": 1.0},
            {"id": "2", "title": "急いで進める", "score": 1.0},
        ]

        # High stakes (>= 0.7)
        score_alternatives(
            intent="plan",
            query="重要な判断",
            alternatives=alts,
            telos_score=0.5,
            stakes=0.8,
            persona_bias=None,
        )

        rest_score = next(a["score"] for a in alts if a["id"] == "1")
        rush_score = next(a["score"] for a in alts if a["id"] == "2")

        assert rest_score > rush_score

    def test_persona_bias_boost(self):
        """persona bias がスコアに反映されるか（@id: 形式を使用）"""
        from veritas_os.core.kernel_stages import score_alternatives

        # @id: 形式を使用してfuzzy matchingを避ける
        alts = [
            {"id": "preferred_123", "title": "First Choice", "score": 1.0},
            {"id": "other_456", "title": "Second Choice", "score": 1.0},
        ]

        score_alternatives(
            intent="plan",
            query="test",
            alternatives=alts,
            telos_score=0.5,
            stakes=0.5,
            # @id: 形式でIDに直接マッチさせる
            persona_bias={"@id:preferred_123": 5.0},
        )

        preferred_score = next(a["score"] for a in alts if a["id"] == "preferred_123")
        other_score = next(a["score"] for a in alts if a["id"] == "other_456")

        # persona_bias_multiplier (0.3) * 5.0 = 1.5 の乗数ブースト
        assert preferred_score > other_score

    def test_telos_scale_applied(self):
        """Telos スコアによるスケーリングが適用されるか"""
        from veritas_os.core.kernel_stages import score_alternatives

        alts_low = [{"id": "1", "title": "test", "score": 1.0}]
        alts_high = [{"id": "1", "title": "test", "score": 1.0}]

        score_alternatives(
            intent="plan",
            query="test",
            alternatives=alts_low,
            telos_score=0.0,  # low
            stakes=0.5,
            persona_bias=None,
        )

        score_alternatives(
            intent="plan",
            query="test",
            alternatives=alts_high,
            telos_score=1.0,  # high
            stakes=0.5,
            persona_bias=None,
        )

        # 高い telos_score はより高いスコアをもたらす
        assert alts_high[0]["score"] > alts_low[0]["score"]

    def test_score_raw_preserved(self):
        """元のスコアが score_raw に保存されるか"""
        from veritas_os.core.kernel_stages import score_alternatives

        alts = [{"id": "1", "title": "test", "score": 0.75}]

        score_alternatives(
            intent="plan",
            query="test",
            alternatives=alts,
            telos_score=0.5,
            stakes=0.5,
            persona_bias=None,
        )

        assert "score_raw" in alts[0]
        assert alts[0]["score_raw"] == 0.75


# =============================================================================
# Test: run_debate_stage
# =============================================================================

class TestRunDebateStage:
    """run_debate_stage 関数のテスト"""

    def test_fast_mode_selects_highest_score(self):
        """fast_mode で最高スコアが選択されるか"""
        from veritas_os.core.kernel_stages import run_debate_stage

        alts = [
            {"id": "1", "title": "Low", "score": 0.3},
            {"id": "2", "title": "High", "score": 0.9},
            {"id": "3", "title": "Medium", "score": 0.6},
        ]

        result = run_debate_stage(
            query="test",
            alternatives=alts,
            context={},
            fast_mode=True,
        )

        assert result["chosen"]["id"] == "2"
        assert result["source"] == "fast_mode"

    def test_fast_mode_creates_default_for_empty_alts(self):
        """fast_mode で空のリストにデフォルトが生成されるか"""
        from veritas_os.core.kernel_stages import run_debate_stage

        result = run_debate_stage(
            query="test",
            alternatives=[],
            context={},
            fast_mode=True,
        )

        assert result["chosen"] is not None
        assert "title" in result["chosen"]

    def test_debate_logs_generated(self):
        """debate_logs が生成されるか"""
        from veritas_os.core.kernel_stages import run_debate_stage

        alts = [{"id": "1", "title": "Test", "score": 1.0}]

        result = run_debate_stage(
            query="test",
            alternatives=alts,
            context={},
            fast_mode=True,
        )

        assert len(result["debate_logs"]) > 0
        assert "summary" in result["debate_logs"][0]


# =============================================================================
# Test: run_fuji_gate
# =============================================================================

class TestRunFujiGate:
    """run_fuji_gate 関数のテスト"""

    def test_returns_valid_structure(self):
        """有効な構造が返されるか"""
        from veritas_os.core.kernel_stages import run_fuji_gate

        result = run_fuji_gate(
            query="safe query",
            context={"user_id": "test", "stakes": 0.5},
            evidence=[],
            alternatives=[],
        )

        assert "status" in result
        assert "risk" in result
        assert "violations" in result

    def test_handles_fuji_error_fail_closed(self):
        """FUJI 例外時に fail-closed で拒否を返すか (CLAUDE.md §4.2)"""
        from veritas_os.core.kernel_stages import run_fuji_gate

        with patch("veritas_os.core.fuji.evaluate") as mock_evaluate:
            mock_evaluate.side_effect = RuntimeError("FUJI error")

            result = run_fuji_gate(
                query="test",
                context={"user_id": "test"},
                evidence=[],
                alternatives=[],
            )

            # Fail-closed: 例外発生時は必ず deny + risk=1.0
            assert result["status"] == "deny"
            assert result["decision_status"] == "deny"
            assert result["risk"] == 1.0
            assert result["rejection_reason"] is not None
            assert "RuntimeError" in result["rejection_reason"]
            assert "FUJI_INTERNAL_ERROR" in result["violations"]
            assert result.get("meta", {}).get("fuji_internal_error") is True

    def test_fail_closed_on_generic_exception(self):
        """任意の Exception サブクラスでも fail-closed になるか"""
        from veritas_os.core.kernel_stages import run_fuji_gate

        class _CustomErr(Exception):
            pass

        with patch("veritas_os.core.fuji.evaluate") as mock_evaluate:
            mock_evaluate.side_effect = _CustomErr("boom")

            result = run_fuji_gate(
                query="test",
                context={"user_id": "test"},
                evidence=[],
                alternatives=[],
            )

            assert result["status"] == "deny"
            assert result["decision_status"] == "deny"
            assert result["risk"] == 1.0


# =============================================================================
# Test: update_persona_and_goals
# =============================================================================

class TestUpdatePersonaAndGoals:
    """update_persona_and_goals 関数のテスト"""

    def test_fast_mode_skips_update(self):
        """fast_mode で更新がスキップされるか"""
        from veritas_os.core.kernel_stages import update_persona_and_goals

        result = update_persona_and_goals(
            chosen={"id": "1", "title": "test"},
            context={},
            fuji_result={"risk": 0.1},
            telos_score=0.5,
            fast_mode=True,
        )

        assert result.get("skipped") is True

    def test_pipeline_provided_skips_update(self):
        """パイプラインで既に処理済みの場合スキップされるか"""
        from veritas_os.core.kernel_stages import update_persona_and_goals

        result = update_persona_and_goals(
            chosen={"id": "1", "title": "test"},
            context={"_agi_goals_adjusted_by_pipeline": True},
            fuji_result={"risk": 0.1},
            telos_score=0.5,
            fast_mode=False,
        )

        assert result.get("skipped") is True


# =============================================================================
# Test: save_episode_to_memory
# =============================================================================

class TestSaveEpisodeToMemory:
    """save_episode_to_memory 関数のテスト"""

    def test_pipeline_provided_returns_true(self):
        """パイプラインで既に保存済みの場合 True を返すか"""
        from veritas_os.core.kernel_stages import save_episode_to_memory

        result = save_episode_to_memory(
            query="test",
            chosen={"id": "1", "title": "test"},
            context={"_episode_saved_by_pipeline": True},
            intent="test",
            mode="fast",
            telos_score=0.5,
        )

        assert result is True


# =============================================================================
# Test: Utility functions
# =============================================================================

class TestUtilityFunctions:
    """ユーティリティ関数のテスト"""

    def test_mk_option_generates_valid_structure(self):
        """_mk_option が有効な構造を生成するか"""
        from veritas_os.core.kernel_stages import _mk_option

        opt = _mk_option("Test Title", "Test Description")

        assert "id" in opt
        assert opt["title"] == "Test Title"
        assert opt["description"] == "Test Description"
        assert opt["score"] == 1.0

    def test_mk_option_with_custom_id(self):
        """_mk_option でカスタム ID が使用できるか"""
        from veritas_os.core.kernel_stages import _mk_option

        opt = _mk_option("Test", _id="custom_id")

        assert opt["id"] == "custom_id"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


# ============================================================
# Source: test_kernel_stages_coverage.py
# ============================================================

# -*- coding: utf-8 -*-
"""
kernel_stages モジュールの追加カバレッジテスト

既存の test_kernel_stages.py でカバーされていないパスをテストする。
"""
import pytest
import uuid
from unittest.mock import patch, MagicMock, PropertyMock
from typing import Dict, Any


# =============================================================================
# Test: collect_memory_evidence – exception handler (lines 104-117)
# =============================================================================

class TestCollectMemoryEvidenceExceptionPaths:

    def test_memory_summarize_success(self):
        """memory import succeeds and summarize_for_planner returns a summary."""
        from veritas_os.core import kernel_stages

        with patch("veritas_os.core.memory.summarize_for_planner", return_value="summary text"):
            result = kernel_stages.collect_memory_evidence(
                user_id="u1", query="q", context={}, fast_mode=False,
            )

        assert result["source"] == "MemoryOS.summarize_for_planner"

    def test_memory_summarize_exception(self):
        """summarize_for_planner raises → source contains error string."""
        from veritas_os.core import kernel_stages

        with patch("veritas_os.core.memory.summarize_for_planner", side_effect=RuntimeError("db down")):
            result = kernel_stages.collect_memory_evidence(
                user_id="u1", query="q", context={}, fast_mode=False,
            )

        assert "error" in result["source"]
        assert result["memory_summary"] == ""


# =============================================================================
# Test: run_world_simulation – actual world module (lines 159-172)
# =============================================================================

class TestRunWorldSimulationActualModule:

    def test_world_simulate_success(self):
        """world.simulate succeeds → result populated."""
        from veritas_os.core import kernel_stages

        with patch("veritas_os.core.world.simulate", return_value={"outcome": "ok"}):
            result = kernel_stages.run_world_simulation(
                user_id="u1", query="q", context={}, fast_mode=False,
            )

        assert result["simulation"] == {"outcome": "ok"}
        assert result["source"] == "world.simulate()"

    def test_world_simulate_exception(self):
        """world.simulate raises → error source."""
        from veritas_os.core import kernel_stages

        with patch("veritas_os.core.world.simulate", side_effect=ConnectionError("timeout")):
            result = kernel_stages.run_world_simulation(
                user_id="u1", query="q", context={}, fast_mode=False,
            )

        assert "error" in result["source"]
        assert result["simulation"] is None


# =============================================================================
# Test: run_environment_tools – full execution (lines 205-228)
# =============================================================================

class TestRunEnvironmentToolsFull:

    def test_use_env_tools_flag_calls_both(self):
        """use_env_tools=True → web_search and github_search called."""
        from veritas_os.core import kernel_stages

        mock_call_tool = MagicMock(return_value={"ok": True, "results": ["r"]})

        with patch("veritas_os.tools.call_tool", mock_call_tool):
            result = kernel_stages.run_environment_tools(
                query="find repos",
                context={"use_env_tools": True},
                fast_mode=False,
            )

        assert "web_search" in result
        assert "github_search" in result
        assert result["web_search"]["ok"] is True

    def test_github_keyword_triggers_github_search(self):
        """Query containing 'github' triggers github_search only."""
        from veritas_os.core import kernel_stages

        mock_call_tool = MagicMock(return_value={"ok": True, "results": []})

        with patch("veritas_os.tools.call_tool", mock_call_tool):
            result = kernel_stages.run_environment_tools(
                query="search github repos",
                context={},
                fast_mode=False,
            )

        assert "github_search" in result
        assert "web_search" not in result

    def test_agi_keyword_triggers_web_search(self):
        """Query containing 'agi' triggers web_search."""
        from veritas_os.core import kernel_stages

        mock_call_tool = MagicMock(return_value={"ok": True, "results": []})

        with patch("veritas_os.tools.call_tool", mock_call_tool):
            result = kernel_stages.run_environment_tools(
                query="latest agi research",
                context={},
                fast_mode=False,
            )

        assert "web_search" in result

    def test_paper_keyword_triggers_web_search(self):
        """Query containing 'paper' triggers web_search."""
        from veritas_os.core import kernel_stages

        mock_call_tool = MagicMock(return_value={"ok": True, "results": []})

        with patch("veritas_os.tools.call_tool", mock_call_tool):
            result = kernel_stages.run_environment_tools(
                query="new paper on transformers",
                context={},
                fast_mode=False,
            )

        assert "web_search" in result

    def test_no_keyword_match_returns_empty(self):
        """Query with no matching keywords → empty result."""
        from veritas_os.core import kernel_stages

        mock_call_tool = MagicMock(return_value={"ok": True, "results": []})

        with patch("veritas_os.tools.call_tool", mock_call_tool):
            result = kernel_stages.run_environment_tools(
                query="hello world",
                context={},
                fast_mode=False,
            )

        assert "web_search" not in result
        assert "github_search" not in result

    def test_call_tool_import_exception(self):
        """If call_tool import fails → error key in result."""
        from veritas_os.core import kernel_stages

        with patch("veritas_os.tools.call_tool", side_effect=ImportError("no module")):
            result = kernel_stages.run_environment_tools(
                query="github test",
                context={},
                fast_mode=False,
            )

        # _run_tool_safe catches the error per-tool
        assert result["github_search"]["ok"] is False


# =============================================================================
# Test: _run_tool_safe (lines 231-245)
# =============================================================================

class TestRunToolSafe:

    def test_success_returns_dict_with_ok(self):
        """Successful call_tool returns dict → ok=True preserved."""
        from veritas_os.core.kernel_stages import _run_tool_safe

        fn = MagicMock(return_value={"data": 42})
        result = _run_tool_safe(fn, "web_search", query="q")

        assert result["ok"] is True
        assert result["data"] == 42
        assert "results" in result

    def test_non_dict_return_wrapped(self):
        """Non-dict return → wrapped in {'raw': ...}."""
        from veritas_os.core.kernel_stages import _run_tool_safe

        fn = MagicMock(return_value="plain string")
        result = _run_tool_safe(fn, "web_search")

        assert result["raw"] == "plain string"
        assert result["ok"] is True

    def test_exception_returns_error(self):
        """Exception in callable → ok=False with error message."""
        from veritas_os.core.kernel_stages import _run_tool_safe

        fn = MagicMock(side_effect=ValueError("bad value"))
        result = _run_tool_safe(fn, "web_search")

        assert result["ok"] is False
        assert "error" in result
        assert "bad value" in result["error"]


# =============================================================================
# Test: score_alternatives – value_core integration (lines 279-360)
# =============================================================================

class TestScoreAlternativesValueCore:

    @patch("veritas_os.core.value_core.compute_value_score", create=True, return_value=1.5)
    @patch("veritas_os.core.value_core.OptionScore", create=True, new_callable=MagicMock)
    def test_value_core_multiplier_applied(self, mock_os_cls, mock_compute):
        """When value_core is available, vscore multiplier is applied."""
        from veritas_os.core import kernel_stages

        alts_with = [{"id": "a", "title": "Test", "description": "d", "score": 1.0}]
        kernel_stages.score_alternatives(
            intent="plan", query="test", alternatives=alts_with,
            telos_score=0.5, stakes=0.5, persona_bias=None,
        )

        # compute_value_score was called
        assert mock_compute.called
        assert "score_raw" in alts_with[0]

    @patch("veritas_os.core.value_core.compute_value_score", create=True, side_effect=RuntimeError("boom"))
    @patch("veritas_os.core.value_core.OptionScore", create=True, new_callable=MagicMock)
    def test_value_core_exception_ignored(self, mock_os_cls, mock_compute):
        """If value_core.compute_value_score raises, score still set."""
        from veritas_os.core import kernel_stages

        alts = [{"id": "a", "title": "Test", "description": "d", "score": 1.0}]
        kernel_stages.score_alternatives(
            intent="plan", query="test", alternatives=alts,
            telos_score=0.5, stakes=0.5, persona_bias=None,
        )

        assert isinstance(alts[0]["score"], float)
        assert "score_raw" in alts[0]

    def test_value_core_import_failure(self):
        """If value_core import fails, scoring still works."""
        from veritas_os.core import kernel_stages

        with patch.dict("sys.modules", {"veritas_os.core.value_core": None}):
            alts = [{"id": "a", "title": "Test", "score": 1.0}]
            kernel_stages.score_alternatives(
                intent="plan", query="test", alternatives=alts,
                telos_score=0.5, stakes=0.5, persona_bias=None,
            )

        assert isinstance(alts[0]["score"], float)

    def test_empty_alternatives_returns_early(self):
        """Empty alternatives list → immediate return."""
        from veritas_os.core.kernel_stages import score_alternatives

        score_alternatives(
            intent="plan",
            query="test",
            alternatives=[],
            telos_score=0.5,
            stakes=0.5,
            persona_bias=None,
        )
        # No exception, no crash


# =============================================================================
# Test: run_debate_stage – non-fast-mode (lines 370-459)
# =============================================================================

class TestRunDebateStageNonFast:

    def test_debate_success_path(self):
        """debate.run_debate succeeds → chosen from debate result."""
        from veritas_os.core import kernel_stages

        mock_return = {
            "chosen": {"id": "d1", "title": "Debated"},
            "options": [{"id": "d1", "title": "Debated", "score": 2.0}],
            "source": "openai_llm",
        }

        with patch("veritas_os.core.debate.run_debate", return_value=mock_return):
            alts = [{"id": "1", "title": "A", "score": 1.0}]
            result = kernel_stages.run_debate_stage(
                query="test", alternatives=alts, context={"user_id": "u1"}, fast_mode=False,
            )

        assert result["chosen"]["id"] == "d1"
        assert result["source"] == "openai_llm"
        assert len(result["debate_logs"]) == 1

    def test_debate_exception_fallback_with_alts(self):
        """debate.run_debate raises → fallback picks max score."""
        from veritas_os.core import kernel_stages

        with patch("veritas_os.core.debate.run_debate", side_effect=RuntimeError("LLM unavailable")):
            alts = [
                {"id": "1", "title": "Low", "score": 0.3},
                {"id": "2", "title": "High", "score": 0.9},
            ]
            result = kernel_stages.run_debate_stage(
                query="test", alternatives=alts, context={}, fast_mode=False,
            )

        assert result["chosen"]["id"] == "2"
        assert result["source"] == "fallback"

    def test_debate_exception_fallback_empty_alts(self):
        """debate.run_debate raises with empty alts → fallback option created."""
        from veritas_os.core import kernel_stages

        with patch("veritas_os.core.debate.run_debate", side_effect=RuntimeError("fail")):
            result = kernel_stages.run_debate_stage(
                query="test", alternatives=[], context={}, fast_mode=False,
            )

        assert result["chosen"] is not None
        assert result["chosen"]["title"] == "フォールバック選択"
        assert result["source"] == "fallback"


# =============================================================================
# Test: run_fuji_gate – full execution (lines 466-520)
# =============================================================================

class TestRunFujiGateFullExecution:

    @patch("veritas_os.core.fuji.evaluate")
    def test_fuji_evaluate_success(self, mock_evaluate):
        """fuji.evaluate succeeds → result returned directly."""
        from veritas_os.core import kernel_stages

        mock_evaluate.return_value = {
            "status": "allow",
            "decision_status": "allow",
            "risk": 0.02,
            "violations": [],
            "reasons": [],
        }

        result = kernel_stages.run_fuji_gate(
            query="safe query",
            context={"user_id": "u1", "stakes": 0.3, "mode": "normal",
                     "_computed_telos_score": 0.5},
            evidence=[{"text": "ev1"}],
            alternatives=[{"id": "a1"}],
        )

        assert result["status"] == "allow"
        assert result["risk"] == 0.02
        mock_evaluate.assert_called_once()

    @patch("veritas_os.core.fuji.evaluate")
    def test_fuji_evaluate_exception_fail_closed(self, mock_evaluate):
        """fuji.evaluate raises → fail-closed deny (CLAUDE.md §4.2)."""
        from veritas_os.core import kernel_stages

        mock_evaluate.side_effect = Exception("fuji crash")

        result = kernel_stages.run_fuji_gate(
            query="test",
            context={"user_id": "u1"},
            evidence=[],
            alternatives=[],
        )

        assert result["status"] == "deny"
        assert result["decision_status"] == "deny"
        assert result["risk"] == 1.0
        assert result["rejection_reason"] is not None
        assert "FUJI_INTERNAL_ERROR" in result["violations"]
        assert any("fuji_error" in r for r in result["reasons"])


# =============================================================================
# Test: update_persona_and_goals – full execution (lines 527-600)
# =============================================================================

class TestUpdatePersonaAndGoalsFull:

    @patch("veritas_os.core.agi_goals.auto_adjust_goals")
    @patch("veritas_os.core.adapt.save_persona")
    @patch("veritas_os.core.adapt.clean_bias_weights", side_effect=lambda b: b)
    @patch("veritas_os.core.adapt.update_persona_bias_from_history")
    def test_full_update_success(self, mock_update, mock_clean, mock_save, mock_adjust):
        """adapt + agi_goals + world all available → updated=True."""
        from veritas_os.core import kernel_stages

        mock_update.return_value = {
            "bias_weights": {"rest": 0.5, "work": 0.5},
        }
        mock_adjust.return_value = {"rest": 0.6, "work": 0.4}

        result = kernel_stages.update_persona_and_goals(
            chosen={"id": "1", "title": "休息"},
            context={"_world_sim_result": {"state": "ok"}},
            fuji_result={"risk": 0.1},
            telos_score=0.6,
            fast_mode=False,
        )

        assert result["updated"] is True
        assert result["error"] is None
        assert result["last_auto_adjust"]["value_ema"] == 0.6
        assert result["last_auto_adjust"]["fuji_risk"] == 0.1
        mock_save.assert_called_once()

    @patch("veritas_os.core.adapt.update_persona_bias_from_history")
    def test_update_exception_returns_error(self, mock_update):
        """If adapt raises → error captured, updated=False."""
        from veritas_os.core import kernel_stages

        mock_update.side_effect = RuntimeError("db fail")

        result = kernel_stages.update_persona_and_goals(
            chosen={"id": "1", "title": "test"},
            context={},
            fuji_result={"risk": 0.1},
            telos_score=0.5,
            fast_mode=False,
        )

        assert result["updated"] is False
        assert result["error"] is not None
        assert "db fail" in result["error"]

    @patch("veritas_os.core.agi_goals.auto_adjust_goals", return_value={})
    @patch("veritas_os.core.adapt.save_persona")
    @patch("veritas_os.core.adapt.clean_bias_weights", side_effect=lambda b: b)
    @patch("veritas_os.core.adapt.update_persona_bias_from_history")
    def test_update_with_no_world_sim_result(self, mock_update, mock_clean, mock_save, mock_adjust):
        """No _world_sim_result in context → world_snap is empty dict."""
        from veritas_os.core import kernel_stages

        mock_update.return_value = {
            "bias_weights": {},
        }

        result = kernel_stages.update_persona_and_goals(
            chosen={"id": "1", "title": "test"},
            context={},
            fuji_result={"risk": 0.05},
            telos_score=0.5,
            fast_mode=False,
        )

        assert result["updated"] is True


# =============================================================================
# Test: save_episode_to_memory – full execution (lines 603-666)
# =============================================================================

class TestSaveEpisodeToMemoryFull:

    @patch("veritas_os.core.memory.MEM")
    def test_mem_put_success(self, mock_mem_store):
        """MEM.put(episodic, ...) succeeds → True."""
        from veritas_os.core import kernel_stages

        mock_mem_store.put = MagicMock()

        result = kernel_stages.save_episode_to_memory(
            query="test query",
            chosen={"id": "1", "title": "chosen"},
            context={"user_id": "u1", "request_id": "r1"},
            intent="plan",
            mode="normal",
            telos_score=0.5,
        )

        assert result is True
        mock_mem_store.put.assert_called_once()
        args = mock_mem_store.put.call_args
        assert args[0][0] == "episodic"

    @patch("veritas_os.core.memory.MEM")
    def test_mem_put_typeerror_fallback(self, mock_mem_store):
        """MEM.put(episodic, ...) raises TypeError → fallback 3-arg call."""
        from veritas_os.core import kernel_stages

        call_count = 0

        def put_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise TypeError("put() takes 3 positional arguments")
            return None

        mock_mem_store.put = MagicMock(side_effect=put_side_effect)

        result = kernel_stages.save_episode_to_memory(
            query="test",
            chosen={"id": "1", "title": "t"},
            context={"user_id": "u1", "request_id": "r1"},
            intent="test",
            mode="fast",
            telos_score=0.5,
        )

        assert result is True
        assert mock_mem_store.put.call_count == 2

    @patch("veritas_os.core.memory.MEM")
    def test_mem_put_general_exception_returns_false(self, mock_mem_store):
        """If MEM.put raises a non-TypeError exception → returns False."""
        from veritas_os.core import kernel_stages

        mock_mem_store.put = MagicMock(side_effect=ConnectionError("lost"))

        result = kernel_stages.save_episode_to_memory(
            query="test",
            chosen={"id": "1", "title": "t"},
            context={"user_id": "u1"},
            intent="test",
            mode="fast",
            telos_score=0.5,
        )

        assert result is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
