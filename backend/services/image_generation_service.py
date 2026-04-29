import io
import logging
import os
import random
import re
from contextlib import nullcontext
from datetime import datetime
from pathlib import Path

from database import SessionLocal
from models.page import Page
from models.page_asset import PageAsset
from services.prompt_service import build_page_visual_prompt, DEFAULT_STYLE_PRESET

logger = logging.getLogger(__name__)

IMAGE_STORAGE_ROOT = Path(__file__).resolve().parents[1] / "storage" / "images"

_pipeline = None
_torch = None
_device = None
_PIL_Image = None
_PIL_ImageDraw = None
_pipeline_model_name = None

MODE_ALIASES = {"quality", "balanced", "fast", "custom"}
MODE_DEFAULTS = {
    "quality": {"model": "stabilityai/stable-diffusion-xl-base-1.0", "steps": 28, "guidance": 6.5, "width": 1024, "height": 1024},
    "balanced": {"model": "segmind/SSD-1B", "steps": 12, "guidance": 8.0, "width": 768, "height": 768},
    "fast": {"model": "stabilityai/sd-turbo", "steps": 4, "guidance": 1.5, "width": 512, "height": 768},
}


def generate_page_image(
    book_id: int,
    page_number: int,
    style_preset: str = DEFAULT_STYLE_PRESET,
    force_prompt_refresh: bool = False,
    force_regenerate: bool = False,
) -> dict:
    db = SessionLocal()
    try:
        page = (
            db.query(Page)
            .filter(Page.book_id == book_id, Page.page_number == page_number)
            .first()
        )
        if page is None:
            return {"status": "not_found", "book_id": book_id, "page_number": page_number}

        asset = db.query(PageAsset).filter(PageAsset.page_id == page.id).one_or_none()
        if asset and asset.image_path and not force_regenerate:
            return {
                "status": "already_generated",
                "book_id": book_id,
                "page_number": page_number,
                "image_path": asset.image_path,
            }

        prompt_data = build_page_visual_prompt(
            book_id=book_id,
            page_number=page_number,
            style_preset=style_preset,
            force_refresh=force_prompt_refresh,
        )
        if prompt_data.get("status") != "ok":
            return {
                "status": "prompt_unavailable",
                "book_id": book_id,
                "page_number": page_number,
            }

        auto_prompt = prompt_data["visual_prompt"]
        prompt = (asset.prompt_override if asset and asset.prompt_override else auto_prompt)
        negative_prompt = prompt_data.get("negative_prompt", "")
        image_bytes, generation_meta = _generate_image_bytes(prompt, negative_prompt)
        image_path = _save_image_bytes(book_id, page_number, image_bytes)

        asset = db.query(PageAsset).filter(PageAsset.page_id == page.id).one_or_none()
        if asset is None:
            asset = PageAsset(
                book_id=book_id,
                page_id=page.id,
                page_number=page.page_number,
            )
        asset.scene_summary = prompt_data.get("scene_summary", asset.scene_summary)
        asset.summary_short = prompt_data.get("summary_short", getattr(asset, "summary_short", None))
        asset.continuity_summary = prompt_data.get("continuity_summary", getattr(asset, "continuity_summary", None))
        asset.visual_prompt = auto_prompt
        asset.last_used_prompt = prompt
        asset.negative_prompt = negative_prompt
        asset.style_preset = prompt_data.get("style_preset", style_preset)
        asset.image_path = str(image_path)
        asset.image_model_used = generation_meta.get("model_used")
        asset.image_preset_used = generation_meta.get("mode_used")
        asset.image_seed = generation_meta.get("seed")
        asset.image_status = "generated"
        asset.image_generated_at = datetime.utcnow()
        asset.last_error = None
        asset.updated_at = datetime.utcnow()
        db.add(asset)
        db.commit()

        return {
            "status": "generated",
            "book_id": book_id,
            "page_number": page_number,
            "image_path": str(image_path),
            "model_used": generation_meta.get("model_used"),
            "mode_used": generation_meta.get("mode_used"),
            "seed": generation_meta.get("seed"),
        }

    except Exception as exc:
        db.rollback()
        logger.exception("Image generation failed for book=%s page=%s", book_id, page_number)
        _mark_asset_failed(book_id, page_number, str(exc))
        raise
    finally:
        db.close()


def _mark_asset_failed(book_id: int, page_number: int, error: str):
    db = SessionLocal()
    try:
        page = (
            db.query(Page)
            .filter(Page.book_id == book_id, Page.page_number == page_number)
            .first()
        )
        if page is None:
            return
        asset = db.query(PageAsset).filter(PageAsset.page_id == page.id).one_or_none()
        if asset is None:
            asset = PageAsset(book_id=book_id, page_id=page.id, page_number=page_number)
        asset.image_status = "failed"
        asset.last_error = error[:1000]
        asset.updated_at = datetime.utcnow()
        db.add(asset)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to persist image failure state for book=%s page=%s", book_id, page_number)
    finally:
        db.close()


