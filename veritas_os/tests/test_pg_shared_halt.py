"""Two independently imported ASGI applications sharing a deployment halt."""
import asyncio
import json
import multiprocessing
import os
import socket
from contextlib import ExitStack, contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import monotonic, sleep
from unittest.mock import patch
from uuid import uuid4

import pytest


def _worker(pipe, barrier, release_audit, release_key, *, use_lifespan=False):
    from fastapi.testclient import TestClient
    from veritas_os.api import auth, governance, routes_system, server
    from veritas_os.api.startup_health import initialize_system_halt_on_startup
    from veritas_os.core import shared_halt_audit
    from veritas_os.logging import encryption, trust_log
    from veritas_os.logging.trust_log import append_trust_log, iter_trust_log, verify_trust_log

    def pause_and_lose_ack(entry, **kwargs):
        if entry["kind"] == "governance.execution_intent":
            pipe.send("audit blocked")
            assert release_audit.wait(20)
        result = append_trust_log(entry, **kwargs)
        if entry["kind"] == "governance.bind_receipt":
            raise OSError("injected failure after file append")
        return result

    queue = shared_halt_audit.queue_resume_audit

    def fail_after_insert(*args, **kwargs):
        queue(*args, **kwargs)
        raise RuntimeError("injected rollback before database commit")

    build_provider = encryption._build_key_provider

    class SimulatedProviderError(Exception):
        pass

    class UnavailableProvider:
        provider_name = "fixture_kms"

        def load_key(self):
            raise SimulatedProviderError("temporary provider outage")

    class DelayedProvider:
        def load_key(self):
            pipe.send("key provider blocked")
            assert release_key.wait(20)
            return build_provider("env").load_key()

    key_scope = shared_halt_audit.resolved_encryption_key
    fail_next_lookup = True

    @contextmanager
    def key_scope_with_transient_outage():
        nonlocal fail_next_lookup
        if fail_next_lookup:
            fail_next_lookup = False
            with patch.object(encryption, "_build_key_provider", return_value=UnavailableProvider()), key_scope():
                yield
        else:
            with key_scope():
                yield

    client = TestClient(server.app)
    strict = os.getenv("VERITAS_POSTURE") == "secure"
    if not (strict or use_lifespan):
        initialize_system_halt_on_startup()
    with pipe, ExitStack() as worker_cleanup:
        if strict:
            worker_cleanup.enter_context(
                patch.object(governance, "_DEFAULT_POLICY_PATH", Path(os.environ["VERITAS_DATA_DIR"]) / "policy.json"),
            )
            # The external signed mirror is outside this test. Keep the native
            # encrypted TrustLog and independently signed resume approval real.
            worker_cleanup.enter_context(patch.object(trust_log, "append_signed_decision", return_value={}))
            if not use_lifespan:
                # Control which worker drains the outbox for deterministic fault injection.
                worker_cleanup.enter_context(
                    patch.object(shared_halt_audit, "run_resume_audit_publisher", asyncio.Event().wait),
                )
        if use_lifespan:
            worker_cleanup.enter_context(
                patch.object(shared_halt_audit, "resolved_encryption_key", key_scope_with_transient_outage),
            )
        if strict or use_lifespan:
            worker_cleanup.enter_context(client)
        if strict:
            assert server.app.state.security_startup_complete
            assert isinstance(auth._get_effective_auth_store(), auth.RedisAuthSecurityStore)
        pipe.send(os.getpid())
        while True:
            command = pipe.recv()
            if command is None:
                return
            method, path, credential, body = command
            if method == "audit":
                pipe.send([entry for entry in iter_trust_log()
                           if entry.get("execution_intent_id") == path])
                continue
            if method == "publish_with_lost_ack":
                with (
                    patch.object(shared_halt_audit, "append_trust_log", pause_and_lose_ack),
                    patch.object(encryption, "_build_key_provider", wraps=build_provider) as lookup,
                ):
                    published = shared_halt_audit.publish_next_resume_audit()
                pipe.send((published, lookup.call_count))
                continue
            if method == "concurrent_log":
                barrier.wait(timeout=30)
                for index in range(12):
                    append_trust_log({"kind": "fixture.concurrent", "request_id": f"{path}-{index}"})
                pipe.send(True)
                continue
            if method == "verify_log":
                pipe.send(verify_trust_log())
                continue
            if method == "failed_queue":
                with patch.object(shared_halt_audit, "queue_resume_audit", fail_after_insert):
                    result = client.post(path, headers={"X-API-Key": credential}, json=body)
                pipe.send((result.status_code, result.json()))
                continue
            if method == "resume_with_delayed_key":
                with patch.object(encryption, "_build_key_provider", return_value=DelayedProvider()):
                    result = client.post(path, headers={"X-API-Key": credential}, json=body)
                pipe.send((result.status_code, result.json()))
                continue
            if method in {"expire_halt_apply", "expire_resume_apply", "expire_resume_commit"}:
                controller = server.SystemHaltController
                owner, name = {
                    "expire_halt_apply": (controller, "halt"),
                    "expire_resume_apply": (controller, "resume_if_halt_matches"),
                    "expire_resume_commit": (shared_halt_audit, "queue_resume_audit"),
                }[method]
                operation = getattr(owner, name)
                deadline = datetime.now(timezone.utc) + timedelta(seconds=2)
                issued_at = (deadline - timedelta(seconds=30)).isoformat()

                def after_deadline(*args, target=operation, expires=deadline, **kwargs):
                    sleep(max(0, (expires - datetime.now(timezone.utc)).total_seconds()) + 0.05)
                    return target(*args, **kwargs)

                with (
                    patch.object(routes_system, "new_system_control_intent_window", return_value=(issued_at, deadline)),
                    patch.object(owner, name, side_effect=after_deadline) as apply,
                ):
                    result = client.post(path, headers={"X-API-Key": credential}, json=body)
                    assert apply.call_count == 1, result.json()
                pipe.send((result.status_code, result.json()))
                continue
            if method == "decide_without_database":
                # Bind a port without listening so the actual database driver
                # gets a connection refusal without disrupting the other worker.
                with socket.socket() as unavailable:
                    unavailable.bind(("127.0.0.1", 0))
                    port = unavailable.getsockname()[1]
                    with patch.dict(os.environ, {
                        "VERITAS_DATABASE_URL": f"postgresql://127.0.0.1:{port}/unavailable?connect_timeout=1",
                    }):
                        result = client.post(path, headers={"X-API-Key": credential}, json=body)
                pipe.send((result.status_code, result.json()))
                continue
            if method == "race":
                barrier.wait(timeout=30)
                method = "POST"
            result = client.request(method, path, headers={"X-API-Key": credential}, json=body)
            pipe.send((result.status_code, result.json()))


