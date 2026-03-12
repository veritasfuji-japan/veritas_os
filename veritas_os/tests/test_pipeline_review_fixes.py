# -*- coding: utf-8 -*-
"""
Tests for pipeline.py review fixes:
- _norm_alt: id sanitisation (null bytes, control chars, length limit)
- _save_valstats: warning-level logging on I/O failure
- Silent exception handlers: debug logging
- EVIDENCE_MAX validation
- _dedupe_alts type validation
- call_core_decide TypeError propagation
- _to_dict circular reference guard
"""

import logging
import re
from unittest.mock import patch

import pytest

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


# =========================================================
# _to_dict defensive try-except on model_dump / dict
# =========================================================

class TestToDictDefensive:

    def test_dict_passthrough(self):
        from veritas_os.core.pipeline import _to_dict
        d = {"a": 1}
        assert _to_dict(d) is d

    def test_model_dump_failure_falls_through(self):
        from veritas_os.core.pipeline import _to_dict

        class BadModel:
            def model_dump(self, **kwargs):
                raise RuntimeError("model_dump broken")

            def __init__(self):
                self.x = 42

        result = _to_dict(BadModel())
        assert result.get("x") == 42

    def test_dict_method_failure_falls_through(self):
        from veritas_os.core.pipeline import _to_dict

        class BadDictModel:
            def dict(self):
                raise TypeError("dict broken")

            def __init__(self):
                self.y = 99

        result = _to_dict(BadDictModel())
        assert result.get("y") == 99

    def test_all_methods_fail_returns_empty(self):
        from veritas_os.core.pipeline import _to_dict

        class AllBad:
            def model_dump(self, **kwargs):
                raise ValueError("broken")

            def dict(self):
                raise ValueError("broken")

            @property
            def __dict__(self):
                raise TypeError("broken")

        result = _to_dict(AllBad())
        assert result == {}


# =========================================================
# EVIDENCE_MAX bounds validation
# =========================================================

class TestEvidenceMaxBounds:

    def test_evidence_max_is_positive(self):
        from veritas_os.core.pipeline import EVIDENCE_MAX
        assert EVIDENCE_MAX >= 1

    def test_evidence_max_within_bounds(self):
        from veritas_os.core.pipeline import EVIDENCE_MAX, _EVIDENCE_MAX_UPPER
        assert 1 <= EVIDENCE_MAX <= _EVIDENCE_MAX_UPPER

    def test_evidence_max_fallback_on_invalid_env(self, monkeypatch):
        """Values outside [1, 10000] should fall back to 50."""
        import importlib
        import veritas_os.core.pipeline as pipeline_mod

        monkeypatch.setenv("VERITAS_EVIDENCE_MAX", "0")
        importlib.reload(pipeline_mod)
        assert pipeline_mod.EVIDENCE_MAX == 50

        monkeypatch.setenv("VERITAS_EVIDENCE_MAX", "-5")
        importlib.reload(pipeline_mod)
        assert pipeline_mod.EVIDENCE_MAX == 50

        # Restore default
        monkeypatch.delenv("VERITAS_EVIDENCE_MAX", raising=False)
        importlib.reload(pipeline_mod)

    def test_evidence_max_fallback_on_non_numeric_env(self, monkeypatch):
        """Non-numeric string should fall back to 50 without crashing."""
        import importlib
        import veritas_os.core.pipeline as pipeline_mod

        monkeypatch.setenv("VERITAS_EVIDENCE_MAX", "abc")
        importlib.reload(pipeline_mod)
        assert pipeline_mod.EVIDENCE_MAX == 50

        monkeypatch.setenv("VERITAS_EVIDENCE_MAX", "")
        importlib.reload(pipeline_mod)
        assert pipeline_mod.EVIDENCE_MAX == 50

        monkeypatch.setenv("VERITAS_EVIDENCE_MAX", "3.14")
        importlib.reload(pipeline_mod)
        assert pipeline_mod.EVIDENCE_MAX == 50

        # Restore default
        monkeypatch.delenv("VERITAS_EVIDENCE_MAX", raising=False)
        importlib.reload(pipeline_mod)


# =========================================================
# _dedupe_alts type validation
# =========================================================

