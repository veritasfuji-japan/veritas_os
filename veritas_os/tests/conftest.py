"""Pytest configuration for asynchronous test execution and TrustLog encryption.

This project includes ``@pytest.mark.asyncio`` tests but does not require an
external async pytest plugin in all environments. The hook below executes
coroutine test functions with ``asyncio.run`` so async tests remain portable.

TrustLog is secure-by-default and requires ``VERITAS_ENCRYPTION_KEY``.
A session-scoped autouse fixture injects a test key so that all tests
can write to TrustLog without manual key setup.
"""

from __future__ import annotations

import asyncio
import inspect
import os
from typing import Any

import pytest


@pytest.hookimpl(tryfirst=True)
def pytest_pyfunc_call(pyfuncitem: pytest.Function) -> bool | None:
    """Run ``async def`` test functions without external pytest async plugins."""
    test_function = pyfuncitem.obj
    if not inspect.iscoroutinefunction(test_function):
        return None

    fixture_args: dict[str, Any] = {
        arg_name: pyfuncitem.funcargs[arg_name]
        for arg_name in pyfuncitem._fixtureinfo.argnames
    }
    asyncio.run(test_function(**fixture_args))
    return True


@pytest.fixture(autouse=True, scope="session")
def _ensure_encryption_key():
    """Provide a test encryption key for TrustLog secure-by-default.

    TrustLog raises ``EncryptionKeyMissing`` when no key is configured.
    This session-scoped fixture injects a deterministic test key so that
    every test can call ``append_trust_log`` without extra setup.

    The key is only set when the environment variable is absent, so
    production-like CI runs that set a real key are not overridden.
    """
    if not os.environ.get("VERITAS_ENCRYPTION_KEY"):
        from veritas_os.logging.encryption import generate_key

        os.environ["VERITAS_ENCRYPTION_KEY"] = generate_key()
    yield
    # cleanup is intentionally omitted — the key is harmless and
    # removing it mid-session could break teardown logging.


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers used in this test suite."""
    config.addinivalue_line(
        "markers",
        "asyncio: mark test as asynchronous and execute via asyncio.run",
    )
    config.addinivalue_line(
        "markers",
        "slow: mark test as slow or external-I/O dependent",
    )
    config.addinivalue_line(
        "markers",
        "production: production-like validation requiring real services",
    )
    config.addinivalue_line(
        "markers",
        "smoke: lightweight smoke tests for deployment verification",
    )
    config.addinivalue_line(
        "markers",
        "external: tests that depend on external network services",
    )
    config.addinivalue_line(
        "markers",
        "unit: 単体テスト",
    )
    config.addinivalue_line(
        "markers",
        "integration: 統合テスト",
    )
    config.addinivalue_line(
        "markers",
        "scenario: ビジネスシナリオテスト",
    )
    config.addinivalue_line(
        "markers",
        "eu_ai_act: EU AI Act コンプライアンス関連",
    )
    config.addinivalue_line(
        "markers",
        "postgresql: tests requiring a real PostgreSQL service container",
    )
    config.addinivalue_line(
        "markers",
        "contention: advisory-lock contention and concurrency integration tests",
    )
