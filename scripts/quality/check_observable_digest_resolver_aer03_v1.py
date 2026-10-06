#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "security/observable_digest_resolver_aer03_named_target_caller_v1.json"
CONSUMER = ROOT / "veritas_os/audit/observable_digest_evidence_consumer.py"
REPORT = ROOT / "artifacts/observable-digest-resolver-aer03-v1/proof-report.json"

EXPECTED = {
    "target_id": "RESOLVER_EVIDENCE_ONLY_ACTIVATION_V1",
    "caller_module": "veritas_os.audit.observable_digest_evidence_consumer",
    "caller_component": "ObservableDigestEvidenceConsumerV1",
    "caller_role": "EVIDENCE_ONLY",
    "caller_identity": "veritas_os.audit.observable_digest_evidence_consumer:ObservableDigestEvidenceConsumerV1",
    "resolver_profile": "separate_store_readonly_v1",
    "namespace_scope": "wat_observables",
    "locator_prefix": "separate_store://wat_observables/",
    "activation_configuration_id": "observable_digest_evidence_only_activation_v1",
    "default_enabled": False,
}

def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    target = manifest["target"]
    caller_hash = "sha256:" + hashlib.sha256(EXPECTED["caller_identity"].encode("utf-8")).hexdigest()
    source = CONSUMER.read_text(encoding="utf-8")
    forbidden = (
        "from veritas_os.audit.observable_digest_resolver import",
        "import veritas_os.audit.observable_digest_resolver",
        "resolve_separate_store_readonly_v1(",
        "SeparateStoreReadonlyProfile(",
    )
    invariants = {
        "exact_target_and_caller_frozen": all(target.get(k) == v for k, v in EXPECTED.items()),
        "caller_hash_derivation_frozen": target.get("caller_id_hash_derivation") == "sha256(UTF-8 exact caller_identity)",
        "namespace_matches_resolver_segment_grammar": target.get("namespace_scope") == "wat_observables",
        "locator_prefix_is_separate_store_namespace": target.get("locator_prefix") == "separate_store://wat_observables/",
        "default_disabled": target.get("default_enabled") is False,
        "evidence_only_role": target.get("caller_role") == "EVIDENCE_ONLY",
        "named_caller_has_no_resolver_wiring": not any(token in source for token in forbidden),
        "all_forbidden_semantics_remain_false": all(v is False for v in manifest["forbidden_semantics"].values()),
        "manifest_non_authorizing": manifest.get("status") == "DEFINED_NOT_AUTHORIZED_NOT_ACTIVATED",
    }
    passed = all(invariants.values())
    report = {
        "proof_scope": "AER-03_NAMED_ACTIVATION_TARGET_CALLER_V1",
        "tested_sha": subprocess.check_output(["git","rev-parse","HEAD"], cwd=ROOT, text=True).strip(),
        "result": "PASS" if passed else "FAIL",
        "proof_status": "PENDING_INDEPENDENT_CLOSURE" if passed else "NOT_PROVEN",
        "target": target,
        "derived_caller_id_hash": caller_hash,
        "invariants": invariants,
        "non_claims": [
            "This proof does not authorize, approve, or perform activation.",
            "This proof does not add resolver runtime wiring.",
            "This proof does not create Authority, Human Approval, Bind authorization, or execution permission.",
            "This proof does not authorize any effect-bearing path.",
            "AER-04 and later activation-evidence gates remain separate."
        ],
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if passed else 1

if __name__ == "__main__":
    raise SystemExit(main())
