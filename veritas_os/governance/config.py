"""Configuration helpers for governance repository backend selection."""

from __future__ import annotations

import os

_GOVERNANCE_BACKENDS = {"file", "postgresql"}


def get_governance_backend() -> str:
    """Return normalized governance backend name from environment.

    Defaults to ``file`` for backward compatibility.
    """
    return os.getenv("VERITAS_GOVERNANCE_BACKEND", "file").strip().lower()


def validate_governance_backend() -> str:
    """Validate and return configured governance backend.

    Raises:
        ValueError: If backend is unknown.
        RuntimeError: If PostgreSQL backend is requested without DB URL.
    """
    backend = get_governance_backend()
    if backend not in _GOVERNANCE_BACKENDS:
        raise ValueError(
            f"Unknown VERITAS_GOVERNANCE_BACKEND={backend!r}. "
            f"Supported: {sorted(_GOVERNANCE_BACKENDS)}"
        )

    if backend == "postgresql":
        database_url = os.getenv("VERITAS_DATABASE_URL", "").strip()
        if not database_url:
            raise RuntimeError(
                "Governance backend is set to 'postgresql' but "
                "VERITAS_DATABASE_URL is not set. "
                "Set VERITAS_DATABASE_URL to a PostgreSQL DSN."
            )
    return backend
