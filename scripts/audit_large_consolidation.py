#!/usr/bin/env python3
"""Non-destructive repository inventory for the Large Consolidation Audit.

This tool does not delete, rewrite, or classify uncertain code as removable.
It inventories Python files, static imports, top-level symbols and candidate
families so consolidation work can be justified with evidence after the
controlled Execution Proof architecture freeze.
"""

from __future__ import annotations

import argparse
import ast
from collections import Counter, defaultdict
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "artifacts" / "consolidation-audit" / "current-inventory.json"
FREEZE_MANIFEST = (
    ROOT / "docs" / "architecture" / "controlled-execution-proof-freeze-v1.json"
)
CLASSIFICATIONS = {
    "FROZEN_CORE",
    "ACTIVE_NON_CORE",
    "DUPLICATE_CANDIDATE",
    "DEAD_CANDIDATE",
    "COMPATIBILITY_CANDIDATE",
    "UNCERTAIN",
}


@dataclass(frozen=True)
class PythonFile:
    path: str
    module: str | None
    bytes: int
    lines: int
    functions: int
    classes: int
    imports: tuple[str, ...]


def _iter_files(root: Path) -> Iterable[Path]:
    excluded = {".git", ".venv", "node_modules", ".mypy_cache", ".pytest_cache"}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in excluded for part in path.parts):
            continue
        yield path


