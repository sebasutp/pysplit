.PHONY: install dev test lint typecheck e2e build parity clean

PYTHON ?= python3
PYTEST = PYTHONPATH=. .venv/bin/pytest
RUFF = .venv/bin/ruff

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
	backend/.venv/bin/python scripts/check_parity_matrix.py

clean:
	rm -rf backend/.pytest_cache backend/.ruff_cache backend/htmlcov backend/.coverage backend/coverage.xml
	rm -rf frontend/dist frontend/coverage frontend/test-results frontend/playwright-report
