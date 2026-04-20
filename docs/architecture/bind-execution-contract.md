# Native Bind Execution Contract (Minimal Adapter Path)

This change introduces the first native adapter-based bind-boundary execution contract in VERITAS.

## What this PR adds

- A **small internal adapter contract** for bind-boundary execution primitives:
  snapshot, fingerprint, authority/constraint/risk checks, apply, verify, revert, and target description.
- A deterministic **in-memory reference adapter** for unit testing orchestration logic.
- A narrow orchestration path:
  snapshot -> admissibility check -> apply -> verify -> commit/revert -> BindReceipt construction.

## What this PR does not change

- **FUJI semantics are unchanged**. FUJI remains the final safety/policy gate in decision flow.
- **Continuation Runtime semantics are unchanged**. The orchestration reuses its deterministic admissibility evaluator and does not redefine continuation behavior.
- No Mission Control UI changes.
- No new parallel audit/logging framework.
- No broad workflow engine or runtime rewrite.

## Why this exists

This is a proving substrate for governing the bind boundary natively while keeping decision artifacts primary.
The deterministic reference adapter exists to validate fail-closed orchestration behavior before any production integration.
