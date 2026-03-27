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

MAX_SCENE_CHARS = 1200
MAX_PROMPT_CHARS = 700
MAX_PROMPT_WORDS = 130
MAX_CHARACTERS_PER_PAGE = 4
SUMMARY_CONTEXT_LIMIT = 2400
MAX_SCENE_ACTIONS = 3
MAX_SCENE_OBJECTS = 5
MAX_SCENE_SUMMARY_SENTENCES = 4
MAX_ENV_FIELD_CHARS = 140
MAX_CLIP_WORDS = 60
MAX_PROMPT_SCENE_WORDS = 26
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
        scene_details = _build_scene_details(page.text or "", page_number=page.page_number)
        scene_summary = scene_details["summary"]
        visual_prompt, negative_prompt = _compose_visual_prompt(
            scene_details,
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


def _build_scene_details(text: str, page_number: int = 1) -> dict:
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    if not cleaned:
        return {
            "summary": "",
            "setting": "",
            "tone": "",
            "actions": [],
            "objects": [],
            "location": "",
            "time_of_day": "",
            "lighting": "",
            "weather": "",
            "camera_framing": "",
            "background_details": "",
            "character_blocking": "",
            "shot_variation": _shot_variation_directive(page_number),
        }

    details = _summarize_with_ollama(cleaned)
    if not details:
        details = _fallback_scene_details(cleaned)

    summary = _normalize_summary(details.get("summary", ""))
    if not summary:
        summary = _fallback_summary(cleaned)
    details["summary"] = summary[:MAX_SCENE_CHARS]
    details["setting"] = _normalize_inline_text(details.get("setting", ""))[:MAX_ENV_FIELD_CHARS]
    details["tone"] = _normalize_inline_text(details.get("tone", ""))[:MAX_ENV_FIELD_CHARS]
    details["actions"] = _normalize_list(details.get("actions", []), MAX_SCENE_ACTIONS)
    details["objects"] = _normalize_list(details.get("objects", []), MAX_SCENE_OBJECTS)
    details["location"] = _normalize_inline_text(details.get("location", ""))[:MAX_ENV_FIELD_CHARS]
    details["time_of_day"] = _normalize_inline_text(details.get("time_of_day", ""))[:MAX_ENV_FIELD_CHARS]
    details["lighting"] = _normalize_inline_text(details.get("lighting", ""))[:MAX_ENV_FIELD_CHARS]
    details["weather"] = _normalize_inline_text(details.get("weather", ""))[:MAX_ENV_FIELD_CHARS]
    details["camera_framing"] = _normalize_inline_text(details.get("camera_framing", ""))[:MAX_ENV_FIELD_CHARS]
    details["background_details"] = _normalize_inline_text(details.get("background_details", ""))[:MAX_ENV_FIELD_CHARS]
    details["character_blocking"] = _normalize_inline_text(details.get("character_blocking", ""))[:MAX_ENV_FIELD_CHARS]
    details["shot_variation"] = _normalize_inline_text(details.get("shot_variation", ""))[:MAX_ENV_FIELD_CHARS]
    details = _ensure_environment_details(details, cleaned)
    if not details.get("shot_variation"):
        details["shot_variation"] = _shot_variation_directive(page_number)
    return details


def _summarize_with_ollama(text: str) -> dict:
    context = text[:SUMMARY_CONTEXT_LIMIT]
    output_schema = (
        "{"
        "\"narrative_summary\":\"...\","
        "\"visual_description\":\"...\","
        "\"character_descriptions\":["
        "{\"name\":\"...\",\"appearance\":\"...\",\"pose_and_expression\":\"...\"}"
        "],"
        "\"setting\":\"...\","
        "\"time_of_day\":\"...\","
        "\"weather_conditions\":\"...\","
        "\"lighting_style\":\"...\","
        "\"color_palette\":{\"primary_colors\":[\"...\"],\"accent_colors\":[\"...\"],\"mood_colors\":\"...\"},"
        "\"camera_framing\":\"...\","
        "\"composition\":\"...\","
        "\"foreground_elements\":[\"...\"],"
        "\"midground_elements\":[\"...\"],"
        "\"background_elements\":[\"...\"],"
        "\"actions_in_frame\":[\"...\"],"
        "\"character_positioning\":\"...\","
        "\"emotional_tone\":\"...\","
        "\"art_style_reference\":\"...\","
        "\"consistency_notes\":\"...\""
        "}"
    )
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a visual scene extraction engine for story illustration. "
                    "Return valid JSON only using exactly the requested keys. "
                    "Keep all fields concrete and visual. Avoid markdown."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Extract the page into a rich visual planning JSON.\n\n"
                    f"Page text:\n{context}\n\n"
                    "Output format (exact keys): "
                    f"{output_schema}"
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
        details = _extract_scene_details(content)
        if details:
            return details
    except (requests.RequestException, ValueError, KeyError) as exc:
        logger.debug("Ollama summarization failed, using fallback: %s", exc)
    return {}


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


def _extract_scene_details(content: str) -> dict:
    if not content:
        return {}
    parsed = _parse_json_maybe(content)
    if not isinstance(parsed, dict):
        return {}
    narrative_summary = parsed.get("narrative_summary") or parsed.get("summary") or parsed.get("scene_summary") or ""
    visual_description = parsed.get("visual_description") or ""
    summary = " ".join(part for part in [narrative_summary, visual_description] if part).strip()

    color_palette = parsed.get("color_palette") if isinstance(parsed.get("color_palette"), dict) else {}
    primary_colors = color_palette.get("primary_colors") if isinstance(color_palette.get("primary_colors"), list) else []
    accent_colors = color_palette.get("accent_colors") if isinstance(color_palette.get("accent_colors"), list) else []
    mood_colors = color_palette.get("mood_colors") or ""
    color_parts = []
    if primary_colors:
        color_parts.append("primary: " + ", ".join(str(c) for c in primary_colors[:4]))
    if accent_colors:
        color_parts.append("accent: " + ", ".join(str(c) for c in accent_colors[:3]))
    if mood_colors:
        color_parts.append(str(mood_colors))
    color_palette_text = "; ".join(color_parts)

    actions = parsed.get("actions_in_frame") or parsed.get("actions") or parsed.get("key_actions") or []
    objects = parsed.get("foreground_elements") or []
    if isinstance(parsed.get("midground_elements"), list):
        objects = list(objects) + list(parsed.get("midground_elements"))
    if isinstance(parsed.get("background_elements"), list):
        objects = list(objects) + list(parsed.get("background_elements"))
    if not objects:
        objects = parsed.get("objects") or parsed.get("important_objects") or []

    tone = parsed.get("emotional_tone") or parsed.get("tone") or ""
    setting = parsed.get("setting") or ""
    if parsed.get("composition"):
        setting = f"{setting}. composition: {parsed.get('composition')}".strip(". ")

    background_details = parsed.get("background_elements") or parsed.get("background_details") or parsed.get("background") or []
    if isinstance(background_details, list):
        background_details = "; ".join(str(x) for x in background_details[:5])

    character_blocking = parsed.get("character_positioning") or parsed.get("character_blocking") or parsed.get("blocking") or ""

    character_descriptions = parsed.get("character_descriptions") if isinstance(parsed.get("character_descriptions"), list) else []
    character_notes = []
    for item in character_descriptions[:4]:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        appearance = str(item.get("appearance") or "").strip()
        pose = str(item.get("pose_and_expression") or "").strip()
        if not any([name, appearance, pose]):
            continue
        parts = []
        if name:
            parts.append(name)
        if appearance:
            parts.append(f"appearance: {appearance}")
        if pose:
            parts.append(f"pose: {pose}")
        character_notes.append(", ".join(parts))

    return {
        "summary": summary,
        "setting": setting,
        "actions": actions,
        "objects": objects,
        "tone": tone,
        "location": parsed.get("setting") or parsed.get("location") or parsed.get("place") or "",
        "time_of_day": parsed.get("time_of_day") or parsed.get("time") or "",
        "lighting": parsed.get("lighting_style") or parsed.get("lighting") or "",
        "weather": parsed.get("weather_conditions") or parsed.get("weather") or "",
        "camera_framing": parsed.get("camera_framing") or parsed.get("framing") or "",
        "background_details": background_details,
        "character_blocking": character_blocking,
        "color_palette": color_palette_text,
        "art_style_reference": parsed.get("art_style_reference") or "",
        "consistency_notes": parsed.get("consistency_notes") or "",
        "character_notes": character_notes,
    }


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
    return _limit_to_n_sentences(" ".join(snippets[:MAX_SCENE_SUMMARY_SENTENCES]).strip())


def _limit_to_n_sentences(text: str, max_sentences: int = MAX_SCENE_SUMMARY_SENTENCES) -> str:
    if not text:
        return ""
    chunks = re.split(r"(?<=[.!?])\s+", text.strip())
    if not chunks:
        return text.strip()
    selected = [chunk.strip() for chunk in chunks[:max_sentences] if chunk.strip()]
    return " ".join(selected).strip()


def _compose_visual_prompt(
    scene_details: dict,
    characters: list[dict],
    style_preset: str,
) -> tuple[str, str]:
    preset = STYLE_PRESETS.get(style_preset, STYLE_PRESETS[DEFAULT_STYLE_PRESET])
    scene_summary = scene_details.get("summary", "")
    scene_prompt_text = _scene_for_prompt(scene_summary)
    setting = scene_details.get("setting", "")
    actions = scene_details.get("actions", [])
    objects = scene_details.get("objects", [])
    tone = scene_details.get("tone", "")
    location = scene_details.get("location", "")
    time_of_day = scene_details.get("time_of_day", "")
    lighting = scene_details.get("lighting", "")
    weather = scene_details.get("weather", "")
    camera_framing = scene_details.get("camera_framing", "")
    background_details = scene_details.get("background_details", "")
    character_blocking = scene_details.get("character_blocking", "")
    color_palette = scene_details.get("color_palette", "")
    art_style_reference = scene_details.get("art_style_reference", "")
    consistency_notes = scene_details.get("consistency_notes", "")
    character_notes = scene_details.get("character_notes", [])
    shot_variation = scene_details.get("shot_variation", "")
    visual_hook = _build_visual_hook(actions, objects, tone)

    sections = []
    sections.append(("style", preset["style"]))
    if scene_prompt_text:
        sections.append(("scene", f"scene: {scene_prompt_text}"))
    if visual_hook:
        sections.append(("visual_hook", f"distinct visual focus: {visual_hook}"))
    if shot_variation:
        sections.append(("shot_variation", f"shot directive: {shot_variation}"))
    if setting:
        sections.append(("setting", f"setting: {setting}"))
    if actions:
        sections.append(("actions", "actions: " + "; ".join(actions)))
    if objects:
        sections.append(("objects", "important objects: " + "; ".join(objects)))
    if tone:
        sections.append(("tone", f"tone: {tone}"))
    if location:
        sections.append(("location", f"location: {location}"))
    if time_of_day:
        sections.append(("time_of_day", f"time of day: {time_of_day}"))
    if lighting:
        sections.append(("lighting", f"lighting: {lighting}"))
    if weather:
        sections.append(("weather", f"weather: {weather}"))
    if camera_framing:
        sections.append(("camera_framing", f"camera framing: {camera_framing}"))
    if background_details:
        sections.append(("background_details", f"background details: {background_details}"))
    if character_blocking:
        sections.append(("character_blocking", f"character blocking: {character_blocking}"))
    if color_palette:
        sections.append(("color_palette", f"color palette: {color_palette}"))
    if art_style_reference:
        sections.append(("art_style_reference", f"art style: {art_style_reference}"))
    if character_notes:
        sections.append(("character_notes", "character scene notes: " + "; ".join(character_notes)))
    if consistency_notes:
        sections.append(("consistency_notes", f"continuity: {consistency_notes}"))

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
        sections.append(("characters", "characters: " + "; ".join(character_descriptions)))
        sections.append(("consistency", "preserve identity, face structure, hair, and outfit consistency"))
    else:
        sections.append(("no_characters", "focus on environment, mood, and narrative action"))

    prompt = _assemble_clip_friendly_prompt(sections)
    prompt = _guard_prompt(prompt)
    return prompt[:MAX_PROMPT_CHARS], preset["negative"]


def _fallback_scene_details(cleaned: str) -> dict:
    snippets = [part.strip() for part in re.split(r"(?<=[.!?])\s+", cleaned) if part.strip()]
    summary = _fallback_summary(cleaned)
    setting = snippets[0] if snippets else ""
    actions = snippets[1:1 + MAX_SCENE_ACTIONS]
    return {
        "summary": summary,
        "setting": setting[:180],
        "actions": actions,
        "objects": [],
        "tone": "",
        "location": "interior",
        "time_of_day": _infer_time_of_day(cleaned),
        "lighting": _infer_lighting(cleaned),
        "weather": _infer_weather(cleaned),
        "camera_framing": "medium shot",
        "background_details": "period room details and lived-in objects",
        "character_blocking": "main characters facing each other with clear emotional distance",
    }


def _normalize_summary(text: str) -> str:
    text = _normalize_inline_text(text)
    return _limit_to_n_sentences(text, MAX_SCENE_SUMMARY_SENTENCES)


def _normalize_inline_text(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(text or "").strip())
    return cleaned


def _normalize_list(items, max_items: int) -> list[str]:
    if not isinstance(items, list):
        return []
    cleaned_items = []
    for item in items:
        value = _normalize_inline_text(str(item))
        if not value:
            continue
        cleaned_items.append(value)
        if len(cleaned_items) >= max_items:
            break
    return cleaned_items


def _ensure_environment_details(details: dict, text: str) -> dict:
    if not details.get("location"):
        details["location"] = "interior" if _has_any(text, ["room", "house", "chamber", "window", "door"]) else "outdoor setting"
    if not details.get("time_of_day"):
        details["time_of_day"] = _infer_time_of_day(text)
    if not details.get("lighting"):
        details["lighting"] = _infer_lighting(text)
    if not details.get("weather"):
        details["weather"] = _infer_weather(text)
    if not details.get("camera_framing"):
        details["camera_framing"] = "medium shot"
    if not details.get("background_details"):
        details["background_details"] = "period-appropriate setting details relevant to the scene"
    if not details.get("character_blocking"):
        details["character_blocking"] = "characters arranged to emphasize current emotional tension"
    return details


def _infer_time_of_day(text: str) -> str:
    lower = text.lower()
    if _has_any(lower, ["night", "midnight", "moon", "dark"]):
        return "night"
    if _has_any(lower, ["morning", "dawn", "sunrise"]):
        return "morning"
    if _has_any(lower, ["evening", "sunset", "dusk"]):
        return "evening"
    return "unspecified"


def _infer_lighting(text: str) -> str:
    lower = text.lower()
    if _has_any(lower, ["candle", "lamplight", "dim", "shadow"]):
        return "dim low-key light"
    if _has_any(lower, ["sunlight", "bright", "window light"]):
        return "soft natural light"
    return "soft ambient light"


def _infer_weather(text: str) -> str:
    lower = text.lower()
    if _has_any(lower, ["rain", "storm", "thunder"]):
        return "rainy"
    if _has_any(lower, ["snow", "winter"]):
        return "cold/snowy"
    if _has_any(lower, ["wind", "gust"]):
        return "windy"
    return "unspecified"


def _has_any(text: str, keywords: list[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def _guard_prompt(prompt: str) -> str:
    trimmed = prompt[:MAX_PROMPT_CHARS]
    words = trimmed.split()
    if len(words) <= MAX_PROMPT_WORDS:
        return trimmed
    return " ".join(words[:MAX_PROMPT_WORDS])


def _assemble_clip_friendly_prompt(sections: list[tuple[str, str]]) -> str:
    if not sections:
        return ""

    # High-priority sections kept first so truncation, if any, happens on low-impact context.
    priority = {
        "style": 0,
        "scene": 1,
        "characters": 2,
        "consistency": 3,
        "visual_hook": 4,
        "actions": 5,
        "shot_variation": 6,
        "setting": 7,
        "tone": 8,
        "location": 7,
        "lighting": 9,
        "camera_framing": 10,
        "character_blocking": 11,
        "time_of_day": 12,
        "objects": 13,
        "background_details": 14,
        "weather": 15,
        "no_characters": 16,
        "color_palette": 17,
        "art_style_reference": 18,
        "character_notes": 19,
        "consistency_notes": 20,
    }
    ordered = sorted(sections, key=lambda item: priority.get(item[0], 100))
    pieces = []
    for _, content in ordered:
        candidate = ". ".join(pieces + [content]).strip()
        if len(candidate.split()) > MAX_CLIP_WORDS:
            continue
        pieces.append(content)

    if not pieces:
        # Guaranteed minimal fallback.
        return ordered[0][1]
    return ". ".join(pieces).strip()


def _scene_for_prompt(scene_summary: str) -> str:
    text = _normalize_inline_text(scene_summary)
    if not text:
        return ""
    first_sentences = _limit_to_n_sentences(text, max_sentences=2)
    words = first_sentences.split()
    if len(words) <= MAX_PROMPT_SCENE_WORDS:
        return first_sentences
    return " ".join(words[:MAX_PROMPT_SCENE_WORDS]).strip()


def _build_visual_hook(actions: list[str], objects: list[str], tone: str) -> str:
    hooks = []
    if actions:
        hooks.append(actions[0])
    if len(actions) > 1:
        hooks.append(actions[1])
    if objects:
        hooks.append(f"key prop: {objects[0]}")
    if tone:
        hooks.append(f"mood: {tone}")
    return "; ".join(hooks[:3]).strip()


def _shot_variation_directive(page_number: int) -> str:
    variants = [
        "wide establishing composition with layered depth",
        "medium shot with clear character interaction focus",
        "close-up emotional emphasis on faces and gesture",
        "over-shoulder perspective highlighting tension",
        "low-angle dramatic framing with strong silhouettes",
        "high-angle framing showing spatial relationships",
    ]
    index = max(0, (int(page_number) - 1) % len(variants))
    return variants[index]
