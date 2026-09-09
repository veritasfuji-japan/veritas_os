#!/usr/bin/env python3
"""Phase 2 evidence generator for the Large Consolidation Audit.

This is intentionally non-destructive. It computes:
- frozen-core transitive Python dependency closure,
- inbound Python importers,
- exact text references across runtime/tests/scripts/docs/workflows,
- TrustLog verifier role/consumer evidence,
- plan8-plan17 target overlap,
- legacy policy SHA-256 verifier consumer evidence,
- dry-run family suffix pairing.

It never edits runtime files or proposes deletion solely from naming/size.
"""

from __future__ import annotations

import argparse
import ast
from collections import defaultdict, deque
import json
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
FREEZE = ROOT / "docs" / "architecture" / "controlled-execution-proof-freeze-v1.json"
DEFAULT_OUTPUT = ROOT / "artifacts" / "consolidation-audit" / "phase2-generated.json"

_AUDIT_SELF_PATHS = {
    "scripts/audit_large_consolidation.py",
    "scripts/audit_large_consolidation_phase2.py",
    "artifacts/consolidation-audit/2026-09-09-baseline.json",
    "artifacts/consolidation-audit/2026-09-09-report.md",
    "artifacts/consolidation-audit/2026-09-10-phase2-baseline.json",
    "artifacts/consolidation-audit/2026-09-10-phase2-report.md",
    "veritas_os/tests/test_large_consolidation_audit_artifacts.py",
    "veritas_os/tests/test_large_consolidation_audit_phase2.py",
}

_TEXT_SUFFIXES = {
    ".py", ".md", ".txt", ".toml", ".yml", ".yaml", ".json",
    ".ini", ".cfg", ".sh",
}


def _iter_files() -> Iterable[Path]:
    excluded = {".git", ".venv", "node_modules", ".mypy_cache", ".pytest_cache"}
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in excluded for part in path.parts):
            continue
        yield path


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _module_for_path(path: Path) -> str | None:
    rel = path.relative_to(ROOT)
    if path.suffix != ".py" or not rel.parts or rel.parts[0] != "veritas_os":
        return None
    parts = list(rel.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _module_candidates(module: str) -> Iterable[str]:
    current = module
    while current:
        yield current
        if "." not in current:
            break
        current = current.rsplit(".", 1)[0]


def _resolve_from(module_name: str, node: ast.ImportFrom) -> str | None:
    if node.level == 0:
        return node.module
    package = module_name.rsplit(".", 1)[0] if "." in module_name else module_name
    parts = package.split(".")
    up = node.level - 1
    if up > len(parts):
        return None
    base = parts[: len(parts) - up]
    if node.module:
        base.extend(node.module.split("."))
    return ".".join(base)


def _parse_imports(path: Path, module_name: str | None) -> set[str]:
    if module_name is None:
        return set()
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, SyntaxError):
        return set()
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            resolved = _resolve_from(module_name, node)
            if resolved:
                result.add(resolved)
    return result


def _build_python_graph() -> tuple[dict[str, str], dict[str, set[str]], dict[str, set[str]]]:
    py_paths = [path for path in _iter_files() if path.suffix == ".py"]
    module_to_path = {
        module: _rel(path)
        for path in py_paths
        if (module := _module_for_path(path)) is not None
    }
    edges: dict[str, set[str]] = defaultdict(set)
    inbound: dict[str, set[str]] = defaultdict(set)

    for path in py_paths:
        source_module = _module_for_path(path)
        if source_module is None:
            continue
        source_path = _rel(path)
        for imported in _parse_imports(path, source_module):
            target_path = None
            for candidate in _module_candidates(imported):
                if candidate in module_to_path:
                    target_path = module_to_path[candidate]
                    break
            if target_path is None or target_path == source_path:
                continue
            edges[source_path].add(target_path)
            inbound[target_path].add(source_path)
    return module_to_path, edges, inbound


