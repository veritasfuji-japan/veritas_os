#!/usr/bin/env python3
"""Check frontend-used BFF routes remain aligned with BFF policy and OpenAPI.

This lightweight guard addresses review feedback that critical-path checks are
already present while broader frontend-used API routes were not automatically
cross-checked against both the BFF allowlist and the published OpenAPI contract.
"""

from __future__ import annotations

import pathlib
import re
import sys
from dataclasses import dataclass

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
FRONTEND_ROOT = REPO_ROOT / "frontend"
ROUTE_AUTH_PATH = FRONTEND_ROOT / "app" / "api" / "veritas" / "[...path]" / "route-auth.ts"
OPENAPI_PATH = REPO_ROOT / "openapi.yaml"

FRONTEND_FILE_GLOBS = ("*.ts", "*.tsx", "*.js", "*.jsx")
SKIP_FILE_PATTERNS = (
    ".test.",
    ".spec.",
    "frontend/app/api/veritas/",
)

VERITAS_FETCH_CALL_PATTERN = re.compile(
    r"veritasFetch\(\s*([\"'`])(?P<path>/api/veritas/v1/[^\"'`]+)\1(?P<tail>[^\)]*)\)",
    re.DOTALL,
)
EVENTSOURCE_CALL_PATTERN = re.compile(
    r"EventSource\(\s*([\"'`])(?P<path>/api/veritas/v1/[^\"'`]+)\1",
)
METHOD_PATTERN = re.compile(r'method\s*:\s*[\"\'](?P<method>GET|POST|PUT|PATCH|DELETE)[\"\']')
ROUTE_POLICY_PATTERN = re.compile(
    r'pathPattern:\s*/\^(?P<pattern>.+?)\$/\s*,\s*method:\s*"(?P<method>[A-Z]+)"',
)


@dataclass(frozen=True)
class FrontendRouteUsage:
    """Represents one frontend API usage detected from static source code."""

    method: str
    raw_path: str
    file_path: pathlib.Path


@dataclass(frozen=True)
class RouteMatcher:
    """Holds one normalized route regex with its HTTP method."""

    method: str
    pattern: re.Pattern[str]


def should_skip(path: pathlib.Path) -> bool:
    """Return True if the frontend file should be excluded from extraction."""
    path_text = path.as_posix()
    return any(token in path_text for token in SKIP_FILE_PATTERNS)


def _normalize_frontend_path(raw_path: str) -> str:
    """Convert `/api/veritas/v1/...` usage into comparable `/v1/...` path syntax."""
    no_query = raw_path.split("?", maxsplit=1)[0]
    with_placeholders = re.sub(r"\$\{[^}]+\}", "{param}", no_query)
    return with_placeholders.replace("/api/veritas", "", 1)


def collect_frontend_usages() -> list[FrontendRouteUsage]:
    """Extract statically analyzable frontend API usages and inferred methods."""
    usages: list[FrontendRouteUsage] = []

    for ext in FRONTEND_FILE_GLOBS:
        for file_path in FRONTEND_ROOT.rglob(ext):
            if should_skip(file_path):
                continue

            content = file_path.read_text(encoding="utf-8")

            for match in VERITAS_FETCH_CALL_PATTERN.finditer(content):
                method_match = METHOD_PATTERN.search(match.group("tail"))
                method = method_match.group("method") if method_match else "GET"
                usages.append(
                    FrontendRouteUsage(
                        method=method,
                        raw_path=match.group("path"),
                        file_path=file_path,
                    )
                )

            for match in EVENTSOURCE_CALL_PATTERN.finditer(content):
                usages.append(
                    FrontendRouteUsage(
                        method="GET",
                        raw_path=match.group("path"),
                        file_path=file_path,
                    )
                )

    return usages


def load_bff_route_matchers() -> list[RouteMatcher]:
    """Parse route-auth.ts allowlist policies and convert them to regex matchers."""
    if not ROUTE_AUTH_PATH.exists():
        return []

    content = ROUTE_AUTH_PATH.read_text(encoding="utf-8")
    matchers: list[RouteMatcher] = []

    for match in ROUTE_POLICY_PATTERN.finditer(content):
        js_pattern = match.group("pattern")
        python_pattern = "^/" + js_pattern.replace(r"\/", "/") + "$"
        matchers.append(
            RouteMatcher(
                method=match.group("method"),
                pattern=re.compile(python_pattern),
            )
        )

    return matchers


def load_openapi_route_matchers() -> list[RouteMatcher]:
    """Load OpenAPI paths and methods as regex matchers for path comparison."""
    if not OPENAPI_PATH.exists():
        return []

    spec = yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))
    paths = spec.get("paths", {}) if isinstance(spec, dict) else {}

    matchers: list[RouteMatcher] = []
    for path, operations in paths.items():
        if not isinstance(path, str) or not isinstance(operations, dict):
            continue

        normalized_path = re.sub(r"\{[^}]+\}", "[^/]+", path)
        pattern = re.compile(f"^{normalized_path}$")

        for method in operations.keys():
            if not isinstance(method, str):
                continue
            if method.lower() not in {"get", "post", "put", "patch", "delete"}:
                continue
            matchers.append(RouteMatcher(method=method.upper(), pattern=pattern))

    return matchers




def _display_source_path(file_path: pathlib.Path) -> str:
    """Return repo-relative source path when possible, else keep original string."""
    try:
        return str(file_path.relative_to(REPO_ROOT))
    except ValueError:
        return str(file_path)

def _matches_any(path: str, method: str, matchers: list[RouteMatcher]) -> bool:
    """Return True if any matcher supports the given method/path combination."""
    return any(m.method == method and m.pattern.match(path) for m in matchers)


def validate_consistency(
    usages: list[FrontendRouteUsage],
    bff_matchers: list[RouteMatcher],
    openapi_matchers: list[RouteMatcher],
) -> list[str]:
    """Validate frontend usages are reachable via BFF and documented in OpenAPI."""
    errors: list[str] = []

    seen: set[tuple[str, str]] = set()
    for usage in usages:
        normalized_path = _normalize_frontend_path(usage.raw_path)
        usage_key = (usage.method, normalized_path)
        if usage_key in seen:
            continue
        seen.add(usage_key)

        if not _matches_any(normalized_path, usage.method, bff_matchers):
            errors.append(
                "BFF allowlist missing "
                f"{usage.method} {normalized_path} "
                f"(source={_display_source_path(usage.file_path)})"
            )

        if not _matches_any(normalized_path, usage.method, openapi_matchers):
            errors.append(
                "OpenAPI path/method missing "
                f"{usage.method} {normalized_path} "
                f"(source={_display_source_path(usage.file_path)})"
            )

    return errors


def main() -> int:
    """Run the frontend API contract consistency check."""
    usages = collect_frontend_usages()
    if not usages:
        print("[DOCS] No frontend API usages found under frontend/; check extractor patterns.")
        return 1

    bff_matchers = load_bff_route_matchers()
    if not bff_matchers:
        print(f"[DOCS] Missing or unreadable BFF route matrix: {ROUTE_AUTH_PATH}")
        return 1

    openapi_matchers = load_openapi_route_matchers()
    if not openapi_matchers:
        print(f"[DOCS] Missing or unreadable OpenAPI document: {OPENAPI_PATH}")
        return 1

    errors = validate_consistency(usages, bff_matchers, openapi_matchers)
    if errors:
        print("[DOCS] Frontend/BFF/OpenAPI consistency drift detected:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Frontend/BFF/OpenAPI consistency checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
