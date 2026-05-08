# Type Safety Baseline

## Purpose

This page defines the initial type safety baseline for VERITAS OS.
The baseline is intentionally narrow and designed to establish a repeatable,
low-risk typecheck gate for diligence and commercial DD review.

## Current scope

Current command:

```bash
python -m scripts.quality.check_type_baseline
```

Current targets:

- `scripts/demo/one_day_poc_shared.py`
- `scripts/demo/one_day_poc_benchmark.py`
- `scripts/demo/one_day_poc_smoke.py`

## How to run

Install development dependencies and run:

```bash
pip install -e ".[dev]"
python -m scripts.quality.check_type_baseline
```

## What this proves

- A repeatable mypy baseline command exists for local developer/DD workflows.
- Selected PoC/demo helper paths pass static type checking.
- Type safety adoption is tracked as an explicit quality baseline.

## What this does not prove

- Full repository type coverage.
- Repository-wide strict typing.
- Strict typing for all governance modules.
- Runtime correctness certification.
- API compatibility certification.

## Expansion roadmap

This baseline is intentionally narrow and will expand in phases.
Planned next targets include:

- `veritas_os/core/value_core.py`
- `veritas_os/core/llm_client.py`
- bind/admissibility-related modules
- TrustLog and RBAC public surfaces

English documentation is canonical for policy/implementation interpretation.
