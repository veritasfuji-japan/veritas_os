# VERITAS OS — Cross-VM Audit Custody Rehearsal v0.1

**Status:** Locally executed; operator-observed evidence, **not** an independent audit  
**Observation date:** 2026-11-06 JST (observation metadata captured at 2026-11-05T15:32:03+00:00)  
**Code revision:** `6c2f5ef264ee1d0de4970228a03653262e6c9663`  
**Scope:** Synthetic **local audit-history continuity** only  
**Administrative independence demonstrated:** **No**  
**Replayed and recorded test suite:** **7/7 PASS** (per operator-provided terminal output)

## Executive summary

VERITAS OS was exercised in two Ubuntu Linux VMs running under one Mac/UTM host. VM-A held a PostgreSQL audit registry and verifier. VM-B held an Ed25519-signed checkpoint receipt, a SQLite custody-head store, and a read-only HTTPS endpoint. The verifier used a locally provisioned CA bundle, exact TLS hostname, pinned signer public key, and minimum sequence floor to authenticate and compare the custody head, signed checkpoint, and current audit-registry contents.

The operator observed **seven out of seven expected outcomes** in a repeatable local verifier suite; the output was saved in a JSON evidence file. Separately, an interactive outage test rejected a stopped HTTPS service and a recovery test passed after the service restarted. A historical-packet removal test returned `HISTORY_DIVERGED` even though the modified database retained one packet and one observation.

These are **scenario-specific functional findings**, not claims of independently administered custody, immutable storage, authentic external source events, or production security assurance.

## Architecture and trust boundaries

1. **VM-A — audit source and verifier:** PostgreSQL audit registry, signed-checkpoint input copies, verifier-controlled trust configuration, and the cross-host verification CLI.
2. **VM-B — audit custody:** separate OS roles for signing, custody-store ownership, and read-only HTTPS service; Ed25519 signed checkpoint receipt; SQLite custody head; TLS endpoint at the configured hostname.
3. **Verification sequence:** HTTPS CA/hostname validation → remote custody-head retrieval → signer-key and sequence-floor checks → pinned receipt digest and signature validation → signed checkpoint check → current PostgreSQL registry-history comparison.

**Critical qualification:** Both VMs share a physical Mac and the same underlying administrative environment. The rehearsal did not show resistance to a common host administrator or establish independently controlled trust domains. A sequence floor of `1` was verifier-supplied for the baseline; the rejection of floor `2` tests a guard condition and is **not** an actual rollback of the custody SQLite store.

## Evidence-backed test matrix

The following summarizes the operator-provided output from the **seven-case recorded rerun**, not a direct inspection by the report author of the full private evidence bytes.

| Test ID | Scenario | Reported verdict | `verified` | Exit | Result |
|---|---|---|---|---:|---|
| `NORMAL` | Registry matches signed checkpoint | `HISTORY_UNCHANGED_UNAUTHENTICATED` | `true` | `0` | PASS |
| `ALL_DELETED` | All archived synthetic audit observations removed from a test DB | `INCOMPLETE` | `false` | `2` | PASS |
| `HISTORY_DIVERGED` | Original signed-baseline packet deleted; newer packet retained | `HISTORY_DIVERGED` | `false` | `2` | PASS |
| `SEQUENCE_ROLLBACK` | Independently supplied minimum sequence `2` exceeds served head `1` | `REMOTE_HEAD_SEQUENCE_ROLLBACK` | `false` | `2` | PASS |
| `SIGNER_MISMATCH` | Verifier configured with wrong signer-public-key pin | `REMOTE_SIGNER_PIN_MISMATCH` | `false` | `2` | PASS |
| `RECEIPT_INVALID` | Receipt signature field altered without recomputing receipt digest | `RECEIPT_INVALID` | `false` | `2` | PASS |
| `HEAD_MISMATCH` | Altered receipt with recomputed internal digest | `CUSTODY_HEAD_MISMATCH` | `false` | `2` | PASS |

### Additional interactive observations

These were operator-run separately and **are not included in the seven-case JSON rerun**:

- **Baseline extension:** A second synthetic packet was added while the original remained; checkpoint continuity verification returned `HISTORY_EXTENDED_UNAUTHENTICATED`, exit `0`.
- **Service outage:** After the custody HTTPS listener was stopped, the cross-host CLI returned `REMOTE_ANCHOR_UNAVAILABLE`, `verified: false`, exit `2`.
- **Service recovery:** After restarting the same custody listener, the CLI returned `HISTORY_UNCHANGED_UNAUTHENTICATED`, `verified: true`, exit `0`.