def _save_image_bytes(book_id: int, page_number: int, image_bytes: bytes) -> Path:
    target = IMAGE_STORAGE_ROOT / str(book_id)
    target.mkdir(parents=True, exist_ok=True)
    image_path = target / f"page_{page_number}.png"
    image_path.write_bytes(image_bytes)
    return image_path


def reset_pipeline():
    global _pipeline, _pipeline_model_name
    _pipeline = None
    _pipeline_model_name = None


def _generate_image_bytes(prompt: str, negative_prompt: str) -> tuple[bytes, dict]:
    image, generation_meta = _render_with_diffusers(prompt, negative_prompt)
    if image is None:
        image = _render_placeholder(prompt)
        generation_meta = generation_meta or {}
        generation_meta["placeholder"] = True

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue(), generation_meta


def _render_with_diffusers(prompt: str, negative_prompt: str) -> tuple[object | None, dict]:
    config = _resolve_image_config()
    fallback_models = _read_env_list("BOOKTURES_SD_FALLBACK_MODELS", [])
    attempted_models = [config["model"]] + [model for model in fallback_models if model and model != config["model"]]
    seed = _resolve_seed()
    last_error: Exception | None = None

    for model_name in attempted_models:
        pipeline = _get_pipeline(model_name)
        if pipeline is None:
            continue
        try:
            safe_prompt = _clip_safe_prompt(prompt, pipeline)
            safe_negative_prompt = _clip_safe_prompt(negative_prompt, pipeline) if negative_prompt else ""
            context = _torch.autocast("cuda") if _device is not None and _device.type == "cuda" else nullcontext()
            kwargs = {
                "prompt": safe_prompt,
                "negative_prompt": safe_negative_prompt or None,
                "num_inference_steps": int(config["steps"]),
                "guidance_scale": float(config["guidance"]),
                "width": int(config["width"]),
                "height": int(config["height"]),
                "generator": _build_generator(seed),
            }
            with context:
                result = pipeline(**kwargs)
            if result and getattr(result, "images", None):
                return result.images[0], {
                    "model_used": model_name,
                    "mode_used": config["mode"],
                    "seed": seed,
                }
        except Exception as exc:
            last_error = exc
            if not _is_recoverable_generation_error(exc):
                raise
            logger.warning("Image generation failed with model '%s', trying fallback if available: %s", model_name, exc)
            continue

    if last_error:
        logger.warning("Image generation falling back to placeholder after model failures: %s", last_error)
    return None, {"model_used": attempted_models[-1] if attempted_models else None, "mode_used": config["mode"], "seed": seed}


def _get_pipeline(image_model: str):
    global _pipeline, _torch, _device, _pipeline_model_name
    if _pipeline is not None and _pipeline_model_name == image_model:
        return _pipeline
    try:
        import torch as torch_module
        from diffusers import DiffusionPipeline
    except Exception:
        return None

    _torch = torch_module
    _device = torch_module.device("cuda" if torch_module.cuda.is_available() else "cpu")
    dtype = torch_module.float16 if _device.type == "cuda" else torch_module.float32
    load_kwargs = {
        "torch_dtype": dtype,
        "use_safetensors": True,
    }
    if _device.type == "cuda":
        load_kwargs["variant"] = "fp16"
    _pipeline = DiffusionPipeline.from_pretrained(image_model, **load_kwargs)
    _pipeline_model_name = image_model
    if _device.type == "cuda":
        _pipeline.enable_attention_slicing()
        try:
            _pipeline.enable_model_cpu_offload()
        except Exception:
            logger.debug("CPU offload unavailable, keeping pipeline on GPU")
        try:
            _pipeline.enable_xformers_memory_efficient_attention()
        except Exception:
            logger.debug("xformers attention unavailable, using default attention")
    else:
        _pipeline = _pipeline.to(_device)
    return _pipeline


def _resolve_image_config() -> dict:
    mode = (os.getenv("BOOKTURES_IMAGE_MODE", "balanced") or "balanced").strip().lower()
    if mode not in MODE_ALIASES:
        mode = "balanced"
    if mode == "custom":
        return {
            "mode": mode,
            "model": os.getenv("BOOKTURES_SD_MODEL", MODE_DEFAULTS["balanced"]["model"]),
            "width": int(os.getenv("BOOKTURES_SD_WIDTH", "768")),
            "height": int(os.getenv("BOOKTURES_SD_HEIGHT", "768")),
            "steps": int(os.getenv("BOOKTURES_SD_STEPS", "12")),
            "guidance": float(os.getenv("BOOKTURES_SD_GUIDANCE", "8.0")),
        }

    preset_defaults = MODE_DEFAULTS.get(mode, MODE_DEFAULTS["balanced"])
    model = os.getenv(f"BOOKTURES_SD_MODEL_{mode.upper()}", preset_defaults["model"])
    width = int(os.getenv(f"BOOKTURES_SD_WIDTH_{mode.upper()}", str(preset_defaults["width"])))
    height = int(os.getenv(f"BOOKTURES_SD_HEIGHT_{mode.upper()}", str(preset_defaults["height"])))
    steps = int(os.getenv(f"BOOKTURES_SD_STEPS_{mode.upper()}", str(preset_defaults["steps"])))
    guidance = float(os.getenv(f"BOOKTURES_SD_GUIDANCE_{mode.upper()}", str(preset_defaults["guidance"])))
    return {
        "mode": mode,
        "model": model,
        "width": width,
        "height": height,
        "steps": steps,
        "guidance": guidance,
    }


