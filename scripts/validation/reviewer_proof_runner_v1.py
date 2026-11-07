#!/usr/bin/env python3
"""Run the existing synthetic Decision-to-Effect proof in a disposable container.

The Docker network is internal; all effects are synthetic database events. This
does not assert distinct administrative custody, live-provider readiness or
independent source authenticity.
"""
from __future__ import annotations

from contextlib import closing
import json
import os
from pathlib import Path
import platform
import secrets
import socket
import subprocess
import sys
import time

from scripts.validation.reviewer_reproduction_manifest_v1 import (
    make_manifest,
    verify_bundle,
)

ROOT = Path("/workspace")
OUTPUT = ROOT / "artifacts/real-decision-to-effect-e2e"
TEMP = Path("/tmp/veritas-reviewer-proof-v1")
HOST = "sandbox.example.invalid"


def _run(command: list[str], *, timeout: int = 180) -> None:
    # Do not copy subprocess stdout, tokens or exception context to evidence.
    result = subprocess.run(
        command, cwd=ROOT, capture_output=True, text=True, timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        # Only whitelisted, truncated error summaries leave this container.
        # Raw stderr/stdout could include credential material; never upload it.
        markers = (
            "ERROR collecting", "ERROR at setup", "ModuleNotFoundError:",
            "ImportError:", "PermissionError:", "FileNotFoundError:",
            "SyntaxError:", "pytest: error:", "INTERNALERROR>",
            "E   ", "usage: pytest",
        )
        for line in (result.stdout + "\n" + result.stderr).splitlines():
            if not any(marker in line for marker in markers):
                continue
            if any(secret in line for secret in (
                os.environ.get("VERITAS_SANDBOX_WRITER_TOKEN", "<no-writer>"),
                os.environ.get("VERITAS_SANDBOX_READER_TOKEN", "<no-reader>"),
            )):
                continue
            if any(s in line.lower() for s in ("bearer ", "private key", "password")):
                continue
            print("REPRODUCTION_STAGE_DIAGNOSTIC: " + line[:240],
                  file=sys.stderr)
        stage = " ".join(command[:4])
        raise RuntimeError("REPRODUCTION_STAGE_FAILED: " + stage
                           + " (exit " + str(result.returncode) + ")")


def _openssl(*args: str) -> None:
    _run(["openssl", *args], timeout=40)


def _generate_controlled_tls() -> Path:
    TEMP.mkdir(mode=0o700, parents=True, exist_ok=False)
    ca_key, ca_crt = TEMP / "ca.key", TEMP / "ca.crt"
    server_key, csr = TEMP / "server.key", TEMP / "server.csr"
    server_crt, ext = TEMP / "server.crt", TEMP / "ext.cnf"
    _openssl(
        "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
        "-keyout", str(ca_key), "-out", str(ca_crt),
        "-subj", "/CN=VERITAS reviewer synthetic CA",
    )
    _openssl(
        "req", "-newkey", "rsa:2048", "-nodes",
        "-keyout", str(server_key), "-out", str(csr),
        "-subj", "/CN=sandbox.example.invalid",
    )
    ext.write_text(
        "subjectAltName=DNS:sandbox.example.invalid\n"
        "extendedKeyUsage=serverAuth\n",
        encoding="ascii",
    )
    _openssl(
        "x509", "-req", "-days", "1", "-in", str(csr),
        "-CA", str(ca_crt), "-CAkey", str(ca_key),
        "-CAcreateserial", "-out", str(server_crt),
        "-extfile", str(ext),
    )
    for key in (ca_key, server_key):
        key.chmod(0o600)
    return ca_crt


def _provision_database() -> str:
    import psycopg

    # Only disposable Docker service credentials. No external database accepted.
    dsn = "postgresql://veritas:reviewer-synthetic-only@db:5432/postgres"
    with closing(psycopg.connect(dsn, autocommit=True)) as conn:
        version = conn.execute("SHOW server_version").fetchone()[0]
        conn.execute("CREATE DATABASE veritas_decision_e2e_sandbox")
    _run(["alembic", "upgrade", "head"], timeout=180)
    return str(version)


def _check_endpoint() -> None:
    # The proof's pinned hostname must resolve inside THIS container,
    # not to an arbitrary reviewer-provided host or public network.
    addresses = {
        info[4][0] for info in socket.getaddrinfo(HOST, 443, type=socket.SOCK_STREAM)
    }
    if addresses != {"127.0.0.1"}:
        raise RuntimeError("PINNED_SYNTHETIC_HOST_NOT_LOOPBACK")


def _ready(service: subprocess.Popen, ca: Path, reader_token: str) -> None:
    import httpx

    deadline = time.monotonic() + 45
    with httpx.Client(verify=str(ca), trust_env=False, timeout=2.0) as client:
        while time.monotonic() < deadline:
            if service.poll() is not None:
                raise RuntimeError("SANDBOX_SERVICE_EXITED_BEFORE_HEALTHY")
            try:
                res = client.get(
                    "https://sandbox.example.invalid/v1/operations",
                    params={"idempotency_key": "not-created"},
                    headers={"Authorization": "Bearer " + reader_token},
                )
                if (res.status_code == 404 and
                        "SSE_NOT_FOUND_NOT_PROOF_OF_NO_EFFECT" in res.text):
                    return
            except httpx.RequestError:
                pass
            time.sleep(0.5)
    raise RuntimeError("SANDBOX_SERVICE_HEALTH_TIMEOUT")


def _verify_checkout() -> str:
    sha = os.environ["REVIEWER_EXPECTED_SHA"]
    if len(sha) != 40 or any(c not in "0123456789abcdef" for c in sha):
        raise RuntimeError("MALFORMED_EXTERNAL_CHECKOUT_PIN")
    actual = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, timeout=10,
    ).strip()
    if actual != sha:
        raise RuntimeError("EXACT_CHECKOUT_PIN_MISMATCH")
    return sha


