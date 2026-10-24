.PHONY: install dev test lint typecheck e2e build parity clean

PYTHON ?= python3
PYTEST = PYTHONPATH=. .venv/bin/pytest
RUFF = .venv/bin/ruff
# Prefer the backend virtualenv interpreter, but fall back to the system Python
# when a stale/broken venv cannot import PyYAML (CI installs it explicitly).
PARITY_PYTHON = $(shell backend/.venv/bin/python -c 'import yaml' >/dev/null 2>&1 && echo backend/.venv/bin/python || echo $(PYTHON))

install:
	cd backend && $(PYTHON) -m venv .venv
	cd backend && .venv/bin/pip install --upgrade pip
	cd backend && .venv/bin/pip install -r requirements.txt -r requirements-dev.txt
	cd frontend && npm ci

dev:
	./dev

test:
	cd backend && $(PYTEST) -n auto
	cd frontend && npm test -- --run

lint:
	cd backend && $(RUFF) check .
	cd backend && $(RUFF) format --check .
	cd frontend && npm run lint

typecheck:
	cd frontend && npm run typecheck

e2e:
	cd frontend && npx playwright test

build:
	cd frontend && npm run build

parity:
	$(PARITY_PYTHON) scripts/check_parity_matrix.py

clean:
	rm -rf backend/.pytest_cache backend/.ruff_cache backend/htmlcov backend/.coverage backend/coverage.xml
	rm -rf frontend/dist frontend/coverage frontend/test-results frontend/playwright-report
