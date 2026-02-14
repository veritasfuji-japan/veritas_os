"""Pytest configuration for asynchronous test execution.

This project includes ``@pytest.mark.asyncio`` tests but does not require an
external async pytest plugin in all environments. The hook below executes
coroutine test functions with ``asyncio.run`` so async tests remain portable.
"""

from __future__ import annotations

import asyncio
import inspect
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


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers used in this test suite."""
    config.addinivalue_line(
        "markers",
        "asyncio: mark test as asynchronous and execute via asyncio.run",
    )
