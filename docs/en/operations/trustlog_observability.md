# TrustLog Observability Metrics

This document defines production-focused TrustLog metrics, alerting guidance, and SLO suggestions.

## Metrics

### Counters
- `trustlog_append_success_total{posture}`
  - Incremented when `append_trust_log` commits a full-ledger entry successfully.
- `trustlog_append_failure_total{posture,reason}`
  - Incremented when append fails (I/O, JSON, encryption, or validation errors).
- `trustlog_sign_failure_total{signer_backend,reason}`
  - Incremented when witness signing fails.
- `trustlog_mirror_failure_total{backend,reason}`
  - Incremented when WORM/object-lock mirror operations fail.
- `trustlog_anchor_failure_total{backend,reason}`
  - Incremented when transparency anchor operations fail.
- `trustlog_verify_failure_total{ledger,reason}`
  - Incremented when full or witness verification reports a failed result.

### Gauges
- `trustlog_last_success_timestamp`
  - Unix timestamp of the latest successful append operation.
- `trustlog_anchor_lag_seconds{backend}`
  - Difference between local anchor time and external timestamp (or 0 for local/no-op backends).

### Histograms
- `trustlog_mirror_latency_seconds{backend}`
  - Mirror operation latency.
- `trustlog_sign_latency_seconds{signer_backend}`
  - TrustLog signing latency.

## Recommended Alerts

### Availability and pipeline health
- **TrustLog append failures sustained**
  - Trigger: `increase(trustlog_append_failure_total[5m]) > 0` with `increase(trustlog_append_success_total[5m]) == 0`.
  - Severity: Critical in `prod` posture.
- **No recent successful appends**
  - Trigger: `time() - trustlog_last_success_timestamp > 300` (tune to your expected traffic).
  - Severity: Warning/Critical depending on ingest expectations.

### Integrity and security
- **Signing failures**
  - Trigger: `increase(trustlog_sign_failure_total[5m]) > 0`.
  - Severity: Critical (can indicate key/KMS outage or signer misconfiguration).
- **Verification failures**
  - Trigger: `increase(trustlog_verify_failure_total[15m]) > 0`.
  - Severity: Critical (potential tampering, corruption, or key/decryption drift).

### Durability and external dependencies
- **Mirror failures**
  - Trigger: `increase(trustlog_mirror_failure_total[10m]) > 0`.
  - Severity: Critical in secure/prod hard-fail mode; Warning in dev/local.
- **Anchor failures / lag drift**
  - Trigger: `increase(trustlog_anchor_failure_total[10m]) > 0` or `max_over_time(trustlog_anchor_lag_seconds[15m]) > 60`.
  - Severity: Warning/Critical based on compliance policy.

## Suggested SLOs

- **Append success ratio (30d):**
  - `sum(increase(trustlog_append_success_total[30d])) / (sum(increase(trustlog_append_success_total[30d])) + sum(increase(trustlog_append_failure_total[30d]))) >= 99.9%`
- **Signer reliability (30d):**
  - `sum(increase(trustlog_sign_failure_total[30d])) == 0` (strict) or error budget under 0.01% of append volume.
- **Mirror durability path (30d):**
  - `sum(increase(trustlog_mirror_failure_total[30d])) / sum(increase(trustlog_append_success_total[30d])) < 0.1%`
- **Verification integrity checks:**
  - Daily scheduled verification with `trustlog_verify_failure_total` increments = 0.

## Security note

Any sustained increase in `trustlog_verify_failure_total`, `trustlog_sign_failure_total`, or mirror/anchor failures in hardened posture should be treated as a potential security and integrity incident until ruled out.
