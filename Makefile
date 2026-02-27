PYTHON ?= python
PIP ?= $(PYTHON) -m pip

.PHONY: help install install-dev test build-frontend guards preflight compile clean-cache

help:
	@echo "Targets:"
	@echo "  install         Install runtime dependencies"
	@echo "  install-dev     Install runtime + dev dependencies"
	@echo "  test            Run test suite"
	@echo "  build-frontend  Build Svelte frontend assets"
	@echo "  guards          Run architecture/size/complexity guards"
	@echo "  preflight       Run release preflight checks (quick mode)"
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

guards:
	$(PYTHON) scripts/guard_file_line_limits.py --config security/file_line_limits.json --root .
	$(PYTHON) scripts/guard_function_complexity.py --config security/function_complexity_limits.json --root .
	$(PYTHON) scripts/guard_architecture_boundaries.py --config security/architecture_boundaries.json --root .

preflight:
	$(PYTHON) scripts/release_preflight.py --quick

compile:
	$(PYTHON) -m compileall -q writing_agent scripts

clean-cache:
	$(PYTHON) -c "from pathlib import Path; import shutil; [shutil.rmtree(p, ignore_errors=True) for r in ('writing_agent','scripts','tests') for p in Path(r).rglob('__pycache__')]"
