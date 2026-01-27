# veritas_os/tools/coverage_map_pipeline.py
from __future__ import annotations

import ast
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional

# =========================================================
# Config (TEST-COMPAT)
# =========================================================
# tests expect:
#  - this file is veritas_os/tools/coverage_map_pipeline.py
#  - ROOT = __file__.parents[2] so that:
#      tmp_proj/veritas_os/tools/coverage_map_pipeline.py -> ROOT = tmp_proj
ROOT = Path(__file__).resolve().parents[2]

# tests also monkeypatch this symbol directly
COV_JSON = ROOT / "coverage.json"

# Default target: veritas_os/core/pipeline.py
TARGET_SUFFIX = str(Path("veritas_os/core/pipeline.py"))

# coverage.json search candidates (keep compat)
# - 1) explicit: COV_JSON (monkeypatchable / test default)
# - 2) ENV: VERITAS_COVERAGE_JSON
# - 3) ROOT/coverage.json            (same as COV_JSON, but keep as a path candidate)
# - 4) ROOT/veritas_os/coverage.json (legacy/ops placement)
COV_JSON_CANDIDATES: Tuple[Any, ...] = (
    COV_JSON,
    "ENV:VERITAS_COVERAGE_JSON",
    ROOT / "coverage.json",
    ROOT / "veritas_os" / "coverage.json",
)

# Output limits
MAX_OWNERS = 30
MAX_LINES_PREVIEW = 14
MAX_EXITS = 40
MAX_BRANCHES = 40


# =========================================================
# Data structures
# =========================================================
@dataclass
class CovFileEntry:
    missing_lines: List[int]
    missing_branches: List[List[int]]
    executed_branches: List[List[int]]

    @classmethod
    def from_cov(cls, entry: Dict[str, Any]) -> "CovFileEntry":
        ml = entry.get("missing_lines") or []
        mb = entry.get("missing_branches") or []
        eb = entry.get("executed_branches") or []

        # normalize types
        ml2: List[int] = []
        for x in ml:
            try:
                # accept int/float/str numeric
                s = str(x).strip()
                if s.lstrip("-").isdigit():
                    ml2.append(int(float(s)))
            except Exception:
                continue

        mb2: List[List[int]] = []
        for arc in mb:
            if isinstance(arc, (list, tuple)) and len(arc) == 2:
                try:
                    mb2.append([int(arc[0]), int(arc[1])])
                except Exception:
                    continue

        eb2: List[List[int]] = []
        for arc in eb:
            if isinstance(arc, (list, tuple)) and len(arc) == 2:
                try:
                    eb2.append([int(arc[0]), int(arc[1])])
                except Exception:
                    continue

        return cls(missing_lines=ml2, missing_branches=mb2, executed_branches=eb2)


# =========================================================
# Utils: logging / discovery / safe IO
# =========================================================
def _eprint(msg: str) -> None:
    print(msg, file=sys.stderr)


def _resolve_cov_json() -> Optional[Path]:
    """
    Return an existing coverage.json path if found.
    Priority:
      1) COV_JSON (monkeypatchable; tests rely on this)
      2) ENV: VERITAS_COVERAGE_JSON
      3) other candidates
    """
    # 1) COV_JSON (monkeypatchable)
    try:
        p0 = Path(COV_JSON)
        if p0.is_absolute():
            if p0.exists():
                return p0
        else:
            p0r = (Path.cwd() / p0).resolve()
            if p0r.exists():
                return p0r
    except Exception:
        pass

    # 2) env
    env = os.getenv("VERITAS_COVERAGE_JSON")
    if env:
        p = Path(env)
        if not p.is_absolute():
            p = (Path.cwd() / p).resolve()
        if p.exists():
            return p

    # 3) candidates
    for c in COV_JSON_CANDIDATES:
        if isinstance(c, Path):
            try:
                if c.exists():
                    return c
            except Exception:
                continue

    return None