Destructive PostgreSQL tests were carried out against isolated test database copies; the original baseline database retained its one synthetic audit packet and one observation. The partial-deletion database also contained one packet and one observation after deleting the older, checkpoint-covered packet: equality of **counts** alone was not enough to produce a successful check.

## Evidence inventory and SHA-256 pins

The operator reported successful `sha256sum -c` verification (`OK` for both records) of the following private, locally held evidence files. The filenames and hashes are included to facilitate later comparison, **not** to imply public access to the underlying bytes or independent timestamping.

| Local evidence object | SHA-256 |
|---|---|
| `cross-host-observation-v0_1.txt` | `c713437e0ebde759dfe821effcf48e29405acb94627e7d31a3297cc81ae893c8` |
| `cross-host-verdicts-v0_1.json` | `511d911bb77dbe1a5409d15568ed6878dbbc0c0df1053fe0445546825b49eb60` |
| `SHA256SUMS.v0_1` (manifest itself) | `d8523ec0a8cb9e15d703cf269949e6b1fcefe4244b9b84700886762fd787c4d3` |

Additional checkpoint/reference identity values reported in the local observation:

| Object | Canonical SHA-256 digest |
|---|---|
| `reference-seq1.json` | `7c789ae8c45b12e9c09e9a1b4a582628587afea7ea811d6947774a9a629c3176` |
| `receipt-seq1.json` | `37cb6f449da0330a682aed9f1ac4a0fe7a27957c92e14c361ce312e3d6862858` |

The checkpoint and receipt digests above are calculated over canonicalized JSON objects using VERITAS's `_digest` routine. They are **not presented as raw file-byte hashes**. In contrast, the evidence-file and manifest SHA-256 values are from `sha256sum` over their exact stored bytes. The operator also recorded the CA certificate fingerprint privately, but it is omitted from this public summary.

**Evidence limitations:** The JSON and observation text have not been inspected independently by the report author. Local hashing confirms consistency with a recorded digest, not the origin, timing, confidentiality, or independent custody of evidence. GitHub publication of these digests is useful for comparison but is not a WORM store or independent timestamp authority.

## Interpretation and limits

### Supported by the observed scenarios

- Real HTTPS communication between the two local VMs with a configured CA trust and expected TLS hostname.
- Successful comparison of a signed checkpoint against a live PostgreSQL audit registry in the intact case.
- Failure outcomes for tested complete deletion, partial historical deletion, wrong minimum sequence, wrong signer pin, and two manipulated-receipt variants.
- Fail-closed behavior when the custody service was unavailable, plus a successful normal check after service restart.

### Not established

- Independence of hardware, administrators, signers, trust roots, or security domains.
- Source-event authenticity, completeness of original observations, or authorization of any external action.
- WORM/append-only protection, independently trusted timestamps, external reviewer attestation, or production-grade secret custody.
- Recovery from a real custody-store rollback, especially if the verifier loses its independently held highest-seen sequence floor.
- Direct negative-path proof of an Ed25519 cryptographic signature rejection: the receipt tampering trials failed at earlier format/hash or remote-head binding checks.
- Resistance to a malicious party who controls both the audit registry and the trusted custody service or their common host.

The verdict `HISTORY_UNCHANGED_UNAUTHENTICATED` concerns **local audit-history continuity**; it does not authenticate the underlying source event or imply that an effect was authorized or executed.

## Required gates before independent/production assurance

1. Reproduce the scenarios on **separately controlled physical or cloud hosts** with independent administrators and credential custody.
2. Preserve verification pins (CA, signer key, minimum accepted sequence) outside the audited database and independently attest changes to those pins.
3. Advance custody sequences, test **actual SQLite custody rollback**, then show rejection against a separately retained higher floor.
4. Record transport certificates, OS permission boundaries, immutable or append-only evidence-store guarantees, clean/negative test logs, and signed independent reviewer acknowledgment.
5. Sanitize any public supporting artifact; keep raw environment logs, internal IP addresses, account names, private keys, credentials, and non-public data out of Git.

## Disclosure

This report is an **operator-observed local rehearsal summary** based on terminal outputs and hashes supplied during the experiment. It is **not** an independent audit opinion, a complete security assessment, or an externally verified evidence package. The unredacted local evidence files remain outside this public report.