class TestDedupeAltsTypeValidation:

    def test_kernel_returns_none_uses_fallback(self, caplog):
        """When kernel._dedupe_alts returns None, fallback should be used."""
        import veritas_os.core.pipeline as pipeline_mod

        class FakeKernel:
            def _dedupe_alts(self, alts):
                return None  # Not a list

        original = pipeline_mod.veritas_core
        try:
            pipeline_mod.veritas_core = FakeKernel()
            with caplog.at_level(logging.DEBUG, logger="veritas_os.core.pipeline"):
                result = _dedupe_alts([{"title": "a", "description": "b"}])
            assert isinstance(result, list)
            assert len(result) == 1
        finally:
            pipeline_mod.veritas_core = original

    def test_kernel_returns_string_uses_fallback(self):
        """When kernel._dedupe_alts returns a non-list, fallback should be used."""
        import veritas_os.core.pipeline as pipeline_mod

        class FakeKernel:
            def _dedupe_alts(self, alts):
                return "not a list"

        original = pipeline_mod.veritas_core
        try:
            pipeline_mod.veritas_core = FakeKernel()
            result = _dedupe_alts([{"title": "a", "description": "b"}])
            assert isinstance(result, list)
            assert len(result) == 1
        finally:
            pipeline_mod.veritas_core = original


# =========================================================
# _norm_alt Unicode control character sanitisation
# =========================================================

class TestNormAltUnicodeSanitisation:

    def test_bidi_override_removed(self):
        """U+202E (RLO) and U+202C (PDF) should be stripped from IDs."""
        result = _norm_alt({"id": "abc\u202edef\u202c", "text": "x"})
        assert "\u202e" not in result["id"]
        assert "\u202c" not in result["id"]
        assert result["id"] == "abcdef"

    def test_line_separator_removed(self):
        """U+2028 (LINE SEPARATOR) should be stripped."""
        result = _norm_alt({"id": "abc\u2028def", "text": "x"})
        assert "\u2028" not in result["id"]

    def test_paragraph_separator_removed(self):
        """U+2029 (PARAGRAPH SEPARATOR) should be stripped."""
        result = _norm_alt({"id": "abc\u2029def", "text": "x"})
        assert "\u2029" not in result["id"]

    def test_normal_unicode_preserved(self):
        """Regular Unicode text (CJK, accented, emoji) should be kept."""
        result = _norm_alt({"id": "日本語テスト", "text": "x"})
        assert result["id"] == "日本語テスト"

    def test_mixed_control_and_normal_chars(self):
        """Mix of control and normal chars: only control stripped."""
        result = _norm_alt({"id": "ok\x00\u202ebad\u202c", "text": "x"})
        assert result["id"] == "okbad"


# =========================================================
# call_core_decide TypeError propagation
# =========================================================

class TestCallCoreDecideTypeErrorPropagation:

    @pytest.mark.asyncio
    async def test_internal_type_error_propagated(self):
        """TypeError raised *inside* core_fn should not be swallowed."""
        from veritas_os.core.pipeline import call_core_decide

        def bad_core_fn(context, query, alternatives, min_evidence=None):
            # Internal TypeError, not a signature mismatch
            raise TypeError("internal processing error")

        with pytest.raises(TypeError, match="internal processing error"):
            await call_core_decide(
                bad_core_fn,
                context={"q": "test"},
                query="test",
                alternatives=[],
            )

    @pytest.mark.asyncio
    async def test_signature_mismatch_falls_through(self):
        """Signature mismatch (missing args) should try next convention."""
        from veritas_os.core.pipeline import call_core_decide

        def positional_fn(ctx, query, alts, min_evidence=None):
            return {"chosen": "ok"}

        result = await call_core_decide(
            positional_fn,
            context={"q": "test"},
            query="test",
            alternatives=[],
        )
        assert result["chosen"] == "ok"


# =========================================================
# _to_dict circular reference guard
# =========================================================

class TestToDictCircularRef:

    def test_self_referencing_object(self):
        """Object with self-reference should not include the circular ref."""
        from veritas_os.core.pipeline import _to_dict
        import json

        class Circular:
            def __init__(self):
                self.name = "test"
                self.self_ref = self  # circular

        obj = Circular()
        result = _to_dict(obj)
        assert result["name"] == "test"
        assert "self_ref" not in result
        # Must be JSON-serializable
        json.dumps(result)

    def test_non_circular_object_unchanged(self):
        """Normal objects should be converted without filtering."""
        from veritas_os.core.pipeline import _to_dict

        class Normal:
            def __init__(self):
                self.a = 1
                self.b = "hello"

        result = _to_dict(Normal())
        assert result == {"a": 1, "b": "hello"}


# =========================================================
# Security hardening
# =========================================================


