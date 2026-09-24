"""Fail-closed HTTPS webhook bind adapter.

WebhookBindAdapter is a reference external bind adapter.  It sends a
three-endpoint bind flow (snapshot, action, postcondition) through the existing
bind core and compensates only when an explicitly configured compensation
webhook verifies success.  Generic external side effects may be irreversible;
when compensation is absent or unverified, rollback is not claimed.

Receiver contract
-----------------
Action and compensation receivers get JSON POST requests with these headers:
``Content-Type``, ``X-Veritas-Decision-Id``,
``X-Veritas-Execution-Intent-Id``, ``X-Veritas-Idempotency-Key``,
``X-Veritas-Timestamp``, and ``X-Veritas-Signature``.  The signature is
``sha256=<hex hmac-sha256>`` over ``timestamp + "." + canonical_json_body``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from contextvars import ContextVar
from datetime import datetime, timezone
import hashlib
import hmac
import ipaddress
import json
import socket
from typing import Any, Callable, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import ParseResult, urlparse, urlunparse
from urllib.request import Request, build_opener, HTTPRedirectHandler

from veritas_os.policy.bind_artifacts import ExecutionIntent
from veritas_os.policy.bind_core.contracts import BindAdapterContract
from veritas_os.policy.bind_coverage_registry import match_frozen_runtime_boundary
from veritas_os.policy.bind_execution_capability import (
    ImmutableFinalDispatch,
    CompensationGrantBinding,
    PermitBinding,
    _current_consumed_authorization_lineage,
    _mint_bound_execution_permit,
    _mint_grant_from_consumed_action,
    canonical_headers,
    consume_bound_execution_permit,
    consume_compensation_eligibility_grant,
    runtime_implementation_identity,
)
from veritas_os.security.hash import canonical_json_dumps, sha256_of_canonical_json


class WebhookTransport(Protocol):
    """Synchronous transport contract used by WebhookBindAdapter."""

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        json_body: Mapping[str, Any] | None = None,
        body_bytes: bytes | None = None,
        timeout: float,
        allow_redirects: bool = False,
    ) -> "WebhookResponse":
        """Return an HTTP response without following redirects."""


@dataclass(frozen=True)
class WebhookResponse:
    """Minimal sanitized HTTP response shape for webhook calls."""

    status_code: int
    json_data: Any
    headers: Mapping[str, str] = field(default_factory=dict, repr=False)


_AUTHORIZED_WEBHOOK_DISPATCH: ContextVar[
    tuple[ImmutableFinalDispatch, PermitBinding, object] | None
] = ContextVar("authorized_webhook_dispatch", default=None)
_CONSUMED_WEBHOOK_ACTION: ContextVar[
    tuple[object, PermitBinding, str, int, str, str] | None
] = ContextVar("consumed_webhook_action", default=None)


@dataclass(frozen=True, repr=False)
class WebhookBindAdapter(BindAdapterContract):
    """Bind adapter that executes governed changes through HTTPS webhooks."""

    snapshot_url: str
    action_url: str
    postcondition_url: str
    action_payload: dict[str, Any]
    expected_postcondition: dict[str, Any]
    allowed_hosts: set[str] | frozenset[str]
    hmac_secret: bytes | str
    timeout_seconds: float = 5.0
    required_approval_key: str = "external_webhook_action_approved"
    compensation_url: str | None = None
    compensation_payload: dict[str, Any] | None = None
    transport: WebhookTransport | None = field(default=None, repr=False, compare=False)
    dns_resolver: Callable[[str], list[str]] | None = field(
        default=None, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "allowed_hosts", frozenset(self.allowed_hosts))
        if isinstance(self.hmac_secret, str):
            object.__setattr__(self, "hmac_secret", self.hmac_secret.encode("utf-8"))

    def __repr__(self) -> str:
        return (
            "WebhookBindAdapter("
            f"snapshot_url={self._describe_url(self.snapshot_url)!r}, "
            f"action_url={self._describe_url(self.action_url)!r}, "
            f"postcondition_url={self._describe_url(self.postcondition_url)!r}, "
            f"compensation_url={self._describe_url(self.compensation_url)!r}, "
            f"allowed_hosts={sorted(self.allowed_hosts)!r}, "
            f"timeout_seconds={self.timeout_seconds!r})"
        )

    def snapshot(self) -> dict[str, Any]:
        return self._get_json_object(self.snapshot_url, "BIND_WEBHOOK_SNAPSHOT_FAILED")

    def fingerprint_state(self, snapshot: Any) -> str:
        if not isinstance(snapshot, dict):
            raise ValueError("BIND_WEBHOOK_SNAPSHOT_INVALID")
        return sha256_of_canonical_json(snapshot)

    def validate_authority(self, intent: ExecutionIntent, snapshot: Any) -> bool | None:
        del snapshot
        if not isinstance(intent.approval_context, dict):
            return False
        return intent.approval_context.get(self.required_approval_key) is True

    def validate_constraints(
        self,
        intent: ExecutionIntent,
        snapshot: Any,
    ) -> dict[str, bool] | None:
        del intent
        results = {
            "action_payload_is_object": isinstance(self.action_payload, dict),
            "action_payload_is_canonical_json": _is_canonical_json(self.action_payload),
            "expected_postcondition_is_object": isinstance(
                self.expected_postcondition, dict
            ),
            "expected_postcondition_is_canonical_json": _is_canonical_json(
                self.expected_postcondition
            ),
            "snapshot_is_object": isinstance(snapshot, dict),
            "snapshot_url_allowed": self._url_allowed(self.snapshot_url),
            "action_url_allowed": self._url_allowed(self.action_url),
            "postcondition_url_allowed": self._url_allowed(self.postcondition_url),
            "hmac_secret_present": isinstance(self.hmac_secret, bytes)
            and bool(self.hmac_secret),
            "timeout_is_valid": isinstance(self.timeout_seconds, (int, float))
            and 0 < self.timeout_seconds <= 60,
        }
        if self.compensation_url is not None:
            results["compensation_url_allowed"] = self._url_allowed(
                self.compensation_url
            )
            compensation_payload = self.compensation_payload or {}
            results["compensation_payload_is_object"] = isinstance(
                compensation_payload, dict
            )
            results["compensation_payload_is_canonical_json"] = _is_canonical_json(
                compensation_payload
            )
        return results

    def assess_runtime_risk(
        self, intent: ExecutionIntent, snapshot: Any
    ) -> bool | None:
        del intent, snapshot
        urls = [self.snapshot_url, self.action_url, self.postcondition_url]
        if self.compensation_url:
            urls.append(self.compensation_url)
        return all(self._url_allowed(url) for url in urls)

    def apply(self, intent: ExecutionIntent, snapshot: Any) -> bool:
        del snapshot
        self._post_json_object(
            self.action_url,
            self.action_payload,
            intent,
            "BIND_WEBHOOK_ACTION_FAILED",
        )
        return True

    def _authorize_action_dispatch(self, intent: ExecutionIntent) -> object:
        """Called by Bind core immediately before the registered ACTION apply."""
        return self._authorize_dispatch(
            intent,
            url=self.action_url,
            body=self.action_payload,
            dispatch_kind="ACTION",
            effect_boundary_id="registered-webhook-action",
        )

    def _authorize_dispatch(
        self,
        intent: ExecutionIntent,
        *,
        url: str,
        body: dict[str, Any],
        dispatch_kind: str,
        effect_boundary_id: str,
    ) -> object:
        lineage = _current_consumed_authorization_lineage()
        coverage = match_frozen_runtime_boundary(
            self,
            effect_boundary_id=effect_boundary_id,
            dispatch_kind=dispatch_kind,
        )
        endpoint = self._normalized_url(url)
        body_bytes = canonical_json_dumps(body).encode("utf-8")
        body_digest = hashlib.sha256(body_bytes).hexdigest()
        idempotency_key = self.build_idempotency_key(intent)
        timestamp = (
            datetime.now(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z")
        )
        headers = {
            "Content-Type": "application/json",
            "X-Veritas-Decision-Id": intent.decision_id,
            "X-Veritas-Execution-Intent-Id": intent.execution_intent_id,
            "X-Veritas-Idempotency-Key": idempotency_key,
            "X-Veritas-Timestamp": timestamp,
        }
        request_identity = hashlib.sha256(
            b"webhook-dispatch-v1\x00"
            + endpoint.encode("utf-8")
            + b"\x00"
            + body_bytes
            + b"\x00"
            + idempotency_key.encode("utf-8")
        ).hexdigest()
        runtime_identity = runtime_implementation_identity(self)
        final_dispatch = ImmutableFinalDispatch(
            effect_boundary_id=effect_boundary_id,
            dispatch_kind=dispatch_kind,  # type: ignore[arg-type]
            method="POST",
            canonical_endpoint=endpoint,
            canonical_bound_headers=canonical_headers(headers),
            body_bytes=body_bytes,
            body_digest=body_digest,
            request_identity=request_identity,
            idempotency_identity=idempotency_key,
            credential_reference_digest=lineage.credential_reference_digest,
            credential_scope_digest=lineage.credential_scope_digest,
            authorization_consumption_id=lineage.consumption_id,
            runtime_implementation_identity=runtime_identity,
        )
        binding = PermitBinding(
            coverage_entry_id=coverage.coverage_entry_id,
            operation_id=lineage.operation_id,
            action_class=lineage.action_class,
            dispatch_kind=dispatch_kind,  # type: ignore[arg-type]
            execution_intent_hash=lineage.execution_intent_hash,
            authorization_id=lineage.authorization_id,
            authorization_hash=lineage.authorization_hash,
            authorization_consumption_id=lineage.consumption_id,
            target_identity=lineage.target_identity,
            runtime_implementation_identity=runtime_identity,
            effect_boundary_id=effect_boundary_id,
            endpoint_identity=endpoint,
            credential_reference_digest=lineage.credential_reference_digest,
            credential_scope_digest=lineage.credential_scope_digest,
            request_body_digest=body_digest,
            request_identity=request_identity,
            idempotency_identity=idempotency_key,
        )
        permit = _mint_bound_execution_permit(binding)
        return _AUTHORIZED_WEBHOOK_DISPATCH.set((final_dispatch, binding, permit))

    def _authorize_compensation_dispatch(
        self, intent: ExecutionIntent, reason: str
    ) -> object:
        parent = _CONSUMED_WEBHOOK_ACTION.get()
        if parent is None or not self.compensation_url:
            raise RuntimeError("BIND_WEBHOOK_COMPENSATION_GRANT_REQUIRED")
        (
            parent_permit,
            parent_binding,
            parent_consumption,
            parent_adapter_identity,
            expected_endpoint,
            expected_body_digest,
        ) = parent
        body = self.compensation_payload or {}
        endpoint = self._normalized_url(self.compensation_url)
        body_digest = hashlib.sha256(
            canonical_json_dumps(body).encode("utf-8")
        ).hexdigest()
        if (
            parent_adapter_identity != id(self)
            or endpoint != expected_endpoint
            or body_digest != expected_body_digest
        ):
            raise RuntimeError("BIND_WEBHOOK_COMPENSATION_LINEAGE_MISMATCH")
        grant_binding = CompensationGrantBinding(
            parent_permit_identity=hashlib.sha256(
                str(id(parent_permit)).encode("ascii")
            ).hexdigest(),
            parent_permit_consumption_identity=parent_consumption,
            authorization_consumption_id=parent_binding.authorization_consumption_id,
            execution_intent_hash=parent_binding.execution_intent_hash,
            operation_id=parent_binding.operation_id,
            action_class=parent_binding.action_class,
            compensation_reason=reason,
            effect_boundary_id="registered-webhook-compensation",
            endpoint_identity=endpoint,
            request_body_digest=body_digest,
            runtime_implementation_identity=runtime_implementation_identity(self),
        )
        grant = _mint_grant_from_consumed_action(parent_permit, grant_binding)
        consume_compensation_eligibility_grant(grant, grant_binding)
        return self._authorize_dispatch(
            intent,
            url=self.compensation_url,
            body=body,
            dispatch_kind="COMPENSATION",
            effect_boundary_id="registered-webhook-compensation",
        )

    @staticmethod
    def _clear_authorized_dispatch(token: object) -> None:
        _AUTHORIZED_WEBHOOK_DISPATCH.reset(token)  # type: ignore[arg-type]

    def verify_postconditions(self, intent: ExecutionIntent, snapshot: Any) -> bool:
        del intent, snapshot
        try:
            actual = self._get_json_object(
                self.postcondition_url,
                "BIND_WEBHOOK_POSTCONDITION_FAILED",
            )
        except RuntimeError:
            return False
        return _recursive_subset(self.expected_postcondition, actual)

    def revert(self, intent: ExecutionIntent, snapshot: Any) -> bool:
        del snapshot
        if not self.compensation_url:
            return False
        try:
            response = self._post_json_object(
                self.compensation_url,
                self.compensation_payload or {},
                intent,
                "BIND_WEBHOOK_COMPENSATION_FAILED",
            )
        except RuntimeError:
            return False
        return response.get("compensated") is True

    def describe_target(self) -> str:
        return "webhook:" + ",".join(
            part
            for part in [
                self._describe_url(self.action_url),
                self._describe_url(self.postcondition_url),
            ]
            if part
        )

    def build_idempotency_key(self, intent: ExecutionIntent) -> str:
        """Build a stable key without allowing invalid configuration to escape.

        Bind core asks for the key before it enters its adapter error boundary.
        Invalid URLs or non-JSON payloads therefore use explicit invalid
        sentinels here and are rejected later by adapter constraints.
        """
        try:
            action_url = self._normalized_url(self.action_url)
        except (TypeError, ValueError):
            action_url = "<invalid-action-url>"
        action_payload: Any = self.action_payload
        if not _is_canonical_json(action_payload):
            action_payload = "<invalid-action-payload>"
        payload = {
            "execution_intent_id": intent.execution_intent_id,
            "decision_id": intent.decision_id,
            "action_url": action_url,
            "action_payload": action_payload,
        }
        return sha256_of_canonical_json(payload)

    def _get_json_object(self, url: str, error_code: str) -> dict[str, Any]:
        response = self._request("GET", url, headers={}, json_body=None)
        return self._require_json_object(response, error_code)

    def _post_json_object(
        self,
        url: str,
        body: dict[str, Any],
        intent: ExecutionIntent,
        error_code: str,
    ) -> dict[str, Any]:
        del intent
        authorized = _AUTHORIZED_WEBHOOK_DISPATCH.get()
        if authorized is None:
            raise RuntimeError("BIND_WEBHOOK_ACTION_PERMIT_REQUIRED")
        final_dispatch, binding, permit = authorized
        if (
            final_dispatch.canonical_endpoint != self._normalized_url(url)
            or final_dispatch.body_bytes != canonical_json_dumps(body).encode("utf-8")
        ):
            raise RuntimeError("BIND_WEBHOOK_FINAL_DISPATCH_MISMATCH")
        response = self._request(
            "POST",
            url,
            headers=dict(final_dispatch.canonical_bound_headers),
            json_body=None,
            final_dispatch=final_dispatch,
            permit_binding=binding,
            permit=permit,
        )
        return self._require_json_object(response, error_code)

    def _request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None,
        json_body: Mapping[str, Any] | None,
        final_dispatch: ImmutableFinalDispatch | None = None,
        permit_binding: PermitBinding | None = None,
        permit: object | None = None,
    ) -> WebhookResponse:
        if not self._url_allowed(url):
            raise RuntimeError("BIND_WEBHOOK_URL_NOT_ALLOWED")
        transport = self.transport or _UrllibWebhookTransport()
        try:
            body_bytes = None
            if method == "POST":
                if (
                    type(final_dispatch) is not ImmutableFinalDispatch
                    or type(permit_binding) is not PermitBinding
                ):
                    raise RuntimeError("BIND_WEBHOOK_ACTION_PERMIT_REQUIRED")
                consumption_identity = consume_bound_execution_permit(
                    permit, permit_binding, final_dispatch
                )
                if final_dispatch.dispatch_kind == "ACTION":
                    compensation_endpoint = (
                        self._normalized_url(self.compensation_url)
                        if self.compensation_url
                        else ""
                    )
                    compensation_digest = hashlib.sha256(
                        canonical_json_dumps(
                            self.compensation_payload or {}
                        ).encode("utf-8")
                    ).hexdigest()
                    _CONSUMED_WEBHOOK_ACTION.set(
                        (
                            permit,
                            permit_binding,
                            consumption_identity,
                            id(self),
                            compensation_endpoint,
                            compensation_digest,
                        )
                    )
                body_bytes = final_dispatch.body_bytes
                if canonical_headers(dict(headers or {})) != (
                    final_dispatch.canonical_bound_headers
                ):
                    raise RuntimeError("BIND_WEBHOOK_BOUND_HEADERS_MISMATCH")
                timestamp = dict(
                    final_dispatch.canonical_bound_headers
                )["x-veritas-timestamp"]
                signature = hmac.new(
                    self.hmac_secret,
                    timestamp.encode("utf-8") + b"." + body_bytes,
                    hashlib.sha256,
                ).hexdigest()
                headers = dict(headers or {})
                headers["X-Veritas-Signature"] = f"sha256={signature}"
            request_kwargs: dict[str, Any] = {
                "headers": headers,
                "json_body": json_body,
                "timeout": float(self.timeout_seconds),
                "allow_redirects": False,
            }
            if body_bytes is not None:
                request_kwargs["body_bytes"] = body_bytes
            return transport.request(
                method,
                self._normalized_url(url),
                **request_kwargs,
            )
        except Exception:
            # Do not preserve transport exception text or chaining: injected
            # clients can include request headers or secret material in errors.
            raise RuntimeError("BIND_WEBHOOK_REQUEST_FAILED") from None

    @staticmethod
    def _require_json_object(
        response: WebhookResponse, error_code: str
    ) -> dict[str, Any]:
        if not 200 <= int(response.status_code) <= 299:
            raise RuntimeError(error_code)
        if not isinstance(response.json_data, dict):
            raise RuntimeError(error_code)
        return dict(response.json_data)

    def _url_allowed(self, url: str | None) -> bool:
        try:
            parsed = _parse_https_url(url)
        except ValueError:
            return False
        hostname = parsed.hostname or ""
        if hostname not in self.allowed_hosts:
            return False
        return self._hostname_addresses_are_safe(hostname)

    def _hostname_addresses_are_safe(self, hostname: str) -> bool:
        try:
            addresses = (
                self.dns_resolver(hostname)
                if self.dns_resolver
                else _resolve_host(hostname)
            )
        except Exception:
            # Resolver implementations are untrusted boundaries. Any unknown
            # resolver behavior must become a deny signal, not escape bind core.
            return False
        return bool(addresses) and all(
            _address_is_safe(address) for address in addresses
        )

    @staticmethod
    def _normalized_url(url: str) -> str:
        parsed = _parse_https_url(url)
        host = parsed.hostname or ""
        netloc = host if parsed.port in (None, 443) else f"{host}:{parsed.port}"
        return urlunparse(("https", netloc, parsed.path or "/", "", parsed.query, ""))

    @staticmethod
    def _describe_url(url: str | None) -> str:
        if not url:
            return ""
        try:
            parsed = _parse_https_url(url)
        except ValueError:
            return "invalid-url"
        host = parsed.hostname or ""
        netloc = host if parsed.port in (None, 443) else f"{host}:{parsed.port}"
        return urlunparse(("https", netloc, "", "", "", ""))


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


class _UrllibWebhookTransport:
    """Default transport using urllib with redirects disabled."""

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        json_body: Mapping[str, Any] | None = None,
        body_bytes: bytes | None = None,
        timeout: float,
        allow_redirects: bool = False,
    ) -> WebhookResponse:
        del allow_redirects
        data = body_bytes
        if data is None and json_body is not None:
            data = canonical_json_dumps(json_body).encode("utf-8")
        request = Request(url, data=data, headers=dict(headers or {}), method=method)
        opener = build_opener(_NoRedirectHandler)
        try:
            with opener.open(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
                parsed = json.loads(raw) if raw else {}
                return WebhookResponse(
                    response.status, parsed, dict(response.headers.items())
                )
        except HTTPError as exc:
            try:
                parsed = json.loads(exc.read().decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                parsed = None
            return WebhookResponse(exc.code, parsed, dict(exc.headers.items()))
        except (
            TimeoutError,
            URLError,
            json.JSONDecodeError,
            UnicodeDecodeError,
        ) as exc:
            raise RuntimeError("BIND_WEBHOOK_TRANSPORT_FAILED") from exc


def _parse_https_url(url: str | None) -> ParseResult:
    if not isinstance(url, str) or not url.strip():
        raise ValueError("BIND_WEBHOOK_URL_INVALID")
    try:
        parsed = urlparse(url)
        _ = parsed.port
    except ValueError as exc:
        raise ValueError("BIND_WEBHOOK_URL_INVALID") from exc
    if parsed.scheme != "https":
        raise ValueError("BIND_WEBHOOK_URL_SCHEME_INVALID")
    if not parsed.hostname:
        raise ValueError("BIND_WEBHOOK_URL_HOST_MISSING")
    if parsed.username or parsed.password:
        raise ValueError("BIND_WEBHOOK_URL_USERINFO_FORBIDDEN")
    if parsed.fragment:
        raise ValueError("BIND_WEBHOOK_URL_FRAGMENT_FORBIDDEN")
    return parsed


def _resolve_host(hostname: str) -> list[str]:
    return sorted({item[4][0] for item in socket.getaddrinfo(hostname, None)})


def _address_is_safe(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return not (
        ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_unspecified
        or ip.is_reserved
        or ip.is_private
    )


def _recursive_subset(expected: dict[str, Any], actual: dict[str, Any]) -> bool:
    for key, value in expected.items():
        if key not in actual:
            return False
        actual_value = actual[key]
        if isinstance(value, dict):
            if not isinstance(actual_value, dict):
                return False
            if not _recursive_subset(value, actual_value):
                return False
            continue
        if actual_value != value:
            return False
    return True


def _is_canonical_json(value: Any) -> bool:
    """Return whether a value can be serialized by canonical JSON helpers."""
    try:
        canonical_json_dumps(value)
    except (OverflowError, RecursionError, TypeError, ValueError):
        return False
    return True


__all__ = ["WebhookBindAdapter", "WebhookResponse", "WebhookTransport"]
