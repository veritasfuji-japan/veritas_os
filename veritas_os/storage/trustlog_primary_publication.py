"""Primary PostgreSQL TrustLog publication semantics.

This module implements the v1 primary-ledger proof track defined by
``docs/en/architecture/trustlog-publication-boundary-v1.md``.  It is deliberately
separate from mirror/transparency-anchor delivery and from execution authority.

The implementation preserves the existing TrustLog hash chain while adding a
content-bound publication identity.  PostgreSQL durable state, not process-local
flags, decides whether a caller created a publication or observed an already
committed equivalent publication.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from veritas_os.logging.redact import redact_entry
from veritas_os.logging.trust_log_core import compute_sha256, prepare_entry
from veritas_os.storage.db import get_pool

PUBLICATION_SCHEMA_VERSION = "trustlog-primary-publication/v1"
PUBLICATION_RECEIPT_VERSION = "trustlog-primary-publication-receipt/v1"

# Shared TrustLog chain serialization key.  This is derived from the same stable
# byte sequence used by PostgresTrustLogStore rather than duplicating a magic
# integer literal.
_TRUSTLOG_CHAIN_LOCK_KEY = int.from_bytes(b"VERITAS\x01", "big")


class TrustLogPrimaryPublicationError(RuntimeError):
    """Fail-closed primary publication error."""


class TrustLogPrimaryPublicationCollisionError(TrustLogPrimaryPublicationError):
    """Raised when one logical identity is reused with different content."""


@dataclass(frozen=True)
class TrustLogPublicationIdentity:
    """Deterministic identity for one logical TrustLog publication."""

    entry_type: str
    entry_id: str
    schema_version: str
    logical_identity_key: str
    canonical_payload_hash: str
    publication_key: str
    redacted_payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_type": self.entry_type,
            "entry_id": self.entry_id,
            "schema_version": self.schema_version,
            "logical_identity_key": self.logical_identity_key,
            "canonical_payload_hash": self.canonical_payload_hash,
            "publication_key": self.publication_key,
        }


@dataclass(frozen=True)
class TrustLogPrimaryPublicationResult:
    """Reviewer-safe result for one primary durable-ledger publication call."""

    identity: TrustLogPublicationIdentity
    request_id: str
    trustlog_row_id: int
    trustlog_chain_hash: str
    created: bool
    receipt_hash: str

    @property
    def disposition(self) -> str:
        return "created" if self.created else "observed_existing"

    def to_dict(self) -> dict[str, Any]:
        receipt = _receipt_payload(
            identity=self.identity,
            request_id=self.request_id,
            trustlog_row_id=self.trustlog_row_id,
            trustlog_chain_hash=self.trustlog_chain_hash,
            created=self.created,
        )
        return {
            "identity": self.identity.to_dict(),
            "request_id": self.request_id,
            "trustlog_row_id": self.trustlog_row_id,
            "trustlog_chain_hash": self.trustlog_chain_hash,
            "created": self.created,
            "disposition": self.disposition,
            "receipt": receipt,
            "receipt_hash": self.receipt_hash,
        }


def _normalized_nonempty(value: str, *, field: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"trustlog_primary_publication_{field}_required")
    return normalized


def build_trustlog_publication_identity(
    *,
    entry_type: str,
    entry_id: str,
    payload: Mapping[str, Any],
    schema_version: str = PUBLICATION_SCHEMA_VERSION,
) -> TrustLogPublicationIdentity:
    """Build deterministic logical and content-bound publication identities.

    ``logical_identity_key`` intentionally excludes the payload hash so that a
    reused logical entry with changed content collides at the database boundary.
    ``publication_key`` includes the payload hash and therefore identifies the
    exact immutable publication content.

    The payload is deep-redacted before hashing, matching the TrustLog rule that
    secrets/PII are removed before cryptographic evidence is derived.
    """

    normalized_type = _normalized_nonempty(entry_type, field="entry_type")
    normalized_id = _normalized_nonempty(entry_id, field="entry_id")
    normalized_schema = _normalized_nonempty(
        schema_version,
        field="schema_version",
    )
    if not isinstance(payload, Mapping):
        raise ValueError("trustlog_primary_publication_payload_mapping_required")

    redacted_container = redact_entry({"payload": dict(payload)})
    redacted_payload = redacted_container.get("payload")
    if not isinstance(redacted_payload, dict):
        raise ValueError("trustlog_primary_publication_payload_invalid_after_redaction")

    canonical_payload_hash = compute_sha256(redacted_payload)
    logical_identity_digest = compute_sha256(
        {
            "entry_type": normalized_type,
            "entry_id": normalized_id,
            "schema_version": normalized_schema,
        }
    )
    logical_identity_key = f"tlid:v1:sha256:{logical_identity_digest}"
    publication_digest = compute_sha256(
        {
            "logical_identity_key": logical_identity_key,
            "canonical_payload_hash": canonical_payload_hash,
        }
    )
    publication_key = f"tlpub:v1:sha256:{publication_digest}"

    return TrustLogPublicationIdentity(
        entry_type=normalized_type,
        entry_id=normalized_id,
        schema_version=normalized_schema,
        logical_identity_key=logical_identity_key,
        canonical_payload_hash=canonical_payload_hash,
        publication_key=publication_key,
        redacted_payload=redacted_payload,
    )


def _receipt_payload(
    *,
    identity: TrustLogPublicationIdentity,
    request_id: str,
    trustlog_row_id: int,
    trustlog_chain_hash: str,
    created: bool,
) -> dict[str, Any]:
    return {
        "receipt_version": PUBLICATION_RECEIPT_VERSION,
        "logical_identity_key": identity.logical_identity_key,
        "publication_key": identity.publication_key,
        "canonical_payload_hash": identity.canonical_payload_hash,
        "request_id": request_id,
        "trustlog_row_id": trustlog_row_id,
        "trustlog_chain_hash": trustlog_chain_hash,
        "disposition": "created" if created else "observed_existing",
        "primary_backend": "postgresql",
        "primary_logical_exactly_once_scope": True,
        "mirror_delivery_claimed": False,
        "transparency_anchor_delivery_claimed": False,
        "execution_authority_created": False,
        "external_effect_proven": False,
    }


def _build_result(
    *,
    identity: TrustLogPublicationIdentity,
    request_id: str,
    trustlog_row_id: int,
    trustlog_chain_hash: str,
    created: bool,
) -> TrustLogPrimaryPublicationResult:
    receipt = _receipt_payload(
        identity=identity,
        request_id=request_id,
        trustlog_row_id=trustlog_row_id,
        trustlog_chain_hash=trustlog_chain_hash,
        created=created,
    )
    return TrustLogPrimaryPublicationResult(
        identity=identity,
        request_id=request_id,
        trustlog_row_id=trustlog_row_id,
        trustlog_chain_hash=trustlog_chain_hash,
        created=created,
        receipt_hash=compute_sha256(receipt),
    )


class PostgresTrustLogPrimaryPublisher:
    """Publish one immutable logical TrustLog entry to PostgreSQL once."""

    async def publish(
        self,
        *,
        entry_type: str,
        entry_id: str,
        payload: Mapping[str, Any],
        schema_version: str = PUBLICATION_SCHEMA_VERSION,
    ) -> TrustLogPrimaryPublicationResult:
        identity = build_trustlog_publication_identity(
            entry_type=entry_type,
            entry_id=entry_id,
            payload=payload,
            schema_version=schema_version,
        )

        try:
            from psycopg.types.json import Jsonb

            pool = await get_pool()
            async with pool.connection() as conn:
                async with conn.transaction():
                    # Serialize against the existing TrustLog append path so the
                    # hash chain and primary-publication lookup are one critical
                    # section across processes.
                    await conn.execute(
                        "SELECT pg_advisory_xact_lock(%s)",
                        (_TRUSTLOG_CHAIN_LOCK_KEY,),
                    )

                    existing_cur = await conn.execute(
                        """
                        SELECT id,
                               request_id,
                               hash,
                               publication_key,
                               canonical_payload_hash,
                               publication_schema_version,
                               publication_entry_type,
                               publication_entry_id
                        FROM trustlog_entries
                        WHERE logical_identity_key = %s
                        """,
                        (identity.logical_identity_key,),
                    )
                    existing = await existing_cur.fetchone()
                    if existing is not None:
                        (
                            row_id,
                            request_id,
                            chain_hash,
                            publication_key,
                            payload_hash,
                            stored_schema,
                            stored_type,
                            stored_id,
                        ) = existing
                        expected = (
                            identity.publication_key,
                            identity.canonical_payload_hash,
                            identity.schema_version,
                            identity.entry_type,
                            identity.entry_id,
                        )
                        observed = (
                            publication_key,
                            payload_hash,
                            stored_schema,
                            stored_type,
                            stored_id,
                        )
                        if observed != expected or request_id != identity.publication_key:
                            raise TrustLogPrimaryPublicationCollisionError(
                                "TRUSTLOG_PRIMARY_PUBLICATION_COLLISION"
                            )
                        if not isinstance(row_id, int) or not str(chain_hash or ""):
                            raise TrustLogPrimaryPublicationError(
                                "TRUSTLOG_PRIMARY_PUBLICATION_EXISTING_ROW_INVALID"
                            )
                        return _build_result(
                            identity=identity,
                            request_id=str(request_id),
                            trustlog_row_id=row_id,
                            trustlog_chain_hash=str(chain_hash),
                            created=False,
                        )

                    state_cur = await conn.execute(
                        "SELECT last_hash FROM trustlog_chain_state "
                        "WHERE id = 1 FOR UPDATE"
                    )
                    state = await state_cur.fetchone()
                    if state is None:
                        await conn.execute(
                            "INSERT INTO trustlog_chain_state "
                            "(id, last_hash, last_id, updated_at) "
                            "VALUES (1, NULL, NULL, now())"
                        )
                        previous_hash = None
                    else:
                        previous_hash = state[0]

                    raw_entry = {
                        "request_id": identity.publication_key,
                        "entry_type": identity.entry_type,
                        "entry_id": identity.entry_id,
                        "publication_schema_version": identity.schema_version,
                        "logical_identity_key": identity.logical_identity_key,
                        "publication_key": identity.publication_key,
                        "canonical_payload_hash": identity.canonical_payload_hash,
                        "payload": identity.redacted_payload,
                        "trustlog_publication_boundary": (
                            "primary_logical_uniqueness_v1"
                        ),
                    }
                    prepared, _encrypted_line = prepare_entry(
                        raw_entry,
                        previous_hash=previous_hash,
                    )
                    chain_hash = str(prepared.get("sha256") or "")
                    if not chain_hash:
                        raise TrustLogPrimaryPublicationError(
                            "TRUSTLOG_PRIMARY_PUBLICATION_CHAIN_HASH_MISSING"
                        )

                    insert_cur = await conn.execute(
                        """
                        INSERT INTO trustlog_entries
                            (request_id,
                             entry,
                             hash,
                             prev_hash,
                             logical_identity_key,
                             publication_key,
                             canonical_payload_hash,
                             publication_schema_version,
                             publication_entry_type,
                             publication_entry_id,
                             created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                        RETURNING id
                        """,
                        (
                            identity.publication_key,
                            Jsonb(prepared),
                            chain_hash,
                            previous_hash,
                            identity.logical_identity_key,
                            identity.publication_key,
                            identity.canonical_payload_hash,
                            identity.schema_version,
                            identity.entry_type,
                            identity.entry_id,
                        ),
                    )
                    inserted = await insert_cur.fetchone()
                    if inserted is None or not isinstance(inserted[0], int):
                        raise TrustLogPrimaryPublicationError(
                            "TRUSTLOG_PRIMARY_PUBLICATION_INSERT_RESULT_INVALID"
                        )
                    row_id = inserted[0]

                    await conn.execute(
                        "UPDATE trustlog_chain_state "
                        "SET last_hash = %s, last_id = %s, updated_at = now() "
                        "WHERE id = 1",
                        (chain_hash, row_id),
                    )

                    return _build_result(
                        identity=identity,
                        request_id=identity.publication_key,
                        trustlog_row_id=row_id,
                        trustlog_chain_hash=chain_hash,
                        created=True,
                    )
        except TrustLogPrimaryPublicationError:
            raise
        except Exception as exc:
            raise TrustLogPrimaryPublicationError(
                f"TRUSTLOG_PRIMARY_PUBLICATION_PERSISTENCE_FAILED: {exc}"
            ) from exc
