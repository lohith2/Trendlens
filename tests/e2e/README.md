# End-to-end tests (Playwright)

Browser-level coverage of the core flows: grid load, attribute/designer
filtering, full-text search, detail panel + annotation, and upload.

## How it runs

Playwright starts two servers (see `playwright.config.js`):

1. **API** — `tests/e2e/serve.py` launches the FastAPI app against a throwaway
   SQLite DB and uploads dir under `tests/e2e/.tmp/` (recreated each run). It
   seeds three known classified images and **stubs the vision classifier**, so
   the upload flow runs end-to-end without calling OpenAI or spending budget.
2. **Frontend** — the Vite dev server on `:5173`, which proxies `/api` and
   `/uploads` to the API. Tests drive the real UI there.

The tests share one seeded DB and run serially (`workers: 1`); the upload test,
the only one that changes the grid count, is declared last.

## Setup

```bash
cd tests/e2e
npm install
npx playwright install chromium   # one-time browser download
```

Requires the Python venv at the repo root (`.venv`) with the app installed —
the same one the backend and unit/integration tests use.

## Run

```bash
cd tests/e2e
npm test            # headless
npm run test:headed # watch it drive a browser
npm run report      # open the last HTML report
```
