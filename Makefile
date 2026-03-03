PYTHON_VERSION ?= 3.12.12
PYTHON_FALLBACK ?= 3.12
UV ?= uv
TEST_ARGS ?=

.PHONY: setup dev dev-frontend dev-all up down logs health clean-venv test test-cov test-split

# ── Setup & Development ──────────────────────────────────────────────────

setup:
	@bash setup.sh

dev:
	@if [ ! -f .env ]; then echo "[veritas] .env not found. Run 'make setup' first."; exit 1; fi
	@if [ ! -x .venv/bin/python ]; then echo "[veritas] .venv not found. Run 'make setup' first."; exit 1; fi
	@echo "[veritas] Starting backend on http://localhost:8000 ..."
	@set -a && . ./.env && set +a && \
	.venv/bin/uvicorn veritas_os.api.server:app --reload --host 0.0.0.0 --port 8000

dev-frontend:
	@echo "[veritas] Starting frontend on http://localhost:3000 ..."
	pnpm ui:dev

dev-all:
	@echo "[veritas] Starting backend + frontend ..."
	@$(MAKE) dev &
	@$(MAKE) dev-frontend &
	@wait

up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f

health:
	@curl -sf http://localhost:8000/health | python3 -m json.tool 2>/dev/null \
		&& echo "[veritas] Backend OK" \
		|| echo "[veritas] Backend not responding"

clean-venv:
	rm -rf .venv
	@echo "[veritas] .venv removed."

# ── Tests ────────────────────────────────────────────────────────────────

test:
	@command -v $(UV) >/dev/null 2>&1 || { echo "Error: uv is required. Install from https://docs.astral.sh/uv/."; exit 1; }
	@set -e; \
	if [ -x .venv/bin/python ] && .venv/bin/python -c "import pytest" >/dev/null 2>&1; then \
		echo "[veritas] Using existing .venv"; \
		.venv/bin/python -m pytest $(TEST_ARGS); \
		exit 0; \
	fi; \
	echo "[veritas] Running tests with Python $(PYTHON_VERSION) via uv"; \
	if UV_PYTHON_DOWNLOADS=automatic $(UV) run --python $(PYTHON_VERSION) --with pytest pytest $(TEST_ARGS); then \
		exit 0; \
	fi; \
	echo "[veritas] Falling back to Python $(PYTHON_FALLBACK) (local or managed)"; \
	UV_PYTHON_DOWNLOADS=automatic $(UV) run --python $(PYTHON_FALLBACK) --with pytest pytest $(TEST_ARGS)

test-cov:
	@command -v $(UV) >/dev/null 2>&1 || { echo "Error: uv is required. Install from https://docs.astral.sh/uv/."; exit 1; }
	@set -e; \
	if [ -x .venv/bin/python ] && .venv/bin/python -c "import pytest" >/dev/null 2>&1; then \
		echo "[veritas] Using existing .venv"; \
		.venv/bin/python -m pytest --cov=veritas_os $(TEST_ARGS); \
		exit 0; \
	fi; \
	echo "[veritas] Running coverage tests with Python $(PYTHON_VERSION) via uv"; \
	if UV_PYTHON_DOWNLOADS=automatic $(UV) run --python $(PYTHON_VERSION) --with pytest --with pytest-cov pytest --cov=veritas_os $(TEST_ARGS); then \
		exit 0; \
	fi; \
	echo "[veritas] Falling back to Python $(PYTHON_FALLBACK) (local or managed)"; \
	UV_PYTHON_DOWNLOADS=automatic $(UV) run --python $(PYTHON_FALLBACK) --with pytest --with pytest-cov pytest --cov=veritas_os $(TEST_ARGS)


test-split:
	@command -v $(UV) >/dev/null 2>&1 || { echo "Error: uv is required. Install from https://docs.astral.sh/uv/."; exit 1; }
	@set -e; \
	for expr in "not (api or server or dashboard or governance or schemas or openapi or constants or telos or evolver)" \
	            "api or server or dashboard or governance or schemas or openapi or constants or telos or evolver" \
	            "memory or embedder or index_cosine"; do \
		echo "[veritas] Running split tests: -k $$expr"; \
		UV_PYTHON_DOWNLOADS=automatic $(UV) run --python $(PYTHON_FALLBACK) --with pytest pytest -q veritas_os/tests -k "$$expr" --durations=20; \
	done