def load_cov() -> Dict[str, Any]:
    """
    Read coverage.json.
    - If missing / invalid, return {} (no exception).
    NOTE: tests monkeypatch COV_JSON to a temp file and expect this to work.
    """
    p = _resolve_cov_json()
    if not p:
        # don't crash; keep stderr trace for humans
        tried: List[str] = []
        tried.append(f"COV_JSON={str(COV_JSON)!r}")
        env = os.getenv("VERITAS_COVERAGE_JSON")
        tried.append(f"ENV:VERITAS_COVERAGE_JSON={env!r}")
        for x in COV_JSON_CANDIDATES:
            if isinstance(x, Path):
                tried.append(str(x))
        _eprint("[coverage_map_pipeline] coverage.json not found. tried:")
        for t in tried:
            _eprint(f"  - {t}")
        return {}

    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        _eprint(
            f"[coverage_map_pipeline] failed to parse coverage.json: {p}  err={repr(e)[:160]}"
        )
        return {}


def find_target_file(cov: Dict[str, Any], target_suffix: str = TARGET_SUFFIX) -> str:
    """
    Find a target file path key inside coverage.json's "files".
    tests expect:
      - when not found => raise SystemExit
    """
    files = cov.get("files", {})
    if not isinstance(files, dict):
        raise SystemExit(f"Target not found in coverage.json: *{target_suffix}")

    # endswith match
    for fp in files.keys():
        if isinstance(fp, str) and fp.endswith(target_suffix):
            return fp

    # normalized match (Windows separators etc)
    norm_suffix = str(Path(target_suffix)).replace("\\", "/")
    for fp in files.keys():
        if not isinstance(fp, str):
            continue
        norm_fp = fp.replace("\\", "/")
        if norm_fp.endswith(norm_suffix):
            return fp

    raise SystemExit(f"Target not found in coverage.json: *{target_suffix}")


