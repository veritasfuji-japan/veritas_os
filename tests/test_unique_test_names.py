"""Prevent direct test definitions from silently overwriting earlier tests."""

import ast
from pathlib import Path
import subprocess


def _duplicates(body: list[ast.stmt], scope: str = "module") -> list[str]:
    """Find repeated direct test declarations in module and class namespaces."""
    seen: dict[str, int] = {}
    errors = []
    for node in body:
        if isinstance(node, ast.ClassDef):
            errors.extend(_duplicates(node.body, f"{scope}.{node.name}"))
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if not node.name.startswith(("test_", "Test")):
            continue
        if node.name in seen:
            errors.append(f"{scope}.{node.name}: {seen[node.name]}, {node.lineno}")
        seen[node.name] = node.lineno
    return errors


def test_detector_catches_sync_async_and_class_overwrites() -> None:
    source = (
        "def test_same(): pass\n"
        "async def test_same(): pass\n"
        "class TestA:\n"
        " def test_method(self): pass\n"
        " def test_method(self): pass\n"
        "class TestA: pass\n"
    )
    assert _duplicates(ast.parse(source).body) == [
        "module.test_same: 1, 2",
        "module.TestA.test_method: 4, 5",
        "module.TestA: 3, 6",
    ]


def test_detector_keeps_separate_class_namespaces() -> None:
    source = "class TestA:\n def test_x(self): pass\nclass TestB:\n def test_x(self): pass"
    assert _duplicates(ast.parse(source).body) == []


def test_tracked_test_definitions_have_unique_names() -> None:
    """Parse tracked pytest files without importing them or running fixtures."""
    root = Path(__file__).resolve().parents[1]
    paths = subprocess.check_output(
        ["git", "ls-files", "-z", "*.py"], cwd=root, text=True
    ).split("\0")
    errors = []
    for name in paths:
        path = Path(name)
        if "tests" not in path.parts:
            continue
        if not (path.name.startswith("test_") or path.name.endswith("_test.py")):
            continue
        tree = ast.parse((root / path).read_text(encoding="utf-8"), filename=name)
        errors.extend(f"{name}: {error}" for error in _duplicates(tree.body))
    assert not errors, "Overwritten test definitions:\n" + "\n".join(errors)
