"""Run one isolated Keycloak rehearsal using the API worker lifecycle."""

from __future__ import annotations

import asyncio
import os
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import datetime
from typing import TypedDict
from urllib.parse import urlsplit

from psycopg import Error
from psycopg.conninfo import conninfo_to_dict
from psycopg_pool import PoolTimeout

from veritas_os.core import shared_halt
from veritas_os.core.posture import PostureLevel, resolve_posture

from veritas_os.policy.keycloak_lab_executor import (
    KeycloakLabDispatchObservation,
    KeycloakLabExecutor,
    KeycloakLabWriterCredential,
)
from veritas_os.policy.keycloak_role_grant_binding import KeycloakLabDeployment
from veritas_os.policy.live_adapter_bind_authorization_contracts import (
    BindAuthorizationTrustInputs,
    RealBindAuthorizationGovernanceInputs,
)
from veritas_os.policy.native_bind_authorization import (
    NativeBindAuthorizationArtifact,
    NativeAuthorizationSourceInputs,
)
from veritas_os.policy.sandbox_pre_effect import SandboxClockReading, SandboxCurrentInputs
from veritas_os.security.hash import sha256_hex
from veritas_os.storage import db, sandbox_restore

_LOOPBACK = {"127.0.0.1", "::1"}
_DATABASE_NAME = re.compile(r"veritas_rehearsal_[a-z0-9_]{1,45}")


class KeycloakStagingRehearsalBlocked(RuntimeError):
    """The rehearsal was stopped before handing the request to the executor."""


def require_staging_rehearsal_environment() -> None:
    """Validate staging posture and the dedicated authentication Redis URL."""
    if (
        os.getenv("VERITAS_ENV") != "staging"
        or resolve_posture() is not PostureLevel.STAGING
        or os.getenv("VERITAS_ENABLE_KEYCLOAK_STAGING_REHEARSAL") != "1"
    ):
        raise KeycloakStagingRehearsalBlocked("KEYCLOAK_STAGING_DISABLED")
    deployment_id = os.getenv("VERITAS_DEPLOYMENT_ID", "")
    if (
        os.getenv("VERITAS_HALT_BACKEND") != "postgresql"
        or not deployment_id.startswith("veritas-rehearsal-")
        or deployment_id == "veritas-rehearsal-"
    ):
        raise KeycloakStagingRehearsalBlocked("KEYCLOAK_STAGING_HALT_SCOPE_INVALID")
    redis_url = (os.getenv("VERITAS_AUTH_REDIS_URL") or "").strip()
    try:
        redis = urlsplit(redis_url)
        valid_address = (
            redis.scheme in {"redis", "rediss"}
            and redis.hostname in _LOOPBACK
            and redis.port is not None
            and redis.port > 0
            and not redis.query
            and not redis.fragment
            and re.fullmatch(r"/[0-9]+", redis.path)
            and redis_url.isascii()
        )
    except ValueError:
        valid_address = False
    if (
        os.getenv("VERITAS_AUTH_SECURITY_STORE") != "redis"
        or not valid_address
        or sha256_hex(redis_url.encode("ascii")) != os.getenv(
            "VERITAS_KEYCLOAK_STAGING_AUTH_REDIS_SHA256"
        )
    ):
        raise KeycloakStagingRehearsalBlocked("KEYCLOAK_STAGING_AUTH_REDIS_INVALID")


def _require_isolated_configuration(deployment: KeycloakLabDeployment) -> str:
    require_staging_rehearsal_environment()
    if type(deployment) is not KeycloakLabDeployment or deployment.digest() != os.getenv(
        "VERITAS_KEYCLOAK_STAGING_DEPLOYMENT_SHA256"
    ):
        raise KeycloakStagingRehearsalBlocked("KEYCLOAK_STAGING_DEPLOYMENT_MISMATCH")

    try:
        config = conninfo_to_dict(db.build_conninfo())
    except (Error, RuntimeError, ValueError):
        raise KeycloakStagingRehearsalBlocked("KEYCLOAK_STAGING_DATABASE_INVALID") from None

    name = config.get("dbname", "")
    if (
        not _DATABASE_NAME.fullmatch(name)
        or config.get("host") not in _LOOPBACK
        or any(config.get(key) for key in ("service", "hostaddr"))
        or any(os.getenv(key) for key in ("PGSERVICE", "PGHOSTADDR"))
    ):
        raise KeycloakStagingRehearsalBlocked("KEYCLOAK_STAGING_DATABASE_INVALID")
    return name