def _resolve_seed() -> int:
    raw_seed = (os.getenv("BOOKTURES_SD_SEED") or "").strip()
    if raw_seed:
        try:
            return int(raw_seed)
        except ValueError:
            logger.warning("Invalid BOOKTURES_SD_SEED value '%s'; using random seed", raw_seed)
    return random.randint(0, 2**31 - 1)


def _build_generator(seed: int):
    if _torch is None:
        return None
    if _device is None:
        return _torch.Generator().manual_seed(seed)
    return _torch.Generator(device=_device.type).manual_seed(seed)


def _read_env_list(name: str, default: list[str]) -> list[str]:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    return [item.strip() for item in raw.split(",") if item.strip()]


def _is_recoverable_generation_error(exc: Exception) -> bool:
    message = str(exc).lower()
    recoverable_markers = [
        "out of memory",
        "cuda out of memory",
        "cublas",
        "cannot allocate memory",
        "model",
        "weights",
    ]
    return any(marker in message for marker in recoverable_markers)


def _clip_safe_prompt(text: str, pipeline) -> str:
    cleaned = _prioritize_prompt_for_clip(text or "")
    if not cleaned:
        return ""
    tokenizers = [
        getattr(pipeline, "tokenizer", None),
        getattr(pipeline, "tokenizer_2", None),
    ]
    tokenizers = [tokenizer for tokenizer in tokenizers if tokenizer is not None]
    if not tokenizers:
        # Conservative fallback when tokenizer is unavailable.
        return " ".join(cleaned.split()[:90]).strip()
    shortest = cleaned
    for tokenizer in tokenizers:
        try:
            max_len = int(getattr(tokenizer, "model_max_length", 77) or 77)
            encoded = tokenizer(
                cleaned,
                truncation=True,
                max_length=max_len,
                add_special_tokens=True,
            )
            input_ids = encoded.get("input_ids")
            if not input_ids:
                continue
            if isinstance(input_ids[0], list):
                input_ids = input_ids[0]
            decoded = tokenizer.decode(input_ids, skip_special_tokens=True).strip()
            if decoded and len(decoded) < len(shortest):
                shortest = decoded
        except Exception:
            continue
    return shortest


def _prioritize_prompt_for_clip(text: str) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return ""

    # Optional escape hatch to preserve original order exactly.
    if not _read_env_bool("BOOKTURES_ENABLE_PROMPT_BUDGETER", True):
        return cleaned

    parts = [part.strip(" .") for part in re.split(r"[.\n]+", cleaned) if part.strip()]
    if not parts:
        return cleaned

    def section_priority(part: str) -> int:
        lower = part.lower()
        if lower.startswith("characters present:"):
            return 0
        if lower.startswith("page beat:"):
            return 1
        if lower.startswith("scene change:"):
            return 2
        if "continuity anchor:" in lower:
            return 3
        if lower.startswith("setting:"):
            return 4
        if lower.startswith("location:"):
            return 5
        if lower.startswith("camera focus:"):
            return 6
        if lower.startswith("lighting:"):
            return 7
        if lower.startswith("mood:"):
            return 8
        if lower.startswith("page actions:"):
            return 9
        if lower.startswith("key objects:"):
            return 10
        if lower.startswith("time of day:") or lower.startswith("weather:"):
            return 11
        # Keep style descriptors and any untagged text later.
        return 20

    indexed = list(enumerate(parts))
    ordered = [item for _, item in sorted(indexed, key=lambda item: (section_priority(item[1]), item[0]))]
    return ". ".join(ordered).strip()


def _render_placeholder(prompt: str):
    image_module, draw_module = _get_pillow_modules()
    width = int(os.getenv("BOOKTURES_SD_WIDTH", "512"))
    height = int(os.getenv("BOOKTURES_SD_HEIGHT", "768"))
    image = image_module.new("RGB", (width, height), color=(25, 28, 34))
    draw = draw_module.Draw(image)
    text = _wrap_text(f"Preview image\n{prompt}", width=75)
    draw.text((30, 30), text, fill=(240, 240, 240))
    return image


def _get_pillow_modules():
    global _PIL_Image, _PIL_ImageDraw
    if _PIL_Image is not None and _PIL_ImageDraw is not None:
        return _PIL_Image, _PIL_ImageDraw
    from PIL import Image, ImageDraw

    _PIL_Image = Image
    _PIL_ImageDraw = ImageDraw
    return _PIL_Image, _PIL_ImageDraw


def _wrap_text(text: str, width: int) -> str:
    words = text.split()
    if not words:
        return ""
    lines = []
    current = []
    for word in words:
        candidate = " ".join(current + [word]).strip()
        if len(candidate) <= width:
            current.append(word)
        else:
            lines.append(" ".join(current))
            current = [word]
    if current:
        lines.append(" ".join(current))
    return "\n".join(lines[:35])


def _read_env_bool(name: str, default: bool) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}
