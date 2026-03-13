
# VERITAS OS v2.0 — Auditable Decision OS for LLM Agents (Proto-AGI Skeleton)

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.17838349.svg)](https://doi.org/10.5281/zenodo.17838349)
[![DOI (JP Paper)](https://zenodo.org/badge/DOI/10.5281/zenodo.17838456.svg)](https://doi.org/10.5281/zenodo.17838456)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-Multi--license%20(Core%20Proprietary%20%2B%20MIT)-purple.svg)](LICENSE)
[![CI](https://github.com/veritasfuji-japan/veritas_os/actions/workflows/main.yml/badge.svg)](https://github.com/veritasfuji-japan/veritas_os/actions/workflows/main.yml)
[![CodeQL](https://github.com/veritasfuji-japan/veritas_os/actions/workflows/codeql.yml/badge.svg?branch=main)](https://github.com/veritasfuji-japan/veritas_os/actions/workflows/codeql.yml)
[![Docker Publish](https://github.com/veritasfuji-japan/veritas_os/actions/workflows/publish-ghcr.yml/badge.svg)](https://github.com/veritasfuji-japan/veritas_os/actions/workflows/publish-ghcr.yml)
[![Coverage](https://img.shields.io/badge/coverage-92%25-brightgreen.svg)](docs/COVERAGE_REPORT.md) <!-- Snapshot value from docs/COVERAGE_REPORT.md; CI gate is configured in .github/workflows/main.yml -->
[![GHCR](https://img.shields.io/badge/GHCR-ghcr.io%2Fveritasfuji--japan%2Fveritas__os-2496ED?logo=docker&logoColor=white)](https://ghcr.io/veritasfuji-japan/veritas_os)
[![README JP](https://img.shields.io/badge/README-日本語-0f766e.svg)](README_JP.md)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-Takeshi%20Fujishita-0A66C2?logo=linkedin&logoColor=white)](https://www.linkedin.com/in/takeshi-fujishita-279709392?utm_source=share&utm_campaign=share_via&utm_content=profile&utm_medium=ios_app)

**Version**: 2.0.0-alpha  
**Release Status**: In Development  
**Author**: Takeshi Fujishita

VERITAS OS wraps an LLM (e.g. OpenAI GPT-4.1-mini) with a **deterministic, safety-gated, hash-chained decision pipeline**.

> Mental model: **LLM = CPU**, **VERITAS OS = Decision / Agent OS on top**

---

## Quick Links

- **GitHub**: https://github.com/veritasfuji-japan/veritas_os
- **Zenodo paper (EN)**: https://doi.org/10.5281/zenodo.17838349
- **Zenodo paper (JP)**: https://doi.org/10.5281/zenodo.17838456
- **Japanese README**: `README_JP.md` (if present)
- **Code review document map**: `docs/notes/CODE_REVIEW_DOCUMENT_MAP.md`

## Contents

- [Why VERITAS?](#why-veritas)
- [What It Does](#what-it-does)
- [API Overview](#api-overview)
- [Quickstart](#quickstart)
- [Security Notes (Important)](#security-notes-important)
- [Docker (GHCR)](#docker-ghcr)
- [Architecture (High-Level)](#architecture-high-level)
- [TrustLog (Hash-Chained Audit Log)](#trustlog-hash-chained-audit-log)
- [Tests](#tests)
- [Roadmap (Near-Term)](#roadmap-near-term)
- [License](#license)

---

## Why VERITAS?

Most “agent frameworks” optimize autonomy and tool use.
VERITAS optimizes for **governance**:

- **Safety & compliance** enforced by a final gate (**FUJI Gate**)
- **Reproducible decision pipeline** (fixed stages, structured outputs)
- **Auditability** via a **hash-chained TrustLog** (tamper-evident decision history)
- **Memory & world state** as first-class inputs (MemoryOS + WorldModel)
- **Operational visibility** (Doctor dashboard for health & risk distribution)

**Target users**
- AI safety / agent researchers
- Teams operating LLMs in regulated or high-stakes environments
- Governance / compliance teams building “policy-driven” LLM systems

---

## What It Does

### `/v1/decide` — Full Decision Loop (Structured JSON)

`POST /v1/decide` returns a structured decision record.

Key fields (simplified):

| Field | Meaning |
|---|---|
| `chosen` | Selected action + rationale, uncertainty, utility, risk |
| `alternatives[]` | Other candidate actions |
| `evidence[]` | Evidence used (MemoryOS / WorldModel / optional tools) |
| `critique[]` | Self-critique & weaknesses |
| `debate[]` | Pro/con/third-party viewpoints |
| `telos_score` | Alignment score vs ValueCore |
| `fuji` | FUJI Gate result (allow / modify / rejected) |
| `gate.decision_status` | Normalized final status (`DecisionStatus`) |
| `trust_log` | Hash-chained TrustLog entry (`sha256_prev`) |

Pipeline mental model:

```text
Options → Evidence → Critique → Debate → Planner → ValueCore → FUJI → TrustLog
```

Bundled subsystems:

* **MemoryOS** — episodic/semantic memory & retrieval
* **WorldModel** — world state, projects, progress snapshots
* **ValueCore** — value function & Value EMA
* **FUJI Gate** — safety / ethics / compliance gate
* **TrustLog** — hash-chained audit log (JSONL)
* **Doctor** — diagnostics & dashboard

---

## API Overview

All protected endpoints require `X-API-Key`.

| Method | Path                  | Description                       |
| ------ | --------------------- | --------------------------------- |
| GET    | `/health`             | Health check                      |
| POST   | `/v1/decide`          | Full decision loop                |
| POST   | `/v1/fuji/validate`   | Validate a single action via FUJI |
| POST   | `/v1/replay/{decision_id}` | Re-run a stored decision and persist replay report |
| POST   | `/v1/memory/put`      | Persist memory                    |
| GET    | `/v1/memory/get`      | Retrieve memory                   |
| GET    | `/v1/logs/trust/{id}` | TrustLog entry by ID              |

---


## Replay

`POST /v1/replay/{decision_id}` re-executes a stored decision using the original recorded inputs and writes a replay artifact to `REPLAY_REPORT_DIR` (`audit/replay_reports` by default) as:

- `replay_{decision_id}_{YYYYMMDD_HHMMSS}.json`

When `VERITAS_REPLAY_STRICT=1`, replay enforces deterministic settings (`temperature=0`, fixed seed, and mocked external retrieval side effects).

```bash
BODY='{"strict":true}'
TS=$(date +%s)
NONCE="replay-$(uuidgen | tr '[:upper:]' '[:lower:]')"
SIG=$(python - <<'PY'
import hashlib
import hmac
import os

secret=os.environ["VERITAS_API_SECRET"].encode("utf-8")
ts=os.environ["TS"]
nonce=os.environ["NONCE"]
body=os.environ["BODY"]
payload=f"{ts}\n{nonce}\n{body}"
print(hmac.new(secret, payload.encode("utf-8"), hashlib.sha256).hexdigest())
PY
)

curl -X POST "http://127.0.0.1:8000/v1/replay/DECISION_ID" \
  -H "X-API-Key: ${VERITAS_API_KEY}" \
  -H "X-VERITAS-TIMESTAMP: ${TS}" \
  -H "X-VERITAS-NONCE: ${NONCE}" \
  -H "X-VERITAS-SIGNATURE: ${SIG}" \
  -H "Content-Type: application/json" \
  -d "${BODY}"
```

EU AI Act report generation already reads `replay_{decision_id}_*.json`, so invoking the Replay API updates replay verification data consumed by compliance reporting automatically.

---

## Quickstart

### 1) Install

```bash
git clone https://github.com/veritasfuji-japan/veritas_os.git
cd veritas_os

python3.11 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
```

> [!WARNING]
> Avoid placing secrets directly in shell history. Prefer a `.env` file (git-ignored) or a
> secrets manager for production environments.

### 2) Set env vars

```bash
export OPENAI_API_KEY="YOUR_OPENAI_API_KEY"
export VERITAS_API_KEY="your-secret-api-key"
export VERITAS_API_SECRET="your-long-random-secret"
export LLM_PROVIDER="openai"
export LLM_MODEL="gpt-4.1-mini"
export VERITAS_MAX_REQUEST_BODY_SIZE="10485760"
```

### 3) Start server

```bash
python -m uvicorn veritas_os.api.server:app --reload --port 8000
```

### 4) Try Swagger UI

* Open: `http://127.0.0.1:8000/docs`
* Authorize with header: `X-API-Key: $VERITAS_API_KEY`
* Run: `POST /v1/decide`

Example payload:

```json
{
  "query": "Should I check tomorrow's weather before going out?",
  "context": {
    "user_id": "test_user",
    "goals": ["health", "efficiency"],
    "constraints": ["time limit"],
    "affect_hint": "focused"
  }
}
```

---

## Docker (GHCR)

Pull the latest image:

```bash
docker pull ghcr.io/veritasfuji-japan/veritas_os:latest
```

Run the API server (equivalent to the uvicorn command above):

```bash
docker run --rm -p 8000:8000 \
  -e OPENAI_API_KEY="YOUR_OPENAI_API_KEY" \
  -e VERITAS_API_KEY="your-secret-api-key" \
  -e LLM_PROVIDER="openai" \
  -e LLM_MODEL="gpt-4.1-mini" \
  ghcr.io/veritasfuji-japan/veritas_os:latest
```

If your FastAPI entrypoint differs from `veritas_os.api.server:app`, update the
Dockerfile `CMD` accordingly before building the image.

---

## Architecture (High-Level)

### Core execution path

* `veritas_os/core/kernel.py` — orchestrates `/v1/decide`
* `veritas_os/core/pipeline.py` — defines stage order + metrics (`latency_ms` + `stage_latency`)
* `veritas_os/core/llm_client.py` — **single** gateway for LLM calls (`chat_completion`)

### Safety & governance

* `veritas_os/core/fuji.py` — FUJI Gate (allow/modify/reject)
* `veritas_os/core/value_core.py` — Value function + Value EMA
* `veritas_os/logging/trust_log.py` (or equivalent) — hash-chain TrustLog

### Memory & world state

* `veritas_os/core/memory.py` — MemoryOS frontend
* `veritas_os/core/world.py` — World state snapshots

---

## TrustLog (Hash-Chained Audit Log)

TrustLog is a **secure-by-default**, encrypted, hash-chained audit log.

### Security pipeline (per entry)

```text
entry → redact(PII + secrets) → canonicalize(RFC 8785) → chain hash → encrypt → append
```

1. **Redact** — PII (email, phone, address) and secrets (API keys, bearer tokens) are
   automatically masked before any persistence.
2. **Canonicalize** — RFC 8785 canonical JSON ensures deterministic hashing.
3. **Chain hash** — `h_t = SHA256(h_{t-1} || r_t)` provides tamper-evident linking.
4. **Encrypt** — Mandatory at-rest encryption (AES-256-GCM or HMAC-SHA256 CTR-mode).
   Plaintext storage is **not possible** without explicitly opting out.
5. **Append** — Encrypted line written to JSONL with fsync for durability.

### Setup

```bash
# Generate an encryption key (required)
python -c "from veritas_os.logging.encryption import generate_key; print(generate_key())"

# Set the key (required for TrustLog to function)
export VERITAS_ENCRYPTION_KEY="<generated-key>"
```

> **Warning**: Without `VERITAS_ENCRYPTION_KEY`, TrustLog writes will fail with
> `EncryptionKeyMissing`. This is by design — plaintext audit logs are prohibited.

### Verification

```bash
# Verify hash chain integrity (requires decryption key)
python -m veritas_os.scripts.verify_trust_log
```

---

## Tests

Recommended (reproducible):

```bash
make test
make test-cov
```

These targets use `uv` with `PYTHON_VERSION=3.12.12` and automatically download the
interpreter if it is not already installed.

Fast smoke check:

```bash
make test TEST_ARGS="-q veritas_os/tests/test_api_constants.py"
```

Optional overrides:

```bash
make test TEST_ARGS="-q veritas_os/tests/test_time_utils.py"
make test PYTHON_VERSION=3.11
```

### CI / Quality Gate

* GitHub Actions runs **pytest + coverage** on a Python 3.11/3.12 matrix.
* Coverage artifacts are stored as **XML/HTML** outputs.
* CI enforces a minimum coverage gate (`--cov-fail-under`) currently set to **85%**.
* The coverage badge is currently a documentation snapshot value from `docs/COVERAGE_REPORT.md` (planned: automatic update from CI artifacts).
* The CI job fails if tests fail, acting as a quality gate.

## Security Notes (Important)

### Credential and key management

- **API keys**: Avoid exporting secrets directly in shell history where possible. Prefer
  `.env` files (git-ignored) or secret managers and inject them at runtime. Rotate keys
  regularly and limit scope/permissions.
- **Never use placeholder or short secrets**: `VERITAS_API_SECRET` should be a long,
  random value (32+ chars recommended). Placeholder or short secrets can effectively
  disable or weaken HMAC protection.

### API and browser-facing protections

- **CORS safety**: avoid wildcard origins (`*`) when `allow_credentials` is enabled.
  Configure explicit trusted origins only.
- **CORS and API key must be set**: configure `VERITAS_CORS_ALLOW_ORIGINS` and
  `VERITAS_API_KEY` to avoid unsafe defaults.

### Data safety and persistence

- **TrustLog data**: TrustLog is **encrypted by default** (secure-by-default). All
  entries are automatically redacted for PII/secrets and encrypted before persistence.
  `VERITAS_ENCRYPTION_KEY` must be set; without it, writes fail.
- **Automatic PII/secret redaction**: Email, phone, address, API keys, bearer tokens,
  and secret-like strings are masked before storage — no manual `redact()` call required.
- **Encryption at rest (mandatory)**: Set `VERITAS_ENCRYPTION_KEY` (base64-encoded
  32-byte key). Use `generate_key()` to create one. Store keys in a vault/KMS, never in
  source control.
- **Operational logs are excluded from Git**: runtime logs (for example,
  `veritas_os/memory/*.jsonl`) are ignored via `.gitignore`; anonymized samples live
  under `veritas_os/sample_data/memory/`.

### Migration safety

- **Legacy pickle migration is risky**: if you enable legacy pickle migration for
  MemoryOS, treat it as a short-lived migration path and disable it afterward.

---

## Roadmap (Near-Term)

* CI (GitHub Actions): pytest + coverage + artifact reports
* Security hardening: input validation & secret/log hygiene
* Policy-as-Code: **Policy → ValueCore/FUJI rules → generated tests** (compiler layer)

---

## License

This repository is a **multi-license repository** with clear directory scope.

> 日本語補助: このリポジトリは「Coreはプロプライエタリ」「Interfaceはオープン」の二層ライセンスです。

### License matrix (scope by directory)

| Scope | License | Commercial use | Redistribution | Notes |
|---|---|---|---|---|
| Default (entire repo unless overridden) | VERITAS Core Proprietary EULA (`/LICENSE`) | Contract required | Not permitted without written permission | Includes Core decision logic and pipeline |
| `spec/` | MIT (`/spec/LICENSE`) | Permitted | Permitted | Open interface artifacts |
| `sdk/` | MIT (`/sdk/LICENSE`) | Permitted | Permitted | SDK interface layer |
| `cli/` | MIT (`/cli/LICENSE`) | Permitted | Permitted | CLI interface layer |
| `policies/examples/` | MIT (`/policies/examples/LICENSE`) | Permitted | Permitted | Policy templates/examples |

### Core abuse-prevention restrictions (high level)

Under the Core Proprietary EULA, you may not:

- provide Core (or substantially similar functionality) as a competing managed service;
- bypass license keys, metering, or other technical protection controls;
- remove copyright, attribution, proprietary notice, or trademark markings;
- redistribute Core or use Core for commercial production use without a commercial agreement.

See [`LICENSE`](LICENSE), [`TRADEMARKS`](TRADEMARKS), and [`NOTICE`](NOTICE).

### Transition note for existing users

This PR formalizes existing intent into a clearer two-tier structure:

- Core remains proprietary by default.
- Interface assets are explicitly open-licensed by directory.
- No Core logic (Planner/Kernel/FUJI/TrustLog pipeline internals) is open-sourced by this change.

### Roadmap: phased move from mono-repo licensing (Plan B) to multi-repo split (Plan A)

Phase 1 (this PR):
- Directory-scoped licensing in this mono-repo (Core proprietary + interface MIT)

Phase 2 (next PRs):
- `veritas-spec` (OpenAPI/schema)
- `veritas-sdk-python`, `veritas-sdk-js`
- `veritas-cli`
- `veritas-policy-templates`
- Keep `veritas_os` focused on proprietary Core only

For academic use, please cite the Zenodo DOI.

---

## Citation (BibTeX)

```bibtex
@software{veritas_os_2025,
  author = {Fujishita, Takeshi},
  title  = {VERITAS OS: Auditable Decision OS for LLM Agents},
  year   = {2025},
  doi    = {10.5281/zenodo.17838349},
  url    = {https://github.com/veritasfuji-japan/veritas_os}
}
```

---

## Contact

* Issues: [https://github.com/veritasfuji-japan/veritas_os/issues](https://github.com/veritasfuji-japan/veritas_os/issues)
* Email: [veritas.fuji@gmail.com](mailto:veritas.fuji@gmail.com)
