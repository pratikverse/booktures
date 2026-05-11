import os
import subprocess
from dotenv import set_key, load_dotenv
import httpx

ENV_FILE = ".env"

def update_setting(key: str, value: str):
    """Persists a setting to the .env file and active environment."""
    set_key(ENV_FILE, key, value)
    os.environ[key] = value
    load_dotenv(ENV_FILE, override=True)

def get_available_ollama_models(base_url: str | None = None):
    """Detects available models from Ollama's HTTP API, with CLI fallback."""
    target_base = (base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")).rstrip("/")
    try:
        r = httpx.get(f"{target_base}/api/tags", timeout=8.0)
        r.raise_for_status()
        data = r.json()
        names = []
        for item in data.get("models", []):
            name = item.get("name")
            if name and name not in names:
                names.append(name)
        if names:
            return names
    except Exception:
        pass

    # Fallback for environments where HTTP access is blocked but CLI works.
    try:
        result = subprocess.run(["ollama", "list"], capture_output=True, text=True, check=False)
        if result.returncode != 0:
            return []
        models = []
        for line in result.stdout.splitlines():
            row = line.strip()
            if not row or row.upper().startswith("NAME "):
                continue
            name = row.split()[0]
            if name and name not in models:
                models.append(name)
        return models
    except Exception:
        return []

def get_mode_presets(mode: str):
    presets = {"fast": {"steps": 15}, "quality": {"steps": 50}}
    return presets.get(mode, presets["fast"])
