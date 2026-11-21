"""Bound the process-local emergency halt at API startup."""

from __future__ import annotations

import json
import logging
import selectors
import subprocess
import sys

import pytest

from veritas_os.api import auth, startup_health


@pytest.fixture(autouse=True)
def isolated_deployment(monkeypatch):
    for key in (
        "VERITAS_ENV", "VERITAS_POSTURE", "NODE_ENV",
        "VERITAS_REQUIRE_PRODUCTION_TRUSTLOG_POSTURE",
        "WEB_CONCURRENCY", "UVICORN_WORKERS",
        "VERITAS_AUTH_ALLOW_FAIL_OPEN", "VERITAS_AUTH_STORE_FAILURE_MODE",
        "VERITAS_ENABLE_DIRECT_FUJI_API", "NEXT_PUBLIC_VERITAS_API_BASE_URL",
    ):
        monkeypatch.delenv(key, raising=False)
    # Keep unrelated TrustLog configuration out of these deployment checks.
    monkeypatch.setattr(
        startup_health, "validate_trustlog_production_posture_on_startup",
        lambda **kwargs: None,
    )


def _validate_startup() -> None:
    startup_health.run_startup_config_validation(
        logger=logging.getLogger(__name__), validator=lambda: None,
    )


@pytest.mark.parametrize("worker_var", ["WEB_CONCURRENCY", "UVICORN_WORKERS"])
@pytest.mark.parametrize("profile", ["prod", "production", "secure", "hardened"])
def test_strict_multiple_workers_refuse_even_with_redis(monkeypatch, worker_var, profile):
    monkeypatch.setenv("VERITAS_ENV", profile)
    monkeypatch.setenv(worker_var, "2")
    monkeypatch.setenv("VERITAS_AUTH_SECURITY_STORE", "redis")
    with pytest.raises(RuntimeError, match="process-local emergency halt"):
        _validate_startup()


@pytest.mark.parametrize("posture", ["secure", "prod"])
def test_strict_posture_refuses_multiple_workers(monkeypatch, posture):
    monkeypatch.setenv("VERITAS_ENV", "local")
    monkeypatch.setenv("VERITAS_POSTURE", posture)
    monkeypatch.setenv("WEB_CONCURRENCY", "2")
    with pytest.raises(RuntimeError, match="process-local emergency halt"):
        _validate_startup()


@pytest.mark.parametrize("counts", [("invalid", "2"), ("2", "invalid")])
def test_other_worker_setting_cannot_hide_multiple_workers(monkeypatch, counts):
    monkeypatch.setenv("VERITAS_ENV", "production")
    monkeypatch.setenv("WEB_CONCURRENCY", counts[0])
    monkeypatch.setenv("UVICORN_WORKERS", counts[1])
    with pytest.raises(RuntimeError, match="process-local emergency halt"):
        _validate_startup()


def test_enforced_production_posture_refuses_multiple_workers(monkeypatch):
    monkeypatch.setenv("VERITAS_REQUIRE_PRODUCTION_TRUSTLOG_POSTURE", "1")
    monkeypatch.setenv("WEB_CONCURRENCY", "2")
    with pytest.raises(RuntimeError, match="process-local emergency halt"):
        _validate_startup()


def test_local_multiple_workers_warn(monkeypatch, caplog):
    monkeypatch.setenv("VERITAS_ENV", "local")
    monkeypatch.setenv("WEB_CONCURRENCY", "2")
    _validate_startup()
    assert "process-local emergency halt" in caplog.text


def test_strict_single_worker_remains_allowed(monkeypatch, caplog):
    monkeypatch.setenv("VERITAS_ENV", "production")
    monkeypatch.setenv("WEB_CONCURRENCY", "1")
    monkeypatch.setenv("UVICORN_WORKERS", "1")
    _validate_startup()
    assert "process-local emergency halt" not in caplog.text


def test_halt_state_is_not_shared_with_another_process():
    """A second interpreter remains running while the halted one is alive."""
    source = (
        "import json; "
        "from veritas_os.core.eu_ai_act_oversight import SystemHaltController as C; "
    )
    first_source = (
        source + "C.halt(reason='worker-boundary-test', operator='synthetic-operator'); "
        "print(json.dumps(C.status()), flush=True); input()"
    )
    with subprocess.Popen(
        [sys.executable, "-c", first_source],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    ) as first:
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(first.stdout, selectors.EVENT_READ)
                assert selector.select(timeout=15), "halted process did not report status"
                assert json.loads(first.stdout.readline())["halted"] is True
            other = subprocess.run(
                [sys.executable, "-c", source + "print(json.dumps(C.status()))"],
                check=True, capture_output=True, text=True, timeout=15,
            )
            assert first.poll() is None
            assert json.loads(other.stdout)["halted"] is False
        finally:
            first.terminate()
            first.communicate(timeout=5)

def test_strict_shared_halt_requires_shared_auth_even_without_worker_count(monkeypatch):
    monkeypatch.setenv("VERITAS_ENV", "secure")
    monkeypatch.setenv("VERITAS_HALT_BACKEND", "postgresql")
    monkeypatch.setattr(auth, "_get_effective_auth_store", lambda: object())
    with pytest.raises(RuntimeError, match="shared Redis auth store"):
        auth._check_multiworker_auth_store()
