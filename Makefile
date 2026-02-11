PYTHON_VERSION ?= 3.12.7
PYTHON_FALLBACK ?= 3.12
UV ?= uv
TEST_ARGS ?=

.PHONY: test test-cov

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
