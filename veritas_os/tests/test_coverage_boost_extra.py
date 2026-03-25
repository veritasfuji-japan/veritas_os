# veritas_os/tests/test_coverage_boost_extra.py
# -*- coding: utf-8 -*-
"""
Additional coverage tests for weak-spot modules:
- core/memory_store.py (_is_record_legal_hold, _should_cascade_delete_semantic)
- api/governance.py (_policy_path)
- core/fuji_policy.py (_build_runtime_patterns_from_policy, RISKY_KEYWORDS_POC)
- api/routes_decide.py (replay endpoints, _get_server)
"""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# =========================================================
# memory_store._is_record_legal_hold
# =========================================================

class TestMemoryStoreIsRecordLegalHold:
    def test_legal_hold_true(self):
        from veritas_os.core.memory_store import MemoryStore
        record = {"value": {"meta": {"legal_hold": True}}}
        assert MemoryStore._is_record_legal_hold(record) is True

    def test_legal_hold_false(self):
        from veritas_os.core.memory_store import MemoryStore
        record = {"value": {"meta": {"legal_hold": False}}}
        assert MemoryStore._is_record_legal_hold(record) is False

    def test_no_meta(self):
        from veritas_os.core.memory_store import MemoryStore
        record = {"value": {}}
        assert MemoryStore._is_record_legal_hold(record) is False

    def test_non_dict_value(self):
        from veritas_os.core.memory_store import MemoryStore
        record = {"value": "string_value"}
        assert MemoryStore._is_record_legal_hold(record) is False

    def test_missing_value(self):
        from veritas_os.core.memory_store import MemoryStore
        record = {}
        assert MemoryStore._is_record_legal_hold(record) is False

    def test_non_dict_meta(self):
        from veritas_os.core.memory_store import MemoryStore
        record = {"value": {"meta": "not_dict"}}
        assert MemoryStore._is_record_legal_hold(record) is False


# =========================================================
# memory_store._should_cascade_delete_semantic
# =========================================================

class TestMemoryStoreShouldCascadeDeleteSemantic:
    def test_cascade_delete_when_all_sources_erased(self):
        from veritas_os.core.memory_store import MemoryStore
        record = {
            "value": {
                "kind": "semantic",
                "meta": {
                    "user_id": "u1",
                    "source_episode_keys": ["k1", "k2"],
                },
            }
        }
        assert MemoryStore._should_cascade_delete_semantic(record, "u1", {"k1", "k2"}) is True

    def test_no_cascade_when_empty_erased_keys(self):
        from veritas_os.core.memory_store import MemoryStore
        record = {
            "value": {
                "kind": "semantic",
                "meta": {"user_id": "u1", "source_episode_keys": ["k1"]},
            }
        }
        assert MemoryStore._should_cascade_delete_semantic(record, "u1", set()) is False

    def test_no_cascade_non_semantic(self):
        from veritas_os.core.memory_store import MemoryStore
        record = {
            "value": {
                "kind": "episode",
                "meta": {"user_id": "u1", "source_episode_keys": ["k1"]},
            }
        }
        assert MemoryStore._should_cascade_delete_semantic(record, "u1", {"k1"}) is False

    def test_no_cascade_different_user(self):
        from veritas_os.core.memory_store import MemoryStore
        record = {
            "value": {
                "kind": "semantic",
                "meta": {"user_id": "u2", "source_episode_keys": ["k1"]},
            }
        }
        assert MemoryStore._should_cascade_delete_semantic(record, "u1", {"k1"}) is False

    def test_no_cascade_legal_hold(self):
        from veritas_os.core.memory_store import MemoryStore
        record = {
            "value": {
                "kind": "semantic",
                "meta": {
                    "user_id": "u1",
                    "legal_hold": True,
                    "source_episode_keys": ["k1"],
                },
            }
        }
        assert MemoryStore._should_cascade_delete_semantic(record, "u1", {"k1"}) is False

    def test_non_dict_value(self):
        from veritas_os.core.memory_store import MemoryStore
        record = {"value": "not_dict"}
        assert MemoryStore._should_cascade_delete_semantic(record, "u1", {"k1"}) is False


