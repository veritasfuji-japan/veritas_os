# Runtime Data Policy

## Goal
A fresh `git clone` must contain **no user runtime state**:

- no decision history
- no persisted memory state
- no operational logs
- no generated datasets

## Runtime namespaces
VERITAS OS separates runtime storage by namespace:

- `runtime/dev/`
- `runtime/test/`
- `runtime/demo/`
- `runtime/prod/`

Each namespace keeps:

- `logs/` (trust log, meta logs, snapshots)
- `state/` (world state, memory state)
- `datasets/` (generated records)

Only `.gitkeep` files are tracked under `runtime/**`.

## Git-tracked vs. non-tracked data
Not tracked:

- `runtime/**` (except `.gitkeep`)
- `logs/**`
- `datasets/generated/**`
- `data/runtime/**`
- `storage/**`, `cache/**`
- `*.jsonl`, `*.sqlite`, `*.db`, `*.log`, `*.tmp`

Tracked:

- source code
- deterministic fixtures required for tests
- anonymized sample data under `veritas_os/sample_data/`

## Startup behavior requirements
- Startup must not seed prior decision history.
- Default boot must not inject generic historical `chosen_title` values.
- Test runtime should use an isolated temp namespace (`VERITAS_RUNTIME_ENV=test`).
- Demo/sample data must stay in dedicated sample paths and not auto-persist to runtime state.

## Cleanup command
```bash
python scripts/reset_repo_runtime.py --dry-run
python scripts/reset_repo_runtime.py --apply
```

`--dry-run` lists files/directories that would be removed.
`--apply` removes runtime artifacts and restores required `.gitkeep` directories.
