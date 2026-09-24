"""Process-local capabilities for the frozen Bind effect boundaries.

Objects in this module are authority, not evidence.  They deliberately cannot be
serialized or copied, and their state is held by the issuing authority rather
than by caller-visible fields or a ``ContextVar``.
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import hashlib
import threading
from typing import Literal, Mapping
import weakref


PROOF_SCOPE = "BIND_COVERAGE_BYPASS_RESISTANCE_V1"
DispatchKind = Literal["ACTION", "COMPENSATION"]


class BindExecutionCapabilityError(RuntimeError):
    """Fail-closed capability validation error."""


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


@dataclass(frozen=True)
class ImmutableFinalDispatch:
    """Exact frozen, non-secret representation presented to an effect sink."""

    effect_boundary_id: str
    dispatch_kind: DispatchKind
    method: str
    canonical_endpoint: str
    canonical_bound_headers: tuple[tuple[str, str], ...]
    body_bytes: bytes
    body_digest: str
    request_identity: str
    idempotency_identity: str
    credential_reference_digest: str
    credential_scope_digest: str
    authorization_consumption_id: str
    runtime_implementation_identity: str

    def __post_init__(self) -> None:
        if type(self.body_bytes) is not bytes or _digest(self.body_bytes) != self.body_digest:
            raise BindExecutionCapabilityError("IMMUTABLE_DISPATCH_BODY_MISMATCH")
        if self.method not in {"POST"}:
            raise BindExecutionCapabilityError("IMMUTABLE_DISPATCH_METHOD_INVALID")
        for name, value in self.canonical_bound_headers:
            if not name or any(char in name + value for char in "\r\n"):
                raise BindExecutionCapabilityError("IMMUTABLE_DISPATCH_HEADER_INVALID")


@dataclass(frozen=True)
class PermitBinding:
    """Canonical semantics to which one Bound Execution Permit is confined."""

    coverage_entry_id: str
    operation_id: str
    action_class: str
    dispatch_kind: DispatchKind
    execution_intent_hash: str
    authorization_id: str
    authorization_hash: str
    authorization_consumption_id: str
    target_identity: str
    runtime_implementation_identity: str
    effect_boundary_id: str
    endpoint_identity: str
    credential_reference_digest: str
    credential_scope_digest: str
    request_body_digest: str
    request_identity: str
    idempotency_identity: str


class BoundExecutionPermit:
    """Opaque handle recognized only by the process-local issuing authority."""

    __slots__ = ("__weakref__",)

    def __new__(cls, *args: object, **kwargs: object) -> "BoundExecutionPermit":
        del args, kwargs
        raise BindExecutionCapabilityError("PERMIT_CALLER_CONSTRUCTION_FORBIDDEN")

    def __copy__(self) -> "BoundExecutionPermit":
        raise BindExecutionCapabilityError("PERMIT_COPY_FORBIDDEN")

    def __deepcopy__(self, memo: object) -> "BoundExecutionPermit":
        del memo
        raise BindExecutionCapabilityError("PERMIT_COPY_FORBIDDEN")

    def __reduce__(self) -> object:
        raise BindExecutionCapabilityError("PERMIT_SERIALIZATION_FORBIDDEN")


class CompensationEligibilityGrant:
    """Opaque, single-use authority emitted only by a Bind-core transition."""

    __slots__ = ("__weakref__",)

    def __new__(cls, *args: object, **kwargs: object) -> "CompensationEligibilityGrant":
        del args, kwargs
        raise BindExecutionCapabilityError("GRANT_CALLER_CONSTRUCTION_FORBIDDEN")

    def __copy__(self) -> "CompensationEligibilityGrant":
        raise BindExecutionCapabilityError("GRANT_COPY_FORBIDDEN")

    def __deepcopy__(self, memo: object) -> "CompensationEligibilityGrant":
        del memo
        raise BindExecutionCapabilityError("GRANT_COPY_FORBIDDEN")

    def __reduce__(self) -> object:
        raise BindExecutionCapabilityError("GRANT_SERIALIZATION_FORBIDDEN")


@dataclass(frozen=True)
class CompensationGrantBinding:
    """Exact parent ACTION and proposed compensation semantics."""

    parent_permit_identity: str
    parent_permit_consumption_identity: str
    authorization_consumption_id: str
    execution_intent_hash: str
    operation_id: str
    action_class: str
    compensation_reason: str
    effect_boundary_id: str
    endpoint_identity: str
    request_body_digest: str
    runtime_implementation_identity: str


@dataclass(frozen=True)
class ConsumedAuthorizationLineage:
    """Internally transported consumption lineage; not itself effect authority."""

    authorization_id: str
    authorization_hash: str
    consumption_id: str
    execution_intent_hash: str
    operation_id: str
    action_class: str
    target_identity: str
    credential_reference_digest: str
    credential_scope_digest: str


_LINEAGE: ContextVar[ConsumedAuthorizationLineage | None] = ContextVar(
    "bind_consumed_authorization_lineage", default=None
)


@contextmanager
def _transport_consumed_authorization_lineage(
    lineage: ConsumedAuthorizationLineage,
):
    token = _LINEAGE.set(lineage)
    try:
        yield
    finally:
        _LINEAGE.reset(token)


def _current_consumed_authorization_lineage() -> ConsumedAuthorizationLineage:
    lineage = _LINEAGE.get()
    if type(lineage) is not ConsumedAuthorizationLineage:
        raise BindExecutionCapabilityError("CONSUMED_AUTHORIZATION_LINEAGE_REQUIRED")
    return lineage


@dataclass
class _PermitRecord:
    binding: PermitBinding
    task_identity: int | None
    state: Literal["ACTIVE", "CONSUMED"] = "ACTIVE"
    consumption_identity: str = ""
    compensation_grant_minted: bool = False


@dataclass
class _GrantRecord:
    binding: CompensationGrantBinding
    state: Literal["ACTIVE", "CONSUMED"] = "ACTIVE"


def _task_identity() -> int | None:
    try:
        task = asyncio.current_task()
    except RuntimeError:
        return None
    return id(task) if task is not None else None


class _PermitAuthority:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._permits: weakref.WeakKeyDictionary[BoundExecutionPermit, _PermitRecord] = (
            weakref.WeakKeyDictionary()
        )
        self._grants: weakref.WeakKeyDictionary[
            CompensationEligibilityGrant, _GrantRecord
        ] = weakref.WeakKeyDictionary()

    def mint(self, binding: PermitBinding) -> BoundExecutionPermit:
        permit = object.__new__(BoundExecutionPermit)
        with self._lock:
            self._permits[permit] = _PermitRecord(binding, _task_identity())
        return permit

    def consume(
        self, permit: object, binding: PermitBinding, dispatch: ImmutableFinalDispatch
    ) -> str:
        if not _dispatch_matches(binding, dispatch):
            raise BindExecutionCapabilityError("PERMIT_FINAL_DISPATCH_MISMATCH")
        with self._lock:
            try:
                record = self._permits.get(permit)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                record = None
            if record is None:
                raise BindExecutionCapabilityError("PERMIT_PROVENANCE_INVALID")
            if record.task_identity != _task_identity():
                raise BindExecutionCapabilityError("PERMIT_TASK_MISMATCH")
            if record.binding != binding:
                raise BindExecutionCapabilityError("PERMIT_BINDING_MISMATCH")
            if record.state != "ACTIVE":
                raise BindExecutionCapabilityError("PERMIT_NOT_ACTIVE")
            record.state = "CONSUMED"
            record.consumption_identity = _digest(
                f"{id(permit)}:{binding.request_identity}".encode("utf-8")
            )
            return record.consumption_identity

    def mint_grant_for_consumed_action(
        self,
        parent_permit: object,
        binding: CompensationGrantBinding,
    ) -> CompensationEligibilityGrant:
        with self._lock:
            parent = self._permits.get(parent_permit)  # type: ignore[arg-type]
            if (
                parent is None
                or parent.state != "CONSUMED"
                or parent.consumption_identity
                != binding.parent_permit_consumption_identity
                or parent.binding.authorization_consumption_id
                != binding.authorization_consumption_id
                or parent.binding.execution_intent_hash
                != binding.execution_intent_hash
                or parent.binding.operation_id != binding.operation_id
                or parent.compensation_grant_minted
            ):
                raise BindExecutionCapabilityError("GRANT_PARENT_ACTION_INVALID")
            parent.compensation_grant_minted = True
            grant = object.__new__(CompensationEligibilityGrant)
            self._grants[grant] = _GrantRecord(binding)
            return grant

    def consume_grant(
        self, grant: object, binding: CompensationGrantBinding
    ) -> None:
        with self._lock:
            try:
                record = self._grants.get(grant)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                record = None
            if record is None:
                raise BindExecutionCapabilityError("GRANT_PROVENANCE_INVALID")
            if record.binding != binding:
                raise BindExecutionCapabilityError("GRANT_BINDING_MISMATCH")
            if record.state != "ACTIVE":
                raise BindExecutionCapabilityError("GRANT_NOT_ACTIVE")
            record.state = "CONSUMED"


def _dispatch_matches(
    binding: PermitBinding, dispatch: ImmutableFinalDispatch
) -> bool:
    return (
        binding.dispatch_kind == dispatch.dispatch_kind
        and binding.effect_boundary_id == dispatch.effect_boundary_id
        and binding.endpoint_identity == dispatch.canonical_endpoint
        and binding.runtime_implementation_identity
        == dispatch.runtime_implementation_identity
        and binding.authorization_consumption_id
        == dispatch.authorization_consumption_id
        and binding.credential_reference_digest
        == dispatch.credential_reference_digest
        and binding.credential_scope_digest == dispatch.credential_scope_digest
        and binding.request_body_digest == dispatch.body_digest
        and binding.request_identity == dispatch.request_identity
        and binding.idempotency_identity == dispatch.idempotency_identity
    )


_AUTHORITY = _PermitAuthority()


def _mint_bound_execution_permit(binding: PermitBinding) -> BoundExecutionPermit:
    return _AUTHORITY.mint(binding)


def consume_bound_execution_permit(
    permit: object, binding: PermitBinding, dispatch: ImmutableFinalDispatch
) -> str:
    """Atomically validate and consume a permit against the exact dispatch."""
    return _AUTHORITY.consume(permit, binding, dispatch)


def _mint_grant_from_consumed_action(
    parent_permit: object,
    binding: CompensationGrantBinding,
) -> CompensationEligibilityGrant:
    return _AUTHORITY.mint_grant_for_consumed_action(parent_permit, binding)


def consume_compensation_eligibility_grant(
    grant: object, binding: CompensationGrantBinding
) -> None:
    """Atomically consume an exact Bind-core compensation transition grant."""
    _AUTHORITY.consume_grant(grant, binding)


def runtime_implementation_identity(runtime: object | type[object]) -> str:
    """Return identity from the exact concrete Python class, never metadata."""
    concrete = runtime if type(runtime) is type else type(runtime)
    return f"{concrete.__module__}.{concrete.__qualname__}"


def canonical_headers(headers: Mapping[str, str]) -> tuple[tuple[str, str], ...]:
    """Freeze sorted non-secret headers while rejecting delimiter injection."""
    frozen = tuple(sorted((str(key).lower(), str(value)) for key, value in headers.items()))
    for name, value in frozen:
        if not name or any(char in name + value for char in "\r\n"):
            raise BindExecutionCapabilityError("IMMUTABLE_DISPATCH_HEADER_INVALID")
    return frozen


__all__ = [
    "BindExecutionCapabilityError",
    "BoundExecutionPermit",
    "CompensationEligibilityGrant",
    "CompensationGrantBinding",
    "ImmutableFinalDispatch",
    "PROOF_SCOPE",
    "PermitBinding",
    "canonical_headers",
    "consume_bound_execution_permit",
    "consume_compensation_eligibility_grant",
    "runtime_implementation_identity",
]