async def _require_recovery_complete(expected_database: str) -> None:
    try:
        async with asyncio.timeout(5):
            pool = await db.get_pool()
            async with pool.connection() as connection:
                if (
                    connection.info.dbname != expected_database
                    or connection.info.hostaddr not in _LOOPBACK
                ):
                    raise KeycloakStagingRehearsalBlocked(
                        "KEYCLOAK_STAGING_DATABASE_MISMATCH"
                    )
                cursor = await connection.execute(sandbox_restore.RECOVERY_PENDING)
                pending = await cursor.fetchone()
    except (Error, PoolTimeout, TimeoutError):
        raise KeycloakStagingRehearsalBlocked(
            "KEYCLOAK_STAGING_RECOVERY_UNAVAILABLE"
        ) from None

    if pending != (False,):
        raise KeycloakStagingRehearsalBlocked("KEYCLOAK_STAGING_RESTORE_PENDING")


class StagingRehearsalAttempt(TypedDict):
    """Inputs for a single attempt, loaded after the operator resumes."""

    authorization: NativeBindAuthorizationArtifact
    event_id: str
    attempt_id: str
    issuance_source_inputs: NativeAuthorizationSourceInputs
    governance_inputs: RealBindAuthorizationGovernanceInputs
    trust_inputs: BindAuthorizationTrustInputs
    trusted_clock: Callable[[], SandboxClockReading]
    load_current_inputs: Callable[[datetime], SandboxCurrentInputs]
    resolve_writer: Callable[[], Awaitable[KeycloakLabWriterCredential]]


async def _require_operator_resume() -> None:
    try:
        halted = await asyncio.to_thread(shared_halt.status)
    except shared_halt.HaltStoreUnavailable:
        raise KeycloakStagingRehearsalBlocked("KEYCLOAK_STAGING_HALT_UNAVAILABLE") from None
    if halted.get("halted") is not False:
        raise KeycloakStagingRehearsalBlocked("KEYCLOAK_STAGING_HALTED")


@asynccontextmanager
async def keycloak_staging_rehearsal_worker(
    deployment: KeycloakLabDeployment,
    *,
    load_attempt: Callable[[], StagingRehearsalAttempt],
) -> AsyncIterator[Callable[[], Awaitable[KeycloakLabDispatchObservation | None]]]:
    """Yield one dispatch within the normal API lifespan of a dedicated process.

    Signed inputs are loaded once, after the shared halt permits dispatch.
    The ordinary operator resume still applies to the isolated staging
    deployment. This entry point has no HTTP route.
    """
    database = _require_isolated_configuration(deployment)
    available = False
    owner = asyncio.current_task()

    async def dispatch() -> KeycloakLabDispatchObservation | None:
        nonlocal available
        if not available or asyncio.current_task() is not owner:
            raise KeycloakStagingRehearsalBlocked("KEYCLOAK_STAGING_DISPATCH_UNAVAILABLE")
        available = False
        await _require_operator_resume()
        await _require_recovery_complete(database)

        attempt = load_attempt()
        await _require_operator_resume()
        await _require_recovery_complete(database)
        executor = KeycloakLabExecutor(
            deployment,
            trusted_clock=attempt["trusted_clock"],
            load_current_inputs=attempt["load_current_inputs"],
            resolve_writer=attempt["resolve_writer"],
        )
        return await executor.execute(
            attempt["authorization"],
            event_id=attempt["event_id"],
            attempt_id=attempt["attempt_id"],
            issuance_source_inputs=attempt["issuance_source_inputs"],
            governance_inputs=attempt["governance_inputs"],
            trust_inputs=attempt["trust_inputs"],
        )

    try:
        await _require_recovery_complete(database)
        from veritas_os.api.server import app

        from veritas_os.api.auth import RedisAuthSecurityStore, _get_effective_auth_store

        auth_store = _get_effective_auth_store()
        if not isinstance(auth_store, RedisAuthSecurityStore):
            raise KeycloakStagingRehearsalBlocked("KEYCLOAK_STAGING_AUTH_REDIS_UNAVAILABLE")
        redis = urlsplit(os.environ["VERITAS_AUTH_REDIS_URL"].strip())
        settings = auth_store._redis.connection_pool.connection_kwargs
        if (settings.get("host"), settings.get("port"), settings.get("db")) != (
            redis.hostname,
            redis.port,
            int(redis.path[1:]),
        ):
            raise KeycloakStagingRehearsalBlocked("KEYCLOAK_STAGING_AUTH_REDIS_MISMATCH")

        async with app.router.lifespan_context(app):
            available = True
            try:
                yield dispatch
            finally:
                available = False
    finally:
        await db.close_pool()
