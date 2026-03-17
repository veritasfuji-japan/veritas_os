"""Tests for API lifespan orchestration helper."""

from __future__ import annotations

import asyncio
import logging

import pytest

from veritas_os.api.lifespan import run_lifespan


def test_run_lifespan_calls_start_and_stop_in_order(monkeypatch):
    """Lifespan helper should run startup and shutdown callbacks in order."""
    import veritas_os.api.middleware as middleware
    import veritas_os.api.server as server

    monkeypatch.setattr(middleware, "_inflight_count", 0)
    monkeypatch.setattr(server, "_inflight_count", 0)

    calls: list[str] = []

    def _push(name: str):
        def _inner() -> None:
            calls.append(name)

        return _inner

    async def _exercise() -> None:
        async with run_lifespan(
            app=server.app,
            startup_validation=_push("validate"),
            runtime_health_check=_push("health"),
            check_multiworker_auth_store=_push("auth_store"),
            start_nonce_cleanup_scheduler=_push("start_nonce"),
            start_rate_cleanup_scheduler=_push("start_rate"),
            stop_nonce_cleanup_scheduler=_push("stop_nonce"),
            stop_rate_cleanup_scheduler=_push("stop_rate"),
            close_llm_pool=_push("close_pool"),
            logger=logging.getLogger(__name__),
        ):
            calls.append("inside")

    asyncio.run(_exercise())

    assert calls == [
        "validate",
        "health",
        "auth_store",
        "start_nonce",
        "start_rate",
        "inside",
        "stop_nonce",
        "stop_rate",
        "close_pool",
    ]


def test_run_lifespan_fails_fast_before_scheduler_start(monkeypatch):
    """Startup failures must abort lifespan before scheduler startup."""
    import veritas_os.api.server as server

    calls: list[str] = []

    def _raise_validate() -> None:
        calls.append("validate")
        raise RuntimeError("startup invalid")

    def _start_scheduler() -> None:
        calls.append("start")

    async def _exercise() -> None:
        async with run_lifespan(
            app=server.app,
            startup_validation=_raise_validate,
            runtime_health_check=lambda: None,
            check_multiworker_auth_store=lambda: None,
            start_nonce_cleanup_scheduler=_start_scheduler,
            start_rate_cleanup_scheduler=lambda: None,
            stop_nonce_cleanup_scheduler=lambda: None,
            stop_rate_cleanup_scheduler=lambda: None,
            close_llm_pool=None,
            logger=logging.getLogger(__name__),
        ):
            raise AssertionError("unreachable")

    with pytest.raises(RuntimeError, match="startup invalid"):
        asyncio.run(_exercise())

    assert calls == ["validate"]
