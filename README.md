# Trendlens

Turn a scattered pile of fashion inspiration photos into a searchable,
filterable, annotatable library. Upload a garment photo; a vision model
classifies it into structured attributes plus a natural-language description;
designers then search, filter, and annotate.

The design rationale, data model, and trade-offs live in [Design.md](./Design.md).
The classifier evaluation lives in [eval/results.md](./eval/results.md).

## How it works

All intelligence happens once, at upload time. A single vision-model call turns
the image into a rich description and a structured `GarmentAttributes` record
(garment type, style, material, color palette, season, occasion, location). Every
downstream feature — attribute filters, full-text search, annotations — is plain
CRUD over that structured data, so reads are fast and free of model calls.

- **Backend:** FastAPI + SQLite (with an FTS5 index over descriptions and
  annotations). Filter facets are generated from the data itself, never hardcoded.
- **Frontend:** React 18 + Vite + Tailwind.
- **Classifier:** OpenAI `gpt-4o-mini` by default (switchable via `MODEL`),
  output validated against a Pydantic schema with a re-prompt-on-invalid retry loop.

## Quick start

Prerequisites: Python 3.11+ and Node 18+.

```bash
cp .env.example .env   # then set OPENAI_API_KEY
make setup             # create .venv + install backend & frontend deps (first time)
make dev               # run backend (:8000) + frontend (:5173); open http://localhost:5173
```

`make help` lists all targets. `OPENAI_API_KEY` is required for classifying
uploads; `MODEL` defaults to `gpt-4o-mini`.

> **macOS note:** keep this project out of the iCloud-synced `~/Desktop` and
> `~/Documents`. iCloud can evict file contents ("dataless" files), which
> corrupts the `.venv` and `node_modules`. A non-synced path like `~/code/…`
> is safe.

### Run it manually instead

```bash
# backend
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m uvicorn app.backend.main:app --reload   # http://localhost:8000

# frontend (separate terminal)
cd app/frontend && npm install && npm run dev               # http://localhost:5173
```

The dev server proxies `/api` and `/uploads` to the backend on `:8000`, so open
the app at **http://localhost:5173**.

## Testing

Two layers, both runnable locally with no external API calls.

```bash
# Unit + integration (API over a throwaway SQLite DB; classifier not involved)
.venv/bin/python -m pytest

# End-to-end (Playwright drives the real UI; backend runs with a seeded DB
# and a stubbed classifier, so no OpenAI spend)
cd tests/e2e
npm install
npx playwright install chromium   # one-time browser download
npm test
```

See [tests/e2e/README.md](./tests/e2e/README.md) for how the e2e harness boots
its servers.

## Evaluation

The classifier is measured against hand-labeled ground truth, per attribute,
split by image difficulty (street vs studio) and across `gpt-4o-mini` vs `gpt-4o`.

```bash
# Score the test set and (re)write eval/results.md — needs OPENAI_API_KEY
PYTHONPATH=. .venv/bin/python eval/run_eval.py
```

Predictions are cached per model, so re-scoring after a labeling change is free.
Methodology and the full results table + failure analysis are in
[eval/README.md](./eval/README.md) and [eval/results.md](./eval/results.md).

## Project layout

```
app/backend/    FastAPI app, classifier, schemas, SQLite/FTS5 data layer
app/frontend/   React + Vite UI
eval/           evaluation harness, test set, and results
tests/          unit + integration (pytest) and e2e (Playwright)
```
