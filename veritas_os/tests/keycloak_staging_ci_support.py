"""Test-only operator for a disposable Keycloak staging worker."""

import asyncio
from collections.abc import Callable
import json
import os
from pathlib import Path
from secrets import token_urlsafe
import sys
from types import ModuleType
from unittest.mock import patch
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi.testclient import TestClient

from veritas_os.api.keycloak_staging_rehearsal import (
    KeycloakStagingRehearsalBlocked,
    StagingRehearsalAttempt,
)
from veritas_os.policy.keycloak_lab_executor import KeycloakLabExecutionError
from veritas_os.policy.keycloak_role_grant_binding import KeycloakLabDeployment
from veritas_os.security.hash import sha256_hex
from veritas_os.security.signing import store_keypair


def _approve_resume(app, operator: str, reviewer: str) -> None:
    # The CLI owns the lifespan. Opening a second lifespan would re-arm the halt.
    client = TestClient(app)

    def request(method: str, path: str, key: str, body: dict | None = None) -> dict:
        response = client.request(method, path, headers={"X-API-Key": key}, json=body)
        assert response.status_code == 200, (method, path, response.status_code)
        return response.json()

    root = "/v1/system/resume"
    assert request("GET", "/v1/system/halt-status", operator)["halted"] is True
    prepared = request("POST", f"{root}/prepare", operator)
    review_path = f"{root}/requests/{prepared['request_id']}"
    review = request("GET", review_path, reviewer)
    assert review["preparation"] == prepared
    artifact = request("POST", f"{review_path}/approve", reviewer, {
        "decision": "approve",
        "context_hash": review["context_hash"],
    })
    request("POST", root, operator, {
        "operator": "staging-ci",
        "request_id": prepared["request_id"],
        "approval_artifact": artifact,
    })
    assert request("GET", "/v1/system/halt-status", operator)["halted"] is False


async def run_staging_attempt(
    deployment: KeycloakLabDeployment,
    load_attempt: Callable[[], StagingRehearsalAttempt],
    directory: Path,
) -> str:
    """Run the staging entry point and authorize resume through the real API."""
    redis_url = os.environ["VERITAS_AUTH_REDIS_URL"]
    assert urlsplit(redis_url).hostname == "127.0.0.1"
    directory = directory / uuid4().hex
    directory.mkdir(mode=0o700)
    private, public = store_keypair(directory / "approval.key", directory / "approval.pub")
    operator, reviewer = token_urlsafe(32), token_urlsafe(32)

    with patch.dict(os.environ, {
        "VERITAS_ENV": "staging",
        "VERITAS_POSTURE": "staging",
        "VERITAS_DATA_DIR": str(directory),
        "VERITAS_API_KEY": operator,
        "VERITAS_API_KEYS": json.dumps([
            {"key": key, "role": "admin"} for key in (operator, reviewer)
        ]),
        "VERITAS_DEPLOYMENT_ID": f"veritas-rehearsal-{uuid4().hex}",
        "VERITAS_HALT_BACKEND": "postgresql",
        "VERITAS_ENABLE_KEYCLOAK_STAGING_REHEARSAL": "1",
        "VERITAS_AUTH_SECURITY_STORE": "redis",
        "VERITAS_KEYCLOAK_STAGING_AUTH_REDIS_SHA256": sha256_hex(redis_url.encode("ascii")),
        "VERITAS_KEYCLOAK_STAGING_DEPLOYMENT_SHA256": deployment.digest(),
        "VERITAS_SYSTEM_RESUME_PUBLIC_KEY": public.read_text().strip(),
        "VERITAS_SYSTEM_RESUME_SIGNING_KEY_FILE": str(private),
    }):
        from scripts.validation.run_keycloak_staging_rehearsal import run
        from veritas_os.api.auth import _derive_api_user_id
        from veritas_os.api.server import app

        fixture = ModuleType("_keycloak_staging_ci_fixture")
        loaded = False

        def load_approved_attempt() -> StagingRehearsalAttempt:
            nonlocal loaded
            from veritas_os.core import shared_halt

            assert not loaded
            assert shared_halt.status()["halted"] is False
            loaded = True
            return load_attempt()

        fixture.provide = lambda: {
            "deployment": deployment,
            "load_attempt": load_approved_attempt,
        }
        with (
            patch.dict(sys.modules, {fixture.__name__: fixture}),
            patch.dict(os.environ, {
                "VERITAS_SYSTEM_RESUME_APPROVER_ID": _derive_api_user_id(reviewer)
            }),
        ):
            async with asyncio.timeout(25), asyncio.TaskGroup() as tasks:
                # Capture only the allowlisted terminal conditions; unexpected errors fail CI.
                async def attempt() -> str:
                    try:
                        result = await run(f"{fixture.__name__}:provide")
                    except KeycloakStagingRehearsalBlocked as exc:
                        assert str(exc) == "KEYCLOAK_STAGING_RESTORE_PENDING"
                        return "RESTORE_PENDING"
                    except KeycloakLabExecutionError as exc:
                        assert exc.reason == "ALREADY_CONSUMED"
                        return exc.reason
                    assert result == 0
                    return "HTTP_204_UNVERIFIED"

                worker = tasks.create_task(attempt())
                while not worker.done() and not getattr(
                    app.state, "security_startup_complete", False
                ):
                    await asyncio.sleep(0.05)
                if not worker.done():
                    assert not loaded
                    await asyncio.to_thread(_approve_resume, app, operator, reviewer)
            return worker.result()
