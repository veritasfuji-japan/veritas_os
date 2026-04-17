# External Audit Readiness Pack

> VERITAS OS v2.0.0 — External audit evidence generation, verification,
> and third-party timestamping infrastructure.

## Overview

The External Audit Readiness Pack extends VERITAS OS from an internal audit
platform to one that can directly serve external auditors, customers, and
legal teams.  It adds three integrated capabilities:

1. **RFC 3161 TSA Anchoring** — Third-party timestamp proof via standard TSA services
2. **Standalone TrustLog Verifier** — Independent CLI for offline evidence verification
3. **Evidence Bundle** — Deterministic, signed archive format for audit delivery

These integrate naturally with the existing two-ledger TrustLog architecture
(encrypted full ledger + signed witness ledger), Ed25519 signing, WORM
mirrors, and posture governance.

---

## 1. RFC 3161 TSA Backend

### What it does

Sends the TrustLog chain head digest to an RFC 3161 Time-Stamp Authority
and stores the returned timestamp receipt in each witness entry.  This
provides legally recognized, third-party proof that a decision existed at
a specific point in time.

### Why TSA (not blockchain)

- **Standard**: RFC 3161 is an IETF standard supported by all major CAs
- **Legal**: Legally recognized in most jurisdictions (eIDAS, ESIGN Act)
- **Simple**: HTTP POST + DER parsing, no node infrastructure
- **Auditable**: Receipts are self-contained, verifiable with OpenSSL
- **Cost-effective**: Many CAs offer free or low-cost TSA endpoints

### Configuration

```bash
# Enable TSA anchoring
VERITAS_TRUSTLOG_ANCHOR_BACKEND=tsa

# TSA endpoint URL (required)
VERITAS_TRUSTLOG_TSA_URL=https://freetsa.org/tsr

# Request timeout (default: 10 seconds)
VERITAS_TRUSTLOG_TSA_TIMEOUT_SECONDS=10

# Custom CA bundle for TSA server certificate verification (optional)
VERITAS_TRUSTLOG_TSA_CA_BUNDLE=/path/to/tsa-ca-bundle.pem

# Authorization header for authenticated TSA endpoints (optional)
VERITAS_TRUSTLOG_TSA_AUTH_HEADER=Bearer <token>
```

### Witness Entry Fields

When TSA is active, each witness entry includes:

```json
{
  "anchor_backend": "tsa",
  "anchor_status": "anchored",
  "anchor_receipt": {
    "backend": "tsa",
    "status": "anchored",
    "anchored_hash": "sha256...",
    "anchored_at": "2024-01-01T00:00:00Z",
    "receipt_id": "uuid7...",
    "receipt_location": "https://tsa.example.com/tsr",
    "receipt_payload_hash": "sha256_of_raw_receipt",
    "external_timestamp": "2024-01-01T00:00:00Z",
    "details": {
      "raw_receipt_b64": "base64_encoded_tsr...",
      "status_code": 0,
      "status_text": "granted",
      "receipt_size_bytes": 1234,
      "nonce": 12345678
    }
  }
}
```

### Verifying TSA Receipts

TSA receipts can be verified in three ways:

1. **VERITAS verifier** (automatic — checks structure and hash integrity)
2. **OpenSSL** (manual — full cryptographic verification):
   ```bash
   echo '<raw_receipt_b64>' | base64 -d > receipt.tsr
   openssl ts -verify -in receipt.tsr -CAfile tsa-ca-bundle.pem -data digest.bin
   ```
3. **Evidence Bundle** includes receipts for auditor-side verification

---

## 2. Standalone TrustLog Verifier

### What it does

A self-contained CLI tool that verifies TrustLog integrity without the
VERITAS application server.  Auditors can run it on static evidence files.

### Usage

```bash
# Install
pip install veritas-os[signing]

# Verify witness ledger only
veritas-trustlog-verify --witness-ledger trustlog.jsonl

# Verify with JSON output
veritas-trustlog-verify --witness-ledger trustlog.jsonl --json

# Verify both ledgers
veritas-trustlog-verify \
  --full-ledger trust_log.jsonl \
  --witness-ledger trustlog.jsonl \
  --public-key keys/trustlog_ed25519_public.key

# Python module entry point
python -m veritas_os.cli.verify_trustlog --witness-ledger trustlog.jsonl --json
```

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All checks passed |
| 1 | Verification failures detected |
| 2 | Invalid arguments or runtime error |

### Docker Usage

