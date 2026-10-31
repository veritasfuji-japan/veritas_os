#!/usr/bin/env python3
"""Offline draft schema / references / local hash / basic logical consistency check.

NOT a trust chain check, a signature verifier, an execution test or an auditor.
"""
import argparse
import errno
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "schemas/veritas_audit_evidence_profile_v0_1.schema.json"


# Limit disk I/O and memory use when processing untrusted local evidence.
MAX_EVIDENCE_BYTES = 16 * 1024 * 1024


def _hash_evidence_file(base, relative_path):
    """Hash a regular file beneath base using no-follow, directory-relative fds.

    Each directory component is opened relative to an already-open directory.
    This prevents symlink traversal and parent-directory replacement from
    redirecting reads outside the evidence root on supported POSIX platforms.
    The final descriptor is checked before and after bounded streaming.
    """
    components = relative_path.split("/")
    if (not components or any(part in ("", ".", "..") for part in components)
            or "\\" in relative_path or Path(relative_path).is_absolute()):
        return None, "UNSAFE_EVIDENCE_PATH"
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        return None, "UNSUPPORTED_SAFE_FILE_OPEN"
    dir_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    file_flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0)
    dir_fd = None
    file_fd = None
    try:
        dir_fd = os.open(base, dir_flags)
        for component in components[:-1]:
            next_fd = os.open(component, dir_flags, dir_fd=dir_fd)
            os.close(dir_fd)
            dir_fd = next_fd
        file_fd = os.open(components[-1], file_flags, dir_fd=dir_fd)
        before = os.fstat(file_fd)
        if not stat.S_ISREG(before.st_mode):
            return None, "NONREGULAR_EVIDENCE_FILE"
        if before.st_size > MAX_EVIDENCE_BYTES:
            return None, "EVIDENCE_FILE_TOO_LARGE"
        digest = hashlib.sha256()
        size = 0
        while True:
            block = os.read(file_fd, 65536)
            if not block:
                break
            size += len(block)
            if size > MAX_EVIDENCE_BYTES:
                return None, "EVIDENCE_FILE_TOO_LARGE"
            digest.update(block)
        after = os.fstat(file_fd)
        if (size != before.st_size or before.st_size != after.st_size
                or before.st_mtime_ns != after.st_mtime_ns
                or before.st_ctime_ns != after.st_ctime_ns):
            return None, "EVIDENCE_CHANGED_DURING_READ"
        return digest.hexdigest(), None
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            return None, "SYMLINK_EVIDENCE_PATH"
        if exc.errno == errno.ENOENT:
            return None, "MISSING_EVIDENCE_BYTES"
        return None, "UNREADABLE_EVIDENCE_BYTES"
    finally:
        if file_fd is not None:
            os.close(file_fd)
        if dir_fd is not None:
            os.close(dir_fd)


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
        digest, issue = _hash_evidence_file(base, e["relative_path"])
        if issue:
            errors.append(f'{issue}:{e["id"]}')
        elif digest != e["sha256"]:
            errors.append(f'EVIDENCE_HASH_MISMATCH:{e["id"]}')
    # Local hashing cannot authenticate origin or independent trust. Do not
    # accept self-asserted VERIFIED statuses as independent verification.
    for e in evidence:
        if e["authenticity_status"] == "VERIFIED" or e["independent_trust_status"] == "VERIFIED":
            errors.append(f'UNSUPPORTED_TRUST_CLAIM:{e["id"]}')
    for c in cases:
        for x in c["evidence_ids"]:
            if x not in eids:
                errors.append(f'UNRESOLVED_CASE_EVIDENCE:{c["case_id"]}:{x}')
        if c["observed"] == "PASS" and not (
            (c["expectation"] == "ALLOW" and c["actual_effect"] == "ALLOWED")
            or (c["expectation"] == "DENY" and c["actual_effect"] == "DENIED")
        ):
            errors.append(f'INCONSISTENT_CASE_PASS:{c["case_id"]}')
        if c["observed"] == "UNKNOWN" and c["actual_effect"] not in ("NOT_EXECUTED", "UNKNOWN"):
            errors.append(f'UNKNOWN_OBSERVATION_HAS_EFFECT:{c["case_id"]}')
        if c["observed"] == "NOT_TESTED" and c["actual_effect"] not in ("NOT_EXECUTED", "UNKNOWN"):
            errors.append(f'NOT_TESTED_HAS_EFFECT:{c["case_id"]}')
        if c["observed"] in ("PASS", "FAIL") and c["actual_effect"] in ("NOT_EXECUTED", "UNKNOWN"):
            errors.append(f'OBSERVED_WITHOUT_EFFECT:{c["case_id"]}')
        if c["observed"] in ("NOT_TESTED", "NOT_APPLICABLE") and c["actual_effect"] not in ("NOT_EXECUTED", "UNKNOWN"):
            errors.append(f'UNOBSERVED_WITH_EFFECT:{c["case_id"]}')
        if not obj["scope"]["execution_performed"] and c["actual_effect"] not in ("NOT_EXECUTED", "UNKNOWN"):
            errors.append(f'UNEXECUTED_SCOPE_HAS_EFFECT:{c["case_id"]}')
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