def _closure(seeds: Iterable[str], edges: dict[str, set[str]]) -> list[str]:
    seen: set[str] = set()
    queue = deque(sorted(set(seeds)))
    while queue:
        path = queue.popleft()
        if path in seen:
            continue
        seen.add(path)
        for nxt in sorted(edges.get(path, set())):
            if nxt not in seen:
                queue.append(nxt)
    return sorted(seen)


def _category(path: str) -> str:
    if path.startswith("veritas_os/tests/") or path.startswith("tests/"):
        return "test"
    if path.startswith("scripts/") or path.startswith("veritas_os/scripts/"):
        return "script"
    if path.startswith(".github/workflows/"):
        return "workflow"
    if path.startswith("docs/") or path.startswith("artifacts/"):
        return "doc_artifact"
    if path.startswith("veritas_os/"):
        return "runtime"
    return "other"


def _text_references(symbol: str, *, definition_path: str | None = None) -> dict[str, list[str]]:
    refs: dict[str, list[str]] = defaultdict(list)
    for path in _iter_files():
        rel = _rel(path)
        if rel in _AUDIT_SELF_PATHS or path.suffix.lower() not in _TEXT_SUFFIXES:
            continue
        if definition_path is not None and rel == definition_path:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if symbol in text:
            refs[_category(rel)].append(rel)
    return {key: sorted(set(value)) for key, value in sorted(refs.items())}


def _freeze_seed_paths() -> tuple[list[str], list[str]]:
    data = json.loads(FREEZE.read_text(encoding="utf-8"))
    required = data["required_files"]
    all_py = sorted(
        path for path in required
        if path.endswith(".py") and path.startswith("veritas_os/")
    )
    runtime = sorted(path for path in all_py if not path.startswith("veritas_os/tests/"))
    return runtime, all_py


def _plan_test_matrix() -> dict[str, Any]:
    paths = sorted(
        path for path in _iter_files()
        if _rel(path).startswith("veritas_os/tests/unit/test_plan")
        and path.suffix == ".py"
        and any(
            _rel(path).startswith(f"veritas_os/tests/unit/test_plan{n}_")
            for n in range(8, 18)
        )
    )
    rows = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        tests = [
            node.name
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("test_")
        ]
        targets = {
            "rate_limiting": text.count("rl."),
            "routes_decide": text.count("rd."),
            "pipeline_policy": text.count("pp."),
            "pipeline_execute": text.count("pe."),
            "pipeline_response": text.count("pr."),
            "pipeline_contracts": text.count("pc."),
        }
        rows.append({
            "path": _rel(path),
            "test_count": len(tests),
            "tests": tests,
            "target_reference_counts": targets,
        })

    known_overlap_groups = [
        {
            "behavior": "replay_decision_query_param_failure_defaults_mock_true",
            "tests": [
                "test_replay_decision_endpoint_query_params_error_defaults_true",
                "test_replay_decision_endpoint_defaults_mock_true_on_query_error",
                "test_routes_replay_decision_query_param_error_defaults_to_mock_true",
            ],
            "classification": "DUPLICATE_CANDIDATE",
            "confidence": "HIGH",
        },
        {
            "behavior": "unknown_rollout_strategy_safe_full",
            "tests": [
                "test_rollout_enforcement_unknown_strategy_defaults_to_safe_full",
                "test_pipeline_rollout_unknown_strategy_falls_back_to_safe_full",
            ],
            "classification": "DUPLICATE_CANDIDATE",
            "confidence": "HIGH",
        },
        {
            "behavior": "pipeline_unavailable_lazy_state_reset",
            "tests": [
                "test_decide_pipeline_unavailable_resets_lazy_state",
                "test_decide_pipeline_unavailable_resets_lazy_state_when_mutated",
            ],
            "classification": "DUPLICATE_CANDIDATE",
            "confidence": "MEDIUM",
        },
        {
            "behavior": "nonce_cleanup_scheduler_failure_handling",
            "tests": [
                "test_schedule_nonce_cleanup_reschedules_even_after_cleanup_error",
                "test_schedule_nonce_cleanup_logs_and_stops_when_timer_cleared",
                "test_rate_nonce_scheduler_logs_when_cleanup_raises",
            ],
            "classification": "DUPLICATE_CANDIDATE",
            "confidence": "MEDIUM",
        },
        {
            "behavior": "effective_nonce_max_override_fallbacks",
            "tests": [
                "test_effective_nonce_max_import_error_uses_default",
                "test_effective_nonce_max_uses_default_when_server_override_is_non_int",
                "test_effective_nonce_max_prefers_server_integer_override",
            ],
            "classification": "ACTIVE_NON_CORE",
            "confidence": "HIGH",
        },
    ]
    return {
        "files": rows,
        "known_overlap_groups": known_overlap_groups,
    }


