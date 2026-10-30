#!/usr/bin/env python3
"""Offline draft schema / references / local hash / basic logical consistency check.

NOT a trust chain check, a signature verifier, an execution test or an auditor.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "schemas/veritas_audit_evidence_profile_v0_1.schema.json"


def verify(obj, profile_path):
    errors = []
    schema = json.loads(SCHEMA.read_text())
    for e in Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(obj):
        errors.append(f"SCHEMA {list(e.absolute_path)}: {e.message}")
    if errors:
        return errors
    evidence, cases, controls, metrics = (obj[k] for k in ("evidence", "cases", "controls", "metrics"))
    eids = [x["id"] for x in evidence]
    cids = [x["case_id"] for x in cases]
    control_ids = [x["control_id"] for x in controls]
    if len(set(eids)) != len(eids):
        errors.append("DUPLICATE_EVIDENCE_ID")
    if len(set(cids)) != len(cids):
        errors.append("DUPLICATE_CASE_ID")
    if len(set(control_ids)) != len(control_ids):
        errors.append("DUPLICATE_CONTROL_ID")
    base = profile_path.resolve().parent
    for e in evidence:
        p = Path(e["relative_path"])
        if p.is_absolute() or ".." in p.parts:
            errors.append(f'UNSAFE_EVIDENCE_PATH:{e["id"]}')
            continue
        file = (base / p).resolve()
        parts = [base / p, *(base.joinpath(*p.parts[:i]) for i in range(1, len(p.parts)))]
        if any(part.is_symlink() for part in parts):
            errors.append(f'SYMLINK_EVIDENCE_PATH:{e["id"]}')
        elif not file.is_relative_to(base):
            errors.append(f'EVIDENCE_PATH_ESCAPE:{e["id"]}')
        elif not file.is_file():
            errors.append(f'MISSING_EVIDENCE_BYTES:{e["id"]}')
        elif hashlib.sha256(file.read_bytes()).hexdigest() != e["sha256"]:
            errors.append(f'EVIDENCE_HASH_MISMATCH:{e["id"]}')
    for c in cases:
        for x in c["evidence_ids"]:
            if x not in eids:
                errors.append(f'UNRESOLVED_CASE_EVIDENCE:{c["case_id"]}:{x}')
        if c["observed"] == "NOT_TESTED" and c["actual_effect"] not in ("NOT_EXECUTED", "UNKNOWN"):
            errors.append(f'NOT_TESTED_HAS_EFFECT:{c["case_id"]}')
        if c["observed"] in ("PASS", "FAIL") and c["actual_effect"] in ("NOT_EXECUTED", "UNKNOWN"):
            errors.append(f'OBSERVED_WITHOUT_EFFECT:{c["case_id"]}')
        if c["observed"] in ("NOT_TESTED", "NOT_APPLICABLE") and c["actual_effect"] not in ("NOT_EXECUTED", "UNKNOWN"):
            errors.append(f'UNOBSERVED_WITH_EFFECT:{c["case_id"]}')
        if not obj["scope"]["execution_performed"] and c["observed"] not in ("NOT_TESTED", "NOT_APPLICABLE"):
            errors.append(f'UNEXECUTED_CASE_VERDICT:{c["case_id"]}')
    for ctrl in controls:
        for x in ctrl["test_case_ids"]:
            if x not in cids:
                errors.append(f'UNRESOLVED_CONTROL_CASE:{ctrl["control_id"]}:{x}')
        for x in ctrl["supporting_evidence_ids"]:
            if x not in eids:
                errors.append(f'UNRESOLVED_CONTROL_EVIDENCE:{ctrl["control_id"]}:{x}')
        if ctrl["verdict"] == "PASS" and (
            not ctrl["test_case_ids"] or not ctrl["supporting_evidence_ids"] or
            any(next((case["observed"] != "PASS" for case in cases if case["case_id"] == x), True)
                for x in ctrl["test_case_ids"])
        ):
            errors.append(f'UNSUPPORTED_CONTROL_PASS:{ctrl["control_id"]}')
    for m in metrics:
        if m["measurement_status"] == "MEASURED":
            if (not obj["scope"]["execution_performed"] or
                any(m[x] is None for x in ("numerator", "denominator", "source_run_id")) or
                m["denominator"] == 0 or m["numerator"] > m["denominator"]):
                errors.append(f'INVALID_MEASURED_METRIC:{m["metric_id"]}')
        elif m["numerator"] is not None or m["denominator"] is not None:
            errors.append(f'UNMEASURED_METRIC_HAS_COUNTS:{m["metric_id"]}')
    rev = obj["review"]
    if obj["synthetic_example"] and (
        rev["handoff_status"] == "REVIEWABLE" or rev["reviewer_verdict"] == "ACCEPT"
    ):
        errors.append("SYNTHETIC_EXAMPLE_PROMOTED")
    # This format contains only assertions, not authenticated external review evidence.
    # Reject elevated reviewer/handoff claims until an independent verifier is wired in.
    if rev["handoff_status"] == "REVIEWABLE":
        errors.append("UNVERIFIED_REVIEWABLE_HANDOFF")
    if rev["reviewer_verdict"] == "ACCEPT":
        errors.append("UNVERIFIED_REVIEWER_ACCEPTANCE")
    if rev["handoff_status"] == "REVIEWABLE" and (
        not obj["scope"]["execution_performed"] or
        any(c["verdict"] not in ("PASS", "FAIL", "NOT_APPLICABLE") for c in controls) or
        rev["reviewer_verdict"] == "NOT_REVIEWED"
    ):
        errors.append("UNSUPPORTED_REVIEWABLE_HANDOFF")
    if rev["reviewer_verdict"] == "ACCEPT" and (
        rev["reviewer_independence"] != "EXTERNAL" or
        rev["trusted_key_provenance"] == "NOT_ESTABLISHED"
    ):
        errors.append("ACCEPT_WITHOUT_EXTERNAL_REVIEW_OR_TRUST")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", type=Path)
    a = parser.parse_args()
    try:
        obj = json.loads(a.profile.read_text())
        errors = verify(obj, a.profile)
    except (OSError, ValueError, KeyError, TypeError) as e:
        print("FAIL: cannot read input:", e, file=sys.stderr)
        return 2
    if errors:
        print("FAIL (structural / local checks only):")
        print("\n".join(f"- {e}" for e in errors))
        return 1
    print("PASS: schema, local hashes and declared references consistent.")
    print("NO runtime, signature, independent trust, control-effectiveness or ISO assessment was performed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
