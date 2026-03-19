# Core Responsibility Boundaries

## Purpose

This document defines the current public contract, recommended extension points,
and compatibility layers for the core VERITAS modules that most often attract
structural complexity: Planner, Kernel, FUJI, and MemoryOS.

The goal is intentionally narrow:

- preserve the existing Planner / Kernel / FUJI / MemoryOS responsibility split;
- show contributors the recommended extension point before they edit a large
  compatibility-heavy file;
- make it easier for CI and code review to distinguish a valid extension from a
  boundary violation.

## Responsibility map

### Planner (`veritas_os.core.planner`)

**Owns**:
- turning user intent and context into candidate plans/tasks;
- plan normalization and safe shaping of planner output;
- read-only consultation of world and memory context.

**Public contract**:
- `plan_for_veritas_agi(...)`
- compatibility wrapper `generate_plan(...)`

**Preferred extension points**:
- `veritas_os.core.planner_normalization`
- `veritas_os.core.planner_json`
- `veritas_os.core.strategy`

**Compatibility layer notes**:
- legacy planner output normalization and test-compat wrappers remain in
  `planner.py`;
- new parsing or normalization logic should be added to helper modules before
  extending the main planner module.

### Kernel (`veritas_os.core.kernel`)

**Owns**:
- decision computation and orchestration of planner, FUJI, and memory inputs;
- decision shaping compatible with the current kernel response contract.

**Public contract**:
- `decide(...)`
- `run_kernel_qa(...)` via `veritas_os.core.kernel_qa`

**Preferred extension points**:
- `veritas_os.core.kernel_stages`
- `veritas_os.core.kernel_qa`
- `veritas_os.core.pipeline_contracts`

**Compatibility layer notes**:
- response-shape compatibility and fallback handling remain in `kernel.py`;
- new scoring or staging logic should move into stage/helper modules instead of
  deepening the main orchestrator.

### FUJI (`veritas_os.core.fuji`)

**Owns**:
- safety and policy evaluation for actions and generated content;
- FUJI-facing compatibility wrappers for historic policy APIs.

**Public contract**:
- `evaluate(...)`
- `validate_action(...)`
- `reload_policy(...)`

**Preferred extension points**:
- `veritas_os.core.fuji_policy`
- `veritas_os.core.fuji_policy_rollout`
- `veritas_os.core.fuji_helpers`
- `veritas_os.core.fuji_safety_head`

**Compatibility layer notes**:
- policy hot-reload and private-name aliases are retained for backward
  compatibility;
- new policy mechanics should live in the dedicated FUJI helper/policy modules.

### MemoryOS (`veritas_os.core.memory`)

**Owns**:
- public memory CRUD/search entry points;
- compatibility wiring into the shared `MemoryStore` implementation;
- memory-related security and lifecycle gates.

**Public contract**:
- `add(...)`
- `list_all(...)`
- `search(...)`
- `erase_user(...)`
- `MemoryStore`

**Preferred extension points**:
- `veritas_os.core.memory_store`
- `veritas_os.core.memory_helpers`
- `veritas_os.core.memory_search_helpers`
- `veritas_os.core.memory_summary_helpers`
- `veritas_os.core.memory_lifecycle`
- `veritas_os.core.memory_security`

**Compatibility layer notes**:
- `memory.py` intentionally keeps wrapper hooks required by tests and legacy
  callers;
- new storage/search/lifecycle behavior should be added to the helper modules
  above unless the public API itself must change.

## Change policy

When changing one of the four core modules above:

1. Prefer an existing helper/stage module over adding another branch to the main
   module.
2. If a change adds a new recommended extension point, update this document and
   the boundary checker guidance in `scripts/architecture/check_responsibility_boundaries.py`.
3. Do not move responsibilities across Planner / Kernel / FUJI / MemoryOS unless
   the architecture review explicitly approves the boundary change.

## Security note

Boundary violations are not only a maintainability issue. They can also weaken
reviewability of fail-closed behavior, audit paths, and memory/policy controls by
hiding security-sensitive logic inside unrelated compatibility layers. Run the
boundary checker in CI after touching these modules.
