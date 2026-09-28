"""Deterministic non-network observable-digest resolver for separate_store_readonly_v1.

This module implements the narrow behavior approved by the frozen resolver
contract/security-review line. It performs no network, filesystem, database,
object-store SDK, environment, credential-provider, retry, redirect, cache,
policy, Human Approval, Bind authorization, execution, remediation, audit
persistence, or /v1/decide wiring.

The behavior is intentionally monotonic: degraded or missing evidence can only
preserve or reduce what the resolver may conclude. It can never strengthen a
conclusion.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final, Literal

from veritas_os.audit.observable_digest_failure_codes import (
    ObservableDigestFailurePredicate,
)


SEPARATE_STORE_READONLY_PROFILE_ID: Final = "separate_store_readonly_v1"
SEPARATE_STORE_SCHEME: Final = "separate_store"
SEPARATE_STORE_RECORD_VERSION: Final = "1"
MAX_LOCATOR_LENGTH: Final = 500
MAX_OBJECT_KEY_SEGMENTS: Final = 8
MAX_SNAPSHOT_ENTRIES: Final = 4096
MAX_RECORD_FIELDS: Final = 8
MAX_FIELD_NAME_LENGTH: Final = 128
MAX_FIELD_STRING_LENGTH: Final = 1024

_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_SEGMENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

_RESOLVER_SCOPED_FAILURES: Final = frozenset(
    {
        ObservableDigestFailurePredicate.LOCATOR_MISSING,
        ObservableDigestFailurePredicate.LOCATOR_MALFORMED,
        ObservableDigestFailurePredicate.RESOLUTION_FAILED,
        ObservableDigestFailurePredicate.AUTHZ_DENIED,
        ObservableDigestFailurePredicate.SCHEMA_MISMATCH,
        ObservableDigestFailurePredicate.UNKNOWN_TRANSIENT,
    }
)


def _canonical_json_bytes(payload: object) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256_ref(payload: object) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


def _require_non_empty_text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value:
        raise ValueError(f"{field_name} must be non-empty")
    return value


def _require_sha256_ref(value: str, field_name: str) -> str:
    text = _require_non_empty_text(value, field_name)
    if _SHA256_RE.fullmatch(text) is None:
        raise ValueError(f"{field_name} must be sha256:<64 lowercase hex chars>")
    return text


def _require_utc_z(value: str, field_name: str) -> str:
    text = _require_non_empty_text(value, field_name)
    if not text.endswith("Z"):
        raise ValueError(f"{field_name} must be ISO8601 UTC ending in Z")
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError(f"{field_name} must be valid ISO8601 UTC") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError(f"{field_name} must be timezone-aware UTC")
    return text


def _require_segment(value: str, field_name: str) -> str:
    text = _require_non_empty_text(value, field_name)
    if not text.isascii() or _SEGMENT_RE.fullmatch(text) is None:
        raise ValueError(f"{field_name} must match the frozen ASCII segment grammar")
    if text in {".", ".."}:
        raise ValueError(f"{field_name} must not be a dot segment")
    return text


def _parse_canonical_locator(locator: str) -> tuple[str, tuple[str, ...]] | None:
    if not isinstance(locator, str):
        return None
    if not locator or len(locator) > MAX_LOCATOR_LENGTH:
        return None
    if not locator.isascii():
        return None
    if locator != locator.strip():
        return None
    if "%" in locator or "?" in locator or "#" in locator or "@" in locator:
        return None

    prefix = f"{SEPARATE_STORE_SCHEME}://"
    if not locator.startswith(prefix):
        return None

    remainder = locator[len(prefix) :]
    if not remainder or "://" in remainder:
        return None

    parts = remainder.split("/")
    if len(parts) < 2 or len(parts) > MAX_OBJECT_KEY_SEGMENTS + 1:
        return None
    if any(not part for part in parts):
        return None

    namespace = parts[0]
    key_segments = tuple(parts[1:])
    if _SEGMENT_RE.fullmatch(namespace) is None or namespace in {".", ".."}:
        return None
    for segment in key_segments:
        if _SEGMENT_RE.fullmatch(segment) is None or segment in {".", ".."}:
            return None

    return namespace, key_segments


@dataclass(frozen=True)
class ResolverSemanticGuarantees:
    """Hard-false semantic guarantees carried by every resolver result."""

    authority_created: bool = False
    execution_permission_changed: bool = False
    digest_match_asserted: bool = False
    boundary_validation_asserted: bool = False
    uncertainty_erased: bool = False
    remediation_executed: bool = False

    def __post_init__(self) -> None:
        if any(
            (
                self.authority_created,
                self.execution_permission_changed,
                self.digest_match_asserted,
                self.boundary_validation_asserted,
                self.uncertainty_erased,
                self.remediation_executed,
            )
        ):
            raise ValueError("resolver semantic guarantees are hard-false invariants")

    def to_contract_dict(self) -> dict[str, bool]:
        return {
            "authority_created": False,
            "execution_permission_changed": False,
            "digest_match_asserted": False,
            "boundary_validation_asserted": False,
            "uncertainty_erased": False,
            "remediation_executed": False,
        }


@dataclass(frozen=True)
class ObservableDigestResolverRequest:
    """Contract-valid resolver request.

    A truly missing/empty locator cannot be represented by the frozen resolver
    exchange schema because request.locator is required and non-empty. That
    condition remains an upstream locator-selection predicate (LOCATOR_MISSING)
    rather than a contract-valid request handled by this profile.
    """

    request_id: str
    locator: str
    caller_id_hash: str
    requested_at: str
    resolver_profile: str

    def __post_init__(self) -> None:
        _require_non_empty_text(self.request_id, "request_id")
        _require_non_empty_text(self.locator, "locator")
        _require_sha256_ref(self.caller_id_hash, "caller_id_hash")
        _require_utc_z(self.requested_at, "requested_at")
        _require_non_empty_text(self.resolver_profile, "resolver_profile")

    def to_contract_dict(self) -> dict[str, str]:
        return {
            "request_id": self.request_id,
            "locator": self.locator,
            "caller_id_hash": self.caller_id_hash,
            "requested_at": self.requested_at,
            "resolver_profile": self.resolver_profile,
        }

    @property
    def request_hash(self) -> str:
        return _sha256_ref(self.to_contract_dict())


@dataclass(frozen=True)
class SeparateStoreReadonlyProfile:
    """Frozen read-access profile for the initial resolver behavior."""

    resolver_id: str
    namespace: str
    allowed_caller_id_hashes: tuple[str, ...]
    profile_id: str = SEPARATE_STORE_READONLY_PROFILE_ID

    def __post_init__(self) -> None:
        _require_non_empty_text(self.resolver_id, "resolver_id")
        _require_segment(self.namespace, "namespace")
        if self.profile_id != SEPARATE_STORE_READONLY_PROFILE_ID:
            raise ValueError("unsupported resolver profile")

        normalized: list[str] = []
        for caller_hash in self.allowed_caller_id_hashes:
            normalized.append(_require_sha256_ref(caller_hash, "allowed_caller_id_hash"))
        canonical = tuple(sorted(set(normalized)))
        if not canonical:
            raise ValueError("allowed_caller_id_hashes must be non-empty")
        object.__setattr__(self, "allowed_caller_id_hashes", canonical)

    def to_canonical_dict(self) -> dict[str, object]:
        return {
            "profile_id": self.profile_id,
            "resolver_id": self.resolver_id,
            "namespace": self.namespace,
            "allowed_caller_id_hashes": list(self.allowed_caller_id_hashes),
        }

    @property
    def profile_hash(self) -> str:
        return _sha256_ref(self.to_canonical_dict())


ImmutableRecordScalar = str | int | bool | None


@dataclass(frozen=True)
class ImmutableSeparateStoreRecord:
    """Immutable raw record envelope.

    The envelope is deliberately able to hold a bounded malformed record so the
    resolver can return SCHEMA_MISMATCH instead of making snapshot construction
    silently perform downstream schema interpretation.
    """

    fields: tuple[tuple[str, ImmutableRecordScalar], ...]

    def __post_init__(self) -> None:
        if len(self.fields) > MAX_RECORD_FIELDS:
            raise ValueError("record exceeds maximum field count")

        keys: set[str] = set()
        normalized: list[tuple[str, ImmutableRecordScalar]] = []
        for key, value in self.fields:
            if not isinstance(key, str) or not key or len(key) > MAX_FIELD_NAME_LENGTH:
                raise ValueError("record field names must be bounded non-empty strings")
            if key in keys:
                raise ValueError("record field names must be unique")
            keys.add(key)

            if not isinstance(value, (str, int, bool)) and value is not None:
                raise TypeError("record values must be immutable scalar values")
            if isinstance(value, str) and len(value) > MAX_FIELD_STRING_LENGTH:
                raise ValueError("record string value exceeds maximum length")
            normalized.append((key, value))

        object.__setattr__(self, "fields", tuple(sorted(normalized)))

    @classmethod
    def from_mapping(
        cls,
        fields: Mapping[str, ImmutableRecordScalar],
    ) -> "ImmutableSeparateStoreRecord":
        return cls(tuple(fields.items()))

    def to_canonical_dict(self) -> dict[str, ImmutableRecordScalar]:
        return {key: value for key, value in self.fields}


@dataclass(frozen=True)
class ImmutableSeparateStoreSnapshot:
    """Canonical immutable snapshot supplied by the caller/test harness."""

    entries: tuple[tuple[str, ImmutableSeparateStoreRecord], ...]

    def __post_init__(self) -> None:
        if len(self.entries) > MAX_SNAPSHOT_ENTRIES:
            raise ValueError("snapshot exceeds maximum entry count")

        seen: set[str] = set()
        normalized: list[tuple[str, ImmutableSeparateStoreRecord]] = []
        for locator, record in self.entries:
            _require_non_empty_text(locator, "snapshot locator")
            if len(locator) > MAX_LOCATOR_LENGTH:
                raise ValueError("snapshot locator exceeds maximum length")
            if _parse_canonical_locator(locator) is None:
                raise ValueError("snapshot locators must already be canonical")
            if locator in seen:
                raise ValueError("snapshot locators must be unique")
            if not isinstance(record, ImmutableSeparateStoreRecord):
                raise TypeError("snapshot entries must contain immutable store records")
            seen.add(locator)
            normalized.append((locator, record))

        object.__setattr__(self, "entries", tuple(sorted(normalized, key=lambda item: item[0])))

    @classmethod
    def from_mapping(
        cls,
        entries: Mapping[
            str,
            Mapping[str, ImmutableRecordScalar] | ImmutableSeparateStoreRecord,
        ],
    ) -> "ImmutableSeparateStoreSnapshot":
        frozen: list[tuple[str, ImmutableSeparateStoreRecord]] = []
        for locator, raw_record in entries.items():
            if isinstance(raw_record, ImmutableSeparateStoreRecord):
                record = raw_record
            elif isinstance(raw_record, Mapping):
                record = ImmutableSeparateStoreRecord.from_mapping(raw_record)
            else:
                raise TypeError("snapshot record must be a mapping or immutable record")
            frozen.append((locator, record))
        return cls(tuple(frozen))

    def lookup_exact(self, locator: str) -> ImmutableSeparateStoreRecord | None:
        for candidate, record in self.entries:
            if candidate == locator:
                return record
        return None

    def to_canonical_payload(self) -> list[dict[str, object]]:
        return [
            {
                "locator": locator,
                "record": record.to_canonical_dict(),
            }
            for locator, record in self.entries
        ]

    @property
    def snapshot_hash(self) -> str:
        return _sha256_ref(self.to_canonical_payload())


ResolutionState = Literal["RESOLVED", "UNRESOLVED"]


@dataclass(frozen=True)
class ObservableDigestResolverResult:
    """Contract-shaped result for the initial resolver behavior."""

    request_id: str
    locator: str
    resolver_id: str
    observed_at: str
    resolution_state: ResolutionState
    resolved_digest: str | None
    failure_predicates: tuple[ObservableDigestFailurePredicate, ...]
    semantic_guarantees: ResolverSemanticGuarantees = ResolverSemanticGuarantees()
    evidence_ref: None = None

    def __post_init__(self) -> None:
        _require_non_empty_text(self.request_id, "request_id")
        _require_non_empty_text(self.locator, "locator")
        _require_non_empty_text(self.resolver_id, "resolver_id")
        _require_utc_z(self.observed_at, "observed_at")

        if any(predicate not in _RESOLVER_SCOPED_FAILURES for predicate in self.failure_predicates):
            raise ValueError("result contains a non-resolver-scoped failure predicate")
        if len(set(self.failure_predicates)) != len(self.failure_predicates):
            raise ValueError("failure predicates must be unique")

        if self.resolution_state == "RESOLVED":
            if self.resolved_digest is None:
                raise ValueError("RESOLVED requires resolved_digest")
            _require_sha256_ref(self.resolved_digest, "resolved_digest")
            if self.failure_predicates:
                raise ValueError("RESOLVED cannot carry failure predicates")
        elif self.resolution_state == "UNRESOLVED":
            if self.resolved_digest is not None:
                raise ValueError("UNRESOLVED requires resolved_digest = None")
            if not self.failure_predicates:
                raise ValueError("UNRESOLVED requires at least one failure predicate")
        else:
            raise ValueError("unsupported resolution_state")

        if self.evidence_ref is not None:
            raise ValueError("initial resolver profile requires evidence_ref = None")

    def to_contract_dict(self) -> dict[str, object]:
        return {
            "request_id": self.request_id,
            "locator": self.locator,
            "resolver_id": self.resolver_id,
            "observed_at": self.observed_at,
            "resolution_state": self.resolution_state,
            "resolved_digest": self.resolved_digest,
            "evidence_ref": None,
            "failure_predicates": [predicate.value for predicate in self.failure_predicates],
            "semantic_guarantees": self.semantic_guarantees.to_contract_dict(),
        }


@dataclass(frozen=True)
class ObservableDigestResolverObservation:
    """Immutable internal proof object; not an authority or persistence surface."""

    request_id: str
    request_hash: str
    locator: str
    resolver_profile: str
    resolver_id: str
    caller_id_hash: str
    access_scope: str
    profile_hash: str
    snapshot_hash: str
    observed_at: str
    lookup_outcome: str
    resolved_digest: str | None
    failure_predicates: tuple[ObservableDigestFailurePredicate, ...]
    semantic_guarantees: ResolverSemanticGuarantees = ResolverSemanticGuarantees()

    def __post_init__(self) -> None:
        _require_non_empty_text(self.request_id, "request_id")
        _require_sha256_ref(self.request_hash, "request_hash")
        _require_non_empty_text(self.locator, "locator")
        _require_non_empty_text(self.resolver_profile, "resolver_profile")
        _require_non_empty_text(self.resolver_id, "resolver_id")
        _require_sha256_ref(self.caller_id_hash, "caller_id_hash")
        _require_non_empty_text(self.access_scope, "access_scope")
        _require_sha256_ref(self.profile_hash, "profile_hash")
        _require_sha256_ref(self.snapshot_hash, "snapshot_hash")
        _require_utc_z(self.observed_at, "observed_at")
        _require_non_empty_text(self.lookup_outcome, "lookup_outcome")
        if self.resolved_digest is not None:
            _require_sha256_ref(self.resolved_digest, "resolved_digest")

    def to_canonical_dict(self) -> dict[str, object]:
        return {
            "request_id": self.request_id,
            "request_hash": self.request_hash,
            "locator": self.locator,
            "resolver_profile": self.resolver_profile,
            "resolver_id": self.resolver_id,
            "caller_id_hash": self.caller_id_hash,
            "access_scope": self.access_scope,
            "profile_hash": self.profile_hash,
            "snapshot_hash": self.snapshot_hash,
            "observed_at": self.observed_at,
            "lookup_outcome": self.lookup_outcome,
            "resolved_digest": self.resolved_digest,
            "failure_predicates": [predicate.value for predicate in self.failure_predicates],
            "semantic_guarantees": self.semantic_guarantees.to_contract_dict(),
        }

    @property
    def observation_hash(self) -> str:
        return _sha256_ref(self.to_canonical_dict())


@dataclass(frozen=True)
class ObservableDigestResolution:
    result: ObservableDigestResolverResult
    observation: ObservableDigestResolverObservation

    def to_canonical_dict(self) -> dict[str, object]:
        return {
            "result": self.result.to_contract_dict(),
            "observation": self.observation.to_canonical_dict(),
        }

    def to_canonical_json(self) -> str:
        return _canonical_json_bytes(self.to_canonical_dict()).decode("utf-8")


def _record_digest_or_none(record: ImmutableSeparateStoreRecord) -> str | None:
    payload = record.to_canonical_dict()
    if set(payload) != {"resolved_digest", "record_version"}:
        return None
    if payload["record_version"] != SEPARATE_STORE_RECORD_VERSION:
        return None
    digest = payload["resolved_digest"]
    if not isinstance(digest, str) or _SHA256_RE.fullmatch(digest) is None:
        return None
    return digest


def _build_resolution(
    *,
    request: ObservableDigestResolverRequest,
    profile: SeparateStoreReadonlyProfile,
    snapshot: ImmutableSeparateStoreSnapshot,
    observed_at: str,
    resolution_state: ResolutionState,
    resolved_digest: str | None,
    failure_predicates: tuple[ObservableDigestFailurePredicate, ...],
    lookup_outcome: str,
) -> ObservableDigestResolution:
    guarantees = ResolverSemanticGuarantees()
    result = ObservableDigestResolverResult(
        request_id=request.request_id,
        locator=request.locator,
        resolver_id=profile.resolver_id,
        observed_at=observed_at,
        resolution_state=resolution_state,
        resolved_digest=resolved_digest,
        failure_predicates=failure_predicates,
        semantic_guarantees=guarantees,
    )
    observation = ObservableDigestResolverObservation(
        request_id=request.request_id,
        request_hash=request.request_hash,
        locator=request.locator,
        resolver_profile=request.resolver_profile,
        resolver_id=profile.resolver_id,
        caller_id_hash=request.caller_id_hash,
        access_scope=profile.namespace,
        profile_hash=profile.profile_hash,
        snapshot_hash=snapshot.snapshot_hash,
        observed_at=observed_at,
        lookup_outcome=lookup_outcome,
        resolved_digest=resolved_digest,
        failure_predicates=failure_predicates,
        semantic_guarantees=guarantees,
    )
    return ObservableDigestResolution(result=result, observation=observation)


def resolve_separate_store_readonly_v1(
    *,
    request: ObservableDigestResolverRequest,
    profile: SeparateStoreReadonlyProfile,
    snapshot: ImmutableSeparateStoreSnapshot,
    observed_at: str,
) -> ObservableDigestResolution:
    """Resolve one exact canonical locator against one immutable snapshot.

    The function is pure with respect to external state: all inputs are supplied
    explicitly and the implementation performs no external I/O or hidden
    authority lookup.
    """

    if not isinstance(request, ObservableDigestResolverRequest):
        raise TypeError("request must be ObservableDigestResolverRequest")
    if not isinstance(profile, SeparateStoreReadonlyProfile):
        raise TypeError("profile must be SeparateStoreReadonlyProfile")
    if not isinstance(snapshot, ImmutableSeparateStoreSnapshot):
        raise TypeError("snapshot must be ImmutableSeparateStoreSnapshot")
    observed_at = _require_utc_z(observed_at, "observed_at")

    if request.resolver_profile != profile.profile_id:
        return _build_resolution(
            request=request,
            profile=profile,
            snapshot=snapshot,
            observed_at=observed_at,
            resolution_state="UNRESOLVED",
            resolved_digest=None,
            failure_predicates=(ObservableDigestFailurePredicate.SCHEMA_MISMATCH,),
            lookup_outcome="SCHEMA_MISMATCH",
        )

    parsed = _parse_canonical_locator(request.locator)
    if parsed is None:
        return _build_resolution(
            request=request,
            profile=profile,
            snapshot=snapshot,
            observed_at=observed_at,
            resolution_state="UNRESOLVED",
            resolved_digest=None,
            failure_predicates=(ObservableDigestFailurePredicate.LOCATOR_MALFORMED,),
            lookup_outcome="LOCATOR_MALFORMED",
        )

    namespace, _key_segments = parsed

    if request.caller_id_hash not in profile.allowed_caller_id_hashes:
        return _build_resolution(
            request=request,
            profile=profile,
            snapshot=snapshot,
            observed_at=observed_at,
            resolution_state="UNRESOLVED",
            resolved_digest=None,
            failure_predicates=(ObservableDigestFailurePredicate.AUTHZ_DENIED,),
            lookup_outcome="AUTHZ_DENIED",
        )

    if namespace != profile.namespace:
        return _build_resolution(
            request=request,
            profile=profile,
            snapshot=snapshot,
            observed_at=observed_at,
            resolution_state="UNRESOLVED",
            resolved_digest=None,
            failure_predicates=(ObservableDigestFailurePredicate.AUTHZ_DENIED,),
            lookup_outcome="AUTHZ_DENIED",
        )

    record = snapshot.lookup_exact(request.locator)
    if record is None:
        return _build_resolution(
            request=request,
            profile=profile,
            snapshot=snapshot,
            observed_at=observed_at,
            resolution_state="UNRESOLVED",
            resolved_digest=None,
            failure_predicates=(ObservableDigestFailurePredicate.RESOLUTION_FAILED,),
            lookup_outcome="RESOLUTION_FAILED",
        )

    digest = _record_digest_or_none(record)
    if digest is None:
        return _build_resolution(
            request=request,
            profile=profile,
            snapshot=snapshot,
            observed_at=observed_at,
            resolution_state="UNRESOLVED",
            resolved_digest=None,
            failure_predicates=(ObservableDigestFailurePredicate.SCHEMA_MISMATCH,),
            lookup_outcome="SCHEMA_MISMATCH",
        )

    return _build_resolution(
        request=request,
        profile=profile,
        snapshot=snapshot,
        observed_at=observed_at,
        resolution_state="RESOLVED",
        resolved_digest=digest,
        failure_predicates=(),
        lookup_outcome="RESOLVED",
    )