```bash
# Build verifier image
docker build -f Dockerfile.verifier -t veritas-trustlog-verifier .

# Run on evidence directory
docker run --rm \
  -v /path/to/evidence:/evidence:ro \
  veritas-trustlog-verifier \
  --witness-ledger /evidence/trustlog.jsonl \
  --public-key /evidence/keys/trustlog_ed25519_public.key \
  --json
```

### JSON Output Schema

```json
{
  "ok": true,
  "errors": [],
  "notes": [],
  "total_errors": 0,
  "total_notes": 0,
  "witness_ledger": {
    "total_entries": 100,
    "valid_entries": 100,
    "invalid_entries": 0,
    "chain_ok": true,
    "signature_ok": true,
    "linkage_ok": true,
    "mirror_ok": true
  }
}
```

---

## 3. Evidence Bundle

### What it does

Generates deterministic, signed evidence bundles from TrustLog data.
Each bundle is a self-contained directory (or `.tar.gz`) containing all
cryptographic evidence needed to independently verify decisions.

### Bundle Types

| Type | Description | Use Case |
|------|-------------|----------|
| `decision` | Single decision | Customer audit of one decision |
| `incident` | Time range / IDs | Incident investigation |
| `release` | All decisions in release | Release audit / SOX compliance |

### Bundle Contents

```
veritas_bundle_decision_<uuid>/
├── manifest.json              # SHA-256 hashes, metadata, optional signature
├── witness_entries.jsonl       # Witness ledger slice
├── decision_record.json        # Auditor-facing single-decision snapshot
├── acceptance_checklist.json   # Submission acceptance contract checks
├── README.txt                  # Human-readable review and handoff guide
├── ui_delivery_hook.json       # Backend hook for future UI integrations
├── verification_report.json   # Automated verification results
├── signer_metadata.json       # Ed25519 signer info
├── anchor_receipts/
│   └── anchor_receipts.json   # TSA/local anchor receipts
├── mirror_receipts/
│   └── mirror_receipts.json   # S3/WORM mirror receipts
├── artifacts/
│   └── artifact_linkage.json  # Full payload linkage metadata
├── governance_identity.json   # Policy version, governance info
├── incident_metadata.json     # (incident bundles only)
└── release_provenance.json    # (release bundles only)
```

`decision_record.json` is the canonical external handoff artifact for one
decision. It includes:

- full compact `decision_payload`
- `gate_decision` / `business_decision` / `next_action`
- `required_evidence` / `human_review_required`
- TrustLog references (`payload_hash`, `full_payload_hash`, signature/anchor/mirror)
- verification pointer (`verification_report.json`)
- provenance metadata + runtime context (posture/backend/version)

#### decision_record contract profiles

- **minimum set** (baseline external review): `decision_payload`,
  `gate_decision`, `business_decision`, `next_action`,
  `trustlog_references`, `verification`, `provenance`.
- **full set** (legal/deep forensic review): minimum set +
  `required_evidence`, `human_review_required`, `runtime_context`.

`veritas-evidence-bundle generate` defaults to minimum set and can opt into
full set with `--decision-record-profile full`.

#### Acceptance checklist contract

Each bundle now ships `acceptance_checklist.json` with machine-readable checks:

- manifest + file hash integrity material present
- witness entries present
- verification report present
- decision_record contract profile declared (decision bundles)

This checklist is intended to be the explicit pre-submission gate for
external auditors/customers/legal.

### Generating Bundles

```python
from veritas_os.audit.evidence_bundle import generate_evidence_bundle

# Single decision bundle
result = generate_evidence_bundle(
    bundle_type="decision",
    witness_ledger_path=Path("trustlog.jsonl"),
    output_dir=Path("./bundles"),
    request_ids=["req-12345"],
)

# Incident bundle (time range)
result = generate_evidence_bundle(
    bundle_type="incident",
    witness_ledger_path=Path("trustlog.jsonl"),
    output_dir=Path("./bundles"),
    time_range_start="2024-01-01T00:00:00Z",
    time_range_end="2024-01-02T00:00:00Z",
    incident_metadata={"incident_id": "INC-001"},
)

# Release bundle with signed manifest
result = generate_evidence_bundle(
    bundle_type="release",
    witness_ledger_path=Path("trustlog.jsonl"),
    output_dir=Path("./bundles"),
    release_provenance={"version": "2.0.0", "git_sha": "abc123"},
    signer_fn=signer.sign_payload_hash,
    signer_metadata=signer_meta,
)
```