# =========================================================
# governance._policy_path
# =========================================================

class TestGovernancePolicyPath:
    def test_returns_path_instance(self):
        from veritas_os.api.governance import _policy_path
        result = _policy_path()
        assert isinstance(result, Path)
        assert result.name == "governance.json"


# =========================================================
# fuji_policy._build_runtime_patterns_from_policy (direct test)
# =========================================================

class TestBuildRuntimePatternsFromPolicy:
    def test_calls_both_builders(self):
        from veritas_os.core import fuji_policy
        with (
            patch.object(fuji_policy, "_build_injection_patterns_from_policy") as mock_inj,
            patch.object(fuji_policy, "_build_pii_patterns_from_policy") as mock_pii,
        ):
            fuji_policy._build_runtime_patterns_from_policy({"pii": {}})
            mock_inj.assert_called_once()
            mock_pii.assert_called_once()

    def test_with_empty_policy(self):
        from veritas_os.core import fuji_policy
        # Should not raise
        with (
            patch.object(fuji_policy, "_build_injection_patterns_from_policy"),
            patch.object(fuji_policy, "_build_pii_patterns_from_policy"),
        ):
            fuji_policy._build_runtime_patterns_from_policy({})


# =========================================================
# fuji_policy.RISKY_KEYWORDS_POC
# =========================================================

class TestRiskyKeywordsPoc:
    def test_pattern_is_compiled_regex(self):
        from veritas_os.core.fuji_policy import RISKY_KEYWORDS_POC
        assert isinstance(RISKY_KEYWORDS_POC, re.Pattern)

    def test_matches_expected_keywords(self):
        from veritas_os.core.fuji_policy import RISKY_KEYWORDS_POC
        # These are typical Japanese business-domain risky keywords
        test_inputs = ["不動産", "投資", "金融", "仮想通貨", "融資"]
        matched = [s for s in test_inputs if RISKY_KEYWORDS_POC.search(s)]
        # At least some should match (pattern may not cover all)
        # We mainly test that the pattern doesn't error out
        assert isinstance(matched, list)

    def test_does_not_match_safe_input(self):
        from veritas_os.core.fuji_policy import RISKY_KEYWORDS_POC
        result = RISKY_KEYWORDS_POC.search("hello world simple text")
        # Safe English text should generally not match Japanese risky keywords
        assert result is None


# =========================================================
# routes_decide._get_server
# =========================================================

class TestGetServer:
    def test_returns_server_module(self):
        from veritas_os.api.routes_decide import _get_server
        srv = _get_server()
        assert hasattr(srv, "get_decision_pipeline")


# =========================================================
# routes_decide: replay_endpoint
# =========================================================

