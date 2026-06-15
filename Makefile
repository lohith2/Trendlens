# Local dev for Trendlens. Requires Python 3.11+ and Node 18+.
# Pick the newest Python available for fresh venvs (the system `python3` may be old).
PYTHON ?= $(shell command -v python3.13 || command -v python3.12 || command -v python3.11 || command -v python3)
PY := .venv/bin/python

.PHONY: setup backend frontend dev test e2e clean help

help: ## list targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

setup: ## create venv + install backend and frontend deps (first time only)
	$(PYTHON) -m venv .venv
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install --no-cache-dir -r requirements.txt
	cd app/frontend && npm install

backend: ## run the API on :8000
	$(PY) -m uvicorn app.backend.main:app --reload --port 8000

frontend: ## run the Vite dev server on :5173
	cd app/frontend && npm run dev -- --port 5173 --strictPort

dev: ## run backend + frontend together; open http://localhost:5173
	./scripts/dev.sh

test: ## unit + integration tests
	$(PY) -m pytest

e2e: ## end-to-end browser tests (installs Playwright on first run)
	cd tests/e2e && npm install && npx playwright install chromium && npm test

clean: ## drop the venv and the vite cache
	rm -rf .venv app/frontend/node_modules/.vite
