"""Separate sandbox ASGI factory; no default app, credentials or deployment.

Bearer-only exception applies solely to this service. The existing VERITAS API
keeps X-API-Key authentication. Operator-provisioned writer and reader tokens
are distinct, expiring and scoped here; no token is issued or resolved here.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hmac
import re
from typing import Callable

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from veritas_os.policy.sandbox_event_store import (
    PostgresSandboxEventStore, SandboxEventConflict, SandboxEventStoreError,
    parse_event, validate_key, validate_uuid,
)


class SandboxServiceTokens(BaseModel):
    """Trusted service configuration; never populate this from request input."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    writer: SecretStr = Field(repr=False)
    reader: SecretStr = Field(repr=False)
    valid_until: datetime


def create_sandbox_event_service(
    *, store: PostgresSandboxEventStore, tokens: SandboxServiceTokens,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> FastAPI:
    """Create an isolated, authenticated service; mounting into main is forbidden.

An operator must provide dedicated storage and tokens from reviewed secret
configuration. No environment fallback, token generator or public listener is
installed. Writer may register and lookup; reader may only lookup. Authentication
is checked before reading a body or touching the database. HTTP success is an
external observation for VERITAS, never independent consequence proof.
"""
    if type(store) is not PostgresSandboxEventStore or type(tokens) is not SandboxServiceTokens:
        raise ValueError("SSE_CONFIG_REQUIRED")
    tokens = SandboxServiceTokens.model_validate(tokens.model_dump())
    values = (tokens.writer.get_secret_value(), tokens.reader.get_secret_value())
    if (
        any(len(x) > 4096 or not re.fullmatch(r"[A-Za-z0-9._~+/-]{32,4096}=*", x) for x in values)
        or values[0] == values[1]
        or tokens.valid_until.tzinfo is None
        or tokens.valid_until.utcoffset() is None
    ):
        raise ValueError("SSE_CONFIG_INVALID")
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    def authenticate(request: Request, *, write: bool = False) -> None:
        headers = request.headers.getlist("authorization")
        allowed = False
        try:
            now = clock()
            if len(headers) == 1 and headers[0].startswith("Bearer "):
                token = headers[0][7:].encode("ascii")
                writer = hmac.compare_digest(token, tokens.writer.get_secret_value().encode("ascii"))
                reader = hmac.compare_digest(token, tokens.reader.get_secret_value().encode("ascii"))
                allowed = now < tokens.valid_until and (writer or (reader and not write))
        except Exception:
            pass
        if not allowed:
            raise HTTPException(401, "SSE_UNAUTHORIZED", headers={"WWW-Authenticate": "Bearer"})

    @app.middleware("http")
    async def no_cache(request: Request, call_next: Callable) -> JSONResponse:
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.post("/v1/events")
    async def register(request: Request) -> JSONResponse:
        authenticate(request, write=True)
        if request.headers.get("content-type", "").split(";")[0].lower() != "application/json":
            raise HTTPException(415, "SSE_JSON_REQUIRED")
        if request.headers.get("content-encoding", "identity") != "identity":
            raise HTTPException(415, "SSE_ENCODING_UNSUPPORTED")
        keys = request.headers.getlist("idempotency-key")
        body = bytearray()
        try:
            if len(keys) != 1:
                raise ValueError("key")
            key = validate_key(keys[0])
            async for chunk in request.stream():
                if len(body) + len(chunk) > 4096:
                    raise HTTPException(413, "SSE_BODY_TOO_LARGE")
                body.extend(chunk)
            parse_event(bytes(body))
        except HTTPException:
            raise
        except (ValueError, TypeError, UnicodeError, RecursionError):
            raise HTTPException(400, "SSE_INVALID_REQUEST") from None
        try:
            operation, created = await store.register(bytes(body), key)
        except SandboxEventConflict:
            raise HTTPException(409, "SSE_CONFLICT") from None
        except SandboxEventStoreError:
            raise HTTPException(503, "SSE_DATABASE_OUTCOME_UNKNOWN") from None
        return JSONResponse(operation.model_dump(), status_code=201 if created else 200)

    async def lookup(request: Request, operation_id: str | None) -> JSONResponse:
        authenticate(request)
        try:
            if operation_id is not None:
                validate_uuid(operation_id)
                if request.query_params:
                    raise ValueError("query")
                result = await store.lookup(operation_id=operation_id)
            else:
                pairs = list(request.query_params.multi_items())
                if len(pairs) != 1 or pairs[0][0] != "idempotency_key":
                    raise ValueError("key")
                result = await store.lookup(key=validate_key(pairs[0][1]))
        except (ValueError, TypeError):
            raise HTTPException(400, "SSE_INVALID_LOOKUP") from None
        except SandboxEventStoreError:
            raise HTTPException(503, "SSE_LOOKUP_UNAVAILABLE") from None
        if result is None:
            raise HTTPException(404, "SSE_NOT_FOUND_NOT_PROOF_OF_NO_EFFECT")
        return JSONResponse(result.model_dump())

    @app.get("/v1/operations")
    async def lookup_by_key(request: Request) -> JSONResponse:
        return await lookup(request, None)

    @app.get("/v1/operations/{operation_id}")
    async def lookup_by_id(request: Request, operation_id: str) -> JSONResponse:
        return await lookup(request, operation_id)

    return app
