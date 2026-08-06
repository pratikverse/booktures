# Phase 0 — Stability & deploy-blocker fixes

Fixes applied to the existing app before any provider/deployment work. No new features.

## Fixed

- **Job worker crashes on empty PDFs** — `generation_queue_service.py` divided by
  `len(chunks)`/`len(assets)` with no zero-check. Now short-circuits with a clear status.
- **Jobs stuck "running" after a restart** — worker now resets orphaned `running` jobs to
  `queued` on startup, and claims jobs with `FOR UPDATE SKIP LOCKED` so two workers can run
  safely (needed for the planned local-GPU + cloud hybrid setup).
- **DB session leak** — `db.close()` moved into `finally`.
- **CORS** — `allow_origins=["*"]` with `allow_credentials=True` is invalid per spec; origins
  are now an explicit list via `CORS_ORIGINS` env var.
- **Unbounded upload size** — uploads are now streamed and capped by `MAX_UPLOAD_MB` (default 25MB)
  instead of buffering the whole file before checking anything.
- **Hardcoded DB password (`rmcf`)** — removed from `database.py`, `docker-compose.yml`, and README.
  `DATABASE_URL` is now required (app raises a clear error if unset); `backend/.env.example` added.
- **Admin DB auto-create breaks on managed Postgres** — Supabase/Neon/RDS don't grant access to the
  `postgres` admin DB. Added `SKIP_DB_AUTOCREATE` env var to skip that step in those environments.
- **Settings written to `.env` at runtime** — fails on read-only/ephemeral filesystems. Settings are
  now stored in a DB table (`app_settings`) with env-var fallback, loaded into the process env at startup.
- **No schema migrations** — added Alembic, baselined against the current schema
  (`backend/alembic/versions/0001_baseline.py`), safe to run against both fresh and existing databases.
- **No health checks** — added `/health` (liveness) and `/ready` (DB connectivity).
- **`print()` for startup logging** — replaced with `logging`.

## Dependencies split

`requirements.txt` (2000+ lines pulling in torch/spacy-trf/etc.) made API-only deployment
impossible on free-tier build limits. Split into:

- `backend/requirements-api.txt` — FastAPI, DB, PDF/OCR, spaCy small model. Enough to run the
  API and job worker against cloud LLM/image providers.
- `backend/requirements-local-gpu.txt` — torch, diffusers, transformers, spaCy transformer model.
  Only needed for local GPU inference.
- Root `requirements.txt` now just references both, for local dev parity with before.
- Dropped unused packages: `serpapi`, `python-pptx`, `xlsxwriter`, `reportlab`, `textacy`, `PyMuPDF`
  (none were imported anywhere in `backend/`).

## Not done in this phase (tracked separately)

- Cloud LLM/image/storage provider abstraction (Phase 1)
- Auth, rate limiting, file content validation (Phase 3)
- Actual deployment (Phase 2)

## Migration note for existing local dev setups

1. Copy `backend/.env.example` to `backend/.env`, fill in your real `DATABASE_URL`.
2. Run `alembic upgrade head` from `backend/` once (safe no-op if tables already exist).
3. If you were relying on `PUT /settings` writing to `.env`, existing env vars still work as
   defaults — new values now persist to the database instead.
