"""Run the VERITAS / CAGE Phase 5C BindReceipt and evidence-flow proof.

The proof uses the real, source-pinned CAGE Provider03 client. It obtains an
APPROVED VERITAS result over loopback HTTP, carries the VERITAS BindReceipt in
the Provider03 findings, computes the CAGE JCS/SHA-256 ingest digest with the
real ingest_bind_receipt() extension, and submits that digest back through
the real Provider03 submit_evidence() HTTP path.

The proof deliberately keeps the VERITAS BindReceipt self-hash, the CAGE ingest
hash, and the returned evidence seal in separate hash domains. It does not
claim that the CAGE ingest digest is a signature, authority artifact,
persistence receipt, or authenticity proof.
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import importlib
import json
import sys
from pathlib import Path
from typing import Any, Final

from veritas_os.governance.cage_provider03_phase5a_runtime import PHASE5A_PROOF_ID
from veritas_os.security.hash import sha256_of_canonical_json

PHASE5C_PROOF_ID: Final[str] = "veritas-cage-provider03-phase5c-bind-evidence-v1"
APPROVED_SCENARIO: Final[str] = "scenario_a_allowed_internal_escalation"
REJECTED_SCENARIO: Final[str] = "scenario_b_prohibited_account_freeze"
FIELD_MAP: Final[dict[str, str]] = {"amount": "magnitude", "symbol": "context"}


def _jsonable(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return dataclasses.asdict(value)
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "__dict__"):
        return {str(key): _jsonable(item) for key, item in vars(value).items()}
    return value


def _load_cage_provider(cage_repo: Path):
    if not cage_repo.is_dir():
        raise RuntimeError(f"CAGE checkout not found: {cage_repo}")
    sys.path.insert(0, str(cage_repo))
    try:
        module = importlib.import_module("src.integrations.provider_03.provider")
    finally:
        try:
            sys.path.remove(str(cage_repo))
        except ValueError:
            pass
    return module, getattr(module, "Provider03NormativeProvider")


def extract_bind_receipt(validation_result: Any) -> dict[str, Any]:
    """Extract the VERITAS BindReceipt carried in an admitted Provider03 finding."""
    if getattr(validation_result, "admitted", False) is not True:
        raise RuntimeError("BindReceipt extraction requires an admitted Provider03 result")
    findings = getattr(validation_result, "findings", None) or []
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        receipt = finding.get("bind_receipt")
        if isinstance(receipt, dict):
            return dict(receipt)
    raise RuntimeError("admitted Provider03 result did not carry a BindReceipt")


def veritas_bind_receipt_hash_valid(receipt: dict[str, Any]) -> bool:
    """Verify the VERITAS receipt body-hash domain."""
    embedded = receipt.get("bind_receipt_hash")
    if not isinstance(embedded, str) or not embedded:
        return False
    body = {key: value for key, value in receipt.items() if key != "bind_receipt_hash"}
    return sha256_of_canonical_json(body) == embedded


def _findings_expose_bind_receipt(validation_result: Any) -> bool:
    findings = getattr(validation_result, "findings", None) or []
    return any(
        isinstance(finding, dict) and isinstance(finding.get("bind_receipt"), dict)
        for finding in findings
    )


async def _run(*, provider_cls: Any, endpoint: str, token: str) -> dict[str, Any]:
    provider = provider_cls(
        endpoint=endpoint,
        api_key=token,
        timeout=2.0,
        action_context_field_map=FIELD_MAP,
    )

    approved = await provider.validate_fria(
        {
            "action": "aml_kyc_regulated_action",
            "veritas_scenario_name": APPROVED_SCENARIO,
            "action_context": {"amount": 1000, "symbol": "acct"},
        }
    )
    if getattr(approved, "admitted", False) is not True:
        raise RuntimeError("Phase 5C approved scenario was not admitted")

    receipt = extract_bind_receipt(approved)
    if not veritas_bind_receipt_hash_valid(receipt):
        raise RuntimeError("VERITAS BindReceipt self-hash verification failed")

    veritas_receipt_hash = str(receipt["bind_receipt_hash"])
    cage_digest = provider.ingest_bind_receipt(receipt)
    replay_digest = provider.ingest_bind_receipt(dict(receipt))
    if cage_digest != replay_digest:
        raise RuntimeError("CAGE bind-receipt ingest digest is not deterministic")
    if len(cage_digest) != 64:
        raise RuntimeError("CAGE bind-receipt ingest digest is not SHA-256 hex")
    if cage_digest == veritas_receipt_hash:
        raise RuntimeError("VERITAS and CAGE receipt hash domains unexpectedly collapsed")

    tampered = dict(receipt)
    tampered["authority_evidence_id"] = f"{receipt.get('authority_evidence_id', '')}::tampered"
    tampered_digest = provider.ingest_bind_receipt(tampered)
    if tampered_digest == cage_digest:
        raise RuntimeError("CAGE digest did not change after BindReceipt tampering")
    if veritas_bind_receipt_hash_valid(tampered):
        raise RuntimeError("tampered receipt retained a valid VERITAS self-hash")

    thread_id = f"phase5c::{receipt['bind_receipt_id']}"
    evidence = await provider.submit_evidence(thread_id, cage_digest)
    if getattr(evidence, "error", None):
        raise RuntimeError(f"CAGE evidence submission failed: {evidence.error}")
    seal_hash = str(getattr(evidence, "seal_hash", "") or "")
    if not seal_hash:
        raise RuntimeError("CAGE evidence submission returned no seal hash")

    expected_seal_hash = sha256_of_canonical_json(
        {
            "phase5a_proof_id": PHASE5A_PROOF_ID,
            "thread_id": thread_id,
            "evidence_hash": cage_digest,
            "trustlog_proof_status": "lineage_only",
        }
    )
    if seal_hash != expected_seal_hash:
        raise RuntimeError("returned EvidenceSeal does not bind the submitted CAGE digest")

    rejected = await provider.validate_fria(
        {
            "action": "aml_kyc_regulated_action",
            "veritas_scenario_name": REJECTED_SCENARIO,
            "action_context": {"amount": 1000, "symbol": "acct"},
        }
    )
    if getattr(rejected, "admitted", True) is not False:
        raise RuntimeError("Phase 5C rejected scenario was unexpectedly admitted")
    if _findings_expose_bind_receipt(rejected):
        raise RuntimeError("non-admitted Provider03 result exposed a Phase 5C BindReceipt")

    checks = {
        "approved_runtime_result_admitted": True,
        "approved_result_carries_bind_receipt": True,
        "veritas_bind_receipt_self_hash_valid": True,
        "cage_ingest_digest_deterministic": cage_digest == replay_digest,
        "hash_domains_distinct": cage_digest != veritas_receipt_hash,
        "tamper_changes_cage_digest": tampered_digest != cage_digest,
        "tamper_invalidates_veritas_self_hash": not veritas_bind_receipt_hash_valid(tampered),
        "evidence_submission_succeeded": getattr(evidence, "error", None) is None,
        "evidence_seal_binds_cage_digest": seal_hash == expected_seal_hash,
        "rejected_result_non_admitted": getattr(rejected, "admitted", True) is False,
        "rejected_result_exposes_no_bind_receipt": not _findings_expose_bind_receipt(rejected),
    }
    blockers = sorted(key for key, passed in checks.items() if passed is not True)

    return {
        "phase5c_status": "READY_FOR_PHASE5D" if not blockers else "BLOCKED_PHASE5C",
        "phase5c_blockers": blockers,
        "checks": checks,
        "approved_validation": _jsonable(approved),
        "bind_receipt": receipt,
        "hash_domains": {
            "veritas_bind_receipt_hash": {
                "value": veritas_receipt_hash,
                "input": "VERITAS BindReceipt body before bind_receipt_hash insertion",
                "semantic": "VERITAS receipt self-integrity hash",
            },
            "cage_ingested_bind_receipt_digest": {
                "value": cage_digest,
                "input": "complete VERITAS BindReceipt including bind_receipt_hash",
                "semantic": "CAGE RFC 8785 JCS/SHA-256 canonical digest",
                "signature_claim": False,
                "authority_claim": False,
                "persistence_claim": False,
            },
        },
        "tamper_probe": {
            "tampered_cage_digest": tampered_digest,
            "cage_digest_changed": tampered_digest != cage_digest,
            "veritas_self_hash_valid_after_tamper": veritas_bind_receipt_hash_valid(tampered),
        },
        "evidence_flow": {
            "thread_id": thread_id,
            "submitted_evidence_hash": cage_digest,
            "evidence_seal": _jsonable(evidence),
            "expected_seal_hash": expected_seal_hash,
            "trustlog_proof_status": "lineage_only",
            "trustlog_witness_claim": False,
            "signature_verification_claim": False,
        },
        "rejected_validation": _jsonable(rejected),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cage-repo", type=Path, required=True)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--veritas-source-sha", required=True)
    parser.add_argument("--cage-source-sha", required=True)
    parser.add_argument("--phase5b-veritas-baseline", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    module, provider_cls = _load_cage_provider(args.cage_repo.resolve())
    report_body = asyncio.run(
        _run(
            provider_cls=provider_cls,
            endpoint=args.endpoint.rstrip("/"),
            token=args.token,
        )
    )

    report = {
        "format_version": "veritas-cage-phase5c-runtime/v1",
        "proof_id": PHASE5C_PROOF_ID,
        "veritas_source_sha": args.veritas_source_sha,
        "cage_source_sha": args.cage_source_sha,
        "phase5b_veritas_baseline": args.phase5b_veritas_baseline,
        "cage_provider03_module": str(Path(module.__file__).resolve()),
        "runtime_topology": (
            "real CAGE Provider03 validate -> loopback VERITAS -> BindReceipt finding -> "
            "real CAGE ingest_bind_receipt -> real CAGE submit_evidence -> loopback VERITAS"
        ),
        "real_cage_provider03_client": True,
        "real_cage_ingest_bind_receipt": True,
        "real_cage_submit_evidence": True,
        "loopback_http": True,
        "mocked_cage_http_client": False,
        "external_effects_executed": False,
        "production_claim": False,
        "google_endorsement_claim": False,
        "commercial_integration_claim": False,
        **report_body,
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    output_path = args.output_dir / "phase5c-runtime-report.json"
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\\n",
        encoding="utf-8",
    )
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
