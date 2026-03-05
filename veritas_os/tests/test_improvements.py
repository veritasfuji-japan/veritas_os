# veritas_os/tests/test_improvements.py
# -*- coding: utf-8 -*-
"""
Tests for code quality improvements:
- Debug logging in silent except blocks (pipeline_helpers, pipeline_contracts, pipeline_memory_adapter)
- Configurable MAX_LINES in rotate.py via VERITAS_LOG_MAX_LINES env var
- Warning-level logging for dir fsync failures in atomic_io.py
"""
import json
import logging
import os
from pathlib import Path
from unittest import mock

import pytest

from veritas_os.core import pipeline_helpers
from veritas_os.core import pipeline_contracts
from veritas_os.core import pipeline_memory_adapter
from veritas_os.logging import rotate
import veritas_os.logging.paths as log_paths


# =========================================================
# pipeline_helpers: debug logging in except blocks
# =========================================================

class TestPipelineHelpersLogging:
    """Verify that exception fallbacks in pipeline_helpers emit debug logs."""

    def test_as_str_logs_on_str_failure(self, caplog):
        """_as_str should log when str() conversion fails."""
        class BadStr:
            def __str__(self):
                raise RuntimeError("cannot str")
            def __repr__(self):
                return "BadStr()"

        with caplog.at_level(logging.DEBUG, logger="veritas_os.core.pipeline_helpers"):
            result = pipeline_helpers._as_str(BadStr())
        assert result == "BadStr()"
        assert "_as_str" in caplog.text

    def test_norm_severity_logs_on_failure(self, caplog):
        """_norm_severity should log when str() conversion fails."""
        class BadSev:
            def __str__(self):
                raise RuntimeError("cannot str")

        with caplog.at_level(logging.DEBUG, logger="veritas_os.core.pipeline_helpers"):
            result = pipeline_helpers._norm_severity(BadSev())
        assert result == "med"
        assert "_norm_severity" in caplog.text

    def test_to_bool_local_logs_on_failure(self, caplog):
        """_to_bool_local should log when str() conversion fails."""
        class BadBool:
            def __str__(self):
                raise RuntimeError("cannot str")

        with caplog.at_level(logging.DEBUG, logger="veritas_os.core.pipeline_helpers"):
            result = pipeline_helpers._to_bool_local(BadBool())
        assert result is False
        assert "_to_bool_local" in caplog.text

    def test_set_int_metric_logs_on_failure(self, caplog):
        """_set_int_metric should log when int() conversion fails."""
        extras = {}
        with caplog.at_level(logging.DEBUG, logger="veritas_os.core.pipeline_helpers"):
            pipeline_helpers._set_int_metric(extras, "test_key", "not_a_number", default=42)
        assert extras["metrics"]["test_key"] == 42
        assert "_set_int_metric" in caplog.text

    def test_set_bool_metric_still_works(self):
        """_set_bool_metric should still function correctly."""
        extras = {}
        pipeline_helpers._set_bool_metric(extras, "flag", "true", default=False)
        assert extras["metrics"]["flag"] is True

    def test_query_is_step1_hint_logs_on_failure(self, caplog):
        """_query_is_step1_hint should log when check fails."""
        class BadQuery:
            def __bool__(self):
                raise RuntimeError("cannot bool")

        with caplog.at_level(logging.DEBUG, logger="veritas_os.core.pipeline_helpers"):
            result = pipeline_helpers._query_is_step1_hint(BadQuery())
        assert result is False
        assert "_query_is_step1_hint" in caplog.text


# =========================================================
# pipeline_contracts: debug logging in except blocks
# =========================================================

class TestPipelineContractsLogging:
    """Verify that exception fallbacks in pipeline_contracts emit debug logs."""

    def test_ensure_full_contract_logs_context_obj_failure(self, caplog):
        """_ensure_full_contract should log when context_obj conversion fails."""
        class BadContext(dict):
            """dict subclass whose dict() copy constructor raises."""
            def __iter__(self):
                raise RuntimeError("cannot iterate")

        extras = {}
        with caplog.at_level(logging.DEBUG, logger="veritas_os.core.pipeline_contracts"):
            pipeline_contracts._ensure_full_contract(
                extras,
                fast_mode_default=False,
                context_obj=BadContext(),
            )
        # Should still create a valid contract
        assert "metrics" in extras
        assert "memory_meta" in extras

    def test_deep_merge_dict_logs_on_failure(self, caplog):
        """_deep_merge_dict should log when merge fails."""
        class BadDict(dict):
            def items(self):
                raise RuntimeError("cannot iterate")

        dst = {"a": 1}
        with caplog.at_level(logging.DEBUG, logger="veritas_os.core.pipeline_contracts"):
            result = pipeline_contracts._deep_merge_dict(dst, BadDict())
        assert result == {"a": 1}
        assert "_deep_merge_dict" in caplog.text


# =========================================================
# pipeline_memory_adapter: debug logging in except blocks
# =========================================================

