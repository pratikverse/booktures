"""
Image provider abstraction. Swap between local Diffusers inference and a
cloud free-tier provider (Pollinations) via the IMAGE_PROVIDER env var.
"""

import os
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

STORAGE_PATH = Path(__file__).resolve().parents[1] / "storage" / "illustrations"

MODE_ALIASES = {"quality", "balanced", "fast", "custom"}
MODE_DEFAULTS = {
    "quality": {"model": "SG161222/RealVisXL_V4.0", "steps": 24, "guidance": 5.5, "width": 768, "height": 768},
    "balanced": {"model": "segmind/SSD-1B", "steps": 12, "guidance": 8.0, "width": 768, "height": 768},
    "fast": {"model": "stabilityai/sd-turbo", "steps": 4, "guidance": 1.5, "width": 512, "height": 768},
}


def _resolve_generation_config():
    image_mode = os.getenv("IMAGE_PRESET", "balanced").strip().lower()
    if image_mode not in MODE_ALIASES:
        image_mode = "balanced"

    defaults = MODE_DEFAULTS["balanced"] if image_mode == "custom" else MODE_DEFAULTS[image_mode]
    return {
        "model": os.getenv("DIFFUSION_MODEL", defaults["model"]),
        "steps": int(os.getenv("IMAGE_STEPS", str(defaults["steps"]))),
        "guidance": float(os.getenv("IMAGE_GUIDANCE", str(defaults["guidance"]))),
        "width": int(os.getenv("IMAGE_WIDTH", str(defaults["width"]))),
        "height": int(os.getenv("IMAGE_HEIGHT", str(defaults["height"]))),
    }


def _save(image, book_id: int, page_num: int) -> str:
    book_dir = STORAGE_PATH / f"book_{book_id}"
    book_dir.mkdir(parents=True, exist_ok=True)
    file_path = book_dir / f"page_{page_num}.png"
    image.save(file_path)
    return f"storage/illustrations/book_{book_id}/page_{page_num}.png"


class ImageProvider:
    def render(self, prompt: str, negative_prompt: str, book_id: int, page_num: int, seed: int) -> Optional[str]:
        raise NotImplementedError


class DiffusersProvider(ImageProvider):
    """Local inference via a diffusers pipeline (GPU/CPU)."""

    def __init__(self):
        self.pipe = None
        self.model_id = None
        self.device = None

    def _load_pipeline(self, model_id: str):
        import torch
        from diffusers import DiffusionPipeline

        if self.device is None:
            self.device = "cuda" if torch.cuda.is_available() else "cpu"

        if self.pipe is not None and self.model_id != model_id:
            logger.info(f"Model changed from '{self.model_id}' to '{model_id}', reloading pipeline...")
            self.pipe = None

        if self.pipe is not None:
            return

        self.model_id = model_id
        logger.info(f"Loading diffusion pipeline '{model_id}' on {self.device}...")
        dtype = torch.float16 if self.device == "cuda" else torch.float32
        self.pipe = DiffusionPipeline.from_pretrained(
            model_id,
            torch_dtype=dtype,
            use_safetensors=True,
            variant="fp16" if self.device == "cuda" else None,
        )
        self.pipe.to(self.device)
        if self.device == "cuda":
            self.pipe.enable_attention_slicing()
        logger.info("Diffusion pipeline loaded successfully.")

    def render(self, prompt: str, negative_prompt: str, book_id: int, page_num: int, seed: int) -> Optional[str]:
        import torch

        config = _resolve_generation_config()
        self._load_pipeline(config["model"])
        generator = torch.Generator(device=self.device).manual_seed(seed)

        try:
            image = self.pipe(
                prompt=prompt,
                negative_prompt=negative_prompt,
                num_inference_steps=config["steps"],
                guidance_scale=config["guidance"],
                width=config["width"],
                height=config["height"],
                generator=generator,
            ).images[0]

            if not image.getbbox():
                logger.warning(f"Safety filter triggered or generation failed (black frame) for book {book_id} p{page_num}")
                return None

            return _save(image, book_id, page_num)
        except Exception as e:
            logger.error(f"Image generation failed: {e}")
            return None


class PollinationsProvider(ImageProvider):
    """Free, keyless cloud image generation via image.pollinations.ai."""

    def render(self, prompt: str, negative_prompt: str, book_id: int, page_num: int, seed: int) -> Optional[str]:
        import httpx
        from io import BytesIO
        from PIL import Image
        from urllib.parse import quote

        config = _resolve_generation_config()
        url = (
            f"https://image.pollinations.ai/prompt/{quote(prompt)}"
            f"?width={config['width']}&height={config['height']}&seed={seed}&nologo=true"
        )
        try:
            response = httpx.get(url, timeout=float(os.getenv("POLLINATIONS_TIMEOUT_SECONDS", "60.0")))
            response.raise_for_status()
            image = Image.open(BytesIO(response.content)).convert("RGB")
            return _save(image, book_id, page_num)
        except Exception as e:
            logger.error(f"Pollinations image generation failed: {e}")
            return None


_providers = {
    "diffusers": DiffusersProvider,
    "pollinations": PollinationsProvider,
}

_instance_cache = {}


def get_image_provider() -> ImageProvider:
    name = os.getenv("IMAGE_PROVIDER", "diffusers").strip().lower()
    cls = _providers.get(name, DiffusersProvider)
    if name not in _instance_cache:
        _instance_cache[name] = cls()
    return _instance_cache[name]
