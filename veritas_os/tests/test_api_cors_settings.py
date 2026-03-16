"""Unit tests for CORS setting resolution helpers."""

from __future__ import annotations

from unittest.mock import Mock

from veritas_os.api.cors_settings import resolve_cors_settings


def test_resolve_cors_settings_rejects_wildcard_credentials() -> None:
    """Wildcard origins must force credentialed CORS off."""
    logger = Mock()

    origins, allow_credentials = resolve_cors_settings(["*"], logger=logger)

    assert origins == ["*"]
    assert allow_credentials is False
    logger.warning.assert_called_once()


def test_resolve_cors_settings_allows_explicit_origins() -> None:
    """Explicit origins are normalized and allow credentials."""
    logger = Mock()

    origins, allow_credentials = resolve_cors_settings(
        ["https://example.com", "", None, " https://app.example.com "],
        logger=logger,
    )

    assert origins == ["https://example.com", "https://app.example.com"]
    assert allow_credentials is True
    logger.warning.assert_not_called()


def test_resolve_cors_settings_rejects_non_iterable_config() -> None:
    """Unexpected config types should fail closed without warning noise."""
    logger = Mock()

    origins, allow_credentials = resolve_cors_settings("*", logger=logger)

    assert origins == []
    assert allow_credentials is False
    logger.warning.assert_not_called()