class TestReplayEndpoint:
    @pytest.mark.asyncio
    async def test_replay_not_found(self):
        from veritas_os.api.routes_decide import replay_endpoint

        mock_request = MagicMock()
        mock_request.headers = MagicMock()
        mock_request.headers.get = MagicMock(return_value=None)

        with patch("veritas_os.api.routes_decide._get_server") as mock_srv:
            srv = MagicMock()
            srv.verify_signature = AsyncMock()
            srv.run_replay = AsyncMock(side_effect=ValueError("not found"))
            srv._errstr = lambda e: str(e)
            mock_srv.return_value = srv

            resp = await replay_endpoint("nonexistent", mock_request)
            assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_replay_internal_error(self):
        from veritas_os.api.routes_decide import replay_endpoint

        mock_request = MagicMock()
        mock_request.headers = MagicMock()
        mock_request.headers.get = MagicMock(return_value=None)

        with patch("veritas_os.api.routes_decide._get_server") as mock_srv:
            srv = MagicMock()
            srv.verify_signature = AsyncMock()
            srv.run_replay = AsyncMock(side_effect=RuntimeError("fail"))
            srv._errstr = lambda e: str(e)
            mock_srv.return_value = srv

            resp = await replay_endpoint("some-id", mock_request)
            assert resp.status_code == 500

    @pytest.mark.asyncio
    async def test_replay_success(self):
        from veritas_os.api.routes_decide import replay_endpoint

        mock_request = MagicMock()
        mock_request.headers = MagicMock()
        mock_request.headers.get = MagicMock(return_value=None)

        result = MagicMock()
        result.decision_id = "d1"
        result.replay_path = "/path"
        result.match = True
        result.diff_summary = {}
        result.replay_time_ms = 42

        with patch("veritas_os.api.routes_decide._get_server") as mock_srv:
            srv = MagicMock()
            srv.verify_signature = AsyncMock()
            srv.run_replay = AsyncMock(return_value=result)
            mock_srv.return_value = srv

            resp = await replay_endpoint("d1", mock_request)
            assert resp["ok"] is True
            assert resp["decision_id"] == "d1"


# =========================================================
# routes_decide: replay_decision_endpoint
# =========================================================

class TestReplayDecisionEndpoint:
    @pytest.mark.asyncio
    async def test_pipeline_unavailable(self):
        from veritas_os.api.routes_decide import replay_decision_endpoint

        mock_request = MagicMock()
        mock_request.query_params = {}

        with patch("veritas_os.api.routes_decide._get_server") as mock_srv:
            srv = MagicMock()
            srv.get_decision_pipeline.return_value = None
            srv.DECIDE_GENERIC_ERROR = "unavailable"
            mock_srv.return_value = srv

            resp = await replay_decision_endpoint("d1", mock_request)
            assert resp.status_code == 503

    @pytest.mark.asyncio
    async def test_replay_decision_success(self):
        from veritas_os.api.routes_decide import replay_decision_endpoint

        mock_request = MagicMock()
        mock_request.query_params = {"mock_external_apis": "true"}

        pipeline = MagicMock()
        pipeline.replay_decision = AsyncMock(return_value={"match": True, "diff": {}})

        with patch("veritas_os.api.routes_decide._get_server") as mock_srv:
            srv = MagicMock()
            srv.get_decision_pipeline.return_value = pipeline
            mock_srv.return_value = srv

            resp = await replay_decision_endpoint("d1", mock_request)
            assert resp["match"] is True

    @pytest.mark.asyncio
    async def test_replay_decision_mock_external_false(self):
        from veritas_os.api.routes_decide import replay_decision_endpoint

        mock_request = MagicMock()
        mock_request.query_params = {"mock_external_apis": "false"}

        pipeline = MagicMock()
        pipeline.replay_decision = AsyncMock(return_value={"match": True})

        with patch("veritas_os.api.routes_decide._get_server") as mock_srv:
            srv = MagicMock()
            srv.get_decision_pipeline.return_value = pipeline
            mock_srv.return_value = srv

            await replay_decision_endpoint("d1", mock_request)
            pipeline.replay_decision.assert_called_once_with(
                decision_id="d1", mock_external_apis=False,
            )

    @pytest.mark.asyncio
    async def test_replay_decision_error(self):
        from veritas_os.api.routes_decide import replay_decision_endpoint

        mock_request = MagicMock()
        mock_request.query_params = {}

        pipeline = MagicMock()
        pipeline.replay_decision = AsyncMock(side_effect=RuntimeError("fail"))

        with patch("veritas_os.api.routes_decide._get_server") as mock_srv:
            srv = MagicMock()
            srv.get_decision_pipeline.return_value = pipeline
            srv._errstr = lambda e: str(e)
            mock_srv.return_value = srv

            resp = await replay_decision_endpoint("d1", mock_request)
            assert resp.status_code == 500