def _dry_run_matrix(paths: Iterable[Path]) -> dict[str, Any]:
    canonical_prefix = "veritas_os/policy/canonical_promotion_live_adapter_dry_run_"
    live_prefix = "veritas_os/policy/live_adapter_dry_run_"
    canonical = sorted(
        _rel(path)[len(canonical_prefix):-3]
        for path in paths
        if _rel(path).startswith(canonical_prefix) and path.suffix == ".py"
    )
    live = sorted(
        _rel(path)[len(live_prefix):-3]
        for path in paths
        if _rel(path).startswith(live_prefix) and path.suffix == ".py"
    )
    paired = sorted(set(canonical) & set(live))
    return {
        "canonical_suffixes": canonical,
        "live_suffixes": live,
        "paired_suffixes": paired,
        "canonical_only": sorted(set(canonical) - set(live)),
        "live_only": sorted(set(live) - set(canonical)),
        "classification": "UNCERTAIN",
        "deletion_permitted": False,
        "note": (
            "Suffix pairing shows structural parallelism only. Frozen native-v2 "
            "code imports this lineage; behavioral equivalence is not inferred."
        ),
    }


def _trustlog_matrix() -> list[dict[str, Any]]:
    rows = [
        {
            "symbol": "verify_trust_log",
            "definition": "veritas_os/logging/trust_log.py",
            "role": "full encrypted TrustLog compatibility verifier",
            "classification": "ACTIVE_NON_CORE",
        },
        {
            "symbol": "verify_trustlogs",
            "definition": "veritas_os/audit/trustlog_verify.py",
            "role": "unified full + witness ledger verifier",
            "classification": "ACTIVE_NON_CORE",
        },
        {
            "symbol": "verify_entries",
            "definition": "veritas_os/scripts/verify_trust_log.py",
            "role": "backward-compatible tuple-output helper; CLI main uses verify_trustlogs",
            "classification": "COMPATIBILITY_CANDIDATE",
        },
        {
            "symbol": "compute_hash",
            "definition": "veritas_os/scripts/verify_trust_log.py",
            "role": "backward-compatible full-ledger hash helper used by verify_entries/tests/tools",
            "classification": "COMPATIBILITY_CANDIDATE",
        },
    ]
    for row in rows:
        row["references"] = _text_references(
            row["symbol"],
            definition_path=row["definition"],
        )
        row["deletion_permitted"] = False
    return rows


