PYTHON_VERSION ?= 3.12.12
PYTHON_FALLBACK ?= 3.12
UV ?= uv
TEST_ARGS ?=
COVERAGE_FAIL_UNDER ?= 85
PYTEST_MARKEXPR ?= not slow
COVERAGE_XML ?= coverage.xml
COVERAGE_HTML_DIR ?= coverage-html

.PHONY: setup dev dev-frontend dev-all up down logs health clean-venv test test-cov test-split test-production test-smoke quality-checks validate-compose validate-compose-report validate-live validate-live-report validate-staged-report

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
	@mkdir -p $(COVERAGE_HTML_DIR)
	@set -e; \
	if [ -x .venv/bin/python ] && .venv/bin/python -c "import pytest" >/dev/null 2>&1; then \
		echo "[veritas] Using existing .venv"; \
		.venv/bin/python -m pytest -q veritas_os/tests \
			--cov=veritas_os \
			--cov-config=veritas_os/tests/.coveragerc \
			--cov-report=term-missing \
			--cov-report=xml:$(COVERAGE_XML) \
			--cov-report=html:$(COVERAGE_HTML_DIR) \
			--cov-fail-under=$(COVERAGE_FAIL_UNDER) \
			-m "$(PYTEST_MARKEXPR)" \
			--durations=20 \
			--tb=short \
			$(TEST_ARGS); \
		exit 0; \
	fi; \
	echo "[veritas] Running coverage tests with Python $(PYTHON_VERSION) via uv"; \
	if UV_PYTHON_DOWNLOADS=automatic $(UV) run --python $(PYTHON_VERSION) --with pytest --with pytest-cov pytest -q veritas_os/tests \
		--cov=veritas_os \
		--cov-config=veritas_os/tests/.coveragerc \
		--cov-report=term-missing \
		--cov-report=xml:$(COVERAGE_XML) \
		--cov-report=html:$(COVERAGE_HTML_DIR) \
		--cov-fail-under=$(COVERAGE_FAIL_UNDER) \
		-m "$(PYTEST_MARKEXPR)" \
		--durations=20 \
		--tb=short \
		$(TEST_ARGS); then \
		exit 0; \
	fi; \
	echo "[veritas] Falling back to Python $(PYTHON_FALLBACK) (local or managed)"; \
	UV_PYTHON_DOWNLOADS=automatic $(UV) run --python $(PYTHON_FALLBACK) --with pytest --with pytest-cov pytest -q veritas_os/tests \
		--cov=veritas_os \
		--cov-config=veritas_os/tests/.coveragerc \
		--cov-report=term-missing \
		--cov-report=xml:$(COVERAGE_XML) \
		--cov-report=html:$(COVERAGE_HTML_DIR) \
		--cov-fail-under=$(COVERAGE_FAIL_UNDER) \
		-m "$(PYTEST_MARKEXPR)" \
		--durations=20 \
		--tb=short \
		$(TEST_ARGS)


test-split:
	@command -v $(UV) >/dev/null 2>&1 || { echo "Error: uv is required. Install from https://docs.astral.sh/uv/."; exit 1; }
	@set -e; \
	for expr in "not (api or server or dashboard or governance or schemas or openapi or constants or telos or evolver)" \
	            "api or server or dashboard or governance or schemas or openapi or constants or telos or evolver" \
	            "memory or embedder or index_cosine"; do \
		echo "[veritas] Running split tests: -k $$expr"; \
		UV_PYTHON_DOWNLOADS=automatic $(UV) run --python $(PYTHON_FALLBACK) --with pytest pytest -q veritas_os/tests -k "$$expr" --durations=20; \
	done

quality-checks:
	@python scripts/architecture/check_responsibility_boundaries.py --report-format json
	@python scripts/architecture/check_core_complexity_budget.py
	@python scripts/quality/check_operational_docs_consistency.py
	@python scripts/quality/check_frontend_docs_consistency.py
	@python scripts/quality/check_review_improvements_consistency.py
	@python scripts/quality/check_requirements_sync.py
	@python scripts/quality/check_frontend_api_contract_consistency.py
	@python scripts/security/check_memory_dir_allowlist.py
	@python scripts/security/check_httpx_raw_upload_usage.py
	@python scripts/security/check_subprocess_shell_usage.py
	@python scripts/quality/check_replay_pipeline_version_unknown_rate.py --max-unknown-rate 0.0
	@python scripts/quality/check_deployment_env_defaults.py
	@python scripts/security/check_runtime_pickle_artifacts.py

# ── Production-like Validation ───────────────────────────────────────────

test-production:
	@echo "[veritas] Running production-like tests (pytest -m 'production or smoke')..."
	@python -m pytest veritas_os/tests/ -m "production or smoke" -v --tb=short --durations=10

test-smoke:
	@echo "[veritas] Running smoke tests (pytest -m smoke)..."
	@python -m pytest veritas_os/tests/ -m smoke -v --tb=short

validate:
	@echo "[veritas] Running full production validation..."
	@bash scripts/production_validation.sh

validate-compose:
	@echo "[veritas] Running Docker Compose governance validation..."
	@bash scripts/compose_validation.sh

validate-compose-report:
	@echo "[veritas] Running Docker Compose validation with JSON report..."
	@mkdir -p release-artifacts
	@bash scripts/compose_validation.sh --json-report=release-artifacts/compose-validation-report.json

validate-live:
	@echo "[veritas] Running live provider validation (secrets-required)..."
	@bash scripts/live_provider_validation.sh

validate-live-report:
	@echo "[veritas] Running live provider validation with JSON report..."
	@mkdir -p release-artifacts
	@bash scripts/live_provider_validation.sh --json-report=release-artifacts/live-provider-report.json

validate-staged-report:
	@echo "[veritas] Generating staged operational readiness report..."
	@mkdir -p release-artifacts
	@python scripts/generate_staged_readiness_report.py \
		--ref $$(git describe --tags --always 2>/dev/null || echo "local") \
		--sha $$(git rev-parse HEAD 2>/dev/null || echo "unknown") \
		--output release-artifacts/staged-readiness-report.json \
		--text-output release-artifacts/staged-readiness-report.txt
