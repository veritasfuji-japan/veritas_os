"""Dependency-free reference client for the VERITAS OS HTTP API."""

from __future__ import annotations

import json
from typing import Any
from urllib import error, request


class VeritasClientError(Exception):
    """Base error raised by the reference VERITAS client."""


class VeritasAPIError(VeritasClientError):
    """Represent a non-successful response from the VERITAS API."""

    def __init__(self, status_code: int, response_body: str) -> None:
        """Initialize an API response error.

        Args:
            status_code: HTTP response status code.
            response_body: Response body decoded as text.
        """
        self.status_code = status_code
        self.response_body = response_body
        super().__init__(
            f"VERITAS API returned HTTP {status_code}: {response_body}"
        )


class VeritasTransportError(VeritasClientError):
    """Represent a network or response-decoding failure."""


class VeritasClient:
    """Small synchronous client for JSON VERITAS API calls."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout: float = 30.0,
    ) -> None:
        """Initialize the client.

        Args:
            base_url: VERITAS API origin, such as ``http://localhost:8000``.
            api_key: Value sent in the ``X-API-Key`` header.
            timeout: Request timeout in seconds.

        Raises:
            ValueError: If an argument is empty or timeout is not positive.
        """
        if not base_url.strip():
            raise ValueError("base_url must not be empty")
        if not api_key.strip():
            raise ValueError("api_key must not be empty")
        if timeout <= 0:
            raise ValueError("timeout must be positive")

        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def request_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        """POST a JSON object and return a decoded JSON object.

        Args:
            path: Absolute API path beginning with ``/``.
            payload: JSON-serializable request object.

        Returns:
            The response JSON object.

        Raises:
            ValueError: If path is not absolute.
            TypeError: If payload is not a dictionary.
            VeritasAPIError: If the API returns a non-2xx response.
            VeritasTransportError: If transport or JSON decoding fails.
        """
        if not path.startswith("/"):
            raise ValueError("path must begin with '/'")
        if not isinstance(payload, dict):
            raise TypeError("payload must be a dictionary")

        body = json.dumps(payload).encode("utf-8")
        http_request = request.Request(
            f"{self.base_url}{path}",
            data=body,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "X-API-Key": self.api_key,
            },
            method="POST",
        )

        try:
            with request.urlopen(http_request, timeout=self.timeout) as response:
                response_body = response.read().decode("utf-8")
        except error.HTTPError as exc:
            response_body = exc.read().decode("utf-8", errors="replace")
            raise VeritasAPIError(exc.code, response_body) from exc
        except (error.URLError, TimeoutError) as exc:
            raise VeritasTransportError(
                f"VERITAS API request failed: {exc}"
            ) from exc

        try:
            decoded = json.loads(response_body)
        except json.JSONDecodeError as exc:
            raise VeritasTransportError(
                "VERITAS API response was not valid JSON"
            ) from exc
        if not isinstance(decoded, dict):
            raise VeritasTransportError(
                "VERITAS API response JSON must be an object"
            )
        return decoded

    def decide(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Submit a Decision Candidate request to ``POST /v1/decide``.

        The returned decision is not permission to execute an external action.
        Any execution must separately cross the VERITAS Bind Boundary.

        Args:
            payload: Request body matching the deployed ``/v1/decide`` contract.

        Returns:
            The decoded decision response.
        """
        return self.request_json("/v1/decide", payload)


__all__ = [
    "VeritasAPIError",
    "VeritasClient",
    "VeritasClientError",
    "VeritasTransportError",
]
