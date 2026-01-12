# tools/coverage_map_pipeline.py
from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
COV_JSON = ROOT / "coverage.json"
TARGET_SUFFIX = str(Path("veritas_os/core/pipeline.py"))

def load_cov() -> Dict:
    return json.loads(COV_JSON.read_text(encoding="utf-8"))

def find_target_file(cov: Dict) -> str:
    files = cov.get("files", {})
    for fp in files.keys():
        if fp.endswith(TARGET_SUFFIX):
            return fp
    raise SystemExit(f"Target not found in coverage.json: *{TARGET_SUFFIX}")

def index_defs(tree: ast.AST) -> List[Tuple[str, int, int]]:
    defs: List[Tuple[str, int, int]] = []
    class Stack(ast.NodeVisitor):
        def __init__(self):
            self.scope: List[str] = []

        def visit_ClassDef(self, node: ast.ClassDef):
            self.scope.append(node.name)
            self.generic_visit(node)
            self.scope.pop()

        def visit_FunctionDef(self, node: ast.FunctionDef):
            name = ".".join(self.scope + [node.name]) if self.scope else node.name
            end = getattr(node, "end_lineno", None) or node.lineno
            defs.append((name, node.lineno, end))
            self.generic_visit(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
            name = ".".join(self.scope + [node.name]) if self.scope else node.name
            end = getattr(node, "end_lineno", None) or node.lineno
            defs.append((name, node.lineno, end))
            self.generic_visit(node)

    Stack().visit(tree)
    defs.sort(key=lambda x: (x[1], x[2]))
    return defs

def owner(defs: List[Tuple[str,int,int]], line: int) -> str:
    for name, a, b in defs:
        if a <= line <= b:
            return name
    return "<module-level>"

def main():
    cov = load_cov()
    target = find_target_file(cov)
    entry = cov["files"][target]
    missing_lines: List[int] = entry.get("missing_lines", [])
    missing_branches = entry.get("missing_branches", [])  # list of [from, to]
    executed_branches = entry.get("executed_branches", [])

    src_path = Path(target)
    src = src_path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    defs = index_defs(tree)

    # group missing lines by owner
    by_owner: Dict[str, List[int]] = {}
    for ln in missing_lines:
        by_owner.setdefault(owner(defs, ln), []).append(ln)

    # simple summary
    print(f"[pipeline] missing_lines={len(missing_lines)} missing_branches={len(missing_branches)}")
    print(f"[pipeline] file={target}\n")

    # show top owners
    items = sorted(by_owner.items(), key=lambda kv: len(kv[1]), reverse=True)
    for name, lines in items[:20]:
        lines.sort()
        head = ", ".join(map(str, lines[:12])) + (" ..." if len(lines) > 12 else "")
        print(f"- {name}: {len(lines)} lines  [{head}]")

    # show exit arcs quickly (coverage uses -1 for exit)
    exits = [arc for arc in missing_branches if arc[1] in (-1, 0)]
    if exits:
        print("\n[missing exit arcs] (to=-1/0 means exit-ish)")
        for a,b in exits[:25]:
            print(f"  {a} -> {b}")

if __name__ == "__main__":
    main()

