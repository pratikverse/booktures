# Phase 2 (part 1) — storage provider + Gemini

## What changed

- `backend/providers/storage_provider.py` — `StorageProvider` interface,
  `LocalStorageProvider` (existing disk behavior, default), `SupabaseStorageProvider`
  (Supabase Storage REST API), `CloudflareR2Provider` (R2's S3-compatible API via
  boto3). Selected via `STORAGE_PROVIDER` (`local`/`supabase`/`r2`).
- Illustration output now goes through the storage provider (`image_provider.py`'s
  `_save`), so generated pages land wherever `STORAGE_PROVIDER` points instead of
  always writing to local disk.
- `routes.py`'s `_public_storage_url` now passes full `http(s)://` URLs through
  unchanged, so illustrations stored on Supabase/R2 render correctly in the frontend.
- Added `GeminiProvider` to `llm_provider.py` (`LLM_PROVIDER=gemini`), alongside
  Ollama and Groq.

## Scope note: PDFs stay on local disk

Uploaded PDFs are still written to and read from local disk — `pdf_service`
extracts text from the file path directly (`pdfplumber.open(...)`), and that
happens in the same running instance shortly after upload, so ephemeral disk
is fine for that. Only generated illustrations (pure output, no re-read needed)
were moved behind the storage provider. Moving PDF upload storage too would need
a download-back-to-local step before extraction — not needed unless we split
upload and processing across instances, which isn't planned yet.

## Config

```
STORAGE_PROVIDER=local     # or supabase, r2
SUPABASE_URL=
SUPABASE_SERVICE_KEY=
SUPABASE_BUCKET=Booktures

R2_ACCOUNT_ID=
R2_BUCKET=
R2_ACCESS_KEY_ID=
R2_SECRET_ACCESS_KEY=
R2_PUBLIC_URL=

LLM_PROVIDER=gemini        # or ollama, groq
GEMINI_API_KEY=
GROQ_API_KEY=
```

## Supabase — verified working

Local dev is now pointed at a real Supabase project (Postgres + Storage, local
`.env`, not committed):

- `alembic upgrade head` ran cleanly against the Supabase Postgres instance,
  baseline schema created.
- Upload and public-read against the `Booktures` bucket both confirmed working
  via the storage REST API.
- Bucket needs the **Public** toggle on, since `SupabaseStorageProvider` returns
  `.../storage/v1/object/public/<bucket>/<key>` URLs (no signed-URL support yet).
