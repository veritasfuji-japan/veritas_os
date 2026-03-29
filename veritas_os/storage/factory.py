"""Storage backend factory for Dependency Injection."""

from __future__ import annotations

import os
from pathlib import Path

from veritas_os.storage.base import MemoryStore, TrustLogStore
from veritas_os.storage.json_kv import JsonMemoryStore
from veritas_os.storage.jsonl import JsonlTrustLogStore
from veritas_os.storage.postgresql import PostgresMemoryStore, PostgresTrustLogStore


def create_trust_log_store() -> TrustLogStore:
    """Create TrustLog store from backend environment configuration."""
    backend = os.getenv("VERITAS_TRUSTLOG_BACKEND", "jsonl").strip().lower()
    if backend == "postgresql":
        return PostgresTrustLogStore()
    return JsonlTrustLogStore()


def create_memory_store() -> MemoryStore:
    """Create MemoryOS store from backend environment configuration."""
    backend = os.getenv("VERITAS_MEMORY_BACKEND", "json").strip().lower()
    if backend == "postgresql":
        return PostgresMemoryStore()

    memory_path = Path(
        os.getenv("VERITAS_MEMORY_PATH", "./runtime/memory/memory_store.json")
    )
    return JsonMemoryStore(memory_path)
