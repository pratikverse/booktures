import json
import logging
import os
import re
from datetime import datetime

import requests

from database import SessionLocal
from models.character import Character
from models.page import Page
from models.page_asset import PageAsset
from models.page_character import PageCharacter
from services.character_service import resolve_page_characters

logger = logging.getLogger(__name__)

MAX_SCENE_CHARS = 420
MAX_PROMPT_CHARS = 700
MAX_PROMPT_WORDS = 130
MAX_CHARACTERS_PER_PAGE = 4
SUMMARY_CONTEXT_LIMIT = 2400
OLLAMA_URL = os.getenv("BOOKTURES_OLLAMA_URL", "http://127.0.0.1:11434/v1/chat/completions")
OLLAMA_MODEL = os.getenv("BOOKTURES_OLLAMA_MODEL", "qwen2.5:3b-instruct")
OLLAMA_TIMEOUT = int(os.getenv("BOOKTURES_OLLAMA_TIMEOUT", "35"))
DEFAULT_STYLE_PRESET = "storybook"

STYLE_PRESETS = {
    "storybook": {
        "style": "illustrated storybook style, cinematic composition, coherent character continuity",
        "negative": "blurry, distorted face, extra limbs, low detail, text watermark, logo",
    },
    "comic": {
        "style": "graphic novel comic style, bold linework, dramatic lighting, coherent character continuity",
        "negative": "photo-realistic skin, blur, extra fingers, watermark, gibberish text",
    },
    "cinematic": {
        "style": "cinematic digital painting, volumetric light, rich atmosphere, coherent character continuity",
        "negative": "flat lighting, low contrast, blur, deformed anatomy, watermark",
    },
}


def build_page_visual_prompt(
    book_id: int,
    page_number: int,
    style_preset: str = DEFAULT_STYLE_PRESET,
    force_refresh: bool = False,
) -> dict:
    db = SessionLocal()
    try:
        page = (
            db.query(Page)
            .filter(Page.book_id == book_id, Page.page_number == page_number)
            .first()
        )
        if page is None:
            return {
                "book_id": book_id,
                "page_number": page_number,
                "status": "not_found",
                "visual_prompt": "",
                "characters": [],
            }

        asset = _get_or_create_asset(db, book_id, page)
        resolved_style = _resolve_style_preset(style_preset)
        if (
            not force_refresh
            and asset.visual_prompt
            and asset.scene_summary
            and asset.style_preset == resolved_style
        ):
            return {
                "book_id": book_id,
                "page_number": page_number,
                "status": "ok",
                "scene_summary": asset.scene_summary,
                "visual_prompt": asset.visual_prompt,
                "negative_prompt": asset.negative_prompt or "",
                "style_preset": asset.style_preset,
                "characters": _load_page_characters(db, book_id, page),
                "cached": True,
            }

        characters = _load_page_characters(db, book_id, page)
        scene_summary = _build_scene_summary(page.text or "")
        visual_prompt, negative_prompt = _compose_visual_prompt(
            scene_summary,
            characters,
            resolved_style,
        )

        asset.scene_summary = scene_summary
        asset.visual_prompt = visual_prompt
        asset.negative_prompt = negative_prompt
        asset.style_preset = resolved_style
        asset.prompt_generated_at = datetime.utcnow()
        asset.updated_at = datetime.utcnow()
        db.add(asset)
        db.commit()

        return {
            "book_id": book_id,
            "page_number": page_number,
            "status": "ok",
            "scene_summary": scene_summary,
            "visual_prompt": visual_prompt,
            "negative_prompt": negative_prompt,
            "style_preset": resolved_style,
            "characters": characters,
            "cached": False,
        }
    finally:
        db.close()


def _resolve_style_preset(style_preset: str) -> str:
    candidate = (style_preset or DEFAULT_STYLE_PRESET).strip().lower()
    if candidate not in STYLE_PRESETS:
        return DEFAULT_STYLE_PRESET
    return candidate


def _get_or_create_asset(db, book_id: int, page: Page) -> PageAsset:
    asset = db.query(PageAsset).filter(PageAsset.page_id == page.id).one_or_none()
    if asset is not None:
        return asset
    asset = PageAsset(
        book_id=book_id,
        page_id=page.id,
        page_number=page.page_number,
        style_preset=DEFAULT_STYLE_PRESET,
        image_status="pending",
    )
    db.add(asset)
    db.flush()
    return asset


