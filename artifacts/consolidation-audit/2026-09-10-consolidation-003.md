# Consolidation 003 — TrustLog CLI Compatibility Helpers

Status: **IMPLEMENTED IN PR — awaiting merge**  
Source main: `5aab514bb070fd597e374ee8c96c34f35cd0c511`  
Audit basis: PR #2218 Phase 2 TrustLog role matrix

## Objective

Remove script-local backward-compatibility helpers that are not required by the
supported TrustLog CLI path, while preserving all active unified verifier
behavior.

## Removed helpers

From `veritas_os/scripts/verify_trust_log.py`:

- `verify_entries`
- `compute_hash`
- script-local `iter_entries`

The helpers were previously retained for direct test/tool imports. Repository
consumer review found no supported runtime or CLI path depending on them.

## Preserved active CLI path

The supported command remains:

`python -m veritas_os.scripts.verify_trust_log`

Its execution path remains:

`main()`
→ `_read_all_entries(...)`
→ `veritas_os.audit.trustlog_verify.verify_trustlogs(...)`
→ full ledger + witness verification

The following active verifier surfaces are unchanged:

- `veritas_os.audit.trustlog_verify.verify_trustlogs`
- `veritas_os.audit.trustlog_verify.verify_full_ledger`
- `veritas_os.audit.trustlog_verify.verify_witness_ledger`
- `veritas_os.logging.trust_log.verify_trust_log`

## Tests

Removed:

`veritas_os/tests/test_verify_trust_log_script.py`

That file tested only the deleted compatibility-helper surface.

Added:

`veritas_os/tests/test_verify_trust_log_cli_surface.py`

The replacement guard proves:

- the three compatibility helpers are no longer exposed;
- `main()` delegates to the unified `verify_trustlogs` path;
- `full_log_path`, witness entries, signature verifier, and `max_entries` are
  forwarded correctly; and
- successful unified verification still produces CLI success status.

The existing subprocess-based unified CLI test remains unchanged and continues
to verify the public module command and stable JSON output fields.

## Imports simplified

The removed helpers also eliminate script-local dependencies on:

- `hashlib`
- `Any`
- `Iterable`
- `Optional`

The CLI still retains `json`, `Path`, signed-witness loading, signature
verification, and the unified verifier dependency.

## Historical audit note

The Phase 2 audit artifact remains a historical snapshot that classified
`verify_entries` / `compute_hash` as `COMPATIBILITY_CANDIDATE` before this
approved consolidation. This record is the resolution artifact for that
candidate rather than rewriting the earlier audit snapshot.

## Risk boundary

Risk remains LOW–MEDIUM because an unknown external consumer could theoretically
have imported these script-local helper names. They were not part of the active
in-repository CLI execution path.

This PR does not:

- change full-ledger verification semantics;
- change witness verification semantics;
- change cryptography or hash formats;
- change mirror verification;
- change TrustLog persistence;
- claim TrustLog exactly-once publication;
- alter authorization, Bind, external effect, reconciliation, receipt, or
  outcome semantics; or
- alter the frozen controlled Decision-to-Effect proof architecture.

## Validation requirement

Full CI, unified TrustLog CLI tests, governance checks, security checks, and the
frozen reproducible Decision-to-Effect proof must pass before merge.