class TestSecurityHardening:

    @pytest.mark.asyncio
    async def test_safe_web_search_logs_redacted_query(self, monkeypatch, caplog):
        """Debug log should redact query text on adapter failure."""
        import veritas_os.core.pipeline as pipeline_mod

        def bad_search(*args, **kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr(pipeline_mod, "web_search", bad_search, raising=False)
        with caplog.at_level(logging.DEBUG, logger="veritas_os.core.pipeline"):
            result = await pipeline_mod._safe_web_search("mail me at a@example.com")

        assert result is None
        messages = [record.getMessage() for record in caplog.records]
        assert any(
            "_safe_web_search failed for query_redacted=" in message
            for message in messages
        )
        assert any("query_sha256_12=" in message for message in messages)
        assert all("a@example.com" not in message for message in messages)

    def test_safe_paths_rejects_external_env_dir_by_default(
        self,
        monkeypatch,
        caplog,
    ):
        """External env paths should be ignored unless explicitly allowed."""
        import veritas_os.core.pipeline as pipeline_mod

        log_env = "/tmp/veritas_external_logs"
        dataset_env = "/tmp/veritas_external_dataset"
        monkeypatch.delenv("VERITAS_ALLOW_EXTERNAL_PATHS", raising=False)
        monkeypatch.setenv("VERITAS_LOG_DIR", log_env)
        monkeypatch.setenv("VERITAS_DATASET_DIR", dataset_env)

        with caplog.at_level(logging.WARNING, logger="veritas_os.core.pipeline"):
            log_dir, dataset_dir, _, _ = pipeline_mod._safe_paths()

        assert str(log_dir) != log_env
        assert str(dataset_dir) != dataset_env
        assert any(
            "[SECURITY][pipeline] Ignoring VERITAS_LOG_DIR" in record.getMessage()
            for record in caplog.records
        )
        assert any(
            "[SECURITY][pipeline] Ignoring VERITAS_DATASET_DIR" in record.getMessage()
            for record in caplog.records
        )
        assert all(log_env not in record.getMessage() for record in caplog.records)
        assert all(dataset_env not in record.getMessage() for record in caplog.records)

    def test_safe_paths_accepts_external_env_dir_when_explicitly_allowed(
        self,
        monkeypatch,
        tmp_path,
    ):
        """External env paths are allowed only with explicit opt-in."""
        import veritas_os.core.pipeline as pipeline_mod

        monkeypatch.setenv("VERITAS_ALLOW_EXTERNAL_PATHS", "1")
        monkeypatch.setenv("VERITAS_LOG_DIR", str(tmp_path / "logs"))
        monkeypatch.setenv("VERITAS_DATASET_DIR", str(tmp_path / "dataset"))

        log_dir, dataset_dir, _, _ = pipeline_mod._safe_paths()

        assert log_dir == (tmp_path / "logs").resolve()
        assert dataset_dir == (tmp_path / "dataset").resolve()

    def test_safe_paths_warns_when_external_paths_enabled(
        self,
        monkeypatch,
        caplog,
        tmp_path,
    ):
        """Enabling external paths must emit an explicit security warning."""
        import veritas_os.core.pipeline as pipeline_mod

        monkeypatch.setenv("VERITAS_ALLOW_EXTERNAL_PATHS", "1")
        monkeypatch.setenv("VERITAS_LOG_DIR", str(tmp_path / "logs"))
        monkeypatch.setenv("VERITAS_DATASET_DIR", str(tmp_path / "dataset"))

        with caplog.at_level(logging.WARNING, logger="veritas_os.core.pipeline"):
            pipeline_mod._safe_paths()

        assert any(
            "VERITAS_ALLOW_EXTERNAL_PATHS=1 is enabled" in record.getMessage()
            for record in caplog.records
        )

    def test_safe_paths_rejects_external_lp_file_targets_by_default(
        self,
        monkeypatch,
        caplog,
    ):
        """VAL_JSON/META_LOG from logging.paths must also follow path policy."""
        import veritas_os.core.pipeline as pipeline_mod

        from veritas_os.logging import paths as lp

        monkeypatch.delenv("VERITAS_ALLOW_EXTERNAL_PATHS", raising=False)
        monkeypatch.setattr(lp, "LOG_DIR", str(pipeline_mod.REPO_ROOT / "logs"))
        monkeypatch.setattr(lp, "DATASET_DIR", str(pipeline_mod.REPO_ROOT / "dataset"))
        monkeypatch.setattr(lp, "VAL_JSON", "/tmp/veritas_external_value_ema.json")
        monkeypatch.setattr(lp, "META_LOG", "/tmp/veritas_external_meta.log")

        with caplog.at_level(logging.WARNING, logger="veritas_os.core.pipeline"):
            _, _, val_json, meta_log = pipeline_mod._safe_paths()

        assert val_json == (pipeline_mod.REPO_ROOT / "logs" / "value_ema.json").resolve()
        assert meta_log == (pipeline_mod.REPO_ROOT / "logs" / "meta.log").resolve()
        assert any(
            "[SECURITY][pipeline] Ignoring logging.paths.VAL_JSON" in record.getMessage()
            for record in caplog.records
        )
        assert any(
            "[SECURITY][pipeline] Ignoring logging.paths.META_LOG" in record.getMessage()
            for record in caplog.records
        )