class TestPipelineMemoryAdapterLogging:
    """Verify that exception fallbacks in pipeline_memory_adapter emit debug logs."""

    def test_memory_has_logs_on_failure(self, caplog):
        """_memory_has should log when getattr fails."""
        class BadStore:
            def __getattr__(self, name):
                raise RuntimeError("cannot getattr")

        with caplog.at_level(logging.DEBUG, logger="veritas_os.core.pipeline_memory_adapter"):
            result = pipeline_memory_adapter._memory_has(BadStore(), "search")
        assert result is False
        assert "_memory_has" in caplog.text

    def test_memory_put_logs_all_signature_failures(self, caplog):
        """_memory_put should log when all put signatures fail."""
        class MockStore:
            def put(self, *args, **kwargs):
                raise TypeError("bad signature")

        with caplog.at_level(logging.DEBUG, logger="veritas_os.core.pipeline_memory_adapter"):
            pipeline_memory_adapter._memory_put(
                MockStore(), "user1", key="k", value="v", meta=None,
            )
        assert "_memory_put" in caplog.text

    def test_call_with_accepted_kwargs_logs_fallback(self, caplog):
        """_call_with_accepted_kwargs should log when signature filtering fails."""
        def fn(**kwargs):
            return kwargs

        # Create a function whose signature cannot be inspected
        class BadCallable:
            def __call__(self, **kwargs):
                return kwargs

        bad = BadCallable()
        bad.__signature__ = "not a valid signature"  # type: ignore

        with caplog.at_level(logging.DEBUG, logger="veritas_os.core.pipeline_memory_adapter"):
            result = pipeline_memory_adapter._call_with_accepted_kwargs(bad, {"a": 1})
        assert result == {"a": 1}


# =========================================================
# rotate.py: configurable MAX_LINES via environment variable
# =========================================================

class TestRotateConfigurableMaxLines:
    """Test VERITAS_LOG_MAX_LINES environment variable support."""

    def test_env_var_overrides_default(self, monkeypatch):
        """VERITAS_LOG_MAX_LINES should override the default MAX_LINES."""
        monkeypatch.setenv("VERITAS_LOG_MAX_LINES", "1000")
        assert rotate._get_max_lines() == 1000

    def test_env_var_invalid_falls_back_to_module_var(self, monkeypatch):
        """Invalid VERITAS_LOG_MAX_LINES should fall back to module MAX_LINES."""
        monkeypatch.setenv("VERITAS_LOG_MAX_LINES", "not_a_number")
        result = rotate._get_max_lines()
        assert result == rotate.MAX_LINES

    def test_env_var_zero_falls_back_to_module_var(self, monkeypatch):
        """Zero VERITAS_LOG_MAX_LINES should fall back to module MAX_LINES."""
        monkeypatch.setenv("VERITAS_LOG_MAX_LINES", "0")
        result = rotate._get_max_lines()
        assert result == rotate.MAX_LINES

    def test_env_var_negative_falls_back_to_module_var(self, monkeypatch):
        """Negative VERITAS_LOG_MAX_LINES should fall back to module MAX_LINES."""
        monkeypatch.setenv("VERITAS_LOG_MAX_LINES", "-5")
        result = rotate._get_max_lines()
        assert result == rotate.MAX_LINES

    def test_no_env_var_uses_module_max_lines(self, monkeypatch):
        """Without env var, _get_max_lines returns module MAX_LINES."""
        monkeypatch.delenv("VERITAS_LOG_MAX_LINES", raising=False)
        assert rotate._get_max_lines() == rotate.MAX_LINES

    def test_rotate_respects_env_var(self, tmp_path, monkeypatch):
        """rotate_if_needed should use VERITAS_LOG_MAX_LINES threshold."""
        log_path = tmp_path / "trust_log.jsonl"
        monkeypatch.setattr(log_paths, "LOG_JSONL", log_path)
        monkeypatch.setenv("VERITAS_LOG_MAX_LINES", "3")

        # Write 3 lines (at threshold)
        entries = [json.dumps({"sha256": f"h{i}", "d": i}) for i in range(3)]
        log_path.write_text("\n".join(entries) + "\n", encoding="utf-8")

        result = rotate.rotate_if_needed()
        # 3 lines >= 3, so rotation should occur
        assert not log_path.exists()

    def test_default_max_lines_value(self):
        """Default MAX_LINES should be 5000."""
        assert rotate._DEFAULT_MAX_LINES == 5000
        assert rotate.MAX_LINES == 5000


# =========================================================
# atomic_io.py: warning-level fsync logging
# =========================================================

class TestAtomicIoFsyncLogging:
    """Test that dir fsync failures are logged at WARNING level."""

    def test_atomic_write_bytes_logs_warning_on_dir_fsync_failure(self, tmp_path, caplog):
        """Dir fsync failures should be logged at WARNING level."""
        from veritas_os.core import atomic_io

        target = tmp_path / "test.txt"

        # Patch os.open to fail only on the dir fsync call (O_RDONLY for directory)
        original_os_open = os.open

        def patched_os_open(path, flags, *args, **kwargs):
            if flags == os.O_RDONLY and str(path) == str(target.parent):
                raise OSError("dir open failed for test")
            return original_os_open(path, flags, *args, **kwargs)

        with caplog.at_level(logging.WARNING, logger="veritas_os.core.atomic_io"):
            with mock.patch("os.open", side_effect=patched_os_open):
                atomic_io._atomic_write_bytes(target, b"hello")

        assert target.read_bytes() == b"hello"
        assert "dir fsync failed" in caplog.text
        # Verify it's logged at WARNING level, not DEBUG
        warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert any("dir fsync failed" in r.message for r in warning_records)
