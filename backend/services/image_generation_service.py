import io
import logging
import os
from contextlib import nullcontext
from datetime import datetime
from pathlib import Path

from database import SessionLocal
from models.page import Page
from models.page_asset import PageAsset
from services.prompt_service import build_page_visual_prompt, DEFAULT_STYLE_PRESET

logger = logging.getLogger(__name__)

IMAGE_STORAGE_ROOT = Path("storage/images")

_pipeline = None
_torch = None
_device = None
_PIL_Image = None
_PIL_ImageDraw = None
_pipeline_model_name = None


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
        image_bytes = _generate_image_bytes(prompt, negative_prompt)
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


def _generate_image_bytes(prompt: str, negative_prompt: str) -> bytes:
    image = _render_with_diffusers(prompt, negative_prompt)
    if image is None:
        image = _render_placeholder(prompt)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _render_with_diffusers(prompt: str, negative_prompt: str):
    pipeline = _get_pipeline()
    if pipeline is None:
        return None
    width = int(os.getenv("BOOKTURES_SD_WIDTH", "512"))
    height = int(os.getenv("BOOKTURES_SD_HEIGHT", "768"))
    steps = int(os.getenv("BOOKTURES_SD_STEPS", "6"))
    guidance = float(os.getenv("BOOKTURES_SD_GUIDANCE", "8.5"))
    prompt = _clip_safe_prompt(prompt, pipeline)
    negative_prompt = _clip_safe_prompt(negative_prompt, pipeline) if negative_prompt else ""
    context = _torch.autocast("cuda") if _device is not None and _device.type == "cuda" else nullcontext()
    kwargs = {
        "prompt": prompt,
        "negative_prompt": negative_prompt or None,
        "num_inference_steps": steps,
        "guidance_scale": guidance,
        "width": width,
        "height": height,
    }
    with context:
        result = pipeline(**kwargs)
    if not result or not getattr(result, "images", None):
        return None
    return result.images[0]


def _get_pipeline():
    global _pipeline, _torch, _device, _pipeline_model_name
    image_model = os.getenv("BOOKTURES_SD_MODEL", "segmind/SSD-1B")
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


def _clip_safe_prompt(text: str, pipeline) -> str:
    cleaned = (text or "").strip()
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
