PYTHON ?= python
PIP ?= $(PYTHON) -m pip

.PHONY: help install install-dev test build-frontend test-gateway test-engine check compile clean-cache

help:
	@echo "Targets:"
	@echo "  install         Install runtime dependencies"
	@echo "  install-dev     Install runtime + dev dependencies"
	@echo "  test            Run unit and integration tests"
	@echo "  build-frontend  Build Svelte frontend assets"
	@echo "  test-gateway    Run Node AI gateway tests"
	@echo "  test-engine     Run Rust engine tests"
	@echo "  check           Run the maintained local validation suite"
	@echo "  compile         Compile python modules to verify syntax"
	@echo "  clean-cache     Remove local python cache directories"

install:
	$(PIP) install -r requirements.txt

install-dev: install
	$(PIP) install -r requirements-dev.txt

test:
	$(PYTHON) -m pytest -q tests

build-frontend:
	npm --prefix writing_agent/web/frontend_svelte run build

test-gateway:
	npm --prefix gateway/node_ai_gateway test

test-engine:
	cargo test --workspace --manifest-path engine/Cargo.toml

check: compile test build-frontend test-gateway test-engine

compile:
	$(PYTHON) -m compileall -q writing_agent scripts

clean-cache:
	$(PYTHON) -c "from pathlib import Path; import shutil; [shutil.rmtree(p, ignore_errors=True) for r in ('writing_agent','scripts','tests') for p in Path(r).rglob('__pycache__')]"
