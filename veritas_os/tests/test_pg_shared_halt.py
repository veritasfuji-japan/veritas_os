"""Two independently imported ASGI applications sharing a deployment halt."""
import json
import multiprocessing
import os
from contextlib import ExitStack
from uuid import uuid4

import pytest


def _worker(pipe, barrier):
    from fastapi.testclient import TestClient
    from veritas_os.api import server
    from veritas_os.api.startup_health import initialize_system_halt_on_startup
    from veritas_os.logging.trust_log import iter_trust_log

    initialize_system_halt_on_startup()
    with pipe:
        client = TestClient(server.app)
        pipe.send(os.getpid())
        while True:
            command = pipe.recv()
            if command is None:
                return
            method, path, credential, body = command
            if method == "audit":
                pipe.send([entry for entry in iter_trust_log()
                           if entry.get("kind") == "governance.bind_receipt"
                           and entry.get("execution_intent_id") == path])
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
    with ExitStack() as cleanup:
        workers = []
        for _ in range(2):
            parent, child = ctx.Pipe()
            proc = ctx.Process(target=_worker, args=(child, barrier))
            proc.start()
            child.close()
            cleanup.callback(_stop, proc, parent)
            assert _receive(parent) == proc.pid
            workers.append(parent)
        a, b = workers
        halt = request(a, "POST", "/v1/system/halt", executor, {"operator": "fixture", "reason": "test"})
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
        for worker in workers:
            worker.send(("race", url, executor, body))
        responses = [_receive(worker) for worker in workers]
        assert sum(code == 200 for code, _ in responses) == 1, responses
        assert all(code in {200, 404, 409} for code, _ in responses), responses
        winner = next(result for code, result in responses if code == 200)
        for worker in workers:
            assert request(worker, "GET", "/v1/system/halt-status", executor)["halted"] is False
        b.send(("audit", prepared["execution_intent_id"], None, None))
        commits = [entry for entry in _receive(b) if entry["final_outcome"] == "COMMITTED"]
        assert [entry["bind_receipt_id"] for entry in commits] == [winner["bind_receipt_id"]]
        from veritas_os.core import shared_halt
        with shared_halt.transaction() as conn:
            receipts = conn.execute(
                "SELECT receipt FROM deployment_resume_receipts WHERE deployment_id=%s AND halt_id=%s",
                (deployment, halt["halt_id"]),
            ).fetchall()
        assert [row[0]["bind_receipt_id"] for row in receipts] == [winner["bind_receipt_id"]]
        replacement = request(b, "POST", "/v1/system/halt", executor,
                              {"operator": "fixture", "reason": "replacement"})
        request(a, "POST", url, executor, body, expected=404)
        assert request(a, "GET", "/v1/system/halt-status", executor)["halt_id"] == replacement["halt_id"]
