"""
Image Generation Service: thin wrapper that dispatches rendering to the
configured image provider (local diffusers or a cloud free-tier provider).
"""

import os
import logging
from typing import Optional

from providers.image_provider import get_image_provider
from services.prompt_service import VISUAL_STYLES

logger = logging.getLogger(__name__)


class ImageGenerationService:
    def render_page_image(self, prompt: str, book_id: int, page_num: int, seed: int) -> Optional[str]:
        """
        Generates an image for a specific page using a deterministic seed.
        Ensures consistency if the same page is regenerated.
        """
        style_key = os.getenv("IMAGE_STYLE", "storybook")
        negative_prompt = VISUAL_STYLES.get(style_key, VISUAL_STYLES["storybook"])["negative"]
        return get_image_provider().render(prompt, negative_prompt, book_id, page_num, seed)


image_service = ImageGenerationService()
