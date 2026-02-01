"""
Global pytest fixtures for VERITAS OS tests.

These fixtures ensure required API credentials are present by default so
startup validation does not fail in tests that construct TestClient without
explicitly setting environment variables.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _ensure_api_credentials(monkeypatch) -> None:
    """Ensure API credentials exist unless a test overrides them explicitly."""
    monkeypatch.setenv("VERITAS_API_KEY", "test-api-key")
    monkeypatch.setenv("VERITAS_API_SECRET", "test-api-secret")
