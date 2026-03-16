"""CORS configuration helpers for API server startup.

This module centralizes CORS origin normalization and credential policy
resolution so ``server.py`` can stay focused on routing/bootstrap concerns.
"""

from __future__ import annotations

from typing import Any


def resolve_cors_settings(origins: Any, logger: Any) -> tuple[list[str], bool]:
    """Resolve safe CORS settings from raw config values.

    Args:
        origins: Raw origin collection from configuration.
        logger: Logger object with a ``warning`` method.

    Returns:
        A tuple of ``(allow_origins, allow_credentials)``.

    Security:
        Wildcard origins are allowed only with ``allow_credentials=False`` to
        prevent credentialed cross-origin requests from being over-permissive.
    """
    if not isinstance(origins, (list, tuple, set)):
        return [], False

    normalized_origins = [
        str(origin).strip()
        for origin in origins
        if isinstance(origin, str) and origin.strip()
    ]
    if not normalized_origins:
        return [], False

    if "*" in normalized_origins:
        logger.warning(
            "Insecure CORS config detected: wildcard origin with credentials is "
            "disallowed. Falling back to allow_credentials=False.",
        )
        return ["*"], False

    return normalized_origins, True