def build_phase2() -> dict[str, Any]:
    all_paths = list(_iter_files())
    _, edges, inbound = _build_python_graph()
    runtime_seeds, proof_seeds = _freeze_seed_paths()
    runtime_closure = _closure(runtime_seeds, edges)
    proof_closure = _closure(proof_seeds, edges)

    legacy_refs = _text_references(
        "verify_manifest_sha256",
        definition_path="veritas_os/policy/signing.py",
    )
    legacy_runtime_consumers = sorted(
        legacy_refs.get("runtime", [])
        + legacy_refs.get("script", [])
        + legacy_refs.get("workflow", [])
    )

    protected = [
        {
            "path": path,
            "inbound_importers": sorted(inbound.get(path, set())),
        }
        for path in runtime_closure
    ]

    return {
        "format_version": "large-consolidation-audit-phase2/v1",
        "mode": "NON_DESTRUCTIVE",
        "source_main": "52752dbf766d9994f2f3267af47e904748d347a6",
        "frozen_proof_anchor": "ada46f2fe324dd3cbcff6be59d56c4f75c4a6bdc",
        "frozen_dependency_closure": {
            "runtime_seed_count": len(runtime_seeds),
            "runtime_closure_count": len(runtime_closure),
            "runtime_seeds": runtime_seeds,
            "runtime_closure": runtime_closure,
            "proof_seed_count": len(proof_seeds),
            "proof_closure_count": len(proof_closure),
            "proof_closure": proof_closure,
            "protected_runtime_records": protected,
            "limitation": (
                "Static Python import closure only. Dynamic imports, plugin loading, "
                "reflection and configuration-driven entry points require separate evidence."
            ),
        },
        "legacy_policy_sha256": {
            "symbol": "verify_manifest_sha256",
            "definition": "veritas_os/policy/signing.py",
            "classification": (
                "DEAD_CANDIDATE" if not legacy_runtime_consumers
                else "COMPATIBILITY_CANDIDATE"
            ),
            "references": legacy_refs,
            "supported_runtime_script_workflow_consumers": legacy_runtime_consumers,
            "deletion_permitted": False,
        },
        "trustlog_role_matrix": _trustlog_matrix(),
        "plan8_plan17_matrix": _plan_test_matrix(),
        "dry_run_family_matrix": _dry_run_matrix(all_paths),
        "candidate_reference_matrix": {
            "api_schemas": _text_references(
                "veritas_os.api.schemas",
                definition_path="veritas_os/api/schemas.py",
            ),
            "native_bind_authorization": _text_references(
                "native_bind_authorization",
                definition_path="veritas_os/policy/native_bind_authorization.py",
            ),
            "sandbox_recovery": _text_references(
                "sandbox_recovery",
                definition_path="veritas_os/policy/sandbox_recovery.py",
            ),
        },
        "ranked_follow_up_candidates": [
            {
                "rank": 1,
                "target": "verify_manifest_sha256",
                "classification": (
                    "DEAD_CANDIDATE" if not legacy_runtime_consumers
                    else "COMPATIBILITY_CANDIDATE"
                ),
                "confidence": "HIGH" if not legacy_runtime_consumers else "MEDIUM",
                "blast_radius": "LOW",
                "action": (
                    "Prepare narrow removal/deprecation PR only after Human CEO review."
                    if not legacy_runtime_consumers else
                    "Preserve; investigate remaining supported consumers."
                ),
            },
            {
                "rank": 2,
                "target": "plan8-plan17 exact overlap groups",
                "classification": "DUPLICATE_CANDIDATE",
                "confidence": "HIGH_FOR_LISTED_GROUPS",
                "blast_radius": "LOW",
                "action": "Consolidate exact duplicate behavior tests without reducing safety coverage.",
            },
            {
                "rank": 3,
                "target": "verify_entries/compute_hash compatibility helpers",
                "classification": "COMPATIBILITY_CANDIDATE",
                "confidence": "MEDIUM",
                "blast_radius": "LOW_TO_MEDIUM",
                "action": "Confirm external/tool imports before deprecation; CLI main does not need them.",
            },
            {
                "rank": 4,
                "target": "dry-run packet families",
                "classification": "UNCERTAIN",
                "confidence": "HIGH",
                "blast_radius": "HIGH",
                "action": "Preserve until behavioral responsibility matrix and frozen closure permit change.",
            },
            {
                "rank": 5,
                "target": "TrustLog verifier surfaces",
                "classification": "ACTIVE_NON_CORE",
                "confidence": "HIGH",
                "blast_radius": "HIGH",
                "action": "Do not unify by naming; preserve separate ledger/compatibility roles.",
            },
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = build_phase2()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "runtime_closure_count": result["frozen_dependency_closure"]["runtime_closure_count"],
        "proof_closure_count": result["frozen_dependency_closure"]["proof_closure_count"],
        "legacy_classification": result["legacy_policy_sha256"]["classification"],
        "dry_run_pairs": len(result["dry_run_family_matrix"]["paired_suffixes"]),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
