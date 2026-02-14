"""Regression tests for asynchronous pytest compatibility."""

from __future__ import annotations

import asyncio

import pytest


@pytest.mark.asyncio
async def test_asyncio_marked_test_executes_without_plugin() -> None:
    """Ensure ``@pytest.mark.asyncio`` tests execute in minimal environments."""
    await asyncio.sleep(0)
    assert True
