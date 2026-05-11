import os
from services.pdf_service import ollama_generate
from sqlalchemy.orm import Session
from models import DocumentChunk, PageAsset, Character

OLLAMA_MODEL = os.getenv("OLLAMA_DEFAULT_MODEL", "qwen2.5:7b")

VISUAL_STYLES = {
    "normal": {
        "style": "clean illustration, natural colors, clear subjects",
        "negative": "low quality, blurry, distorted, text",
    },
    "storybook": {
        "style": "illustrated storybook scene, cinematic composition, painterly detail, emotionally readable characters",
        "negative": "blurry, distorted face, extra limbs, low detail, text watermark, logo",
    },
    "comic": {
        "style": "graphic novel panel aesthetic, bold linework, dramatic contrast, expressive acting",
        "negative": "photo-realistic skin, blur, extra fingers, watermark, gibberish text",
    },
    "cinematic": {
        "style": "cinematic digital painting, atmospheric depth, expressive lighting, grounded character continuity",
        "negative": "flat lighting, low contrast, blur, deformed anatomy, watermark",
    },
}

# System prompt to generate an image generation prompt
_IMAGE_PROMPT_SYSTEM = (
    "You are a visual prompt engineer. Transform the provided summary and scene into a condensed, "
    "highly visual description for an AI artist. Focus on subjects, actions, and background details. "
    "Avoid metaphors or abstract concepts. Keep it to one concise sentence, maximum 40 words. "
    "Adhere strictly to character descriptions from the Visual Bible. Prioritize key characters and actions."
)

def generate_page_summary(page_text: str, previous_summaries: str = "") -> str:
    """
    Generates a concise narrative summary for a page, optionally considering previous context.
    """
    prompt = f"Previous context: {previous_summaries}\n\nPage Text: {page_text}\n\nTask: Create a visual summary (2-3 sentences)."
    return ollama_generate(prompt, model=OLLAMA_MODEL, system="You are a concise narrative summarizer.")

def generate_illustration_prompt(page_summary: str, visual_bible: str, scene: str = "") -> str:
    """
    Composes the final image generation prompt using the page summary and character bible.
    """
    style_key = os.getenv("IMAGE_STYLE", "storybook")
    style_desc = VISUAL_STYLES.get(style_key, VISUAL_STYLES["storybook"])["style"]

    prompt = (
        f"VISUAL STYLE: {style_desc}\n\n"
        f"VISUAL BIBLE (Character Constraints):\n{visual_bible}\n\n"
        f"PAGE SUMMARY:\n{page_summary}\n\n"
        f"SCENE SETTING:\n{scene}\n\n"
        "Task: Generate a condensed, visual-only description."
    )
    response = ollama_generate(prompt, model=OLLAMA_MODEL, system=_IMAGE_PROMPT_SYSTEM)
    # Return the style + the LLM response to ensure the artist follows the aesthetic
    return f"{style_desc}, {response}"