import io
import logging
from datetime import datetime
from pathlib import Path

from database import SessionLocal
from models.page import Page
from models.page_asset import PageAsset
from services.prompt_service import build_page_visual_prompt, DEFAULT_STYLE_PRESET

logger = logging.getLogger(__name__)

IMAGE_STORAGE_ROOT = Path("storage/images")
DEFAULT_WIDTH = 768
DEFAULT_HEIGHT = 1024
DEFAULT_STEPS = 24
DEFAULT_GUIDANCE = 7.0
DEFAULT_IMAGE_MODEL = "stabilityai/stable-diffusion-2-base"

_pipeline = None
_torch = None
_device = None
_PIL_Image = None
_PIL_ImageDraw = None


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

        prompt = prompt_data["visual_prompt"]
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
        asset.visual_prompt = prompt
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
    kwargs = {
        "prompt": prompt,
        "negative_prompt": negative_prompt or None,
        "num_inference_steps": DEFAULT_STEPS,
        "guidance_scale": DEFAULT_GUIDANCE,
        "width": DEFAULT_WIDTH,
        "height": DEFAULT_HEIGHT,
    }
    result = pipeline(**kwargs)
    if not result or not getattr(result, "images", None):
        return None
    return result.images[0]


def _get_pipeline():
    global _pipeline, _torch, _device
    if _pipeline is not None:
        return _pipeline
    try:
        import torch as torch_module
        from diffusers import StableDiffusionPipeline
    except Exception:
        return None

    _torch = torch_module
    _device = torch_module.device("cuda" if torch_module.cuda.is_available() else "cpu")
    dtype = torch_module.float16 if _device.type == "cuda" else torch_module.float32
    _pipeline = StableDiffusionPipeline.from_pretrained(
        DEFAULT_IMAGE_MODEL,
        torch_dtype=dtype,
    )
    _pipeline = _pipeline.to(_device)
    return _pipeline


def _render_placeholder(prompt: str):
    image_module, draw_module = _get_pillow_modules()
    image = image_module.new("RGB", (DEFAULT_WIDTH, DEFAULT_HEIGHT), color=(25, 28, 34))
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