### Verifying Bundles

```python
from veritas_os.audit.verify_bundle import verify_evidence_bundle

result = verify_evidence_bundle(Path("veritas_bundle_decision_<uuid>"))

if result["ok"]:
    print("Bundle integrity verified")
else:
    print(f"Tampered: {result['tampered']}")
    for error in result["errors"]:
        print(f"  - {error}")
```

### CLI (recommended for ops runbooks)

```bash
veritas-evidence-bundle generate \
  --bundle-type decision \
  --witness-ledger runtime/dev/logs/trustlog.jsonl \
  --output-dir ./bundles \
  --request-id req-12345 \
  --decision-record-profile full

veritas-evidence-bundle verify \
  --bundle-dir ./bundles/veritas_bundle_decision_<uuid>
```

### Financial template sample bundle

Representative fixture:

- `veritas_os/benchmarks/evidence/fixtures/financial_template_bundle_sample.json`

### Creating Archives

```python
from veritas_os.audit.evidence_bundle import create_bundle_archive

archive = create_bundle_archive(Path("veritas_bundle_decision_<uuid>"))
# → veritas_bundle_decision_<uuid>.tar.gz
```

### External delivery policy (auditor/customer/legal)

1. Generate bundle with explicit decision_record profile (`minimum` or `full`).
2. Verify with `veritas-evidence-bundle verify`.
3. Confirm all `acceptance_checklist.json` items are PASS.
4. Include `README.txt` unchanged in handoff package.
5. Deliver as read-only `.tar.gz` plus detached transfer checksum.

Security note: Any tampering with `manifest.json`, `witness_entries.jsonl`,
or hash-referenced files invalidates the delivery contract and requires
regeneration from TrustLog source data.

---

## 4. Posture Integration

### Secure/Prod Posture

In `secure` and `prod` posture:

- `trustlog_transparency_required` is **ON** by default
- When transparency is required:
  - `noop` anchor backend is rejected
  - `local` and `tsa` backends are accepted
  - TSA failures cause write failures (fail-closed)

### Dev/Staging

- All anchor backends are accepted
- TSA failures are warnings, not errors
- Bundles can be generated without signing

### Recommended Production Configuration

```bash
VERITAS_POSTURE=prod
VERITAS_TRUSTLOG_ANCHOR_BACKEND=tsa
VERITAS_TRUSTLOG_TSA_URL=https://your-tsa-provider.com/tsr
VERITAS_TRUSTLOG_MIRROR_BACKEND=s3_object_lock
VERITAS_TRUSTLOG_SIGNER_BACKEND=aws_kms
VERITAS_TRUSTLOG_TRANSPARENCY_REQUIRED=1
VERITAS_TRUSTLOG_WORM_HARD_FAIL=1
```

---

## 5. Known Limitations

1. **TSA receipt full cryptographic verification** requires OpenSSL or a
   dedicated ASN.1 library.  The built-in verifier checks structure and
   hash integrity but does not perform full X.509 chain validation of the
   TSA certificate.

2. **Evidence Bundles** currently support directory-based and tar.gz format.
   ZIP format is not implemented.

3. **Remote S3 verification** in bundles requires the verifier to have AWS
   credentials.  Offline verification uses local receipt data only.

4. **Bundle size** is not currently constrained.  Very large release bundles
   should be split manually if needed.

---

## 6. Future Work

- Full ASN.1 library integration for TSA receipt cryptographic validation
- S3 remote verification within evidence bundles
- Bundle format for ZIP archives
- Web UI for bundle generation in Mission Control
- Automated bundle generation in release pipeline
- Bundle streaming for large-scale audits
- Multi-signer bundle attestation
- Bundle compression and size optimization

---

## 7. New Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `VERITAS_TRUSTLOG_ANCHOR_BACKEND` | No | `local` | Anchor backend: `local`, `noop`, or `tsa` |
| `VERITAS_TRUSTLOG_TSA_URL` | When `tsa` | — | RFC 3161 TSA endpoint URL |
| `VERITAS_TRUSTLOG_TSA_TIMEOUT_SECONDS` | No | `10` | TSA request timeout |
| `VERITAS_TRUSTLOG_TSA_CA_BUNDLE` | No | — | CA bundle for TSA cert verification |
| `VERITAS_TRUSTLOG_TSA_AUTH_HEADER` | No | — | Authorization header for TSA |

---

*Last updated: 2026-04-11*
