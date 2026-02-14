# tests/test_config_coverage.py
# -*- coding: utf-8 -*-
"""Coverage boost tests for veritas_os/core/config.py"""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from veritas_os.core.config import (
    _parse_cors_origins,
    _parse_float,
    _parse_int,
    ScoringConfig,
    FujiConfig,
    PipelineConfig,
    VeritasConfig,
)


# ============================================================
# _parse_cors_origins
# ============================================================

def test_parse_cors_origins_empty():
    assert _parse_cors_origins("") == []


def test_parse_cors_origins_normal():
    result = _parse_cors_origins("https://a.com, https://b.com")
    assert result == ["https://a.com", "https://b.com"]


def test_parse_cors_origins_wildcard_filtered(caplog):
    caplog.set_level(logging.WARNING)
    result = _parse_cors_origins("https://a.com, *, https://b.com")
    assert result == ["https://a.com", "https://b.com"]
    assert "ignored for safety" in caplog.text


def test_parse_cors_origins_only_wildcard(caplog):
    caplog.set_level(logging.WARNING)
    result = _parse_cors_origins("*")
    assert result == []
    assert "ignored for safety" in caplog.text


def test_parse_cors_origins_whitespace():
    result = _parse_cors_origins("  https://a.com  ,  ,  https://b.com  ")
    assert result == ["https://a.com", "https://b.com"]


# ============================================================
# _parse_float
# ============================================================

def test_parse_float_default(monkeypatch):
    monkeypatch.delenv("TEST_FLOAT_KEY", raising=False)
    assert _parse_float("TEST_FLOAT_KEY", 3.14) == 3.14


def test_parse_float_valid(monkeypatch):
    monkeypatch.setenv("TEST_FLOAT_KEY", "2.5")
    assert _parse_float("TEST_FLOAT_KEY", 0.0) == 2.5


def test_parse_float_invalid(monkeypatch):
    monkeypatch.setenv("TEST_FLOAT_KEY", "not_a_number")
    assert _parse_float("TEST_FLOAT_KEY", 9.9) == 9.9


def test_parse_float_invalid_logs_warning(monkeypatch, caplog):
    monkeypatch.setenv("TEST_FLOAT_KEY", "bad")
    caplog.set_level(logging.WARNING)

    assert _parse_float("TEST_FLOAT_KEY", 1.0) == 1.0
    assert "Invalid float for TEST_FLOAT_KEY" in caplog.text


def test_parse_float_empty(monkeypatch):
    monkeypatch.setenv("TEST_FLOAT_KEY", "")
    # empty string -> ValueError -> default
    assert _parse_float("TEST_FLOAT_KEY", 1.1) == 1.1


# ============================================================
# _parse_int
# ============================================================

def test_parse_int_default(monkeypatch):
    monkeypatch.delenv("TEST_INT_KEY", raising=False)
    assert _parse_int("TEST_INT_KEY", 42) == 42


def test_parse_int_valid(monkeypatch):
    monkeypatch.setenv("TEST_INT_KEY", "7")
    assert _parse_int("TEST_INT_KEY", 0) == 7


def test_parse_int_invalid(monkeypatch):
    monkeypatch.setenv("TEST_INT_KEY", "abc")
    assert _parse_int("TEST_INT_KEY", 99) == 99


def test_parse_int_invalid_logs_warning(monkeypatch, caplog):
    monkeypatch.setenv("TEST_INT_KEY", "bad")
    caplog.set_level(logging.WARNING)

    assert _parse_int("TEST_INT_KEY", 2) == 2
    assert "Invalid int for TEST_INT_KEY" in caplog.text


def test_parse_int_float_string(monkeypatch):
    monkeypatch.setenv("TEST_INT_KEY", "3.5")
    # "3.5" -> ValueError for int() -> default
    assert _parse_int("TEST_INT_KEY", 10) == 10


# ============================================================
# VeritasConfig.__post_init__ path defaults
# ============================================================

def test_veritas_config_post_init_defaults():
    """All path fields get defaults when None."""
    cfg = VeritasConfig(api_secret="test_secret_value")
    assert cfg.log_dir is not None
    assert cfg.dataset_dir is not None
    assert cfg.data_dir is not None
    assert cfg.memory_path is not None
    assert cfg.value_stats_path is not None
    assert cfg.trust_log_path is not None
    assert cfg.kv_path is not None


def test_veritas_config_api_key_alias():
    """api_key gets api_key_str value when empty."""
    cfg = VeritasConfig(api_key_str="my_key", api_secret="test_secret_value")
    assert cfg.api_key == "my_key"


def test_veritas_config_api_key_not_overwritten():
    """api_key is preserved when already set."""
    cfg = VeritasConfig(api_key_str="str_key", api_key="explicit", api_secret="test_secret_value")
    assert cfg.api_key == "explicit"


