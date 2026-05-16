"""Optional dependency behavior tests for observability exporters."""

import builtins
import importlib
import sys
from typing import Any

import pytest


def _block_fastapi_import(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    original_import = builtins.__import__
    attempted: list[str] = []

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "fastapi" or name.startswith("fastapi."):
            attempted.append(name)
            raise ModuleNotFoundError("No module named 'fastapi'")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    return attempted


def _drop_observability_exporters(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delitem(sys.modules, "veritas_os.observability.exporters", raising=False)


class _DummyApp:
    def add_api_route(self, *args: Any, **kwargs: Any) -> None:
        raise AssertionError("add_api_route should not be called")


def test_observability_exporters_import_does_not_require_fastapi(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempted = _block_fastapi_import(monkeypatch)
    _drop_observability_exporters(monkeypatch)

    importlib.import_module("veritas_os.observability.exporters")

    assert attempted == []


def test_configure_metrics_exporter_none_does_not_require_fastapi(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempted = _block_fastapi_import(monkeypatch)
    _drop_observability_exporters(monkeypatch)
    monkeypatch.setenv("VERITAS_METRICS_EXPORTER", "none")

    exporters = importlib.import_module("veritas_os.observability.exporters")
    assert exporters.configure_metrics_exporter(_DummyApp()) == "none"
    assert attempted == []


def test_configure_metrics_exporter_unknown_mode_does_not_require_fastapi(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempted = _block_fastapi_import(monkeypatch)
    _drop_observability_exporters(monkeypatch)
    monkeypatch.setenv("VERITAS_METRICS_EXPORTER", "unknown")

    exporters = importlib.import_module("veritas_os.observability.exporters")
    assert exporters.configure_metrics_exporter(_DummyApp()) == "none"
    assert attempted == []


def test_configure_metrics_exporter_otlp_does_not_require_fastapi(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempted = _block_fastapi_import(monkeypatch)
    _drop_observability_exporters(monkeypatch)
    monkeypatch.setenv("VERITAS_METRICS_EXPORTER", "otlp")

    exporters = importlib.import_module("veritas_os.observability.exporters")
    monkeypatch.setattr(exporters, "_configure_otlp_exporter", lambda: True)

    assert exporters.configure_metrics_exporter(_DummyApp()) == "otlp"
    assert attempted == []


def test_configure_metrics_exporter_prometheus_requires_fastapi_responses_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempted = _block_fastapi_import(monkeypatch)
    _drop_observability_exporters(monkeypatch)
    monkeypatch.setenv("VERITAS_METRICS_EXPORTER", "prometheus")

    exporters = importlib.import_module("veritas_os.observability.exporters")

    with pytest.raises(RuntimeError, match="FastAPI|API dependencies"):
        exporters.configure_metrics_exporter(_DummyApp())

    assert any(name == "fastapi.responses" or name == "fastapi" for name in attempted)
