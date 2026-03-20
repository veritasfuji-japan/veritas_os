"""Requests-compatible fallback for optional HTTP tool dependencies.

This module keeps ``web_search`` and ``github_adapter`` importable even when
the third-party ``requests`` package is unavailable. Runtime HTTP calls still
work via ``urllib`` with a minimal compatibility surface, while tests can keep
monkeypatching ``requests.get`` / ``requests.post`` and ``requests.exceptions``.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Optional
from urllib import parse as urllib_parse


class RequestException(Exception):
    """Base compatibility exception for requests-like transport failures."""


class Timeout(RequestException):
    """Timeout compatibility exception."""


class HTTPError(RequestException):
    """HTTP status error carrying an optional response object."""

    def __init__(
        self,
        message: str = "",
        *,
        response: Any | None = None,
    ) -> None:
        super().__init__(message)
        self.response = response


@dataclass
class _CompatResponse:
    """Small subset of the ``requests.Response`` interface used in VERITAS."""

    status_code: int
    _body: bytes
    headers: dict[str, str]

    @property
    def text(self) -> str:
        return self._body.decode("utf-8", errors="replace")

    def json(self) -> Any:
        return json.loads(self.text)

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise HTTPError(
                f"HTTP {self.status_code}",
                response=self,
            )


class _RequestsCompat:
    """Minimal requests-like adapter backed by ``urllib``."""

    Response = _CompatResponse
    exceptions = SimpleNamespace(
        RequestException=RequestException,
        Timeout=Timeout,
        HTTPError=HTTPError,
    )
    RequestException = RequestException

    def get(
        self,
        url: str,
        *,
        headers: Optional[dict[str, str]] = None,
        timeout: Optional[float] = None,
        params: Optional[dict[str, Any]] = None,
    ) -> _CompatResponse:
        if params:
            encoded = urllib_parse.urlencode(params)
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}{encoded}"
        return self._request("GET", url, headers=headers, timeout=timeout)

    def post(
        self,
        url: str,
        *,
        headers: Optional[dict[str, str]] = None,
        timeout: Optional[float] = None,
        json: Optional[dict[str, Any]] = None,
    ) -> _CompatResponse:
        data = None
        request_headers = dict(headers or {})
        if json is not None:
            data = json_module.dumps(json).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/json")
        return self._request(
            "POST",
            url,
            headers=request_headers,
            timeout=timeout,
            data=data,
        )

    def _request(
        self,
        method: str,
        url: str,
        *,
        headers: Optional[dict[str, str]] = None,
        timeout: Optional[float] = None,
        data: bytes | None = None,
    ) -> _CompatResponse:
        httpx = importlib.import_module("httpx")

        try:
            response = httpx.request(
                method,
                url,
                content=data,
                headers=headers or {},
                timeout=timeout,
            )
            return _CompatResponse(
                status_code=response.status_code,
                _body=response.content,
                headers=dict(response.headers.items()),
            )
        except httpx.TimeoutException as exc:
            raise Timeout(str(exc)) from exc
        except httpx.HTTPStatusError as exc:
            response = _CompatResponse(
                status_code=exc.response.status_code,
                _body=exc.response.content,
                headers=dict(exc.response.headers.items()),
            )
            raise HTTPError(
                str(exc),
                response=response,
            ) from exc
        except httpx.HTTPError as exc:
            raise RequestException(str(exc)) from exc


json_module = json


def load_requests_compat() -> Any:
    """Return ``requests`` when installed, otherwise a local compatibility shim."""
    if importlib.util.find_spec("requests") is not None:
        return importlib.import_module("requests")
    return _RequestsCompat()
