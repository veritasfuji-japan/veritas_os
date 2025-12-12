
# VERITAS OS v2.0 — Auditable Decision OS for LLM Agents (Proto-AGI Skeleton)

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.17838349.svg)](https://doi.org/10.5281/zenodo.17838349)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-All%20Rights%20Reserved-red.svg)](LICENSE)
[![CI](https://github.com/veritasfuji-japan/veritas_os/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/veritasfuji-japan/veritas_os/actions/workflows/ci.yml?query=branch%3Amain)

**Version**: 2.0.0  
**Release Date**: 2025-12-01  
**Author**: Takeshi Fujishita

VERITAS OS wraps an LLM (e.g. OpenAI GPT-4.1-mini) with a **deterministic, safety-gated, hash-chained decision pipeline**.

> Mental model: **LLM = CPU**, **VERITAS OS = Decision / Agent OS on top**

---

## Quick Links

- **GitHub**: https://github.com/veritasfuji-japan/veritas_os
- **Zenodo paper (EN)**: https://doi.org/10.5281/zenodo.17838349
- **Zenodo paper (JP)**: https://doi.org/10.5281/zenodo.17838456
- **Japanese README**: `README_JP.md` (if present)

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
````

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
| POST   | `/v1/memory/put`      | Persist memory                    |
| GET    | `/v1/memory/get`      | Retrieve memory                   |
| GET    | `/v1/logs/trust/{id}` | TrustLog entry by ID              |

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

### 2) Set env vars

```bash
export OPENAI_API_KEY="YOUR_OPENAI_API_KEY"
export VERITAS_API_KEY="your-secret-api-key"
export LLM_PROVIDER="openai"
export LLM_MODEL="gpt-4.1-mini"
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

## Architecture (High-Level)

### Core execution path

* `veritas_os/core/kernel.py` — orchestrates `/v1/decide`
* `veritas_os/core/pipeline.py` — defines stage order + metrics
* `veritas_os/core/llm_client.py` — **single** gateway for LLM calls

### Safety & governance

* `veritas_os/core/fuji.py` — FUJI Gate (allow/modify/reject)
* `veritas_os/core/value_core.py` — Value function + Value EMA
* `veritas_os/logging/trust_log.py` (or equivalent) — hash-chain TrustLog

### Memory & world state

* `veritas_os/core/memory.py` — MemoryOS frontend
* `veritas_os/core/world.py` — World state snapshots

---

## TrustLog (Hash-Chained Audit Log)

The TrustLog is append-only JSONL. Each entry includes a hash pointer:

```text
h_t = SHA256(h_{t-1} || r_t)
```

This enables integrity verification and tamper-evident audit trails.

---

## Tests

```bash
pytest
pytest --cov=veritas_os
```

> Note: Coverage/CI badges will be added via GitHub Actions (recommended for external trust).

---

## Roadmap (Near-Term)

* CI (GitHub Actions): pytest + coverage + artifact reports
* Security hardening: input validation & secret/log hygiene
* Policy-as-Code: **Policy → ValueCore/FUJI rules → generated tests** (compiler layer)

---

## License

**All Rights Reserved.**
See [`LICENSE`](LICENSE).

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