def _load_page_characters(db, book_id: int, page: Page) -> list[dict]:
    linked_rows = (
        db.query(PageCharacter, Character)
        .join(Character, Character.id == PageCharacter.character_id)
        .filter(PageCharacter.book_id == book_id, PageCharacter.page_id == page.id)
        .order_by(PageCharacter.confidence.desc(), PageCharacter.mention_count.desc())
        .all()
    )
    if linked_rows:
        return [
            {
                "character_id": character.id,
                "name": character.name,
                "mention_count": link.mention_count,
                "confidence": float(link.confidence),
                "visual_profile": character.visual_profile or "",
            }
            for link, character in linked_rows[:MAX_CHARACTERS_PER_PAGE]
        ]

    all_characters = (
        db.query(Character)
        .filter(Character.book_id == book_id)
        .order_by(Character.mention_count.desc())
        .all()
    )
    return resolve_page_characters(page, all_characters)[:MAX_CHARACTERS_PER_PAGE]


def _build_scene_summary(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    if not cleaned:
        return ""
    summary = _summarize_with_ollama(cleaned)
    if summary:
        return summary[:MAX_SCENE_CHARS]
    return _fallback_summary(cleaned)[:MAX_SCENE_CHARS]


def _summarize_with_ollama(text: str) -> str:
    context = text[:SUMMARY_CONTEXT_LIMIT]
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You summarize a single book page. Return JSON only with key "
                    "`scene_summary` as one to two concise sentences."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Summarize the page text for visual storytelling.\n\n"
                    f"Page text:\n{context}\n\n"
                    "Output format: {\"scene_summary\": \"...\"}"
                ),
            },
        ],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }

    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=OLLAMA_TIMEOUT)
        response.raise_for_status()
        content = _extract_chat_content(response.json())
        summary = _extract_scene_summary(content)
        if summary:
            return summary
    except (requests.RequestException, ValueError, KeyError) as exc:
        logger.debug("Ollama summarization failed, using fallback: %s", exc)
    return ""


def _extract_chat_content(data: dict) -> str:
    if content := data.get("content"):
        return str(content)
    choices = data.get("choices") or []
    if choices and isinstance(choices, list):
        first = choices[0] or {}
        message = first.get("message") or {}
        if message_content := message.get("content"):
            return str(message_content)
        delta = first.get("delta") or {}
        if delta_content := delta.get("content"):
            return str(delta_content)
    return ""


def _extract_scene_summary(content: str) -> str:
    if not content:
        return ""
    parsed = _parse_json_maybe(content)
    if not isinstance(parsed, dict):
        return ""
    summary = str(parsed.get("scene_summary", "")).strip()
    summary = re.sub(r"\s+", " ", summary)
    return _limit_to_single_sentence(summary)


def _parse_json_maybe(content: str):
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", content, flags=re.DOTALL)
    if not match:
        return {}
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}


def _fallback_summary(cleaned: str) -> str:
    snippets = re.split(r"(?<=[.!?])\s+", cleaned)
    return _limit_to_single_sentence(" ".join(snippets[:1]).strip())


def _limit_to_single_sentence(text: str) -> str:
    if not text:
        return ""
    chunks = re.split(r"(?<=[.!?])\s+", text.strip())
    return chunks[0].strip() if chunks else text.strip()


def _compose_visual_prompt(
    scene_summary: str,
    characters: list[dict],
    style_preset: str,
) -> tuple[str, str]:
    preset = STYLE_PRESETS.get(style_preset, STYLE_PRESETS[DEFAULT_STYLE_PRESET])
    pieces = [
        preset["style"],
    ]
    if scene_summary:
        pieces.append(f"scene: {scene_summary}")

    if characters:
        character_descriptions = []
        for character in characters:
            descriptor = character["name"]
            profile = (character.get("visual_profile") or "").strip()
            if profile:
                traits = [trait.strip() for trait in profile.split(",") if trait.strip()][:3]
                if traits:
                    descriptor = f"{descriptor} ({', '.join(traits)})"
            character_descriptions.append(descriptor)
        pieces.append("characters: " + "; ".join(character_descriptions))
        pieces.append("preserve identity, face structure, hair, and outfit consistency")
    else:
        pieces.append("focus on environment, mood, and narrative action")

    prompt = ". ".join(piece for piece in pieces if piece).strip()
    prompt = _guard_prompt(prompt)
    return prompt[:MAX_PROMPT_CHARS], preset["negative"]


def _guard_prompt(prompt: str) -> str:
    trimmed = prompt[:MAX_PROMPT_CHARS]
    words = trimmed.split()
    if len(words) <= MAX_PROMPT_WORDS:
        return trimmed
    return " ".join(words[:MAX_PROMPT_WORDS])
