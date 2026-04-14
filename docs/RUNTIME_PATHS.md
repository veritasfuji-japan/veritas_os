# Runtime Artifact Paths

All runtime-generated files (logs, state, data, reports) are stored under a
single canonical tree inside the repository:

```
runtime/
  <namespace>/          # dev (default) | test | demo | prod
    logs/               # trust_log.jsonl, decide_*.json, meta_log.jsonl, persona.json
      DASH/             # shadow / observe mode decision logs
      doctor/           # doctor_auto.log, doctor_auto.err, doctor_report.json
    data/               # memory.json, world_state.json, value_stats.json, kv.sqlite3
    datasets/           # training datasets
    benchmarks/         # benchmark result JSONs
    reports/            # generated HTML / JSON reports
    models/             # trained model artifacts (ONNX, metadata)
```

## Environment Variable Overrides

| Variable | Description | Default |
|---|---|---|
| `VERITAS_RUNTIME_ROOT` | Override the entire runtime root directory | `<repo>/runtime` |
| `VERITAS_RUNTIME_NAMESPACE` | Override the namespace subdirectory | `dev` |
| `VERITAS_ENV` | Alternative to RUNTIME_NAMESPACE (mapped: production→prod, staging→dev, etc.) | — |
| `VERITAS_LOG_ROOT` | Override log directory specifically | `runtime/<ns>/logs` |
| `VERITAS_DATA_DIR` | Override data directory specifically | `runtime/<ns>/data` |
| `VERITAS_ENCRYPTED_LOG_ROOT` | Encrypted log mount point (highest priority for logs) | — |
| `VERITAS_WORLD_PATH` | Override world state file path directly | `runtime/<ns>/data/world_state.json` |
| `VERITAS_MEMORY_PATH` | Override memory file path directly | `runtime/<ns>/data/memory.json` |

## Design Principles

1. **Repo-local by default**: No files are created outside the repository unless
   explicitly configured via environment variables.

2. **No stray directories**: Legacy paths like `scripts/logs`, `.veritas/`,
   `~/veritas`, or `~/.veritas_os` are no longer used as defaults.

3. **Single source of truth**: Path logic is centralized in:
   - `veritas_os/logging/paths.py` — canonical path constants for the core system
   - `veritas_os/scripts/_runtime_paths.py` — shared path constants for scripts
   - `veritas_os/core/config.py` — `VeritasConfig` dataclass (uses same resolution)

4. **Namespace separation**: Different environments (dev, test, prod) get
   isolated directory trees under `runtime/`.

5. **Explicit override required**: Writing outside the repository requires
   setting environment variables deliberately.

## Cleaning Up

```bash
# Preview what would be removed
python scripts/reset_repo_runtime.py --dry-run

# Remove all runtime artifacts (preserves .gitkeep placeholders)
python scripts/reset_repo_runtime.py --apply
```

## Migration from Legacy Paths

If you have existing runtime artifacts in legacy locations, move them to the
canonical structure:

| Legacy Location | New Location |
|---|---|
| `veritas_os/scripts/logs/` | `runtime/dev/logs/` |
| `veritas_os/scripts/logs/doctor_report.json` | `runtime/dev/logs/doctor/doctor_report.json` |
| `veritas_os/scripts/logs/benchmarks/` | `runtime/dev/benchmarks/` |
| `veritas_os/.veritas/memory.json` | `runtime/dev/data/memory.json` |
| `veritas_os/.veritas/value_stats.json` | `runtime/dev/data/value_stats.json` |
| `veritas_os/reports/` | `runtime/dev/reports/` |
| `veritas_os/core/models/` | `runtime/dev/models/` |
| `~/veritas/` | `runtime/dev/data/` |
| `~/.veritas_os/` | `runtime/dev/` |