def _module_name(path: Path) -> str | None:
    rel = path.relative_to(ROOT)
    if not rel.as_posix().endswith(".py"):
        return None
    if rel.parts[0] != "veritas_os":
        return None
    parts = list(rel.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _imports(tree: ast.AST) -> tuple[str, ...]:
    values: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            values.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            values.add(node.module)
    return tuple(sorted(values))


def _python_file(path: Path) -> PythonFile:
    raw = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(raw)
    except SyntaxError:
        # Audit must surface unparsable source without pretending it is dead.
        return PythonFile(
            path=path.relative_to(ROOT).as_posix(),
            module=_module_name(path),
            bytes=path.stat().st_size,
            lines=raw.count("\n") + 1,
            functions=0,
            classes=0,
            imports=(),
        )
    functions = sum(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        for node in tree.body
    )
    classes = sum(isinstance(node, ast.ClassDef) for node in tree.body)
    return PythonFile(
        path=path.relative_to(ROOT).as_posix(),
        module=_module_name(path),
        bytes=path.stat().st_size,
        lines=raw.count("\n") + 1,
        functions=functions,
        classes=classes,
        imports=_imports(tree),
    )


def _freeze_files() -> set[str]:
    data = json.loads(FREEZE_MANIFEST.read_text(encoding="utf-8"))
    return set(data["required_files"])


def _test_family(files: list[PythonFile]) -> list[dict]:
    prefixes = (
        "veritas_os/tests/unit/test_plan8_",
        "veritas_os/tests/unit/test_plan9_",
        "veritas_os/tests/unit/test_plan10_",
        "veritas_os/tests/unit/test_plan11_",
        "veritas_os/tests/unit/test_plan12_",
        "veritas_os/tests/unit/test_plan13_",
        "veritas_os/tests/unit/test_plan14_",
        "veritas_os/tests/unit/test_plan15_",
        "veritas_os/tests/unit/test_plan16_",
        "veritas_os/tests/unit/test_plan17_",
    )
    return [
        {"path": item.path, "bytes": item.bytes, "lines": item.lines}
        for item in files
        if item.path.startswith(prefixes)
    ]


def build_inventory() -> dict:
    paths = list(_iter_files(ROOT))
    python = [_python_file(path) for path in paths if path.suffix == ".py"]
    freeze_files = _freeze_files()

    module_to_path = {
        item.module: item.path for item in python if item.module is not None
    }
    inbound: Counter[str] = Counter()
    importers: dict[str, set[str]] = defaultdict(set)

    for item in python:
        for imported in item.imports:
            candidate = imported
            while candidate:
                target = module_to_path.get(candidate)
                if target:
                    inbound[target] += 1
                    importers[target].add(item.path)
                    break
                if "." not in candidate:
                    break
                candidate = candidate.rsplit(".", 1)[0]

    runtime = [
        item
        for item in python
        if item.path.startswith("veritas_os/")
        and not item.path.startswith("veritas_os/tests/")
    ]
    tests = [item for item in python if item.path.startswith("veritas_os/tests/")]
    scripts = [item for item in python if item.path.startswith("scripts/")]

    dry_canonical = [
        item
        for item in runtime
        if item.path.startswith(
            "veritas_os/policy/canonical_promotion_live_adapter_dry_run_"
        )
    ]
    dry_live = [
        item
        for item in runtime
        if item.path.startswith("veritas_os/policy/live_adapter_dry_run_")
    ]
    trustlog = [
        item
        for item in python
        if "trustlog" in item.path.lower() or "trust_log" in item.path.lower()
    ]
    plan_tests = _test_family(python)

    biggest_runtime = sorted(runtime, key=lambda x: x.bytes, reverse=True)[:30]
    biggest_tests = sorted(tests, key=lambda x: x.bytes, reverse=True)[:30]

    frozen_records = []
    for path in sorted(freeze_files):
        match = next((item for item in python if item.path == path), None)
        frozen_records.append(
            {
                "path": path,
                "classification": "FROZEN_CORE",
                "bytes": match.bytes if match else None,
                "inbound_python_importers": sorted(importers.get(path, set())),
            }
        )

    return {
        "format_version": "large-consolidation-audit-inventory/v1",
        "mode": "NON_DESTRUCTIVE",
        "classifications": sorted(CLASSIFICATIONS),
        "totals": {
            "files": len(paths),
            "python_files": len(python),
            "runtime_python_files": len(runtime),
            "test_python_files": len(tests),
            "script_python_files": len(scripts),
        },
        "frozen_core": frozen_records,
        "largest_runtime_python": [
            {
                "path": item.path,
                "bytes": item.bytes,
                "lines": item.lines,
                "functions": item.functions,
                "classes": item.classes,
                "inbound_python_import_count": inbound[item.path],
            }
            for item in biggest_runtime
        ],
        "largest_test_python": [
            {
                "path": item.path,
                "bytes": item.bytes,
                "lines": item.lines,
                "functions": item.functions,
                "classes": item.classes,
            }
            for item in biggest_tests
        ],
        "candidate_families": {
            "plan8_to_plan17_tests": {
                "classification": "DUPLICATE_CANDIDATE",
                "confidence": "MEDIUM",
                "files": plan_tests,
                "note": (
                    "Coverage-plan files repeatedly target pipeline/routes/rate "
                    "abnormal edges. Map tests to unique target behaviors before "
                    "merging; this classification is not deletion approval."
                ),
            },
            "canonical_promotion_live_adapter_dry_run": {
                "classification": "UNCERTAIN",
                "confidence": "HIGH",
                "file_count": len(dry_canonical),
                "total_bytes": sum(item.bytes for item in dry_canonical),
                "files": [item.path for item in dry_canonical],
                "note": (
                    "Large parallel family with frozen-path dependencies. Do not "
                    "consolidate until transitive dependency closure is recorded."
                ),
            },
            "live_adapter_dry_run": {
                "classification": "UNCERTAIN",
                "confidence": "HIGH",
                "file_count": len(dry_live),
                "total_bytes": sum(item.bytes for item in dry_live),
                "files": [item.path for item in dry_live],
                "note": (
                    "Naming overlaps canonical-promotion dry-run family, but active "
                    "native authorization code imports this lineage. No deletion."
                ),
            },
            "trustlog_surfaces": {
                "classification": "UNCERTAIN",
                "confidence": "HIGH",
                "file_count": len(trustlog),
                "total_bytes": sum(item.bytes for item in trustlog),
                "files": [item.path for item in trustlog],
                "note": (
                    "Multiple active ledger/verifier/CLI roles exist. Build a role "
                    "matrix before attempting unification."
                ),
            },
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    inventory = build_inventory()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(inventory, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(inventory["totals"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
