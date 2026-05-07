# One-Day VERITAS PoC Reviewer Pack

## 1. Purpose

This pack helps external reviewers verify VERITAS PoC evidence quickly.
It is intended for review, diligence, and technical evaluation.
It is **not** production certification.

## 2. Who this is for

- HPAN reviewers
- Enterprise AI governance teams
- Security and audit reviewers
- Investors and technical diligence reviewers
- Integration partners

## 3. What reviewers should verify

- Observability capabilities endpoint can be checked.
- JSON evidence packet can be generated.
- Markdown evidence packet can be generated.
- Generated evidence can be self-validated.
- Evidence JSON follows the repo-local schema.
- Sample evidence packet is available before running the script.
- No API key, token, raw endpoint, raw env value, or raw request/response body is written into evidence.

## 4. Minimum command

Use this exact command:

```bash
VERITAS_API_KEY=... python scripts/demo/one_day_poc_smoke.py \
  --json \
  --evidence-json /tmp/veritas_poc_evidence.json \
  --evidence-md /tmp/veritas_poc_evidence.md \
  --validate-generated-evidence
```

## 5. Expected success output

You should see output that includes the following lines:

- `Wrote sanitized evidence JSON: ...`
- `Generated evidence validation: VALID one_day_poc_evidence.v1`
- `Wrote sanitized evidence Markdown: ...`
- JSON summary output that includes `ok` and `capabilities_ok`
- If `--json` is used, parse stdout as JSON and inspect status lines on stderr.

Do not require an exact full stdout ordering; verify presence of the expected success signals.

## 6. Optional offline validation command

```bash
python scripts/demo/one_day_poc_smoke.py \
  --validate-evidence /tmp/veritas_poc_evidence.json
```

Expected output includes:

- `VALID one_day_poc_evidence.v1`

## 7. Optional schema discovery command

```bash
python scripts/demo/one_day_poc_smoke.py --print-schema-path
```

Expected output includes:

- `schemas/poc/one_day_poc_evidence.v1.schema.json`

## 8. Files reviewers should inspect

- `/tmp/veritas_poc_evidence.json`
- `/tmp/veritas_poc_evidence.md`
- `schemas/poc/one_day_poc_evidence.v1.schema.json`
- `docs/en/poc/sample-one-day-poc-evidence.json`
- `docs/en/poc/sample-one-day-poc-evidence.md`
- `docs/ja/poc/sample-one-day-poc-evidence.md`
- `docs/en/poc/one-day-poc-walkthrough.md`
- `docs/ja/poc/one-day-poc-walkthrough.md`

## 9. Success criteria checklist

- [ ] API server is running
- [ ] API key is mapped to `governance_read` role, such as `auditor` or `admin`
- [ ] Smoke script completes
- [ ] JSON evidence file is created
- [ ] Markdown evidence file is created
- [ ] Generated evidence validation reports `VALID`
- [ ] Offline validation reports `VALID`
- [ ] Evidence does not contain API key
- [ ] Evidence does not contain raw exporter endpoint
- [ ] Evidence does not contain raw env values
- [ ] Evidence does not copy raw request/response bodies
- [ ] `generated_at` uses fixed UTC Z format: `YYYY-MM-DDTHH:MM:SSZ`
- [ ] `non_goals` are present
- [ ] `limitations` are understood

## 10. Security boundary

- API keys are not written.
- Raw endpoints are not written.
- Raw env values are not written.
- Raw request/response bodies are not copied.
- Validation output does not print raw evidence body.
- CLI validation is a stdlib lightweight contract check aligned with v1 schema.
- CLI validation is **not** a full external `jsonschema` engine.

## 11. Non-goals / limitations

- Not production certification.
- Not final enterprise SLA.
- No Jaeger, Grafana, Tempo, or OTLP deployment is included.
- No cryptographic human approval signature is included.
- No stronger TrustLog durability guarantee beyond current implementation.
- Not a live customer integration proof by itself.

## 12. Suggested reviewer notes

- "The relevant question is not whether this is a full enterprise deployment, but whether VERITAS can produce reviewable, sanitized, schema-aligned evidence for governed AI action flows."
- "The PoC should be evaluated as an auditable decision-boundary demonstration."
- "Production hardening would require deployment architecture, operational controls, retention policy, identity integration, and customer-specific risk controls."


## Optional performance benchmark

```bash
VERITAS_API_KEY=... python scripts/demo/one_day_poc_benchmark.py \
  --runs 10 \
  --warmup 2 \
  --json \
  --out-json /tmp/veritas_poc_benchmark.json \
  --out-md /tmp/veritas_poc_benchmark.md
```

Include `/tmp/veritas_poc_benchmark.json` and `/tmp/veritas_poc_benchmark.md` in reviewer handoff artifacts.

## 13. Troubleshooting

- Missing API key: set `VERITAS_API_KEY` and retry.
- `401` / `403`: verify key validity and role mapping (`governance_read`, e.g. `auditor` or `admin`).
- `capabilities_ok: false`: check API server status and capabilities endpoint availability.
- Evidence validation invalid: re-run generation and inspect evidence JSON shape against the v1 schema path.
- Write failure: ensure target path is writable (for example `/tmp`).
- `generated_at` invalid: verify timestamp format is `YYYY-MM-DDTHH:MM:SSZ`.
- Schema path not found: verify repo checkout includes `schemas/poc/one_day_poc_evidence.v1.schema.json`.

## 14. What to send after the PoC

- Generated JSON evidence packet
- Generated Markdown evidence packet
- Command used
- VERITAS commit hash or release tag, if available
- Reviewer notes
- Known limitations
