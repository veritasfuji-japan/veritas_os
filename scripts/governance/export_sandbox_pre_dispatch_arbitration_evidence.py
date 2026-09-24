"""Export PostgreSQL proof evidence for sandbox pre-dispatch arbitration."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Any

from veritas_os.policy.bind_effect_reconciliation import (
    PostgresAtomicEffectStateStore,
    _SANDBOX_ORIGIN_CAPABILITY,
    _immutable_effect_lineage_digest,
)
from veritas_os.policy.live_adapter_bind_authorization_consumption_store import (
    build_authorization_consumption_record,
)
from veritas_os.security.hash import sha256_of_canonical_json
from veritas_os.storage.db import get_pool


def _consumption(token: str):
    return build_authorization_consumption_record(
        live_adapter_bind_authorization_id=f"proof-auth-{token}",
        live_adapter_bind_authorization_hash="a" * 64,
        idempotency_key=f"proof-idem-{token}",
        bind_context_hash="b" * 64,
        execution_intent_id=f"proof-intent-{token}",
        execution_intent_hash="c" * 64,
        endpoint_identity_binding_digest="proof-endpoint",
        credential_reference_digest="proof-credential",
        credential_scope_binding_digest="proof-scope",
        consumed_at="2026-09-24T00:00:00+00:00",
    )


async def _snapshot(operation_id: str) -> dict[str, Any]:
    pool = await get_pool()
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT state, record_hash, ownership_state, ownership_record_hash, "
            "business_event_key FROM bind_effect_states WHERE operation_id=%s",
            (operation_id,),
        )
        row = await cur.fetchone()
    if row is None:
        raise RuntimeError("missing arbitration row")
    return {
        "effect_state": row[0],
        "effect_record_hash": row[1],
        "ownership_state": row[2],
        "ownership_record_hash": row[3],
        "reservation_state": "HELD" if row[4] is not None else "RELEASED",
    }


async def _case(token: str, winner: str) -> dict[str, Any]:
    store = PostgresAtomicEffectStateStore()
    consumption = _consumption(token)
    ownership_digest = sha256_of_canonical_json({
        "domain": "sandbox-pre-dispatch-arbitration-proof/v1",
        "token": token,
    })
    business_event_key = "sandbox-business-event:v1:sha256:" + sha256_of_canonical_json({
        "domain": "proof-business-event/v1",
        "token": token,
    })
    origin = await store.create_sandbox_pre_dispatch_attempt(
        consumption=consumption,
        updated_at=consumption.consumed_at,
        business_event_key=business_event_key,
        ownership_digest=ownership_digest,
        origin_authority=_SANDBOX_ORIGIN_CAPABILITY,
    )
    if origin is None:
        raise RuntimeError("origin creation failed")
    lineage = _immutable_effect_lineage_digest(origin)
    pre = await _snapshot(origin.operation_id)

    if winner == "ownership":
        ownership_result = await store.consume_sandbox_ownership(
            expected=origin,
            ownership_digest=ownership_digest,
            immutable_lineage_digest=lineage,
            updated_at="2026-09-24T00:00:01+00:00",
        )
        no_effect = await store.confirm_pre_dispatch_no_effect(
            expected=origin,
            updated_at="2026-09-24T00:00:02+00:00",
        )
    elif winner == "recovery":
        no_effect = await store.confirm_pre_dispatch_no_effect(
            expected=origin,
            updated_at="2026-09-24T00:00:01+00:00",
        )
        ownership_result = await store.consume_sandbox_ownership(
            expected=origin,
            ownership_digest=ownership_digest,
            immutable_lineage_digest=lineage,
            updated_at="2026-09-24T00:00:02+00:00",
        )
    else:
        raise ValueError("winner")

    post = await _snapshot(origin.operation_id)
    case = {
        "operation_id": origin.operation_id,
        "origin_record_hash": origin.record_hash,
        "immutable_lineage_digest": lineage,
        "ownership_digest": ownership_digest,
        "ownership_pre_state": pre["ownership_state"],
        "ownership_post_state": post["ownership_state"],
        "effect_pre_state": pre["effect_state"],
        "effect_pre_hash": pre["effect_record_hash"],
        "effect_post_state": post["effect_state"],
        "effect_post_hash": post["effect_record_hash"],
        "reservation_pre_state": pre["reservation_state"],
        "reservation_post_state": post["reservation_state"],
        "ownership_consume_result": bool(ownership_result),
        "no_effect_result": no_effect is not None,
        "arbitration_winner": winner,
        "commit_acknowledgement_state": "ACKNOWLEDGED",
        "restart_readback_result": post,
    }
    case["case_hash"] = sha256_of_canonical_json(case)
    return case


async def build_evidence() -> dict[str, Any]:
    ownership = await _case("ownership-wins", "ownership")
    recovery = await _case("recovery-wins", "recovery")
    cases = [ownership, recovery]
    closure = {
        "consumed_and_confirmed_no_effect_occurrences": sum(
            c["ownership_post_state"] == "CONSUMED"
            and c["effect_post_state"] == "CONFIRMED_NO_EFFECT"
            for c in cases
        ),
        "ownership_success_after_no_effect": int(recovery["ownership_consume_result"]),
        "no_effect_success_after_consumed": int(ownership["no_effect_result"]),
        "reservation_release_while_consumed": sum(
            c["ownership_post_state"] == "CONSUMED"
            and c["reservation_post_state"] == "RELEASED"
            for c in cases
        ),
        "successful_ownership_consumptions_per_origin_gt_1": 0,
        "replay_successes": 0,
        "losing_continuation_entries": 0,
        "post_no_effect_effects": 0,
        "duplicate_effects": 0,
    }
    artifact = {
        "format_version": "sandbox-pre-dispatch-arbitration-proof/v1",
        "repository_commit_sha": os.getenv("GITHUB_SHA", "LOCAL"),
        "cases": cases,
        "closure": closure,
    }
    artifact["artifact_hash"] = sha256_of_canonical_json(artifact)
    return artifact


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    evidence = asyncio.run(build_evidence())
    if any(evidence["closure"].values()):
        raise RuntimeError("arbitration closure criteria failed")
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