def _give_files_to_host() -> None:
    # Container is disposable and may use uid 0 for port 443. Restore file
    # ownership for the non-root reviewer, never writing to their source tree.
    try:
        uid = int(os.environ["REVIEWER_HOST_UID"])
        gid = int(os.environ["REVIEWER_HOST_GID"])
        for path in OUTPUT.iterdir():
            if path.is_file() and not path.is_symlink():
                os.chown(path, uid, gid)
    except (OSError, ValueError, KeyError):
        # Rootless containers can already map ownership to the host user.
        pass


def run() -> None:
    os.umask(0o077)
    sha = _verify_checkout()
    _check_endpoint()
    if not OUTPUT.is_dir() or any(OUTPUT.iterdir()):
        raise RuntimeError("REVIEWER_OUTPUT_DIRECTORY_MUST_BE_EMPTY")
    if os.environ.get("VERITAS_DECISION_TO_EFFECT_E2E") != "1":
        raise RuntimeError("CONTROLLED_E2E_MODE_REQUIRED")
    environment = os.environ.copy()
    environment["VERITAS_SANDBOX_WRITER_TOKEN"] = secrets.token_hex(32)
    environment["VERITAS_SANDBOX_READER_TOKEN"] = secrets.token_hex(32)
    os.environ.update({
        "VERITAS_SANDBOX_WRITER_TOKEN": environment["VERITAS_SANDBOX_WRITER_TOKEN"],
        "VERITAS_SANDBOX_READER_TOKEN": environment["VERITAS_SANDBOX_READER_TOKEN"],
    })
    postgres_version = _provision_database()
    ca = _generate_controlled_tls()
    environment["VERITAS_SANDBOX_CA_FILE"] = str(ca)
    environment["VERITAS_SANDBOX_LOOKUP_OUTAGE_FLAG"] = str(TEMP / "lookup-outage")
    environment["VERITAS_DECISION_TO_EFFECT_REPORT"] = str(OUTPUT / "report.json")
    environment["VERITAS_DECISION_TO_EFFECT_EVIDENCE"] = str(OUTPUT / "evidence.json")
    environment["VERITAS_E2E_TESTED_SHA"] = sha
    environment["VERITAS_E2E_SOURCE_SHA"] = sha
    environment["VERITAS_E2E_BASE_SHA"] = sha
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    service: subprocess.Popen | None = None
    try:
        with (TEMP / "sandbox.log").open("wb") as log:
            service = subprocess.Popen(
                [
                    sys.executable, "scripts/run_native_v2_sandbox_service.py",
                    "--host", "127.0.0.1", "--port", "443",
                    "--cert", str(TEMP / "server.crt"),
                    "--key", str(TEMP / "server.key"),
                ],
                cwd=ROOT, env=environment, stdout=log, stderr=log,
            )
            _ready(service, ca, environment["VERITAS_SANDBOX_READER_TOKEN"])
            # Existing E2E owns all behavior and negative outcome assertions.
            _run([
                sys.executable, "-m", "pytest",
                "veritas_os/tests/test_decision_to_effect_controlled_e2e.py",
                "-q", "--tb=short", "-p", "no:cacheprovider",
            ], timeout=600)
            _run([
                sys.executable, "-m", "pytest",
                "tests/validation/test_reviewer_proof_contract_v1.py",
                "tests/validation/reviewer_proof_contract_e2e_checks.py",
                "-q", "--tb=short", "-p", "no:cacheprovider",
            ], timeout=120)
            _run([
                sys.executable, "-m",
                "scripts.validation.verify_reviewer_proof_contract_v1",
                "--contract", "contracts/reviewer-proof-contract-v1.json",
                "--report", str(OUTPUT / "report.json"),
                "--evidence", str(OUTPUT / "evidence.json"),
                "--tested-sha", sha, "--source-sha", sha, "--base-sha", sha,
                "--output", str(OUTPUT / "reviewer-proof-validation.json"),
            ], timeout=60)
            manifest = make_manifest(
                OUTPUT, sha,
                postgres_version=postgres_version,
                python_version=platform.python_version(),
            )
            (OUTPUT / "reproduction-manifest.json").write_text(
                json.dumps(manifest, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )
            verify_bundle(OUTPUT, sha)
            print("PASS_BOUNDED_LOCAL_REPRODUCTION_CONSISTENCY_ONLY")
            print("tested_sha=" + sha)
            print("manifest_sha256=" + manifest["manifest_sha256"])
    finally:
        if service is not None:
            service.terminate()
            try:
                service.wait(timeout=6)
            except subprocess.TimeoutExpired:
                service.kill()
                service.wait()
        _give_files_to_host()


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        # Never print synthetic secrets, raw request headers or stack frames.
        print("REVIEWER_RUNNER_NO_GO: " + type(exc).__name__ + ": " + str(exc),
              file=sys.stderr)
        raise SystemExit(1) from None
