# -*- coding: utf-8 -*-
"""
Tests for pipeline.py review fixes:
- _norm_alt: id sanitisation (null bytes, control chars, length limit)
- _save_valstats: warning-level logging on I/O failure
- Silent exception handlers: debug logging
"""

import logging
import re
from unittest.mock import patch

from veritas_os.core.pipeline import (
    _norm_alt,
    _save_valstats,
    _dedupe_alts,
    _get_request_params,
    _mem_model_path,
)


# =========================================================
# _norm_alt id sanitisation
# =========================================================

class TestNormAltIdSanitisation:

    def test_normal_id_preserved(self):
        result = _norm_alt({"id": "abc-123", "text": "x"})
        assert result["id"] == "abc-123"

    def test_none_id_generates_uuid(self):
        result = _norm_alt({"text": "x"})
        assert len(result["id"]) == 32  # uuid4().hex

    def test_empty_id_generates_uuid(self):
        result = _norm_alt({"id": "", "text": "x"})
        assert len(result["id"]) == 32

    def test_whitespace_only_id_generates_uuid(self):
        result = _norm_alt({"id": "   ", "text": "x"})
        assert len(result["id"]) == 32

    def test_null_bytes_removed(self):
        result = _norm_alt({"id": "abc\x00def", "text": "x"})
        assert "\x00" not in result["id"]
        assert result["id"] == "abcdef"

    def test_control_chars_removed(self):
        result = _norm_alt({"id": "abc\x01\x02\x1fdef", "text": "x"})
        assert result["id"] == "abcdef"
        assert not re.search(r"[\x00-\x1f\x7f]", result["id"])

    def test_del_char_removed(self):
        result = _norm_alt({"id": "abc\x7fdef", "text": "x"})
        assert "\x7f" not in result["id"]
        assert result["id"] == "abcdef"

    def test_id_truncated_at_256(self):
        long_id = "a" * 300
        result = _norm_alt({"id": long_id, "text": "x"})
        assert len(result["id"]) == 256

    def test_id_at_exactly_256_not_truncated(self):
        exact_id = "b" * 256
        result = _norm_alt({"id": exact_id, "text": "x"})
        assert result["id"] == exact_id

    def test_id_all_control_chars_generates_uuid(self):
        result = _norm_alt({"id": "\x00\x01\x02", "text": "x"})
        # After stripping control chars, empty -> uuid
        assert len(result["id"]) == 32

    def test_unicode_id_preserved(self):
        result = _norm_alt({"id": "日本語テスト", "text": "x"})
        assert result["id"] == "日本語テスト"


# =========================================================
# _save_valstats log level
# =========================================================

class TestSaveValstatsLogging:

    def test_save_failure_logs_warning(self, tmp_path, caplog):
        """I/O failure should produce a WARNING log, not DEBUG."""
        with patch("veritas_os.core.pipeline.VAL_JSON", str(tmp_path / "no" / "such" / "deep" / "nested" / "file.json")):
            # Force the parent mkdir to fail by making it a file
            blocker = tmp_path / "no"
            blocker.write_text("block")  # file blocks mkdir

            with caplog.at_level(logging.WARNING, logger="veritas_os.core.pipeline"):
                _save_valstats({"ema": 0.5})

            assert any("_save_valstats failed" in r.message for r in caplog.records)
            assert any(r.levelno == logging.WARNING for r in caplog.records if "_save_valstats" in r.message)


# =========================================================
# Silent exception handlers now log at DEBUG
# =========================================================

class TestDebugLoggingOnExceptions:

    def test_get_request_params_logs_debug_on_error(self, caplog):
        """_get_request_params should log at DEBUG when params extraction fails."""

        class BadReq:
            query_params = None

            def __getattribute__(self, name):
                if name == "params":
                    raise RuntimeError("boom")
                return object.__getattribute__(self, name)

        with caplog.at_level(logging.DEBUG, logger="veritas_os.core.pipeline"):
            result = _get_request_params(BadReq())

        assert result == {}
        assert any("params extraction failed" in r.message for r in caplog.records)

    def test_dedupe_alts_logs_debug_on_kernel_error(self, caplog):
        """_dedupe_alts should log at DEBUG when kernel helper fails."""
        import veritas_os.core.pipeline as pipeline_mod

        class FakeKernel:
            def _dedupe_alts(self, alts):
                raise ValueError("kernel error")

        original = pipeline_mod.veritas_core
        try:
            pipeline_mod.veritas_core = FakeKernel()
            with caplog.at_level(logging.DEBUG, logger="veritas_os.core.pipeline"):
                result = _dedupe_alts([{"title": "a", "description": "b"}])

            assert len(result) == 1
            assert any("kernel helper failed" in r.message for r in caplog.records)
        finally:
            pipeline_mod.veritas_core = original
