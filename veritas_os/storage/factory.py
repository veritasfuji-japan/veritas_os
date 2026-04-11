"""Storage backend factory for Dependency Injection.

Supported backends
------------------
* ``VERITAS_TRUSTLOG_BACKEND``: ``jsonl`` (default) | ``postgresql``
* ``VERITAS_MEMORY_BACKEND``:   ``json``  (default) | ``postgresql``

Unknown or empty values cause the factory to raise ``ValueError``
at startup so that mis-configuration is caught early.

Fail-fast validation
--------------------
When either backend is set to ``postgresql``, the factory verifies that
``VERITAS_DATABASE_URL`` is present.  This prevents silent fallback to
an unconfigured or unreachable database at runtime.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Dict

from veritas_os.storage.base import MemoryStore, TrustLogStore
from veritas_os.storage.json_kv import JsonMemoryStore
from veritas_os.storage.jsonl import JsonlTrustLogStore
from veritas_os.storage.postgresql import PostgresMemoryStore, PostgresTrustLogStore

logger = logging.getLogger(__name__)

_TRUSTLOG_BACKENDS = {"jsonl", "postgresql"}
_MEMORY_BACKENDS = {"json", "postgresql"}


def _require_database_url(component: str) -> None:
    """Fail fast when a postgresql backend is requested without a DB URL.

    Args:
        component: Human-readable name (e.g. "Memory", "TrustLog").

    Raises:
        RuntimeError: When ``VERITAS_DATABASE_URL`` is missing or empty.
    """
    url = os.getenv("VERITAS_DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError(
            f"{component} backend is set to 'postgresql' but "
            "VERITAS_DATABASE_URL is not set.  "
            "Set VERITAS_DATABASE_URL to a PostgreSQL DSN, e.g. "
            "postgresql://user:pass@localhost:5432/veritas"
        )


def get_backend_info() -> Dict[str, str]:
    """Return the currently configured storage backends.

    Returns
    -------
    dict
        A mapping with ``memory`` and ``trustlog`` keys indicating the
        active backend name (e.g. ``"json"``, ``"jsonl"``, ``"postgresql"``).
    """
    return {
        "memory": os.getenv("VERITAS_MEMORY_BACKEND", "json").strip().lower(),
        "trustlog": os.getenv("VERITAS_TRUSTLOG_BACKEND", "jsonl").strip().lower(),
    }


def validate_backend_config() -> None:
    """Validate storage backend environment configuration at startup.

    Raises
    ------
    RuntimeError
        When a postgresql backend is requested but ``VERITAS_DATABASE_URL``
        is missing, or when backend selectors contain unrecognised values.
    """
    info = get_backend_info()

    if info["memory"] not in _MEMORY_BACKENDS:
        raise ValueError(
            f"Unknown VERITAS_MEMORY_BACKEND={info['memory']!r}. "
            f"Supported: {sorted(_MEMORY_BACKENDS)}"
        )
    if info["trustlog"] not in _TRUSTLOG_BACKENDS:
        raise ValueError(
            f"Unknown VERITAS_TRUSTLOG_BACKEND={info['trustlog']!r}. "
            f"Supported: {sorted(_TRUSTLOG_BACKENDS)}"
        )

    needs_pg = info["memory"] == "postgresql" or info["trustlog"] == "postgresql"
    if needs_pg:
        url = os.getenv("VERITAS_DATABASE_URL", "").strip()
        if not url:
            raise RuntimeError(
                "PostgreSQL backend is requested "
                f"(memory={info['memory']}, trustlog={info['trustlog']}) "
                "but VERITAS_DATABASE_URL is not set.  "
                "Set VERITAS_DATABASE_URL to a PostgreSQL DSN."
            )

    logger.info(
        "Storage backends: memory=%s, trustlog=%s",
        info["memory"],
        info["trustlog"],
    )


def create_trust_log_store() -> TrustLogStore:
    """Create TrustLog store from ``VERITAS_TRUSTLOG_BACKEND`` env var.

    Returns
    -------
    TrustLogStore
        A concrete backend that satisfies the ``TrustLogStore`` protocol.

    Raises
    ------
    ValueError
        When the configured backend name is not recognised.
    RuntimeError
        When ``postgresql`` is selected but ``VERITAS_DATABASE_URL`` is
        not set.
    """
    backend = os.getenv("VERITAS_TRUSTLOG_BACKEND", "jsonl").strip().lower()
    if backend not in _TRUSTLOG_BACKENDS:
        raise ValueError(
            f"Unknown VERITAS_TRUSTLOG_BACKEND={backend!r}. "
            f"Supported: {sorted(_TRUSTLOG_BACKENDS)}"
        )
    if backend == "postgresql":
        _require_database_url("TrustLog")
        logger.info("TrustLog backend: postgresql")
        return PostgresTrustLogStore()
    logger.info("TrustLog backend: jsonl")
    return JsonlTrustLogStore()


def create_memory_store() -> MemoryStore:
    """Create MemoryOS store from ``VERITAS_MEMORY_BACKEND`` env var.

    Returns
    -------
    MemoryStore
        A concrete backend that satisfies the ``MemoryStore`` protocol.

    Raises
    ------
    ValueError
        When the configured backend name is not recognised.
    RuntimeError
        When ``postgresql`` is selected but ``VERITAS_DATABASE_URL`` is
        not set.
    """
    backend = os.getenv("VERITAS_MEMORY_BACKEND", "json").strip().lower()
    if backend not in _MEMORY_BACKENDS:
        raise ValueError(
            f"Unknown VERITAS_MEMORY_BACKEND={backend!r}. "
            f"Supported: {sorted(_MEMORY_BACKENDS)}"
        )
    if backend == "postgresql":
        _require_database_url("Memory")
        logger.info("Memory backend: postgresql")
        return PostgresMemoryStore()

    memory_path = Path(
        os.getenv("VERITAS_MEMORY_PATH", "./runtime/memory/memory_store.json")
    )
    logger.info("Memory backend: json (path=%s)", memory_path)
    return JsonMemoryStore(memory_path)