def _safe_read_text(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8")
    except Exception as e:
        _eprint(f"[coverage_map_pipeline] cannot read source: {path} err={repr(e)[:160]}")
        return None


# =========================================================
# AST indexing
# =========================================================
def index_defs(tree: ast.AST) -> List[Tuple[str, int, int]]:
    """
    Collect Class / Function / AsyncFunction spans for owner mapping.
    Returns: [(qualified_name, start_lineno, end_lineno), ...] sorted
    """
    defs: List[Tuple[str, int, int]] = []

    class Stack(ast.NodeVisitor):
        def __init__(self) -> None:
            self.scope: List[str] = []

        def visit_ClassDef(self, node: ast.ClassDef) -> Any:
            self.scope.append(node.name)
            self.generic_visit(node)
            self.scope.pop()

        def _visit_func(self, node: Any) -> Any:
            name = ".".join(self.scope + [node.name]) if self.scope else node.name
            end = getattr(node, "end_lineno", None) or node.lineno
            defs.append((name, int(node.lineno), int(end)))
            self.generic_visit(node)

        def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
            return self._visit_func(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:
            return self._visit_func(node)

    Stack().visit(tree)
    defs.sort(key=lambda x: (x[1], x[2]))
    return defs


def owner(defs: List[Tuple[str, int, int]], line: int) -> str:
    # first match is fine (outer-first); stable with sorted defs
    for name, a, b in defs:
        if a <= line <= b:
            return name
    return "<module-level>"


# =========================================================
# Reporting helpers
# =========================================================
def _preview_ints(xs: List[int], max_n: int = MAX_LINES_PREVIEW) -> str:
    xs2 = sorted(set(int(x) for x in xs))
    head = ", ".join(map(str, xs2[:max_n]))
    return head + (" ..." if len(xs2) > max_n else "")


def _exit_arcs(branches: List[List[int]]) -> List[List[int]]:
    # coverage uses -1 or 0 for exit-ish
    return [arc for arc in branches if len(arc) == 2 and arc[1] in (-1, 0)]


def _parse_target_suffix(argv: List[str]) -> str:
    """
    optional:
      --target veritas_os/core/pipeline.py
    """
    target_suffix = TARGET_SUFFIX
    if "--target" in argv:
        try:
            i = argv.index("--target")
            target_suffix = argv[i + 1].strip()
        except Exception:
            _eprint(
                "[coverage_map_pipeline] invalid --target usage. example: --target veritas_os/core/pipeline.py"
            )
    return target_suffix


# =========================================================
# Main
# =========================================================
def main(argv: Optional[List[str]] = None) -> int:
    """
    CLI-friendly main.
    tests constraints:
      - running as `python -m veritas_os.tools.coverage_map_pipeline` must return code 0
      - stdout must contain "[pipeline]" and "missing_lines="
      - even if coverage.json missing/invalid, still print missing_lines=
    """
    argv = argv or sys.argv[1:]
    target_suffix = _parse_target_suffix(argv)

    cov = load_cov()
    if not cov:
        # IMPORTANT: still print missing_lines= for isolated test expectation
        print("[pipeline] missing_lines=0 missing_branches=0 executed_branches=0")
        print("[pipeline] file=<coverage.json missing or invalid>")
        return 0

    try:
        target = find_target_file(cov, target_suffix=target_suffix)
    except SystemExit as e:
        # function-level tests want SystemExit, but CLI should not fail
        print("[pipeline] missing_lines=0 missing_branches=0 executed_branches=0")
        print(f"[pipeline] file=<target not found: *{target_suffix}>")
        # keep a hint (stdout ok)
        print(f"[pipeline] note={str(e)}")
        return 0

    files = cov.get("files", {})
    entry_raw = files.get(target, {}) if isinstance(files, dict) else {}
    entry = CovFileEntry.from_cov(entry_raw if isinstance(entry_raw, dict) else {})

    missing_lines = entry.missing_lines
    missing_branches = entry.missing_branches
    executed_branches = entry.executed_branches

    # read source: target key might be absolute; if not readable, try ROOT-relative
    src_path = Path(target)
    src = _safe_read_text(src_path)
    if src is None:
        alt = (ROOT / target).resolve()
        src = _safe_read_text(alt)

    defs: List[Tuple[str, int, int]] = []
    if src is not None:
        try:
            tree = ast.parse(src)
            defs = index_defs(tree)
        except Exception as e:
            _eprint(
                f"[coverage_map_pipeline] AST parse failed for {target}: {repr(e)[:160]}"
            )
            defs = []

    # group missing lines by owner
    by_owner: Dict[str, List[int]] = {}
    if defs:
        for ln in missing_lines:
            by_owner.setdefault(owner(defs, int(ln)), []).append(int(ln))
    else:
        # if AST unavailable, place all into module-level
        by_owner["<module-level>"] = list(sorted(set(int(x) for x in missing_lines)))

    # -----------------------------------------------------
    # Output
    # -----------------------------------------------------
    print(f"[pipeline] file={target}")
    print(
        f"[pipeline] missing_lines={len(missing_lines)} "
        f"missing_branches={len(missing_branches)} "
        f"executed_branches={len(executed_branches)}"
    )
    print("")

    # Owners
    items = sorted(by_owner.items(), key=lambda kv: len(set(kv[1])), reverse=True)
    if items:
        print("[top owners]")
        for name, lines in items[:MAX_OWNERS]:
            uniq = sorted(set(lines))
            print(f"- {name}: {len(uniq)} lines  [{_preview_ints(uniq)}]")
    else:
        print("[top owners] (none)")

    # Missing exit arcs
    exits = _exit_arcs(missing_branches)
    if exits:
        print("\n[missing exit arcs] (to=-1/0 means exit-ish)")
        for a, b in exits[:MAX_EXITS]:
            print(f"  {a} -> {b}")

    # Missing branches preview
    if missing_branches:
        print("\n[missing branches preview]")
        for a, b in missing_branches[:MAX_BRANCHES]:
            print(f"  {a} -> {b}")

    # If source was unreadable, say so (but do not fail)
    if src is None:
        print("\n[pipeline] source unreadable -> owner mapping may be incomplete")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())




