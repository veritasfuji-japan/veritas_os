# Decision Pipeline PoC

This reviewer proof makes one deliberately narrow claim: **real VERITAS
decision/governance runtime with controlled model output**.

## Proof boundary

```text
synthetic request
  ↓
real authenticated POST /v1/decide
  ↓
real DecideRequest validation and Permission.decide authorization
  ↓
real route, service, decision pipeline, and kernel
  ↓
controlled transcript at veritas_os.core.llm_client.chat
  ↓
real FUJI, ValueCore, gate, evidence, and actionability semantics
  ↓
real encrypted local TrustLog append and chain verification
  ↓
runtime replay snapshot and linked shadow persistence
  ↓
validated DecideResponse
  ↓
STOP
```

Run it from the repository root:

```bash
python scripts/run_decide_pipeline_poc.py
```

The command creates isolated temporary storage, generates ephemeral API and
encryption keys, enters the real FastAPI lifespan, rejects an invalid key, and
then submits the fixture with an operator key through `POST /v1/decide`. The
legacy `options` field intentionally exercises request coercion. Optional web
retrieval is disabled by the supported mock-external-APIs request behavior.

Only `veritas_os.core.llm_client.chat` is intercepted. The fixed, non-sensitive
fixture is in
`veritas_os/tests/fixtures/decide_pipeline/provider_transcript.json`. Every call
is counted; zero calls fails the proof. Because the provider client is replaced
at this central seam, no OpenAI, Anthropic, Google, OpenRouter, Ollama, or other
provider transport is contacted. The pipeline, kernel, FUJI, ValueCore, gate,
evidence processing, response assembly, authentication, and RBAC are not
replaced.

## Strict persistence verification

HTTP 200 is necessary but insufficient. The runner independently requires the
canonical encrypted `trust_log.jsonl` to exist, requires a decrypted record
whose `request_id` matches the `DecideResponse`, and calls the existing
`verify_trust_log()` full-ledger verifier. It also links the response replay
snapshot and runtime-created shadow artifact to that request ID. The ciphertext
is scanned to ensure it contains neither ephemeral key nor the synthetic query.
Missing encryption material, a broken chain, missing linkage, or HTTP 200 with
failed verification exits non-zero and does not emit a passing report.

The normalized reviewer projection is written to
`artifacts/decide-pipeline-poc/report.json`. Runtime IDs, times, temporary paths,
and latency remain untouched in raw runtime artifacts. The projection replaces
the request ID with a marker; runtime-dependent response, replay, and ledger
digests remain evidence values and can be ignored when comparing normalized
runs.

## Decision semantics and STOP boundary

A recorded decision remains non-executable until appropriate bind lineage
exists. `ALLOW`, `APPROVE`, or `proceed` is not permission for an external
effect. `chosen` and `next_action` are not automatically executable actions,
and authenticated identity is not bind authority. `human_review_required=true`
does not prove that a human approved anything.

This PoC does not create an `ExecutionIntent`, invoke the Bind Boundary, import
or invoke `WebhookBindAdapter`, fabricate Human Approval or Authority Evidence,
or cause an external side effect. The existing External Bind Boundary PoC is a
separate proof and is not called or modified here.

## Explicit non-claims

This PoC does **not** prove:

- real OpenAI, Anthropic, Google, OpenRouter, or Ollama inference;
- live provider authentication, transport, retry behavior, availability, or
  deterministic live-model behavior;
- production TrustLog infrastructure, WORM storage, KMS, PostgreSQL, HA
  durability, deployment, customer deployment, or production readiness;
- live financial-institution integration;
- regulatory certification or regulatory approval;
- execution authority, Human Approval, or Authority Evidence;
- successful Bind Boundary execution or any external effect; or
- decision-to-bind end-to-end lineage.

## Security review warning

This is local reviewer evidence, not a production storage certification. The
ephemeral environment key is suitable only for the temporary PoC directory.
Production secrets must remain in the approved vault/KMS path. Human maintainer
approval remains required for governance- and TrustLog-sensitive claims.
