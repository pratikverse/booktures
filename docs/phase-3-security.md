# Phase 3 — security hardening

Done before deployment since the app will be publicly reachable with live
Groq/Gemini/Cloudflare keys behind it.

## What changed

- **Shared API key auth** (`backend/api/auth.py`) — `require_api_key` checks
  `X-API-Key` against `APP_API_KEY`, applied to the whole router in `main.py`.
  If `APP_API_KEY` is unset, auth is skipped entirely (local dev unaffected).
  `/health` and `/ready` stay open (needed for host health checks).
- **Rate limiting** (`backend/api/limiter.py`, via `slowapi`) — `/upload-pdf`
  and `/books/{id}/generate-images` capped at 5/minute per IP, since those
  are the two endpoints that spend LLM/image provider credits.
- **PDF validation on upload** — extension check narrowed to `.pdf` only
  (`.jpg`/`.png` were accepted before but never actually processed -
  `extract_text_by_page` only handles PDFs, so those uploads were already
  dead ends). Added a magic-byte check (`content.startswith(b"%PDF-")`) so a
  renamed non-PDF is rejected before it reaches the job worker.
- **Frontend sends the key** — `apiClient.ts` attaches `X-API-Key` from
  `VITE_API_KEY` when set.

## Verified locally

Ran a real server and confirmed: no key -> 401, wrong key -> 401, correct
key -> 200, `/health` reachable without a key, and the 5/minute upload limit
actually kicks in on the 6th request (429).

## Config

```
APP_API_KEY=some-long-random-string   # required for any public deploy
```

```
VITE_API_KEY=same-value-as-APP_API_KEY
```

## Not done

Per-user accounts/login - out of scope, this is a single-operator app. The
shared API key is the appropriate level of protection for "keep it private
to me and whoever I share the key with," not a multi-tenant auth system.
