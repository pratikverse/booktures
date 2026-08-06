# Phase 4 — backend deployment (HF Spaces)

## What changed

- Root `Dockerfile` — builds an API-only image from `backend/requirements-api.txt`
  (no torch/diffusers), installs `tesseract-ocr` for OCR fallback, runs
  `alembic upgrade head` then `uvicorn` on `$PORT` (defaults to 7860, the port
  HF Spaces expects).
- Root `.dockerignore` — excludes `frontend/`, `docs/`, `backend/storage/`,
  `backend/.env`, and the GPU requirements file from the build context.
- HF Spaces YAML frontmatter added to the top of the root `README.md` (`sdk:
  docker`, `app_port: 7860`) - required for HF to recognize this as a Docker
  Space when the Space is linked directly to this GitHub repo.

## Verified locally

Built the image and ran it in a real container against the actual Supabase
DB and Cloudflare/Groq keys:

- `docker build` succeeds off `requirements-api.txt` alone.
- Container boots, runs the Alembic migration, and starts uvicorn cleanly.
- `/health` → 200, `/ready` → `{"status": "ready"}` (real DB round-trip),
  `/books` → 401 without the API key, 200 with it.

## Bug caught: Supabase direct connection needs IPv6

The direct `DATABASE_URL` (`db.<ref>.supabase.co:5432`) resolves to an
IPv6-only address. Docker Desktop's default network - and most free-tier
hosts, HF Spaces included - have no IPv6 egress, so every connection failed
with "Network is unreachable". Fixed by switching to Supabase's **Session
pooler** connection string instead (`aws-0-<region>.pooler.supabase.com:5432`),
which is IPv4-compatible. Anyone deploying this needs the pooler string, not
the direct one - the direct string is fine for local dev only.

## Deploying to Hugging Face Spaces

1. Create a new Space at huggingface.co/new-space. SDK: **Docker**,
   visibility: your choice. (You can also pick a different default port,
   but leave it matching `app_port` in the README frontmatter.)
2. In the Space's **Settings → Repository secrets**, add every value from
   `backend/.env.example` that has a real value in your local `backend/.env`:
   `DATABASE_URL` (the **pooler** string), `APP_API_KEY`, `STORAGE_PROVIDER`,
   `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `SUPABASE_BUCKET`, `LLM_PROVIDER`,
   `GROQ_API_KEY`, `GEMINI_API_KEY`, `IMAGE_PROVIDER`, `CF_ACCOUNT_ID`,
   `CF_API_TOKEN`, `SKIP_DB_AUTOCREATE=true`, and `CORS_ORIGINS` set to
   wherever the frontend ends up hosted.
3. Link the Space to this GitHub repo (Settings → "Sync from a GitHub
   repository") so pushes to `main` auto-deploy, or push directly to the
   Space's own git remote.
4. Once deployed, confirm `https://<your-space>.hf.space/health` and
   `/ready` both return healthy, then point the frontend's
   `VITE_API_BASE_URL` at that URL.

## Not done yet

Frontend hosting (Vercel/Netlify/Cloudflare Pages) - next step once the
backend URL is live and confirmed.
