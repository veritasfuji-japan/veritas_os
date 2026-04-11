"""Storage backend factory for Dependency Injection.

Supported backends
------------------
* ``VERITAS_TRUSTLOG_BACKEND``: ``jsonl`` (default) | ``postgresql``
* ``VERITAS_MEMORY_BACKEND``:   ``json``  (default) | ``postgresql``

Unknown or empty values cause the factory to raise ``ValueError``
at startup so that mis-configuration is caught early.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from veritas_os.storage.base import MemoryStore, TrustLogStore
from veritas_os.storage.json_kv import JsonMemoryStore
from veritas_os.storage.jsonl import JsonlTrustLogStore
from veritas_os.storage.postgresql import PostgresMemoryStore, PostgresTrustLogStore

logger = logging.getLogger(__name__)

_TRUSTLOG_BACKENDS = {"jsonl", "postgresql"}
_MEMORY_BACKENDS = {"json", "postgresql"}


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
    """
    backend = os.getenv("VERITAS_TRUSTLOG_BACKEND", "jsonl").strip().lower()
    if backend not in _TRUSTLOG_BACKENDS:
        raise ValueError(
            f"Unknown VERITAS_TRUSTLOG_BACKEND={backend!r}. "
            f"Supported: {sorted(_TRUSTLOG_BACKENDS)}"
        )
    if backend == "postgresql":
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
    """
    backend = os.getenv("VERITAS_MEMORY_BACKEND", "json").strip().lower()
    if backend not in _MEMORY_BACKENDS:
        raise ValueError(
            f"Unknown VERITAS_MEMORY_BACKEND={backend!r}. "
            f"Supported: {sorted(_MEMORY_BACKENDS)}"
        )
    if backend == "postgresql":
        logger.info("Memory backend: postgresql")
        return PostgresMemoryStore()

    memory_path = Path(
        os.getenv("VERITAS_MEMORY_PATH", "./runtime/memory/memory_store.json")
    )
    logger.info("Memory backend: json (path=%s)", memory_path)
    return JsonMemoryStore(memory_path)
