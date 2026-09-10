# Consolidation 001 — Remove dead duplicate policy SHA-256 verifier

Status: **IMPLEMENTED IN PR — awaiting merge**  
Source main: `45231de4e75b5270450660fc0186886800e81f49`  
Audit source: Large Consolidation Audit Phase 2 / PR #2218

## Candidate

`veritas_os/policy/signing.py::verify_manifest_sha256`

Phase 2 classified this symbol as `DEAD_CANDIDATE / HIGH` after repository-wide
consumer analysis found no supported runtime, script or workflow consumer outside
the defining module.

## Change

This consolidation removes only the duplicate legacy verifier from
`veritas_os.policy.signing`.

It also removes:

- the now-unused `hmac` import;
- the now-unused `Path` import; and
- two unit tests that exercised only the removed duplicate helper.

A regression test now asserts that the duplicate verifier is no longer exposed.

## What remains unchanged

Legacy SHA-256 policy bundle compatibility is **not removed**.

The following path remains intact:

`compile_policy_to_bundle`
→ `sha256_manifest_hex`
→ `manifest.sig`
→ `runtime_adapter.verify_manifest_signature`
→ constant-time `hmac.compare_digest`

The existing integration test
`test_legacy_bundle_still_loads_without_key`
continues to verify the supported dev/staging compatibility path.

Ed25519 signing and verification behavior is unchanged.

Strict secure/prod posture requirements are unchanged.

## Audit-tool maintenance

The Phase 2 evidence generator now records whether the legacy symbol is
`PRESENT` or `REMOVED`, preventing the completed cleanup from remaining a stale
open recommendation.

The Phase 2 non-destructive changed-path guard is scoped to the dedicated Phase 2
audit branch. Without this correction, the merged audit workflow would reject
every later runtime consolidation PR simply because runtime code changed.

## Safety / claim boundary

This PR does not:

- remove legacy SHA-256 bundle generation;
- remove runtime SHA-256 verification;
- change secure/prod Ed25519 requirements;
- touch the controlled Decision-to-Effect frozen proof path;
- change migrations;
- change authorization, Bind, effect, reconciliation, receipt or outcome semantics.

## Expected simplification

One unused verifier implementation and its duplicate unit-only surface are removed.
The canonical supported SHA-256 verification responsibility remains centralized in
`veritas_os.policy.runtime_adapter.verify_manifest_signature`.
