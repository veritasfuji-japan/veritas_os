# Dependency Advisory Closure v1 — TASK-017F

Status: **CLOSURE CANDIDATE — merge requires green blocking dependency audits**

Reviewed Product baseline:

`5e2a8d84ed59540d4d4e21c1a96df9d212289426`

## Purpose

TASK-017F is the remaining dependency-advisory disposition item from the
2026-09-18 security review. The goal is to remove temporary audit exceptions,
record actual runtime reachability, and move the affected dependency set to
patched versions that can be enforced in CI.

## Observed pre-change audit result

The full-profile `pip-audit` run on the reviewed baseline reported six known
vulnerabilities in two packages:

- Starlette 0.49.1 / resolved transitive 0.49.x family:
  - `PYSEC-2026-161`
  - `PYSEC-2026-249`
  - `PYSEC-2026-248`
  - `PYSEC-2026-2281`
  - `PYSEC-2026-2280`
- Transformers 5.5.0:
  - `PYSEC-2026-3929`, fixed in Transformers 5.10.0.

## Disposition

This closure does not rely only on a non-reachability waiver.

The dependency set is moved to:

- FastAPI `0.137.2`
- Starlette `1.3.1` in the full-profile compatibility pin
- sentence-transformers `5.3.0`
- Transformers `5.10.0`

FastAPI 0.137.x accepts Starlette 1.x, removing the old resolver constraint
that required the temporary Starlette audit exceptions.

Both the core and full Python dependency audits are blocking after this change.
The prior `starlette_temp_ignores` list is removed.

## Reachability review

### Starlette

Repository search found no VERITAS runtime use of the reported vulnerable
application surfaces:

- `request.form()`
- `HTTPEndpoint`
- `StaticFiles`
- `request.url.hostname`

The project still uses FastAPI/Starlette as its ASGI stack, so the dependency
is upgraded rather than treated as harmless solely because those direct call
sites were absent.

### Transformers

VERITAS does not directly call `save_pretrained()`, which is the operation
named in the reported `PYSEC-2026-3929` path-traversal advisory.

The ML path loads `SentenceTransformer(model_name)` only when
`VERITAS_CAP_MEMORY_SENTENCE_TRANSFORMERS=1`; that capability defaults to
false. Even with that bounded reachability, the full-profile dependency is
upgraded to Transformers 5.10.0 instead of being audit-exempted.

sentence-transformers 5.3.0 declares Transformers `>=4.41.0,<6.0.0`, so
Transformers 5.10.0 remains within its supported dependency range.

## Closure gate

TASK-017F should be treated as closed only after the PR containing this record
has:

1. blocking core `pip-audit` success;
2. blocking full-profile `pip-audit` success;
3. the normal Python test matrix green;
4. Security Gates green;
5. CAGE Phase 5B / 5C proof workflows green; and
6. the exact merged Product SHA recorded in the company repository.

## Explicit non-claims

This closes the bounded dependency-advisory disposition only. It does not prove:

- production readiness;
- security certification;
- penetration-test completion;
- independent third-party assurance;
- absence of future dependency vulnerabilities; or
- customer production deployment.
