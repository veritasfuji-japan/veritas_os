"""Contract tests for Planner / Kernel / Fuji / MemoryOS responsibility boundaries.

These tests are intentionally conservative: they focus on import direction,
I/O ownership, and public-API-level behavior so boundary breaks fail fast.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Dict, Iterable, Set

from veritas_os.core import fuji, memory, planner

CORE_DIR = Path(__file__).resolve().parents[1] / "core"


MODULE_FILES: Dict[str, Path] = {
    "planner": CORE_DIR / "planner.py",
    "kernel": CORE_DIR / "kernel.py",
    "fuji": CORE_DIR / "fuji.py",
    "memory": CORE_DIR / "memory.py",
}


def _read_ast(path: Path) -> ast.Module:
    """Parse a Python module and return its AST."""
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _imported_module_names(tree: ast.Module) -> Set[str]:
    """Collect imported module names from an AST."""
    imported: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(node.module)
            elif node.level and node.names:
                for alias in node.names:
                    imported.add(alias.name)
    return imported


def _has_forbidden_write_calls(tree: ast.Module, names: Iterable[str]) -> bool:
    """Return True when AST includes forbidden write-like call names."""
    forbidden = set(names)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name) and node.func.id in forbidden:
            return True
        if isinstance(node.func, ast.Attribute) and node.func.attr in forbidden:
            return True
    return False


def test_import_direction_contract_for_boundary_modules() -> None:
    """Boundary modules must not import each other in forbidden directions."""
    forbidden_imports = {
        "planner": {"veritas_os.core.kernel", "veritas_os.core.fuji", "kernel", "fuji"},
        "fuji": {"veritas_os.core.kernel", "veritas_os.core.planner", "kernel", "planner"},
        "memory": {"veritas_os.core.kernel", "veritas_os.core.planner", "veritas_os.core.fuji", "kernel", "planner", "fuji"},
    }

    for module_name, forbidden in forbidden_imports.items():
        tree = _read_ast(MODULE_FILES[module_name])
        imported = _imported_module_names(tree)
        assert imported.isdisjoint(forbidden), (
            f"{module_name} imported forbidden modules: {sorted(imported & forbidden)}"
        )


def test_io_boundary_planner_does_not_perform_direct_write_calls() -> None:
    """Planner should avoid stateful file writes; MemoryOS owns persistence."""
    forbidden_write_ops = {"open", "write_text", "write_bytes", "unlink", "mkdir", "replace", "rename"}

    planner_tree = _read_ast(MODULE_FILES["planner"])

    assert not _has_forbidden_write_calls(planner_tree, forbidden_write_ops)


def test_state_ownership_memory_store_declared_only_in_memory_module() -> None:
    """MemoryStore type should be owned by MemoryOS only."""
    memory_tree = _read_ast(MODULE_FILES["memory"])
    class_names = {node.name for node in ast.walk(memory_tree) if isinstance(node, ast.ClassDef)}
    assert "MemoryStore" in class_names

    for module_name in ("planner", "kernel", "fuji"):
        tree = _read_ast(MODULE_FILES[module_name])
        other_class_names = {node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}
        assert "MemoryStore" not in other_class_names


def test_planner_public_api_does_not_mutate_context(monkeypatch) -> None:
    """Planner public API should treat input context as caller-owned state."""
    original_context = {"mode": "simple_qa", "nested": {"a": 1}}
    snapshot = {"mode": "simple_qa", "nested": {"a": 1}}

    monkeypatch.setattr(planner.world_model, "snapshot", lambda *_args, **_kwargs: {"progress": 0.1})
    monkeypatch.setattr(planner.mem, "search", lambda *_args, **_kwargs: [])

    result = planner.plan_for_veritas_agi(original_context, "短い質問です")

    assert isinstance(result, dict)
    assert original_context == snapshot


def test_public_api_smoke_fuji_and_memory(tmp_path, monkeypatch) -> None:
    """Boundary modules remain usable through public APIs only."""
    fuji_result = fuji.evaluate("これは安全です", context={"enforce_low_evidence": False})
    assert isinstance(fuji_result, dict)
    assert "status" in fuji_result

    monkeypatch.setattr(memory, "MEM_PATH", tmp_path / "memory.json")
    memory.MEM = memory._LazyMemoryStore(lambda: memory.MemoryStore.load(memory.MEM_PATH))

    result = memory.add(
        user_id="tester",
        text="boundary test",
        kind="episodic",
    )
    assert isinstance(result, dict)
    records = memory.list_all("tester")
    assert isinstance(records, list)
