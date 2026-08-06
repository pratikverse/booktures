# Phase 2 (part 3) — character extraction hardening

The character/visual-bible pipeline is the core of illustration consistency,
so it needed to fail loud instead of quietly degrading. Changes in
`backend/services/character_service.py`:

- **Alias grouping rewritten as union-find** — was first-match-wins fuzzy
  matching, order-dependent and non-transitive. Now honorific-stripped
  (Mr./Mrs./Dr./etc.) and transitively merged, so "Mr. Sherlock Holmes",
  "Sherlock", and "Holmes" always land in one group regardless of scan order.
- **Wider context sampling** — visual trait extraction used to sample only
  the first 8 mentions; now spreads samples across the whole book so traits
  revealed late aren't missed.
- **Fail loud, not silent** — empty LLM responses get one retry, then log a
  warning and fall back to an explicit "No visual description available."
  instead of baking `""` into the visual bible.
- **`extract_page_metadata` now uses JSON** instead of brittle
  `"Characters:"/"Scene:"` string splitting, with a retry on malformed output.
- **Removed `generate_visual_bible()`** — dead code, unused by the actual
  pipeline (which rebuilds the bible inline in the job worker).
- **New `CHARACTER_EXTRACTION_MODE=llm`** — a single LLM pass that extracts
  characters + visual traits directly, no spaCy needed. Useful on API-only/
  no-GPU deploys where the transformer NER model isn't installed and the
  small model's PERSON detection is weak. Default stays `spacy` (unchanged
  behavior).

## Bug found while testing: cross-provider model override

`ollama_generate()` callers were passing Ollama-specific model tags (e.g.
`qwen2.5:7b`) straight through even when `LLM_PROVIDER=groq`/`gemini` — Groq
returned 404 (no such model) for every character/prompt call. Fixed in
`pdf_service.ollama_generate()`: the explicit model override is now dropped
unless the active provider is `ollama`, so cloud providers fall back to their
own configured default model. Verified against a real Groq call after the fix.

## Config

```
CHARACTER_EXTRACTION_MODE=spacy   # or llm
```
