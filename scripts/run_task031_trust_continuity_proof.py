#!/usr/bin/env python3
"""Generate deterministic TASK-031 frozen-corpus proof artifacts.

The runtime evaluator receives only the scenario observation. Offline expected
labels are consulted only after the runtime result has been produced.

This is a synthetic, controlled, side-effect-free proof harness. It does not
claim production DR, live IAM/KMS/HSM trust, customer credential correctness,
or third-party certification.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable

from veritas_os.policy.post_compromise_trust_continuity import (
    RecoveryTrustState,
    TrustContinuityObservation,
    evaluate_post_compromise_trust,
)
from veritas_os.security.hash import sha256_of_canonical_json

PROOF_FORMAT = "task031-post-compromise-trust-continuity-proof/v1"
PROTOCOL_VERSION = "task031-frozen-corpus/v1"
SNAPSHOT_ID = "snapshot:task031:proof-v1"


def _base(**updates: Any) -> TrustContinuityObservation:
    values: dict[str, Any] = {
        "snapshot_id": SNAPSHOT_ID,
        "historical_trust_generation": 41,
        "current_trust_generation": 41,
        "observation_generation": 41,
        "authority_state": "VALID",
        "credential_state": "VALID",
        "credential_material_source": "CURRENT_PROVIDER",
        "policy_state": "ADMISSIBLE",
        "human_approval_required": True,
        "human_approval_state": "VERIFIED",
        "action_binding_state": "CURRENT",
        "external_effect_state": "NONE",
        "historical_authorization_present": True,
        "historical_authorization_consumed": True,
        "historical_authorization_reuse_attempted": False,
    }
    values.update(updates)
    return TrustContinuityObservation(**values)


# Runtime case builders intentionally contain no expected result labels.
RUNTIME_CASES: dict[str, Callable[[], TrustContinuityObservation]] = {
    "T31-01": lambda: _base(),
    "T31-02": lambda: _base(credential_state="REVOKED"),
    "T31-03": lambda: _base(authority_state="REVOKED"),
    "T31-04": lambda: _base(human_approval_state="EXPIRED"),
    "T31-05": lambda: _base(
        current_trust_generation=42,
        observation_generation=42,
        credential_material_source="HISTORICAL_SNAPSHOT",
    ),
    "T31-06": lambda: _base(
        current_trust_generation=42,
        observation_generation=41,
    ),
    "T31-07": lambda: _base(authority_state="UNAVAILABLE"),
    "T31-08": lambda: _base(policy_state="DENIED"),
    "T31-09": lambda: _base(
        current_trust_generation=42,
        observation_generation=42,
        historical_authorization_reuse_attempted=True,
    ),
    "T31-10": lambda: _base(
        current_trust_generation=42,
        observation_generation=42,
    ),
}


# Offline oracle. This table is never passed into evaluate_post_compromise_trust.
EXPECTED_AFTER_RUNTIME: dict[str, tuple[RecoveryTrustState, str, bool]] = {
    "T31-01": (
        RecoveryTrustState.TRUST_REVALIDATED,
        "PTC_TRUST_REVALIDATED_NEW_AUTHORIZATION_REQUIRED",
        True,
    ),
    "T31-02": (
        RecoveryTrustState.TRUST_INVALID,
        "PTC_CREDENTIAL_NOT_CURRENT",
        False,
    ),
    "T31-03": (
        RecoveryTrustState.TRUST_INVALID,
        "PTC_AUTHORITY_NOT_CURRENT",
        False,
    ),
    "T31-04": (
        RecoveryTrustState.TRUST_INVALID,
        "PTC_APPROVAL_NOT_CURRENT",
        False,
    ),
    "T31-05": (
        RecoveryTrustState.TRUST_INVALID,
        "PTC_CREDENTIAL_SOURCE_NOT_CURRENT",
        False,
    ),
    "T31-06": (
        RecoveryTrustState.TRUST_NOT_REVALIDATED,
        "PTC_OBSERVATION_GENERATION_STALE",
        False,
    ),
    "T31-07": (
        RecoveryTrustState.TRUST_INVALID,
        "PTC_AUTHORITY_NOT_CURRENT",
        False,
    ),
    "T31-08": (
        RecoveryTrustState.TRUST_INVALID,
        "PTC_POLICY_NOT_CURRENT",
        False,
    ),
    "T31-09": (
        RecoveryTrustState.TRUST_INVALID,
        "PTC_HISTORICAL_AUTHORIZATION_REUSE_REJECTED",
        False,
    ),
    "T31-10": (
        RecoveryTrustState.TRUST_REVALIDATED,
        "PTC_TRUST_REVALIDATED_NEW_AUTHORIZATION_REQUIRED",
        True,
    ),
}


def _load_freeze(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("format_version") != "post-compromise-trust-state-continuity-freeze/v1":
        raise RuntimeError("TASK031_FREEZE_FORMAT_MISMATCH")
    ids = [item["id"] for item in data.get("initial_scenarios", [])]
    if ids != list(RUNTIME_CASES):
        raise RuntimeError("TASK031_FREEZE_SCENARIO_SET_MISMATCH")
    return data


def build_proof(freeze_path: Path) -> dict[str, Any]:
    freeze = _load_freeze(freeze_path)
    frozen_by_id = {item["id"]: item for item in freeze["initial_scenarios"]}

    runtime_records: list[dict[str, Any]] = []
    # Runtime phase: no expected labels are looked up inside this loop before
    # the evaluator has returned.
    for case_id, builder in RUNTIME_CASES.items():
        observation = builder()
        result = evaluate_post_compromise_trust(observation)
        runtime_records.append(
            {
                "case_id": case_id,
                "snapshot_identity": observation.snapshot_id,
                "historical_trust_generation": observation.historical_trust_generation,
                "current_trust_generation": observation.current_trust_generation,
                "observation_generation": observation.observation_generation,
                "authority_revocation_observation": observation.authority_state,
                "credential_reference_and_non_secret_resolution_evidence": {
                    "credential_state": observation.credential_state,
                    "credential_material_source": observation.credential_material_source,
                    "raw_secret_present": False,
                },
                "policy_state": observation.policy_state,
                "human_approval_state": observation.human_approval_state,
                "authorization_identity_and_consumption_state": {
                    "historical_authorization_present": observation.historical_authorization_present,
                    "historical_authorization_consumed": observation.historical_authorization_consumed,
                    "historical_authorization_reuse_attempted": observation.historical_authorization_reuse_attempted,
                    "historical_authorization_reusable": result.historical_authorization_reusable,
                },
                "unresolved_external_effect_state": observation.external_effect_state,
                "recovery_classification": result.state.value,
                "allow_block_reason_code": result.reason_code,
                "new_authorization_eligible": result.new_authorization_eligible,
                "external_effect_retry_permitted": result.external_effect_retry_permitted,
                "runtime_record_hashes": {
                    "observation_hash": result.observation_hash,
                    "result_hash": result.result_hash,
                },
                "reconciliation_evidence_if_used": None,
            }
        )

    # Offline scoring phase begins only after all runtime results exist.
    scored: list[dict[str, Any]] = []
    for record in runtime_records:
        case_id = record["case_id"]
        expected_state, expected_reason, expected_eligible = EXPECTED_AFTER_RUNTIME[case_id]
        matched = (
            record["recovery_classification"] == expected_state.value
            and record["allow_block_reason_code"] == expected_reason
            and record["new_authorization_eligible"] is expected_eligible
        )
        scored.append(
            {
                **record,
                "frozen_name": frozen_by_id[case_id]["name"],
                "frozen_expected": frozen_by_id[case_id]["expected"],
                "offline_expected_runtime_state": expected_state.value,
                "offline_expected_reason_code": expected_reason,
                "offline_expected_new_authorization_eligible": expected_eligible,
                "matched": matched,
            }
        )

    all_matched = all(item["matched"] for item in scored)
    proof_body = {
        "format_version": PROOF_FORMAT,
        "protocol_version": PROTOCOL_VERSION,
        "proof_scope": freeze["proof_scope"],
        "freeze_status": freeze["status"],
        "scenario_count": len(scored),
        "offline_oracle_applied_after_runtime": True,
        "runtime_received_expected_labels": False,
        "all_scenarios_matched": all_matched,
        "scenarios": scored,
        "explicit_non_claims": freeze["explicit_non_claims"],
        "claim_boundary": {
            "synthetic_controlled_corpus": True,
            "side_effect_free": True,
            "production_disaster_recovery": False,
            "live_customer_iam_kms_hsm": False,
            "live_customer_credentials": False,
            "third_party_certification": False,
            "regulatory_approval": False,
        },
    }
    return {
        **proof_body,
        "proof_hash": sha256_of_canonical_json(proof_body),
    }


def write_proof(output_dir: Path, freeze_path: Path) -> dict[str, Any]:
    proof = build_proof(freeze_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "corpus-results.json").write_text(
        json.dumps(proof, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    summary_body = {
        "format_version": "task031-proof-summary/v1",
        "protocol_version": proof["protocol_version"],
        "scenario_count": proof["scenario_count"],
        "matched_count": sum(1 for item in proof["scenarios"] if item["matched"]),
        "all_scenarios_matched": proof["all_scenarios_matched"],
        "runtime_received_expected_labels": proof["runtime_received_expected_labels"],
        "offline_oracle_applied_after_runtime": proof["offline_oracle_applied_after_runtime"],
        "historical_authorization_reusable_in_any_case": any(
            item["authorization_identity_and_consumption_state"][
                "historical_authorization_reusable"
            ]
            for item in proof["scenarios"]
        ),
        "external_effect_retry_permitted_in_any_case": any(
            item["external_effect_retry_permitted"] for item in proof["scenarios"]
        ),
        "proof_hash": proof["proof_hash"],
    }
    summary = {
        **summary_body,
        "summary_hash": sha256_of_canonical_json(summary_body),
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return {"proof": proof, "summary": summary}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--freeze",
        type=Path,
        default=Path(
            "docs/architecture/post-compromise-trust-state-continuity-freeze-v1.json"
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/task031-trust-continuity-proof"),
    )
    args = parser.parse_args()
    bundle = write_proof(args.output_dir, args.freeze)
    if not bundle["summary"]["all_scenarios_matched"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
