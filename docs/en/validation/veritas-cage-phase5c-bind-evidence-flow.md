# VERITAS / CAGE Phase 5C — BindReceipt / Evidence Flow

## Status

Phase 5C extends the merged Phase 5A/5B runtime proof with the first bounded
BindReceipt-to-evidence chain.

Expected successful result:

`READY_FOR_PHASE5D`

## Source pins

- VERITAS Phase 5B merged baseline:
  `0fc73e27b5d423102b9e4bb474169a815f1ab659`
- CAGE source:
  `fcb98bef0b5faea1afcc5a430148fe065b985ef4`

The proof is commit-pinned. It does not follow a moving CAGE branch.

## Runtime chain

The proof executes this bounded path:

`CAGE Provider03.validate_fria()`
→ loopback HTTP
→ VERITAS regulated-action decision
→ APPROVED finding carrying the VERITAS BindReceipt
→ CAGE `ingest_bind_receipt()`
→ CAGE RFC 8785 JCS / SHA-256 digest
→ CAGE `submit_evidence()`
→ loopback HTTP
→ VERITAS evidence endpoint
→ CAGE `EvidenceSeal`

No external business effect is performed.

## Hash domains

Two receipt hashes remain explicitly distinct.

### VERITAS BindReceipt self-hash

`bind_receipt_hash`

This is calculated over the VERITAS receipt body before the
`bind_receipt_hash` field is inserted.

### CAGE ingest digest

`cage_ingested_bind_receipt_digest`

This is calculated by the real CAGE Provider03
`ingest_bind_receipt()` method over the complete receipt, including the
VERITAS `bind_receipt_hash`.

The Phase 5C proof requires these values to be different.

The CAGE digest is a canonical integrity digest. Phase 5C does **not** claim
that it is:

- a digital signature;
- execution authority;
- receipt authenticity verification;
- durable CAGE persistence; or
- a TrustLog witness.

## Tamper probe

The proof changes one field after the VERITAS receipt self-hash is fixed.

It then requires:

- the CAGE ingest digest to change; and
- the unchanged VERITAS self-hash to fail local verification.

This proves that the two hash domains expose content changes without collapsing
their semantics.

## Evidence submission

The CAGE ingest digest is submitted through the real Provider03
`submit_evidence()` path.

The loopback VERITAS endpoint returns a deterministic seal bound to:

- the thread ID;
- the submitted CAGE digest; and
- `trustlog_proof_status = lineage_only`.

The returned CAGE `EvidenceSeal` is checked against that expected binding.

This is a local prototype acknowledgement. It is not represented as a
signature, production attestation, or TrustLog witness.

## Negative boundary

A REJECTED Provider03 path is also executed.

The proof requires:

- `admitted=False`; and
- no Phase 5C BindReceipt to be exposed in the rejected result.

Only the admitted fixture path carries the receipt into the Phase 5C evidence
chain.

## Claim boundary

Phase 5C does not claim:

- production deployment;
- a live customer integration;
- an external business effect;
- Google endorsement or corporate approval;
- a commercial integration;
- a TrustLog witness;
- CAGE-side signature verification of the VERITAS BindReceipt; or
- that Provider03 admission creates VERITAS execution authority.

The proof is limited to runtime interoperability and evidence-chain integrity
for the bounded loopback prototype.

## Evidence artifacts

The CI workflow writes:

- `phase5c-runtime-report.json`
- `run-manifest.json`

The run manifest binds the proof to the exact VERITAS and CAGE source SHAs and
records SHA-256 digests of the emitted JSON artifacts.
