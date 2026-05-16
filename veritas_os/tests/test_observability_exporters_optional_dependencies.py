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


class _RecordingApp:
    def __init__(self) -> None:
        self.routes: list[dict[str, Any]] = []

    def add_api_route(self, *args: Any, **kwargs: Any) -> None:
        self.routes.append({"args": args, "kwargs": kwargs})


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


def test_configure_metrics_exporter_prometheus_auth_requires_fastapi_depends_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _drop_observability_exporters(monkeypatch)
    monkeypatch.setenv("VERITAS_METRICS_EXPORTER", "prometheus")
    monkeypatch.setenv("VERITAS_METRICS_AUTH", "1")

    exporters = importlib.import_module("veritas_os.observability.exporters")
    monkeypatch.setattr(exporters, "_build_prometheus_endpoint", lambda: lambda: None)

    def missing_depends() -> Any:
        raise RuntimeError(
            "Authenticated Prometheus metrics endpoint requires FastAPI. "
            "Install API dependencies before enabling VERITAS_METRICS_AUTH=1."
        )

    monkeypatch.setattr(exporters, "_resolve_fastapi_depends", missing_depends)

    def auth_dependency() -> bool:
        return True

    with pytest.raises(RuntimeError) as exc_info:
        exporters.configure_metrics_exporter(
            _RecordingApp(),
            auth_dependency=auth_dependency,
        )

    assert "VERITAS_METRICS_AUTH=1" in str(exc_info.value)


def test_configure_metrics_exporter_prometheus_auth_adds_dependency_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("fastapi")
    _drop_observability_exporters(monkeypatch)
    monkeypatch.setenv("VERITAS_METRICS_EXPORTER", "prometheus")
    monkeypatch.setenv("VERITAS_METRICS_AUTH", "1")

    exporters = importlib.import_module("veritas_os.observability.exporters")
    monkeypatch.setattr(exporters, "_build_prometheus_endpoint", lambda: lambda: None)

    app = _RecordingApp()

    def auth_dependency() -> bool:
        return True

    assert exporters.configure_metrics_exporter(
        app,
        auth_dependency=auth_dependency,
    ) == "prometheus"
    assert len(app.routes) == 1
    dependencies = app.routes[0]["kwargs"]["dependencies"]
    assert dependencies


def test_configure_metrics_exporter_prometheus_auth_disabled_does_not_resolve_depends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _drop_observability_exporters(monkeypatch)
    monkeypatch.setenv("VERITAS_METRICS_EXPORTER", "prometheus")
    monkeypatch.setenv("VERITAS_METRICS_AUTH", "0")

    exporters = importlib.import_module("veritas_os.observability.exporters")
    monkeypatch.setattr(exporters, "_build_prometheus_endpoint", lambda: lambda: None)

    def fail_depends() -> Any:
        raise AssertionError("_resolve_fastapi_depends should not be called")

    monkeypatch.setattr(exporters, "_resolve_fastapi_depends", fail_depends)

    app = _RecordingApp()

    def auth_dependency() -> bool:
        return True

    assert exporters.configure_metrics_exporter(
        app,
        auth_dependency=auth_dependency,
    ) == "prometheus"
    assert len(app.routes) == 1
    assert app.routes[0]["kwargs"]["dependencies"] == []
