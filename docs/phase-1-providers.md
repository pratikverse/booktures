# Phase 1 — LLM/image provider abstraction

Goal: run the app on free-tier infra without a GPU, by swapping local
inference for cloud calls, without touching call sites elsewhere in the app.

## What changed

- `backend/providers/llm_provider.py` — `LLMProvider` interface, `OllamaProvider`
  (local, existing behavior), `GroqProvider` (free-tier cloud, OpenAI-compatible
  API). Selected via `LLM_PROVIDER` env var (`ollama` default, or `groq`).
- `backend/providers/image_provider.py` — `ImageProvider` interface,
  `DiffusersProvider` (local GPU/CPU, existing behavior), `PollinationsProvider`
  (free, keyless cloud image gen). Selected via `IMAGE_PROVIDER` env var
  (`diffusers` default, or `pollinations`).
- `pdf_service.ollama_generate()` and `image_generation_service.render_page_image()`
  now delegate to the configured provider. Every caller (`character_service`,
  `prompt_service`, the job worker) is unchanged.
- `torch`/`diffusers` imports are now inside `DiffusersProvider` methods, not
  module-level — so `IMAGE_PROVIDER=pollinations` runs fine off
  `requirements-api.txt` alone, no GPU stack needed.

## Config

```
LLM_PROVIDER=ollama            # or groq
GROQ_API_KEY=                  # required if LLM_PROVIDER=groq
GROQ_MODEL=llama-3.1-8b-instant

IMAGE_PROVIDER=diffusers       # or pollinations
```

## Not done in this phase

- Storage provider abstraction (local disk vs. Supabase/R2) — tracked for
  when actual deployment (Phase 2) is scoped.
- No changes to character NER (spaCy) — still local/CPU, cheap enough to keep.
