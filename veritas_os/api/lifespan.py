from __future__ import annotations

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Callable

from veritas_os.storage.factory import create_memory_store, create_trust_log_store


@asynccontextmanager
async def run_lifespan(
    app: Any,
    *,
    startup_validation: Callable[[], None],
    runtime_health_check: Callable[[], None],
    check_multiworker_auth_store: Callable[[], None],
    start_nonce_cleanup_scheduler: Callable[[], None],
    start_rate_cleanup_scheduler: Callable[[], None],
    stop_nonce_cleanup_scheduler: Callable[[], None],
    stop_rate_cleanup_scheduler: Callable[[], None],
    close_llm_pool: Callable[[], None] | None,
    logger: logging.Logger,
) -> AsyncIterator[None]:
    """Run API lifespan startup/shutdown flow with graceful drain.

    This helper keeps server bootstrap concerns out of ``server.py`` while
    preserving behavior and backward compatibility.
    """
    import veritas_os.api.middleware as middleware
    import veritas_os.api.server as server

    middleware._shutting_down = False
    middleware._inflight_count = 0
    server._shutting_down = False
    server._inflight_count = 0


    # Storage DI: initialize backend instances once per application lifecycle.
    app.state.trust_log_store = create_trust_log_store()
    app.state.memory_store = create_memory_store()

    # ── Posture: resolve, validate, log banner ──
    from veritas_os.core.posture import init_posture, set_active_posture

    posture_defaults = init_posture(fail_on_error=True)
    set_active_posture(posture_defaults)

    startup_validation()
    runtime_health_check()
    check_multiworker_auth_store()
    start_nonce_cleanup_scheduler()
    start_rate_cleanup_scheduler()

    try:
        yield
    finally:
        middleware._shutting_down = True
        server._shutting_down = True

        drain_sec = float(os.getenv("VERITAS_SHUTDOWN_DRAIN_SEC", "10"))
        deadline = time.monotonic() + drain_sec
        while time.monotonic() < deadline:
            with middleware._inflight_lock:
                if middleware._inflight_count <= 0:
                    break
            await asyncio.sleep(0.25)

        with middleware._inflight_lock:
            remaining = middleware._inflight_count

        if remaining > 0:
            logger.warning(
                "Shutting down with %d in-flight request(s) after %.0fs "
                "drain timeout",
                remaining,
                drain_sec,
            )
        else:
            logger.info("All in-flight requests drained, shutting down cleanly")

        stop_nonce_cleanup_scheduler()
        stop_rate_cleanup_scheduler()
        if close_llm_pool is not None:
            close_llm_pool()
