# TASK-J3-06 — inert receiver-owned E3-model, durability and hard clock-gap counterexample

**Status:** RESEARCH-ONLY LOCAL MODEL / NOT REAL E3 / NOT STRICT RC1 CONFORMANCE  
**Predecessors:** merged PRs #2454–#2458, especially J3-05 ADR and partner questions Q01/Q04/Q05.  
**Source:** `veritas_os/tests/research_j3_06_inert_receiver.py`  
**Tests:** `veritas_os/tests/test_research_j3_06_inert_receiver.py`  
**No production imports, network listeners, TLS, external providers, credentials, actual effects, or changes to Broker Admission draft2.**

## 1. What is actually implemented

An isolated **SQLite-backed receiver admission model**, not a real network receiver. It persists a frozen attempt ID, target, owner incarnation and SHA-256 of the inert request bytes. Two separately keyed **HMAC-SHA256 test fixtures** simulate authenticated issuer evidence from Sanction and VERITAS. HMAC fixture keys are **not** real issuer signatures, asymmetric public-key trust, or revocation evidence.

`register()` durably records `PENDING`. `attempt_admit()` first atomically changes `PENDING` to `IN_PROGRESS` and commits, spending the only right to attempt admission. It then begins a second SQLite `BEGIN IMMEDIATE` transaction, reads the same-database STOP state, validates operation/evidence/clock, and commits either `DENIED`, `UNKNOWN`, or `ADMITTED`. `ADMITTED` means **E3_MODEL_ONLY: local database logical admission**. It does not prove receiver network acceptance, kernel acceptance, physical transmission or external effect.

SQLite is configured with WAL, `synchronous=FULL`, busy timeout and short-lived connections. These settings support the local test's transaction semantics but do not prove disk hardware durability, independent recovery across machines, global STOP ordering or correct behavior under all filesystem/power-failure models.

The local STOP flag and model admission share the same SQLite writer lock. Therefore a STOP **committed before** admission is visible and denies; a STOP attempt that cannot acquire the lock until **after** admission is not effective before that admission. This is **local database ordering only**, not instantaneous remote revocation or globally authoritative STOP.

## 2. Predicates implemented in the fixture

- Two **distinct** issuer records with fixture HMAC signatures and exact attempt/target/owner/body-SHA256 binding.
- Proposed per-issuer final-check ages `[0,2000]` ms on both fixture UTC interval and monotonic reading; strict `UTC upper bound < issuer expiry`.
- Fixture clock health and nonnegative uncertainty, conservatively using interval `[UTC-uncertainty, UTC+uncertainty]`.
- One attempt ID can be claimed once, including 32 concurrent contenders and reopening the same SQLite file.
- Claim-before-admission interruption stays `IN_PROGRESS`, never re-armed after restart; lost response after commit returns `UNKNOWN_NO_RETRY` and requires read-only inspection.
- Payload substitution is checked using a computed SHA-256 digest rather than J3-03's opaque fixture label.

**Caveat:** `FixtureClock(trusted_in_fixture=True)` is merely a test input, not an authenticated clock. There is no measured UTC uncertainty or verified monotonic-to-UTC calibration. HMAC does not establish real Sanction/VERITAS provenance.

## 3. Tests and interpretation

| Case | Expected result | What it proves / does not prove |
| --- | --- | --- |
| Ages 0/1999/2000 ms | One local E3-model admission | Fixture predicate only |
| Either issuer 2001 ms old | Denied | Fixture predicate only |
| Expiry equal to or past fixture entry time | Denied | No real-world clock proof |
| Missing issuer, bad signature, wrong target/body/owner | Denied | Only local fixture-key trust |
| STOP committed before admission | Denied | Same SQLite file ordering only |
| STOP after model admission | Existing row remains admitted; replay denied | No external rollback/effect |
| 32 concurrent contenders | At most one local admission | No cross-host distributed guarantee |
| Restart and replay | Denied | Same SQLite file; not power-loss proof |
| Crash injected after durable claim | Remains IN_PROGRESS; replay denied | No real process kill or fsync audit |
| Lost receipt | UNKNOWN_NO_RETRY; read-only state inspection | No actual network acknowledgement |
| Clock rollback, uncertainty hitting expiry, unhealthy fixture | Denied | Not a trusted clock implementation |
| Test hook interrupted before commit | UNKNOWN_NO_RETRY | No actual process crash |
| **Physical >2000 ms pause after clock sample, inside SQLite transaction** | **Still ADMITTED** in this intentionally incomplete model | **Negative counterexample: a DB transaction cannot freeze physical time** |

The final test is a **deliberate failure of the desired Strict RC1 physical-time property**, not a passing conformance test. The pytest assertion passes precisely when the counterexample is observed.

## 4. Unresolved limitations and STOP criteria

1. **No physical-time atomicity:** a Python clock sample and a later SQLite commit are distinct events, even within one transaction. A scheduler pause inside that transaction can invalidate freshness before the commit. This is the critical J3 gap in a new location. Do not present the model as a solved Trusted Entry Gate.
2. **No independent time trust:** the clock is a supplied fixture snapshot; it does not advance automatically with real elapsed time.
3. **No real receiver E3:** no socket listener, authenticated receiver service, request parsing boundary, or external authority. `E3_MODEL_ONLY` is deliberately named.
4. **No global STOP/revocation semantics:** same-file STOP is not a distributed revocation guarantee. Remote revocation, propagation latency, STOP acknowledgment and cross-domain ordering are unscored.
5. **No production issuer trust:** two fixture HMAC keys do not establish real public-key signatures, provenance, rotation or revocation.
6. **No hardware crash guarantee:** restart tests reopen the same local SQLite file; they do not exercise actual power loss or adversarial filesystem behavior.
7. **No complete 38-row matrix:** this PR tests a selected subset of J3-02 oracles, not the full suite. J3-05 P01–P12 are not all satisfied.
8. **No effect claim:** a local `ADMITTED` row does not imply E1 kernel acceptance, E2 transmission, E3 network admission or E4 effect.

## 5. Next decision

**Do not promote this receiver model to production or Strict RC1 conformance.** The next technical task must solve or explicitly bound the **clock-sample-to-selected-entry** interval under a named trust root. An independently reviewed receiver-native atomic primitive, hardware/real-time assumption, or revised contract may be necessary. First ask Eric to settle J3-05 Q01 (E1/E2/E3), Q04 (STOP-effective point), Q05 (remote revocation visibility).

**Status remains: Strict RC1/J3 BLOCKED; J5–J7 OPEN; BA6 PENDING.** No partner approval inferred.
