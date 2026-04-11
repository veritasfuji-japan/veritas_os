"""Storage protocol interfaces for TrustLog and MemoryOS backends.

Backend Parity Contract
=======================
Every concrete backend (JSON/JSONL, PostgreSQL, …) **must** satisfy the
behavioural contract defined by these protocols.  The contract tests in
``tests/test_storage_backend_contract.py`` exercise each backend through
a single, shared test suite so that "same interface ⇒ same semantics"
is machine-verified.

Key cross-cutting guarantees
----------------------------
* **Error semantics** — All backends raise the same exception hierarchy:
  ``KeyError`` for missing keys, ``ValueError`` for invalid arguments,
  ``RuntimeError`` for infrastructure failures.  Backends must **never**
  silently swallow errors.
* **Metadata fields** — Optional metadata (``created_at``, ``updated_at``,
  ``sha256``, ``previous_hash``, …) may be added by a backend but must
  not be *required* by callers.  Callers that need them must use
  ``.get()`` with a default.
"""

from __future__ import annotations

from typing import Any, AsyncIterator, Dict, List, Optional, Protocol


class TrustLogStore(Protocol):
    """TrustLog 永続化の抽象インターフェース。

    Contract
    --------
    * **Append-only** — ``append`` must never overwrite an existing entry.
    * **request_id uniqueness** — Each ``request_id`` value maps to at most
      one stored entry.  ``get_by_id`` returns ``None`` for unknown IDs.
    * **Ordering** — ``iter_entries`` yields entries in *insertion order*
      (oldest first within each page).
    * **Pagination** — ``offset`` is 0-based.  ``limit <= 0`` yields
      nothing.  ``offset`` beyond the data set yields nothing.
    * **Hash chain** — ``get_last_hash`` returns the ``sha256`` (or
      equivalent chain hash) of the most-recently-appended entry, or
      ``None`` when the log is empty.
    * **Return value** — ``append`` returns the ``request_id`` string
      assigned to the stored entry.
    * **Error semantics** — Infrastructure failures raise
      ``RuntimeError``.  Invalid entry dicts raise ``ValueError``.
    """

    async def append(self, entry: Dict[str, Any]) -> str:
        """Append *entry* and return the assigned ``request_id``.

        The entry dict is treated as opaque by the store; the caller
        (TrustLog layer) is responsible for hash-chain fields.
        """
        ...

    async def get_by_id(self, request_id: str) -> Optional[Dict[str, Any]]:
        """Return the entry matching *request_id*, or ``None``."""
        ...

    async def iter_entries(
        self,
        limit: int = 100,
        offset: int = 0,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Yield entries in insertion order with offset/limit pagination.

        ``limit <= 0`` or ``offset`` past the end ⇒ empty iterator.
        """
        ...  # type: ignore[return-value]  # pragma: no cover

    async def get_last_hash(self) -> Optional[str]:
        """Return the chain hash of the newest entry, or ``None``."""
        ...


class MemoryStore(Protocol):
    """MemoryOS 永続化の抽象インターフェース。

    Contract
    --------
    * **Key uniqueness** — ``put(key, …, user_id)`` is an **upsert**:
      writing to an existing key replaces the stored value.
    * **User isolation** — ``search``, ``list_all``, ``delete``, and
      ``erase_user_data`` are scoped to *user_id*.  Data for one user
      must never leak into another user's results.
    * **Ordering** — ``list_all`` returns entries in *insertion order*
      (oldest first).
    * **Search limit** — ``search(…, limit=N)`` returns at most *N*
      results.  ``limit <= 0`` returns an empty list.
    * **Delete return** — ``delete`` returns ``True`` when a matching
      record was actually removed, ``False`` otherwise.
    * **Erase return** — ``erase_user_data`` returns the count of records
      deleted (``int >= 0``).
    * **Error semantics** — Infrastructure failures raise
      ``RuntimeError``.  Invalid arguments raise ``ValueError``.
    """

    async def put(self, key: str, value: Dict[str, Any], *, user_id: str) -> None:
        """Store *value* under *key* for *user_id* (upsert semantics)."""
        ...

    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Return the value stored under *key*, or ``None``."""
        ...

    async def search(
        self,
        query: str,
        *,
        user_id: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Return up to *limit* records matching *query* for *user_id*."""
        ...

    async def delete(self, key: str, *, user_id: str) -> bool:
        """Delete the record for *key* / *user_id*; return whether it existed."""
        ...

    async def list_all(self, *, user_id: str) -> List[Dict[str, Any]]:
        """Return all records for *user_id* in insertion order."""
        ...

    async def erase_user_data(self, user_id: str) -> int:
        """Erase **all** records for *user_id* and return the delete count."""
        ...
