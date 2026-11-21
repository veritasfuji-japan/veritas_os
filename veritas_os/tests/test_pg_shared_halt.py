"""Two independently imported ASGI applications sharing a deployment halt."""
import json
import multiprocessing
import os
from contextlib import ExitStack, nullcontext
from time import monotonic, sleep
from unittest.mock import patch
from uuid import uuid4

import pytest


def _worker(pipe, barrier, release_audit, *, use_lifespan=False):
    from fastapi.testclient import TestClient
    from veritas_os.api import server
    from veritas_os.api.startup_health import initialize_system_halt_on_startup
    from veritas_os.core import shared_halt_audit
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

    def fail_after_insert(*args):
        queue(*args)
        raise RuntimeError("injected rollback before database commit")

    client = TestClient(server.app)
    if not use_lifespan:
        initialize_system_halt_on_startup()
    with pipe, client if use_lifespan else nullcontext():
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
                with patch.object(shared_halt_audit, "append_trust_log", pause_and_lose_ack):
                    pipe.send(shared_halt_audit.publish_next_resume_audit())
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
def test_two_processes_share_halt_approval_and_single_commit(monkeypatch, tmp_path):
    from veritas_os.api.auth import _derive_api_user_id
    from veritas_os.core import shared_halt
    from veritas_os.logging.encryption import generate_key
    from veritas_os.security.signing import store_keypair

    executor, reviewer = uuid4().hex, uuid4().hex
    private, public = store_keypair(tmp_path / "approval.key", tmp_path / "approval.pub")
    deployment = uuid4().hex
    for name, value in {
        "VERITAS_ENV": "test", "VERITAS_POSTURE": "dev",
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

    def request(worker, method, path, credential, body=None, expected=200):
        worker.send((method, path, credential, body))
        code, response = _receive(worker)
        assert code == expected, response
        return response

    ctx = multiprocessing.get_context("spawn")
    barrier = ctx.Barrier(2)
    release_audit = ctx.Event()
    with ExitStack() as cleanup:
        def start_worker(*, use_lifespan=False):
            parent, child = ctx.Pipe()
            proc = ctx.Process(target=_worker, args=(child, barrier, release_audit),
                               kwargs={"use_lifespan": use_lifespan})
            proc.start()
            child.close()
            cleanup.callback(_stop, proc, parent)
            assert _receive(parent) == proc.pid
            return parent

        a, b = workers = [start_worker(), start_worker()]
        request(a, "POST", "/v1/system/halt", executor, {"operator": "fixture", "reason": "test"})
        halt = request(a, "GET", "/v1/system/halt-status", executor)
        assert halt["halted"] and halt["reason"] == "test"
        assert request(b, "GET", "/v1/system/halt-status", executor)["halt_id"] == halt["halt_id"]
        blocked = request(b, "POST", "/v1/decide", executor, {"query": "blocked"}, expected=503)
        assert blocked["status"] == "HALTED"
        url = "/v1/system/resume"
        prepared = request(a, "POST", url + "/prepare", executor)
        review = url + "/requests/" + prepared["request_id"]
        approval = request(b, "GET", review, reviewer)
        assert approval["preparation"] == prepared
        artifact = request(b, "POST", review + "/approve", reviewer,
                           {"decision": "approve", "context_hash": approval["context_hash"]})
        body = {"operator": "fixture", "request_id": prepared["request_id"], "approval_artifact": artifact}
        request(a, "failed_queue", url, executor, body, expected=500)
        assert request(b, "GET", "/v1/system/halt-status", executor)["halt_id"] == halt["halt_id"]
        blocked = request(b, "POST", "/v1/decide", executor, {"query": "blocked"}, expected=503)
        assert blocked["status"] == "HALTED"
        a.send(("audit", prepared["execution_intent_id"], None, None))
        assert not _receive(a)
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

        a.send(("publish_with_lost_ack", None, None, None))
        assert _receive(a) == "audit blocked"
        try:
            request(b, "POST", "/v1/system/halt", executor,
                    {"operator": "fixture", "reason": "replacement"})
            replacement = request(b, "GET", "/v1/system/halt-status", executor)
            assert replacement["halt_id"] != halt["halt_id"]
        finally:
            release_audit.set()
        assert _receive(a) is True
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
        entries = _receive(b)
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
