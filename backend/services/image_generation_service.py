"""
Image Generation Service: Manages the local diffusion pipeline using the Diffusers library.
Handles deterministic seeding, model caching, and safety sanitization.
"""

import os
import torch
import logging
from pathlib import Path
from typing import Optional
from diffusers import DiffusionPipeline
from services.prompt_service import VISUAL_STYLES

logger = logging.getLogger(__name__)

MODE_ALIASES = {"quality", "balanced", "fast", "custom"}

MODE_DEFAULTS = {
    "quality": {"model": "SG161222/RealVisXL_V4.0", "steps": 24, "guidance": 5.5, "width": 768, "height": 768},
    "balanced": {"model": "segmind/SSD-1B", "steps": 12, "guidance": 8.0, "width": 768, "height": 768},
    "fast": {"model": "stabilityai/sd-turbo", "steps": 4, "guidance": 1.5, "width": 512, "height": 768},
}

class ImageGenerationService:
    def __init__(self):
        self.pipe = None
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model_id = os.getenv("DIFFUSION_MODEL", "segmind/SSD-1B")
        self.storage_path = Path(__file__).resolve().parents[1] / "storage" / "illustrations"

    def _resolve_generation_config(self):
        image_mode = os.getenv("IMAGE_PRESET", "balanced").strip().lower()
        if image_mode not in MODE_ALIASES:
            image_mode = "balanced"

        if image_mode == "custom":
            return {
                "model": os.getenv("DIFFUSION_MODEL", MODE_DEFAULTS["balanced"]["model"]),
                "steps": int(os.getenv("IMAGE_STEPS", str(MODE_DEFAULTS["balanced"]["steps"]))),
                "guidance": float(os.getenv("IMAGE_GUIDANCE", str(MODE_DEFAULTS["balanced"]["guidance"]))),
                "width": int(os.getenv("IMAGE_WIDTH", str(MODE_DEFAULTS["balanced"]["width"]))),
                "height": int(os.getenv("IMAGE_HEIGHT", str(MODE_DEFAULTS["balanced"]["height"]))),
            }

        mode_defaults = MODE_DEFAULTS[image_mode]
        return {
            "model": os.getenv("DIFFUSION_MODEL", mode_defaults["model"]),
            "steps": int(os.getenv("IMAGE_STEPS", str(mode_defaults["steps"]))),
            "guidance": float(os.getenv("IMAGE_GUIDANCE", str(mode_defaults["guidance"]))),
            "width": int(os.getenv("IMAGE_WIDTH", str(mode_defaults["width"]))),
            "height": int(os.getenv("IMAGE_HEIGHT", str(mode_defaults["height"]))),
        }

    def _load_pipeline(self):
        """Lazy loading of the diffusion pipeline to conserve VRAM/RAM."""
        config = self._resolve_generation_config()
        desired_model_id = config["model"]

        # Hot-swap model if mode/settings changed since last call.
        if self.pipe is not None and self.model_id != desired_model_id:
            logger.info(f"Model changed from '{self.model_id}' to '{desired_model_id}', reloading pipeline...")
            self.pipe = None

        if self.pipe is not None:
            return

        self.model_id = desired_model_id
        logger.info(f"Loading diffusion pipeline '{self.model_id}' on {self.device}...")
        
        try:
            # Using float16 for significant speedup and lower VRAM usage on CUDA
            dtype = torch.float16 if self.device == "cuda" else torch.float32
            
            self.pipe = DiffusionPipeline.from_pretrained(
                self.model_id,
                torch_dtype=dtype,
                use_safetensors=True,
                variant="fp16" if self.device == "cuda" else None
            )
            
            self.pipe.to(self.device)
            
            # Optimize for limited hardware if necessary
            if self.device == "cuda":
                self.pipe.enable_attention_slicing()
            
            logger.info("Diffusion pipeline loaded successfully.")
        except Exception as e:
            logger.error(f"Failed to load diffusion pipeline: {e}")
            raise

    def render_page_image(self, prompt: str, book_id: int, page_num: int, seed: int) -> Optional[str]:
        """
        Generates an image for a specific page using a deterministic seed.
        Ensures consistency if the same page is regenerated.
        """
        self._load_pipeline()
        
        # Deterministic seeding based on book and page context
        generator = torch.Generator(device=self.device).manual_seed(seed)
        
        try:
            config = self._resolve_generation_config()
            steps = config["steps"]
            guidance = config["guidance"]
            width = config["width"]
            height = config["height"]

            style_key = os.getenv("IMAGE_STYLE", "storybook")
            negative_prompt = VISUAL_STYLES.get(style_key, VISUAL_STYLES["storybook"])["negative"]

            # Image generation execution
            image = self.pipe(
                prompt=prompt,
                negative_prompt=negative_prompt,
                num_inference_steps=steps,
                guidance_scale=guidance,
                width=width,
                height=height,
                generator=generator
            ).images[0]

            # Post-generation sanity check (Black frame detection)
            if not image.getbbox():
                logger.warning(f"Safety filter triggered or generation failed (black frame) for book {book_id} p{page_num}")
                return None

            # Persist result to book-specific directory
            book_dir = self.storage_path / f"book_{book_id}"
            book_dir.mkdir(parents=True, exist_ok=True)
            file_path = book_dir / f"page_{page_num}.png"
            image.save(file_path)

            # Persist as web path so API can serve directly from mounted /storage.
            return f"storage/illustrations/book_{book_id}/page_{page_num}.png"
        except Exception as e:
            logger.error(f"Image generation failed: {e}")
            return None

image_service = ImageGenerationService()
