# VERITAS OS — Dependency Profiles

> Last updated: 2026-03-25

## Overview

VERITAS OS uses **extras** (`[project.optional-dependencies]` in `pyproject.toml`)
to separate **core** dependencies from **optional** feature groups.
This allows lighter installs for backend-only or CI-lint scenarios while
keeping full backward compatibility via the `[full]` extra.

## Install Profiles

| Profile | Command | Use-case |
|---|---|---|
| **Core** | `pip install .` | API server + primary LLM (OpenAI). Smallest footprint. |
| **+ ML** | `pip install ".[ml]"` | Adds sentence-transformers & scikit-learn for memory model training. |
| **+ Reports** | `pip install ".[reports]"` | Adds matplotlib, pandas, PDF tooling for report generation. |
| **+ Anthropic** | `pip install ".[anthropic]"` | Adds the Anthropic SDK for Claude LLM support. |
| **+ System** | `pip install ".[system]"` | Adds psutil, trio, pinned starlette for system monitoring scripts. |
| **+ PostgreSQL** | `pip install ".[postgresql]"` | Adds psycopg 3, psycopg-pool, Alembic for PostgreSQL storage backend. |
| **Full** | `pip install ".[full]"` | All optional groups. Equivalent to the old flat install. |
| **requirements.txt** | `pip install -r veritas_os/requirements.txt` | Full pinned list — CI and Docker default. |

## Dependency Classification

### Core (always installed)

| Package | Version | Role |
|---|---|---|
| fastapi | 0.121.0 | API framework |
| uvicorn | 0.30.3 | ASGI server |
| pydantic | 2.8.2 | Data validation / schemas |
| python-dotenv | 1.0.1 | `.env` file loading |
| orjson | 3.11.6 | Fast JSON serialization |
| PyYAML | 6.0.1 | Policy YAML parsing |
| jinja2 | 3.1.6 | Template support (FastAPI transitive) |
| openai | 1.51.0 | Primary LLM provider SDK |
| httpx | 0.27.2 | HTTP client (used by LLM client) |
| numpy | 1.26.4 | Numerical operations (memory subsystem) |

### Optional `[ml]`

| Package | Version | Role | Graceful degradation |
|---|---|---|---|
| scikit-learn | 1.5.2 | Memory model training (scripts) | Lazy import in `memory_train.py` |
| sentence-transformers | 3.0.1 | Sentence embeddings (memory vector) | Lazy import with env-var guard in `memory_vector.py` |

### Optional `[reports]`

| Package | Version | Role | Graceful degradation |
|---|---|---|---|
| matplotlib | 3.9.2 | Graph generation (scripts) | `HAS_MPL` flag in `generate_report.py` |
| pandas | 2.2.3 | Data analysis (reserved) | Not imported in current codebase |
| pdfplumber | 0.11.9 | PDF memory import (scripts) | Script-only; not loaded at runtime |
| pdfminer.six | 20251230 | PDF text extraction (pdfplumber dep) | Not directly imported |

### Optional `[anthropic]`

| Package | Version | Role | Graceful degradation |
|---|---|---|---|
| anthropic | 0.34.2 | Anthropic/Claude LLM provider | Not imported; provider selection via env var |

### Optional `[system]`

| Package | Version | Role | Graceful degradation |
|---|---|---|---|
| psutil | 6.0.0 | System monitoring utilities | Not imported in current codebase |
| trio | 0.26.2 | Async framework (reserved) | Not imported in current codebase |
| starlette | 0.49.1 | ASGI toolkit (FastAPI transitive; pinned for compatibility) | Installed transitively by FastAPI |

## CI / Docker Behavior

- **CI** (`main.yml`): Installs via `requirements.txt` → full dependency set. No change needed.
- **Docker** (`Dockerfile`): Installs via `requirements.txt` → full dependency set. No change needed.
- **`setup.sh`**: Installs via `requirements.txt` → full dependency set. No change needed.

All existing workflows continue to install the complete dependency set.
The extras mechanism is additive — it enables _lighter_ installs without
breaking the default path.

## Future Candidates for Optional-ization

| Package | Current group | Notes |
|---|---|---|
| jinja2 | core | FastAPI transitive; could be optional if template features are confirmed unused |
| numpy | core | Used in memory subsystem; could move to `[ml]` if memory modules add lazy imports |
| openai | core | Could move to `[llm]` extra if a provider-agnostic fallback is added |
