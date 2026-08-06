"""
LLM provider abstraction. Swap between local Ollama and a cloud free-tier
provider (Groq) via the LLM_PROVIDER env var, without touching call sites.
"""

import os
import logging
import httpx

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_TIMEOUT_SECONDS = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "180.0"))
OLLAMA_DEFAULT_MODEL = os.getenv("OLLAMA_DEFAULT_MODEL", "qwen2.5:7b")

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_DEFAULT_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
GROQ_TIMEOUT_SECONDS = float(os.getenv("GROQ_TIMEOUT_SECONDS", "60.0"))

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
GEMINI_DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
GEMINI_TIMEOUT_SECONDS = float(os.getenv("GEMINI_TIMEOUT_SECONDS", "60.0"))


class LLMProvider:
    def generate(self, prompt: str, system: str = "", model: str | None = None) -> str:
        raise NotImplementedError


class OllamaProvider(LLMProvider):
    """Local inference via Ollama's HTTP API."""

    def generate(self, prompt: str, system: str = "", model: str | None = None) -> str:
        payload = {
            "model": model or OLLAMA_DEFAULT_MODEL,
            "prompt": prompt,
            "stream": False,
        }
        if system:
            payload["system"] = system

        try:
            response = httpx.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json=payload,
                timeout=OLLAMA_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            return response.json().get("response", "").strip()
        except httpx.HTTPError as exc:
            logger.warning("Ollama HTTP request failed (model=%s): %s", payload["model"], exc)
        except Exception as exc:
            logger.warning("Unexpected Ollama error (model=%s): %s", payload["model"], exc)
        return ""


class GroqProvider(LLMProvider):
    """Cloud inference via Groq's free-tier OpenAI-compatible API."""

    def generate(self, prompt: str, system: str = "", model: str | None = None) -> str:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            logger.warning("GROQ_API_KEY not set; skipping LLM call.")
            return ""

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        try:
            response = httpx.post(
                f"{GROQ_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"model": model or GROQ_DEFAULT_MODEL, "messages": messages},
                timeout=GROQ_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"].strip()
        except httpx.HTTPError as exc:
            logger.warning("Groq HTTP request failed: %s", exc)
        except Exception as exc:
            logger.warning("Unexpected Groq error: %s", exc)
        return ""


class GeminiProvider(LLMProvider):
    """Cloud inference via Google's Gemini free-tier API."""

    def generate(self, prompt: str, system: str = "", model: str | None = None) -> str:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            logger.warning("GEMINI_API_KEY not set; skipping LLM call.")
            return ""

        body = {"contents": [{"parts": [{"text": prompt}]}]}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}

        try:
            response = httpx.post(
                f"{GEMINI_BASE_URL}/models/{model or GEMINI_DEFAULT_MODEL}:generateContent",
                params={"key": api_key},
                json=body,
                timeout=GEMINI_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            data = response.json()
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
        except httpx.HTTPError as exc:
            logger.warning("Gemini HTTP request failed: %s", exc)
        except Exception as exc:
            logger.warning("Unexpected Gemini error: %s", exc)
        return ""


_providers = {
    "ollama": OllamaProvider,
    "groq": GroqProvider,
    "gemini": GeminiProvider,
}


def get_llm_provider() -> LLMProvider:
    name = os.getenv("LLM_PROVIDER", "ollama").strip().lower()
    cls = _providers.get(name, OllamaProvider)
    return cls()