def test_veritas_config_no_secret_warning(caplog):
    """Warning logged when api_secret is empty."""
    caplog.set_level(logging.WARNING)
    cfg = VeritasConfig(api_secret="")
    assert "VERITAS_API_SECRET is not set" in caplog.text


def test_veritas_config_custom_paths():
    """Explicit paths are preserved."""
    cfg = VeritasConfig(
        log_dir=Path("/tmp/logs"),
        dataset_dir=Path("/tmp/ds"),
        api_secret="test_secret_value",
    )
    assert cfg.log_dir == Path("/tmp/logs")
    assert cfg.dataset_dir == Path("/tmp/ds")


# ============================================================
# ensure_dirs
# ============================================================

def test_ensure_dirs_creates(tmp_path):
    cfg = VeritasConfig(
        log_dir=tmp_path / "logs",
        dataset_dir=tmp_path / "ds",
        data_dir=tmp_path / "data",
        kv_path=tmp_path / "kv" / "kv.sqlite3",
        api_secret="test_secret_value",
    )
    cfg.ensure_dirs()
    assert (tmp_path / "logs").exists()
    assert (tmp_path / "ds").exists()
    assert (tmp_path / "data").exists()
    assert (tmp_path / "kv").exists()


def test_ensure_dirs_idempotent(tmp_path):
    cfg = VeritasConfig(
        log_dir=tmp_path / "logs",
        dataset_dir=tmp_path / "ds",
        data_dir=tmp_path / "data",
        kv_path=tmp_path / "kv" / "kv.sqlite3",
        api_secret="test_secret_value",
    )
    cfg.ensure_dirs()
    cfg.ensure_dirs()  # second call should be no-op
    assert cfg._dirs_ensured is True


def test_ensure_dirs_oserror(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.WARNING)
    cfg = VeritasConfig(
        log_dir=tmp_path / "logs",
        dataset_dir=tmp_path / "ds",
        data_dir=tmp_path / "data",
        kv_path=tmp_path / "kv" / "kv.sqlite3",
        api_secret="test_secret_value",
    )
    # Monkey-patch mkdir to raise OSError
    original_mkdir = Path.mkdir

    def _fail_mkdir(self, *args, **kwargs):
        raise OSError("permission denied")

    monkeypatch.setattr(Path, "mkdir", _fail_mkdir)
    cfg.ensure_dirs()
    assert "Failed to create directories" in caplog.text
    assert cfg._dirs_ensured is False


# ============================================================
# __repr__
# ============================================================

def test_veritas_config_repr():
    cfg = VeritasConfig(api_secret="test_secret_value")
    r = repr(cfg)
    assert "***" in r
    assert "test_secret_value" not in r


# ============================================================
# api_secret_configured
# ============================================================

def test_api_secret_configured_empty():
    cfg = VeritasConfig(api_secret="")
    assert cfg.api_secret_configured is False


def test_api_secret_configured_placeholder():
    cfg = VeritasConfig(api_secret="YOUR_VERITAS_API_SECRET_HERE")
    assert cfg.api_secret_configured is False


def test_api_secret_configured_valid():
    cfg = VeritasConfig(api_secret="real_secret_123")
    assert cfg.api_secret_configured is True


def test_api_secret_configured_whitespace():
    cfg = VeritasConfig(api_secret="   ")
    assert cfg.api_secret_configured is False


def test_api_secret_configured_placeholder_with_spaces():
    cfg = VeritasConfig(api_secret="  YOUR_VERITAS_API_SECRET_HERE  ")
    assert cfg.api_secret_configured is False


# ============================================================
# ScoringConfig defaults
# ============================================================

def test_scoring_config_defaults():
    sc = ScoringConfig()
    assert sc.intent_weather_bonus == pytest.approx(0.4)
    assert sc.query_match_bonus == pytest.approx(0.2)
    assert sc.high_stakes_threshold == pytest.approx(0.7)


# ============================================================
# FujiConfig defaults
# ============================================================

def test_fuji_config_defaults():
    fc = FujiConfig()
    assert fc.default_min_evidence == 1
    assert fc.max_uncertainty == pytest.approx(0.60)


# ============================================================
# PipelineConfig defaults
# ============================================================

def test_pipeline_config_defaults():
    pc = PipelineConfig()
    assert pc.memory_search_limit == 8
    assert pc.max_plan_steps == 10


# ============================================================
# data_dir defaults to log_dir
# ============================================================

def test_data_dir_defaults_to_log_dir():
    cfg = VeritasConfig(api_secret="test_secret_value")
    assert cfg.data_dir == cfg.log_dir
