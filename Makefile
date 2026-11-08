.PHONY: install dev test test-coverage lint typecheck e2e build parity architecture i18n i18n-keys i18n-coverage i18n-sync-check performance backup restore clean

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

test-coverage:
	cd frontend && npm run test:coverage

lint: i18n-sync-check
	cd backend && $(RUFF) check .
	cd backend && $(RUFF) format --check .
	cd frontend && npm run lint

typecheck:
	cd frontend && npm run typecheck

e2e:
	cd frontend && npx playwright test

build:
	cd frontend && npm run build

# Stage 12 operational checks. Use BACKUP_DATABASE/BACKUP_UPLOADS/BACKUP_OUTPUT
# or pass the scripts' flags directly for production paths.
performance:
	cd backend && PYTHONPATH=. .venv/bin/python scripts/performance_check.py
	cd frontend && npm run build && npm run check:bundle

backup:
	cd backend && PYTHONPATH=. .venv/bin/python scripts/backup.py \
		--database "$${BACKUP_DATABASE:-../data/dev/pysplit.db}" \
		--uploads "$${BACKUP_UPLOADS:-../data/dev/uploads}" \
		--output "$${BACKUP_OUTPUT:-../data/backups}"

restore:
	cd backend && PYTHONPATH=. .venv/bin/python scripts/restore.py \
		--backup "$${BACKUP_PATH:?set BACKUP_PATH to a backup directory}" \
		--database "$${BACKUP_DATABASE:-../data/dev/pysplit.db}" \
		--uploads "$${BACKUP_UPLOADS:-../data/dev/uploads}"

parity:
	$(PARITY_PYTHON) scripts/check_parity_matrix.py

architecture:
	$(PYTHON) scripts/check_architecture.py

i18n: i18n-keys i18n-coverage i18n-sync-check

i18n-keys:
	$(PYTHON) scripts/check_i18n_keys.py

i18n-coverage:
	$(PYTHON) scripts/check_i18n_coverage.py \
		--baseline frontend/src/locales/translation-baseline.json \
		--strict --allowlist scripts/i18n-allowlist.json

# Verify the committed app catalogues match the vendored upstream snapshot
# without writing any files. Uses frontend/locales-upstream, so no network or
# local spliit/ checkout is required. Reviewed app translations are preserved.
i18n-sync-check:
	node frontend/scripts/sync-locales.mjs --source frontend/locales-upstream --check

clean:
	rm -rf backend/.pytest_cache backend/.ruff_cache backend/htmlcov backend/.coverage backend/coverage.xml
	rm -rf frontend/dist frontend/coverage frontend/test-results frontend/playwright-report
