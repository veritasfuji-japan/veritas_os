# Runtime Proof Evidence from CI

The **Runtime Proof Evidence** workflow creates downloadable, commit-linked
reviewer evidence for two independent proof boundaries. It does not join them
into an end-to-end execution chain.

## Proof boundaries

**Decision Pipeline PoC:** authenticated `POST /v1/decide` → controlled model
output at the central client seam → real decision/governance runtime → verified
encrypted TrustLog and replay → `DecideResponse` → **STOP**. It creates no
`ExecutionIntent`, invokes no Bind Boundary, and causes no external effect.

**External Bind Boundary PoC:** synthetic Decision Candidate → real bind
adjudication → real `WebhookBindAdapter` → simulated external effect → verified
`COMMITTED`, `BLOCKED`, and `ROLLED_BACK` evidence. Its decision stage is
`synthetic_fixture`; it does not claim that `/v1/decide` ran.

## Reviewer procedure

1. Open the GitHub Actions run for the repository commit.
2. Select **Runtime Proof Evidence**.
3. Download the `veritas-runtime-proof-evidence` artifact.
4. Inspect `decision-pipeline/report.json`, `external-bind/*`,
   `verification-report.json`, `ci-context.json`, `reviewer-summary.md`, and
   `runtime-proof-evidence-manifest.json`.
5. From the extracted artifact directory, verify every size and SHA-256 hash
   offline:

   ```bash
   python scripts/demo/verify_runtime_proof_evidence_manifest.py \
     artifacts/runtime-proof-evidence
   ```

The manifest's `manifest_hash` is SHA-256 over canonical JSON (sorted keys and
compact separators) of the manifest object with `manifest_hash` omitted. The
manifest enumerates all other bundle files and excludes itself to avoid a
recursive self-hash.

Proof evidence retains the PoCs' existing deterministic behavior. CI provenance
(`commit_sha`, ref, workflow run ID, and attempt) naturally varies, so the
downloaded ZIP is not claimed to be byte-identical across runs.

## Non-claims

This local CI bundle does **not** prove live model inference or live provider
behavior; production TrustLog infrastructure, PostgreSQL, KMS/WORM, deployment,
or readiness; execution authority from `/v1/decide`; Human Approval or Authority
Evidence; Decision Pipeline → Bind Boundary lineage; live bank or financial
institution integration; customer deployment; or regulatory approval or
certification.

