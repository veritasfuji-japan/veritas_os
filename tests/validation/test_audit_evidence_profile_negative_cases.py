#!/usr/bin/env python3
import sys
import copy
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/validation"))
from validate_audit_evidence_profile import verify

p = ROOT / "tests/validation/fixtures/synthetic_example.json"
base = json.loads(p.read_text())
assert verify(base, p) == [], verify(base, p)
variants = {}
v = copy.deepcopy(base); v["cases"][0]["evidence_ids"] = ["NO-SUCH-EVIDENCE"]; variants["bad ref"] = v
v = copy.deepcopy(base); v["evidence"][0]["sha256"] = "f" * 64; variants["bad sha"] = v
v = copy.deepcopy(base); v["controls"][0]["verdict"] = "PASS"; variants["false pass"] = v
v = copy.deepcopy(base); v["review"]["handoff_status"] = "REVIEWABLE"; variants["fake handoff"] = v
v = copy.deepcopy(base); v["metrics"][0]["measurement_status"] = "MEASURED"; v["metrics"][0]["numerator"] = 0; v["metrics"][0]["denominator"] = 1; v["metrics"][0]["source_run_id"] = "run"; variants["fake measurement"] = v
v = copy.deepcopy(base); v["review"]["reviewer_verdict"] = "ACCEPT"; variants["fake acceptance"] = v
v = copy.deepcopy(base); v["synthetic_example"] = False; v["scope"]["execution_performed"] = True; v["review"]["handoff_status"] = "REVIEWABLE"; v["review"]["reviewer_verdict"] = "REJECT"; variants["self asserted handoff"] = v
v = copy.deepcopy(base); v["synthetic_example"] = False; v["review"]["reviewer_verdict"] = "ACCEPT"; v["review"]["reviewer_independence"] = "EXTERNAL"; v["review"]["trusted_key_provenance"] = "ESTABLISHED"; variants["self asserted external acceptance"] = v
v = copy.deepcopy(base); v["scope"]["execution_performed"] = True; v["cases"][0]["observed"] = "PASS"; variants["observed without effect"] = v
v = copy.deepcopy(base); v["cases"][0]["actual_effect"] = "ALLOWED"; variants["unobserved with effect"] = v
for name, v in variants.items():
    issues = verify(v, p)
    assert issues, f"negative test falsely accepted: {name}"
    print(name, "REJECTED:", issues[0])
print("PASS: base and all", len(variants), "negative tests.")

import tempfile
with tempfile.TemporaryDirectory() as tmp:
    temp = Path(tmp)
    (temp / "sample_trace.txt").write_bytes((ROOT / "tests/validation/fixtures/sample_trace.txt").read_bytes())
    (temp / "synthetic_example.json").write_text(p.read_text())
    (temp / "evidence_link.txt").symlink_to(temp / "sample_trace.txt")
    obj = copy.deepcopy(base)
    for item in obj["evidence"]:
        if item["relative_path"] == "sample_trace.txt":
            item["relative_path"] = "evidence_link.txt"
    issues = verify(obj, temp / "synthetic_example.json")
    assert any(x.startswith("SYMLINK_EVIDENCE_PATH:") for x in issues), issues
    print("symlink evidence REJECTED")