def _receive(pipe):
    assert pipe.poll(60), "worker did not respond"
    return pipe.recv()


def _stop(proc, pipe):
    if proc.is_alive():
        pipe.send(None)
        proc.join(5)
    if proc.is_alive():
        proc.terminate()
        proc.join(5)
    pipe.close()


@pytest.mark.postgresql
@pytest.mark.contention
@pytest.mark.skipif(not os.getenv("VERITAS_DATABASE_URL"), reason="requires migrated PostgreSQL")
@pytest.mark.parametrize("posture", ["dev", "secure"])
def test_two_processes_share_halt_approval_and_single_commit(monkeypatch, tmp_path, posture):
    from veritas_os.api.auth import _derive_api_user_id
    from veritas_os.api.governance import GovernancePolicy
    from veritas_os.core import shared_halt
    from veritas_os.logging.encryption import generate_key
    from veritas_os.security.signing import store_keypair

    executor, reviewer = uuid4().hex, uuid4().hex
    private, public = store_keypair(tmp_path / "approval.key", tmp_path / "approval.pub")
    deployment = uuid4().hex
    if posture == "secure" and not os.getenv("VERITAS_TEST_SHARED_HALT_REDIS_URL"):
        pytest.skip("requires the dedicated Redis 7+ AOF service for secure startup")
    for name, value in {
        "VERITAS_ENV": "test", "VERITAS_POSTURE": posture,
        "VERITAS_DATA_DIR": str(tmp_path), "VERITAS_ENCRYPTION_KEY": generate_key(),
        "VERITAS_DEPLOYMENT_ID": deployment, "VERITAS_HALT_BACKEND": "postgresql",
        "VERITAS_SYSTEM_RESUME_PUBLIC_KEY": public.read_text().strip(),
        "VERITAS_SYSTEM_RESUME_SIGNING_KEY_FILE": str(private),
        "VERITAS_SYSTEM_RESUME_APPROVER_ID": _derive_api_user_id(reviewer),
        "VERITAS_API_KEY": executor, "VERITAS_API_KEYS": json.dumps([
            {"key": key, "role": "admin"} for key in (executor, reviewer)
        ]),
    }.items():
        monkeypatch.setenv(name, value)

    if posture == "secure":
        policy = GovernancePolicy().model_dump()
        policy["bind_adjudication"].update(
            ttl_required=True, approval_freshness_required=True, rollback_on_apply_failure=True,
        )
        (tmp_path / "policy.json").write_text(json.dumps(policy), encoding="utf-8")
        for name, value in {
            "WEB_CONCURRENCY": "2",
            "VERITAS_API_SECRET": uuid4().hex,
            "VERITAS_ENFORCE_API_SECRET_IN_TESTS": "1",
            "VERITAS_AUTH_SECURITY_STORE": "redis",
            "VERITAS_AUTH_REDIS_URL": os.environ["VERITAS_TEST_SHARED_HALT_REDIS_URL"],
            "VERITAS_POSTURE_OVERRIDE_EXTERNAL_SECRET_MGR": "0",
            "VERITAS_TRUSTLOG_BACKEND": "postgresql",
            "VERITAS_TRUSTLOG_SIGNER_BACKEND": "aws_kms",
            "VERITAS_TRUSTLOG_KMS_KEY_ID": "fixture-only",
            "VERITAS_TRUSTLOG_MIRROR_BACKEND": "s3_object_lock",
            "VERITAS_TRUSTLOG_S3_BUCKET": "fixture-only",
            "VERITAS_TRUSTLOG_S3_PREFIX": "fixture-only",
            "VERITAS_TRUSTLOG_ANCHOR_BACKEND": "local",
            "VERITAS_TRUSTLOG_TRANSPARENCY_LOG_PATH": str(tmp_path / "anchor.jsonl"),
        }.items():
            monkeypatch.setenv(name, value)

    def request(worker, method, path, credential, body=None, expected=200):
        worker.send((method, path, credential, body))
        code, response = _receive(worker)
        assert code == expected, response
        return response

    ctx = multiprocessing.get_context("spawn")
    barrier = ctx.Barrier(2)
    release_audit = ctx.Event()
    release_key = ctx.Event()
    with ExitStack() as cleanup:
        def start_worker(*, use_lifespan=False):
            parent, child = ctx.Pipe()
            proc = ctx.Process(target=_worker, args=(child, barrier, release_audit, release_key),
                               kwargs={"use_lifespan": use_lifespan})
            proc.start()
            child.close()
            cleanup.callback(_stop, proc, parent)
            assert _receive(parent) == proc.pid
            return parent

        def approve_resume(executor_worker, reviewer_worker):
            prepared = request(executor_worker, "POST", url + "/prepare", executor)
            review = url + "/requests/" + prepared["request_id"]
            approval = request(reviewer_worker, "GET", review, reviewer)
            assert approval["preparation"] == prepared
            artifact = request(reviewer_worker, "POST", review + "/approve", reviewer,
                               {"decision": "approve", "context_hash": approval["context_hash"]})
            return prepared, {"operator": "fixture", "request_id": prepared["request_id"], "approval_artifact": artifact}

        url = "/v1/system/resume"
        a, b = workers = [start_worker(), start_worker()]
        if posture == "secure":
            request(a, "GET", "/v1/system/halt-status", "wrong-fixture-key", expected=401)
        request(a, "POST", "/v1/system/halt", executor, {"operator": "fixture", "reason": "test"})
        halt = request(a, "GET", "/v1/system/halt-status", executor)
        assert halt["halted"] and halt["reason"] == "test"
        assert request(b, "GET", "/v1/system/halt-status", executor)["halt_id"] == halt["halt_id"]
        blocked = request(b, "POST", "/v1/decide", executor, {"query": "blocked"}, expected=503)
        assert blocked["status"] == "HALTED"
        if posture == "secure":
            unavailable = request(
                b, "decide_without_database", "/v1/decide", executor, {"query": "blocked"}, expected=503,
            )
            assert unavailable["error"] == "Emergency halt state unavailable"
        prepared, body = approve_resume(a, b)
        if posture == "secure":
            refused = request(
                a, "expire_halt_apply", "/v1/system/halt", executor,
                {"operator": "fixture", "reason": "expired stop"}, expected=403,
            )
            assert refused["bind_outcome"] == "BLOCKED"
            assert request(b, "GET", "/v1/system/halt-status", executor)["halt_id"] == halt["halt_id"]

            refused = request(a, "expire_resume_apply", url, executor, body, expected=403)
            assert refused["bind_outcome"] == "BLOCKED"
            assert request(b, "GET", "/v1/system/halt-status", executor)["halt_id"] == halt["halt_id"]
            refused = request(a, "expire_resume_commit", url, executor, body, expected=409)
            assert refused["detail"] == "Resume intent or approval expired before commit"
            assert request(b, "GET", "/v1/system/halt-status", executor)["halt_id"] == halt["halt_id"]

        request(a, "failed_queue", url, executor, body, expected=500)
        assert request(b, "GET", "/v1/system/halt-status", executor)["halt_id"] == halt["halt_id"]
        blocked = request(b, "POST", "/v1/decide", executor, {"query": "blocked"}, expected=503)
        assert blocked["status"] == "HALTED"
        a.send(("audit", prepared["execution_intent_id"], None, None))
        assert not any(entry.get("final_outcome") == "COMMITTED" for entry in _receive(a))
        with shared_halt.transaction() as conn:
            assert conn.execute(
                "SELECT count(*) FROM deployment_resume_receipts WHERE deployment_id=%s", (deployment,),
            ).fetchone()[0] == 0

        for worker in workers:
            worker.send(("race", url, executor, body))
        responses = [_receive(worker) for worker in workers]
        assert sum(code == 200 for code, _ in responses) == 1, responses
        assert all(code in {200, 404, 409} for code, _ in responses), responses
        winner = next(result for code, result in responses if code == 200)
        for worker in workers:
            assert request(worker, "GET", "/v1/system/halt-status", executor)["halted"] is False
        with shared_halt.transaction() as conn:
            receipts = conn.execute(
                "SELECT receipt, audit_entries, published_at FROM deployment_resume_receipts "
                "WHERE deployment_id=%s AND halt_id=%s",
                (deployment, halt["halt_id"]),
            ).fetchall()
        assert [row[0]["bind_receipt_id"] for row in receipts] == [winner["bind_receipt_id"]]
        assert receipts[0][1].startswith("ENC:") and receipts[0][2] is None
        if posture == "secure":
            assert receipts[0][0]["revalidation_context"]["approval_expires_at"] == body["approval_artifact"]["receipt"]["expires_at"]
            replacement_worker = start_worker()
            restarted = request(replacement_worker, "GET", "/v1/system/halt-status", executor)
            assert restarted["halted"] and restarted["halt_id"] != halt["halt_id"]
            assert request(b, "GET", "/v1/system/halt-status", executor)["halt_id"] == restarted["halt_id"]
            request(b, "POST", url, executor, body, expected=404)

        a.send(("publish_with_lost_ack", None, None, None))
        assert _receive(a) == "audit blocked"
        try:
            request(b, "POST", "/v1/system/halt", executor,
                    {"operator": "fixture", "reason": "replacement"})
            replacement = request(b, "GET", "/v1/system/halt-status", executor)
            assert replacement["halt_id"] != halt["halt_id"]
        finally:
            release_audit.set()
        assert _receive(a) == (True, 1)
        with shared_halt.transaction() as conn:
            assert conn.execute(
                "SELECT published_at FROM deployment_resume_receipts WHERE deployment_id=%s",
                (deployment,),
            ).fetchone()[0] is None
            conn.execute(
                "UPDATE deployment_resume_receipts SET next_attempt_at=clock_timestamp() WHERE deployment_id=%s",
                (deployment,),
            )

        # A freshly started worker must recover the pending acknowledgement without
        # duplicating either of the two native records or replacing the active stop.
        recovery = start_worker(use_lifespan=True)
        deadline = monotonic() + 10
        while monotonic() < deadline:
            with shared_halt.transaction() as conn:
                scheduled_retry, published_at = conn.execute(
                    "SELECT next_attempt_at > clock_timestamp(), published_at FROM deployment_resume_receipts "
                    "WHERE deployment_id=%s", (deployment,),
                ).fetchone()
                if scheduled_retry:
                    assert published_at is None
                    conn.execute(
                        "UPDATE deployment_resume_receipts SET next_attempt_at=clock_timestamp() WHERE deployment_id=%s",
                        (deployment,),
                    )
            if scheduled_retry:
                break
            sleep(0.1)
        else:
            pytest.fail("key provider failure did not schedule another delivery attempt")

        deadline = monotonic() + 10
        while monotonic() < deadline:
            with shared_halt.transaction() as conn:
                published_at = conn.execute(
                    "SELECT published_at FROM deployment_resume_receipts WHERE deployment_id=%s",
                    (deployment,),
                ).fetchone()[0]
            if published_at is not None:
                break
            sleep(0.1)
        else:
            pytest.fail("restarted worker did not publish the pending audit receipt")
        assert request(recovery, "GET", "/v1/system/halt-status", executor)["halt_id"] == replacement["halt_id"]
        b.send(("audit", prepared["execution_intent_id"], None, None))
        entries = [entry for entry in _receive(b) if entry.get("resume_publication_id")]
        assert [entry["kind"] for entry in entries] == ["governance.execution_intent", "governance.bind_receipt"]
        assert entries[-1]["final_outcome"] == "COMMITTED"
        assert entries[-1]["bind_receipt_id"] == winner["bind_receipt_id"]

        request(a, "POST", url, executor, body, expected=404)
        assert request(a, "GET", "/v1/system/halt-status", executor)["halt_id"] == replacement["halt_id"]
        for label, worker in zip(("a", "b"), workers, strict=True):
            worker.send(("concurrent_log", label, None, None))
        assert all(_receive(worker) is True for worker in workers)
        b.send(("verify_log", None, None, None))
        verification = _receive(b)
        assert verification["ok"], verification

        _, next_body = approve_resume(a, b)
        a.send(("resume_with_delayed_key", url, executor, next_body))
        assert _receive(a) == "key provider blocked"
        try:
            request(b, "POST", "/v1/system/halt", executor,
                    {"operator": "fixture", "reason": "while key provider is blocked"})
            newer_halt = request(b, "GET", "/v1/system/halt-status", executor)
            assert newer_halt["halt_id"] != replacement["halt_id"]
        finally:
            release_key.set()
        code, response = _receive(a)
        assert code == 409, response
        assert request(a, "GET", "/v1/system/halt-status", executor)["halt_id"] == newer_halt["halt_id"]
