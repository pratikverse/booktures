import os
from pathlib import Path


ENV_PATH = Path(__file__).resolve().parent.parent / ".env"

SETTINGS_KEYS = [
    "BOOKTURES_OLLAMA_URL",
    "BOOKTURES_OLLAMA_MODEL",
    "BOOKTURES_OLLAMA_TIMEOUT",
    "BOOKTURES_SD_MODEL",
    "BOOKTURES_SD_WIDTH",
    "BOOKTURES_SD_HEIGHT",
    "BOOKTURES_SD_STEPS",
    "BOOKTURES_SD_GUIDANCE",
]

DEFAULTS = {
    "BOOKTURES_OLLAMA_URL": "http://127.0.0.1:11434/v1/chat/completions",
    "BOOKTURES_OLLAMA_MODEL": "granite3.2:8b",
    "BOOKTURES_OLLAMA_TIMEOUT": "45",
    "BOOKTURES_SD_MODEL": "segmind/SSD-1B",
    "BOOKTURES_SD_WIDTH": "512",
    "BOOKTURES_SD_HEIGHT": "768",
    "BOOKTURES_SD_STEPS": "6",
    "BOOKTURES_SD_GUIDANCE": "8.5",
}


def apply_env_file():
    for key, value in _read_env_file().items():
        os.environ[key] = value


def get_settings() -> dict:
    values = {}
    file_values = _read_env_file()
    for key in SETTINGS_KEYS:
        values[key] = os.environ.get(key) or file_values.get(key) or DEFAULTS[key]
    return {
        "ollama_url": values["BOOKTURES_OLLAMA_URL"],
        "model_name": values["BOOKTURES_OLLAMA_MODEL"],
        "timeout": int(values["BOOKTURES_OLLAMA_TIMEOUT"]),
        "image_model": values["BOOKTURES_SD_MODEL"],
        "image_width": int(values["BOOKTURES_SD_WIDTH"]),
        "image_height": int(values["BOOKTURES_SD_HEIGHT"]),
        "image_steps": int(values["BOOKTURES_SD_STEPS"]),
        "image_guidance": float(values["BOOKTURES_SD_GUIDANCE"]),
    }


def update_settings(payload: dict) -> dict:
    normalized = {
        "BOOKTURES_OLLAMA_URL": str(payload["ollama_url"]).strip(),
        "BOOKTURES_OLLAMA_MODEL": str(payload["model_name"]).strip(),
        "BOOKTURES_OLLAMA_TIMEOUT": str(int(payload["timeout"])),
        "BOOKTURES_SD_MODEL": str(payload["image_model"]).strip(),
        "BOOKTURES_SD_WIDTH": str(int(payload["image_width"])),
        "BOOKTURES_SD_HEIGHT": str(int(payload["image_height"])),
        "BOOKTURES_SD_STEPS": str(int(payload["image_steps"])),
        "BOOKTURES_SD_GUIDANCE": _format_float(payload["image_guidance"]),
    }
    _write_env_file(normalized)
    for key, value in normalized.items():
        os.environ[key] = value
    return get_settings()


def _format_float(value) -> str:
    number = float(value)
    return f"{number:g}"


def _read_env_file() -> dict[str, str]:
    if not ENV_PATH.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in ENV_PATH.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _write_env_file(updates: dict[str, str]):
    existing_lines = ENV_PATH.read_text().splitlines() if ENV_PATH.exists() else []
    remaining = dict(updates)
    written_lines: list[str] = []

    for raw_line in existing_lines:
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#") or "=" not in raw_line:
            written_lines.append(raw_line)
            continue
        key, _value = raw_line.split("=", 1)
        normalized_key = key.strip()
        if normalized_key in remaining:
            written_lines.append(f"{normalized_key}={remaining.pop(normalized_key)}")
        else:
            written_lines.append(raw_line)

    for key in SETTINGS_KEYS:
        if key in remaining:
            written_lines.append(f"{key}={remaining.pop(key)}")

    ENV_PATH.write_text("\n".join(written_lines).rstrip() + "\n")
