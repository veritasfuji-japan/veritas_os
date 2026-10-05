#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TARGET_MODULE = "veritas_os.audit.observable_digest_resolver"
TARGET_PATH = "veritas_os/audit/observable_digest_resolver.py"
ALLOWED_CALLER = "veritas_os/tests/test_observable_digest_resolver_behavior.py"
REPORT = ROOT / "artifacts/observable-digest-resolver-aer02-v1/proof-report.json"

SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "artifacts", "__pycache__"}

def py_files() -> list[Path]:
    out = []
    for path in ROOT.rglob("*.py"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        out.append(path)
    return sorted(out)

def classify(path: Path) -> str:
    rel = path.relative_to(ROOT).as_posix()
    if rel == TARGET_PATH:
        return "implementation"
    if rel.startswith("veritas_os/tests/") or rel.startswith("tests/"):
        return "test"
    if rel.startswith("scripts/"):
        return "tooling"
    return "production"

def scan(path: Path) -> dict[str, object]:
    rel = path.relative_to(ROOT).as_posix()
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
    hits: list[dict[str, object]] = []
    aliases: set[str] = set()
    module_aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == TARGET_MODULE:
            for name in node.names:
                aliases.add(name.asname or name.name)
                hits.append({"kind":"import_from","line":node.lineno,"name":name.name})
        elif isinstance(node, ast.Import):
            for name in node.names:
                if name.name == TARGET_MODULE:
                    module_aliases.add(name.asname or name.name)
                    hits.append({"kind":"import_module","line":node.lineno,"name":name.name})
    call_lines: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if isinstance(fn, ast.Name) and fn.id in aliases:
            call_lines.append(node.lineno)
        elif isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name) and fn.value.id in module_aliases:
            call_lines.append(node.lineno)
    return {"path":rel,"class":classify(path),"imports":hits,"call_lines":sorted(call_lines)}

def main() -> int:
    scans = [scan(p) for p in py_files()]
    relevant = [x for x in scans if x["imports"] or x["call_lines"]]
    production = [x for x in relevant if x["class"] == "production"]
    undeclared = [
        x for x in relevant
        if x["path"] not in {ALLOWED_CALLER} and x["class"] != "implementation"
    ]
    test = next((x for x in relevant if x["path"] == ALLOWED_CALLER), None)
    invariants = {
        "no_production_import_or_call_path": not production,
        "only_declared_nonimplementation_caller": not undeclared,
        "declared_focused_test_present": test is not None,
        "declared_focused_test_calls_resolver": bool(test and test["call_lines"]),
    }
    passed = all(invariants.values())
    report = {
        "proof_scope":"AER-02_RUNTIME_REACHABILITY_INVENTORY_V1",
        "tested_sha":subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
        "result":"PASS" if passed else "FAIL",
        "proof_status":"PENDING_EXACT_MAIN_AND_INDEPENDENT_CLOSURE",
        "target_module":TARGET_MODULE,
        "declared_nonimplementation_caller":ALLOWED_CALLER,
        "repository_python_file_count":len(scans),
        "reachability_inventory":relevant,
        "production_runtime_paths":production,
        "undeclared_paths":undeclared,
        "invariants":invariants,
        "non_claims":[
            "This source-level inventory does not prove arbitrary runtime reflection or code outside the repository absent.",
            "This proof does not authorize or activate the resolver.",
            "This proof does not name an activation target or caller for AER-03.",
            "Any future declared runtime caller requires review and a new AER-02 proof round."
        ]
    }
    REPORT.parent.mkdir(parents=True,exist_ok=True)
    REPORT.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(report,indent=2,sort_keys=True))
    return 0 if passed else 1

if __name__ == "__main__":
    raise SystemExit(main())
