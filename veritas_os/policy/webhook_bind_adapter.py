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
        verified_snapshot = getattr(self, "_verified_revert_snapshot", None)
        if isinstance(verified_snapshot, dict):
            object.__setattr__(self, "_verified_revert_snapshot", None)
            return dict(verified_snapshot)
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
            "expected_postcondition_is_object": isinstance(
                self.expected_postcondition, dict
            ),
            "snapshot_is_object": isinstance(snapshot, dict),
            "snapshot_url_allowed": self._url_allowed(self.snapshot_url),
            "action_url_allowed": self._url_allowed(self.action_url),
            "postcondition_url_allowed": self._url_allowed(self.postcondition_url),
            "hmac_secret_present": bool(self.hmac_secret),
            "timeout_is_valid": isinstance(self.timeout_seconds, (int, float))
            and 0 < self.timeout_seconds <= 60,
        }
        if self.compensation_url is not None:
            results["compensation_url_allowed"] = self._url_allowed(
                self.compensation_url
            )
            results["compensation_payload_is_object"] = (
                self.compensation_payload is None
                or isinstance(self.compensation_payload, dict)
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
        data = self._post_json_object(
            self.action_url,
            self.action_payload,
            intent,
            "BIND_WEBHOOK_ACTION_FAILED",
        )
        object.__setattr__(self, "_last_action_metadata", self._response_metadata(data))
        return True

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
        """Compensate and verify restoration of the exact pre-bind snapshot."""
        if not self.compensation_url or not isinstance(snapshot, dict):
            return False
        if self.compensation_payload is not None and not isinstance(
            self.compensation_payload, dict
        ):
            return False
        try:
            self._post_json_object(
                self.compensation_url,
                self.compensation_payload or {},
                intent,
                "BIND_WEBHOOK_COMPENSATION_FAILED",
            )
            restored_snapshot = self._get_json_object(
                self.snapshot_url,
                "BIND_WEBHOOK_COMPENSATION_VERIFICATION_FAILED",
            )
            restored_fingerprint = self.fingerprint_state(restored_snapshot)
            original_fingerprint = self.fingerprint_state(snapshot)
        except (RuntimeError, TypeError, ValueError):
            return False
        if restored_fingerprint != original_fingerprint:
            return False
        # Bind core takes its own post-revert snapshot before reporting rollback.
        # Reuse the exact state already verified to avoid a second network race.
        object.__setattr__(self, "_verified_revert_snapshot", restored_snapshot)
        return True

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
        """Build a deterministic key without allowing malformed URLs to escape."""
        payload = {
            "execution_intent_id": intent.execution_intent_id,
            "decision_id": intent.decision_id,
            "action_url": self._safe_normalized_url(self.action_url),
            "action_payload": self.action_payload,
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
        idempotency_key = self.build_idempotency_key(intent)
        canonical_body = canonical_json_dumps(body)
        timestamp = (
            datetime.now(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z")
        )
        signature_input = f"{timestamp}.{canonical_body}".encode("utf-8")
        signature = hmac.new(
            self.hmac_secret, signature_input, hashlib.sha256
        ).hexdigest()
        headers = {
            "Content-Type": "application/json",
            "X-Veritas-Decision-Id": intent.decision_id,
            "X-Veritas-Execution-Intent-Id": intent.execution_intent_id,
            "X-Veritas-Idempotency-Key": idempotency_key,
            "X-Veritas-Timestamp": timestamp,
            "X-Veritas-Signature": f"sha256={signature}",
        }
        response = self._request("POST", url, headers=headers, json_body=body)
        return self._require_json_object(response, error_code)

    def _request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None,
        json_body: Mapping[str, Any] | None,
    ) -> WebhookResponse:
        if not self._url_allowed(url):
            raise RuntimeError("BIND_WEBHOOK_URL_NOT_ALLOWED")
        transport = self.transport or _UrllibWebhookTransport()
        try:
            return transport.request(
                method,
                self._normalized_url(url),
                headers=headers,
                json_body=json_body,
                timeout=float(self.timeout_seconds),
                allow_redirects=False,
            )
        except Exception as exc:
            raise RuntimeError("BIND_WEBHOOK_REQUEST_FAILED") from exc

    @staticmethod
    def _require_json_object(
        response: WebhookResponse, error_code: str
    ) -> dict[str, Any]:
        if not 200 <= int(response.status_code) <= 299:
            raise RuntimeError(error_code)
        if not isinstance(response.json_data, dict):
            raise RuntimeError(error_code)
        return dict(response.json_data)

    @staticmethod
    def _response_metadata(data: dict[str, Any]) -> dict[str, Any]:
        return {"response_keys": sorted(str(key) for key in data.keys())[:20]}

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
        except OSError:
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
    def _safe_normalized_url(url: Any) -> str:
        """Normalize a URL or return a non-sensitive deterministic sentinel."""
        try:
            return WebhookBindAdapter._normalized_url(url)
        except (AttributeError, TypeError, ValueError):
            raw_digest = sha256_of_canonical_json({"raw_url": str(url)})
            return f"invalid-url:sha256:{raw_digest}"

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
        timeout: float,
        allow_redirects: bool = False,
    ) -> WebhookResponse:
        del allow_redirects
        data = None
        if json_body is not None:
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


__all__ = ["WebhookBindAdapter", "WebhookResponse", "WebhookTransport"]
