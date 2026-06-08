# Evidence Bundle Signature Verification Demo

This page fixes the reviewer-facing Evidence Bundle verification path for
external auditors and design partners. It is intentionally minimal: generate a
signed bundle, obtain the trusted Ed25519 public key from a separate trust
channel, then verify both file/hash integrity and manifest authenticity.

For a reviewer-facing sample transcript covering success, missing-key failure,
and wrong-key failure, see [Sample Evidence Bundle Verification Output](sample-evidence-bundle-verification-output.md).

## Security boundary

- Do not treat hash integrity as authenticity.
- Do not trust a public key solely because it is included in the bundle.
- Trusted public keys must come from a reviewer/operator trust channel.

Hash integrity proves that files match the hashes recorded in `manifest.json`.
It does not prove who created that manifest. Manifest signature verification is
the authenticity check, and it is only meaningful when the reviewer supplies a
trusted Ed25519 public key received out-of-band from the bundle.

## Minimal reproducible demo

### 1. Generate a signed evidence bundle

Use the same signing key management policy that applies to the handoff. The
example below is local/dev only; production handoff should use the configured
managed signer and distribute the public key through the reviewer/operator trust
channel.

```python
from pathlib import Path

from veritas_os.audit.evidence_bundle import generate_evidence_bundle
from veritas_os.security.signing import sign_payload_hash, store_keypair

private_key = Path("./demo_keys/manifest_ed25519_private.key")
public_key = Path("./demo_keys/manifest_ed25519_public.key")
store_keypair(private_key, public_key)

result = generate_evidence_bundle(
    bundle_type="decision",
    witness_ledger_path=Path("runtime/dev/logs/trustlog.jsonl"),
    output_dir=Path("./bundles"),
    request_ids=["req-12345"],
    signer_fn=lambda payload_hash: sign_payload_hash(payload_hash, private_key),
    signer_metadata={"type": "ed25519", "trust_channel": "operator-provided"},
)
print(result["bundle_dir"])
print(public_key)
```

The bundle directory contains `manifest.json` with `manifest_hash` and
`manifest_signature`. The public key path printed above is shown only for the
operator side of the demo. Reviewers must receive the trusted public key through
a separate channel, not by trusting a copy embedded in the bundle.

### 2. Obtain the trusted public key out-of-band

Before verification, the reviewer must obtain
`<trusted_ed25519_public_key>` from a reviewer/operator trust channel, such as:

- a pre-approved key registry entry;
- a signed operator handoff note outside the bundle transfer;
- an enterprise key-management or certificate-management process.

A public key that appears only inside the bundle is not enough, because an
attacker who can replace the bundle may also replace an included key.

### 3. Run strict verification

```bash
veritas-evidence-bundle verify \
  --bundle-dir <bundle_dir> \
  --public-key <trusted_ed25519_public_key> \
  --require-signature
```

The same strict command is also written into generated bundle handoff metadata
(`README.txt` and `ui_delivery_hook.json`) so reviewers and future UI delivery
flows use one consistent verification path.

### 4. Read the two PASS lines separately

Expected success output includes two separate checks:

```text
Evidence bundle verification: PASS
File/hash integrity: PASS
Manifest signature: PASS
```

Interpretation:

| Line | PASS means | PASS does not mean |
|---|---|---|
| `File/hash integrity` | The files in the bundle match the hashes recorded in `manifest.json`; no hash-covered file tampering was detected. | The manifest is authentic, or the signer is trusted. |
| `Manifest signature` | The manifest signature verifies under the trusted Ed25519 public key supplied by the reviewer. | The public key itself is trustworthy unless it came from the reviewer/operator trust channel. |

Reviewer-facing Evidence Bundle verification is established only when both
`File/hash integrity: PASS` and `Manifest signature: PASS` are present in the
strict verification run.

## Expected failure examples

| Scenario | Example command or setup | Expected result |
|---|---|---|
| Public key missing | Run the strict command without `--public-key`. | `FAIL`; authenticity cannot be verified because no trusted public key was supplied. |
| Wrong public key | Use a valid Ed25519 public key that did not sign the manifest. | `FAIL`; `Manifest signature` fails even when file/hash integrity may still pass. |
| Malformed signature | Replace `manifest_signature` with invalid base64 or invalid signature bytes. | `FAIL`; signature verification is reported as an authenticity error/failure. |
| Unsigned bundle under secure/prod posture | Set `VERITAS_POSTURE=secure` or `VERITAS_POSTURE=prod` and verify an unsigned bundle. | `FAIL`; secure/prod posture requires manifest signature verification and fails closed. |

A common failure shape is:

```text
Evidence bundle verification: FAIL
File/hash integrity: PASS
Manifest signature: FAIL
```

That output means the bundle files still match the manifest, but the manifest's
authenticity was not established. Do not accept it as reviewer-facing evidence
bundle verification.

## CI reviewer path

The evidence-bundle CLI tests lock the reviewer path by covering:

1. signed bundle generation;
2. successful strict verification with the correct trusted public key;
3. strict verification failure with the wrong public key;
4. secure/prod posture failure for unsigned bundles;
5. strict verification failure when the public key is missing;
6. malformed signature classification.

Run the focused test file:

```bash
pytest -q veritas_os/tests/test_evidence_bundle_cli.py
```
