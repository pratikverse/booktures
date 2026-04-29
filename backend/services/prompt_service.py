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

PROMPT_PIPELINE_MARKER = "continuity anchor:"
MAX_SCENE_CHARS = 1500
MAX_PROMPT_CHARS = 1400
MAX_PROMPT_WORDS = 220
MAX_CHARACTERS_PER_PAGE = 4
SUMMARY_CONTEXT_LIMIT = 6000
CONTINUITY_PAGE_WINDOW = 3
PREVIOUS_SUMMARY_CHARS = 320
MAX_PAGE_BEATS = 4
MAX_KEY_OBJECTS = 6
MAX_CHARACTER_MOMENTS = 4
MAX_FIELD_CHARS = 220
DEFAULT_STYLE_PRESET = "storybook"

STYLE_PRESETS = {
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

DEFAULT_LEGAL_PAGE_PATTERNS = [
    r"without any warranty",
    r"merchantabilit(?:y|ies)",
    r"all rights reserved",
    r"public domain",
    r"project gutenberg",
    r"copyright",
]


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
            and _prompt_matches_current_pipeline(asset.visual_prompt)
        ):
            return {
                "book_id": book_id,
                "page_number": page_number,
                "status": "ok",
                "scene_summary": asset.scene_summary,
                "summary_short": getattr(asset, "summary_short", None),
                "continuity_summary": getattr(asset, "continuity_summary", None),
                "visual_prompt": asset.visual_prompt,
                "negative_prompt": asset.negative_prompt or "",
                "style_preset": asset.style_preset,
                "characters": _load_page_characters(db, book_id, page),
                "cached": True,
            }

        characters = _load_page_characters(db, book_id, page)
        continuity_context = _build_continuity_context(db, book_id, page.page_number, characters)
        page_summary = _build_page_summary(
            page.text or "",
            page_number=page.page_number,
            continuity_context=continuity_context,
            characters=characters,
            weak_text=bool(getattr(page, "weak_text", False)),
            extraction_score=getattr(page, "extraction_score", None),
        )
        scene_summary = page_summary["full_summary"]
        summary_short = page_summary["condensed_summary"]
        continuity_summary = continuity_context.get("previous_summary_text", "")[:MAX_SCENE_CHARS]
        visual_prompt, negative_prompt = _compose_visual_prompt(
            page_summary=page_summary,
            continuity_context=continuity_context,
            characters=characters,
            style_preset=resolved_style,
        )

        asset.scene_summary = scene_summary
        asset.summary_short = summary_short
        asset.continuity_summary = continuity_summary
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
            "summary_short": summary_short,
            "continuity_summary": continuity_summary,
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


def _build_continuity_context(db, book_id: int, page_number: int, characters: list[dict]) -> dict:
    previous_pages = (
        db.query(Page, PageAsset)
        .outerjoin(PageAsset, PageAsset.page_id == Page.id)
        .filter(Page.book_id == book_id, Page.page_number < page_number)
        .order_by(Page.page_number.desc())
        .limit(CONTINUITY_PAGE_WINDOW)
        .all()
    )

    previous_summaries = []
    for previous_page, asset in previous_pages:
        summary = ""
        if asset is not None and asset.scene_summary:
            summary = asset.scene_summary
        elif previous_page.text:
            summary = _fallback_condensed_summary(previous_page.text)
        summary = _normalize_inline_text(summary)
        if summary:
            previous_summaries.append(
                {
                    "page_number": previous_page.page_number,
                    "summary": summary[:PREVIOUS_SUMMARY_CHARS],
                }
            )

    previous_summaries.sort(key=lambda item: item["page_number"])

    named_characters = []
    for character in characters[:MAX_CHARACTERS_PER_PAGE]:
        name = _normalize_inline_text(character.get("name", ""))
        profile = _normalize_inline_text(character.get("visual_profile", ""))
        if not name:
            continue
        if profile:
            named_characters.append(f"{name}: {profile}")
        else:
            named_characters.append(name)

    continuity_anchor = " | ".join(
        f"p{item['page_number']}: {item['summary']}" for item in previous_summaries
    )
    return {
        "previous_summaries": previous_summaries,
        "previous_summary_text": continuity_anchor,
        "character_anchor": "; ".join(named_characters),
    }


def _build_page_summary(
    text: str,
    page_number: int,
    continuity_context: dict,
    characters: list[dict],
    weak_text: bool = False,
    extraction_score: float | None = None,
) -> dict:
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    page_kind = _classify_page_kind(cleaned, page_number)
    if not cleaned:
        return {
            "page_kind": "blank",
            "full_summary": "",
            "condensed_summary": "",
            "page_beats": [],
            "key_objects": [],
            "setting": "",
            "location": "",
            "time_of_day": "",
            "lighting": "",
            "weather": "",
            "mood": "",
            "camera_focus": _shot_variation_directive(page_number),
            "character_focus": [],
            "continuity_anchor": continuity_context.get("previous_summary_text", "") or "opening page establish the world and cast",
            "scene_change": "",
        }

    if page_kind != "story":
        return _summarize_non_story_page(cleaned, page_number, page_kind, continuity_context)

    if weak_text or _is_low_extraction_score(extraction_score):
        details = _fallback_page_summary(cleaned, page_number, continuity_context, characters)
        details["scene_change"] = details.get("scene_change") or "source text is weak; preserve continuity and avoid invented detail"
        return _ensure_page_summary_defaults(details, cleaned, page_number, continuity_context, characters)

    details = _summarize_page_with_ollama(cleaned, continuity_context, characters)
    if details and not _is_summary_output_usable(cleaned, details):
        details = {}
    if not details:
        details = _fallback_page_summary(cleaned, page_number, continuity_context, characters)

    full_summary = _normalize_summary(details.get("full_summary") or details.get("summary") or cleaned, max_sentences=6)
    condensed_summary = _normalize_summary(details.get("condensed_summary") or details.get("visual_summary") or full_summary, max_sentences=3)
    page_beats = _normalize_list(details.get("page_beats", []), MAX_PAGE_BEATS)
    key_objects = _normalize_list(details.get("key_objects", []), MAX_KEY_OBJECTS)
    character_focus = _normalize_list(details.get("character_focus", []), MAX_CHARACTER_MOMENTS)
    continuity_anchor = _normalize_inline_text(details.get("continuity_anchor", ""))
    scene_change = _normalize_inline_text(details.get("scene_change", ""))

    normalized = {
        "page_kind": page_kind,
        "full_summary": full_summary[:SUMMARY_CONTEXT_LIMIT],
        "condensed_summary": condensed_summary[:MAX_SCENE_CHARS],
        "page_beats": page_beats,
        "key_objects": key_objects,
        "setting": _normalize_inline_text(details.get("setting", ""))[:MAX_FIELD_CHARS],
        "location": _normalize_inline_text(details.get("location", ""))[:MAX_FIELD_CHARS],
        "time_of_day": _normalize_inline_text(details.get("time_of_day", ""))[:MAX_FIELD_CHARS],
        "lighting": _normalize_inline_text(details.get("lighting", ""))[:MAX_FIELD_CHARS],
        "weather": _normalize_inline_text(details.get("weather", ""))[:MAX_FIELD_CHARS],
        "mood": _normalize_inline_text(details.get("mood", ""))[:MAX_FIELD_CHARS],
        "camera_focus": _normalize_inline_text(details.get("camera_focus", ""))[:MAX_FIELD_CHARS],
        "character_focus": character_focus,
        "continuity_anchor": continuity_anchor[:MAX_SCENE_CHARS],
        "scene_change": scene_change[:MAX_FIELD_CHARS],
    }
    normalized = _ensure_page_summary_defaults(normalized, cleaned, page_number, continuity_context, characters)
    return normalized


def _summarize_page_with_ollama(text: str, continuity_context: dict, characters: list[dict]) -> dict:
    ollama_url = os.getenv("BOOKTURES_OLLAMA_URL", "http://127.0.0.1:11434/v1/chat/completions")
    ollama_model = os.getenv("BOOKTURES_OLLAMA_MODEL", "granite3.2:8b")
    ollama_timeout = int(os.getenv("BOOKTURES_OLLAMA_TIMEOUT", "45"))
    character_lines = []
    for character in characters[:MAX_CHARACTERS_PER_PAGE]:
        name = _normalize_inline_text(character.get("name", ""))
        profile = _normalize_inline_text(character.get("visual_profile", ""))
        if not name:
            continue
        character_lines.append(f"- {name}: {profile or 'keep appearance stable from prior pages'}")
    character_block = "\n".join(character_lines) or "- no reliable named characters detected"

    previous_pages = continuity_context.get("previous_summaries", [])
    previous_block = "\n".join(
        f"- page {item['page_number']}: {item['summary']}" for item in previous_pages
    ) or "- no prior page summaries available"

    output_schema = (
        "{"
        '"full_summary":"...",'
        '"condensed_summary":"...",'
        '"page_beats":["..."],'
        '"key_objects":["..."],'
        '"setting":"...",'
        '"location":"...",'
        '"time_of_day":"...",'
        '"lighting":"...",'
        '"weather":"...",'
        '"mood":"...",'
        '"camera_focus":"...",'
        '"character_focus":["..."],'
        '"continuity_anchor":"...",'
        '"scene_change":"..."'
        "}"
    )
    payload = {
        "model": ollama_model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You condense a full book page into a visual summary for illustration planning. "
                    "Return valid JSON only using exactly the requested keys. "
                    "Make the condensed summary specific to this page, with concrete imagery, actions, and changes from previous pages. "
                    "Avoid vague wording like 'something happens' or 'a dramatic moment'; always name visible actions, props, positions, and spatial relationships."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Current page text:\n"
                    f"{text[:SUMMARY_CONTEXT_LIMIT]}\n\n"
                    "Previous page summaries for continuity:\n"
                    f"{previous_block}\n\n"
                    "Known character anchors:\n"
                    f"{character_block}\n\n"
                    "Instructions:\n"
                    "- Capture what is visually unique about this page.\n"
                    "- Keep character appearance consistent with known anchors.\n"
                    "- Prefer concrete nouns and verbs over abstract adjectives.\n"
                    "- If the source text is weak, stay grounded and avoid inventing plot facts.\n"
                    "- Make continuity_anchor a short note about what should stay stable from previous pages.\n"
                    "- Make scene_change explain what visually changes on this page versus earlier context.\n"
                    "- condensed_summary should be 2 to 3 sentences and image-friendly.\n\n"
                    f"Output format (exact keys): {output_schema}"
                ),
            },
        ],
        "temperature": _read_env_float("BOOKTURES_SUMMARY_TEMPERATURE", 0.2),
        "response_format": {"type": "json_object"},
    }

    try:
        response = requests.post(ollama_url, json=payload, timeout=ollama_timeout)
        response.raise_for_status()
        content = _extract_chat_content(response.json())
        parsed = _parse_json_maybe(content)
        if isinstance(parsed, dict) and parsed:
            return parsed
    except (requests.RequestException, ValueError, KeyError) as exc:
        logger.debug("Ollama page summarization failed, using fallback: %s", exc)
    return {}


def _compose_visual_prompt(
    page_summary: dict,
    continuity_context: dict,
    characters: list[dict],
    style_preset: str,
) -> tuple[str, str]:
    prompt = _prompt_with_ollama(page_summary, continuity_context, characters, style_preset)
    if prompt:
        return _guard_prompt(prompt), STYLE_PRESETS.get(style_preset, STYLE_PRESETS[DEFAULT_STYLE_PRESET])["negative"]

    return _fallback_visual_prompt(page_summary, continuity_context, characters, style_preset)


def _prompt_with_ollama(
    page_summary: dict,
    continuity_context: dict,
    characters: list[dict],
    style_preset: str,
) -> str:
    ollama_url = os.getenv("BOOKTURES_OLLAMA_URL", "http://127.0.0.1:11434/v1/chat/completions")
    ollama_model = os.getenv("BOOKTURES_OLLAMA_MODEL", "granite3.2:8b")
    ollama_timeout = int(os.getenv("BOOKTURES_OLLAMA_TIMEOUT", "45"))
    preset = STYLE_PRESETS.get(style_preset, STYLE_PRESETS[DEFAULT_STYLE_PRESET])
    previous_block = "\n".join(
        f"- page {item['page_number']}: {item['summary']}"
        for item in continuity_context.get("previous_summaries", [])
    ) or "- no prior pages"
    character_block = "\n".join(
        f"- {character['name']}: {_normalize_inline_text(character.get('visual_profile', '')) or 'preserve established appearance'}"
        for character in characters[:MAX_CHARACTERS_PER_PAGE]
        if character.get("name")
    ) or "- no reliable named characters"

    output_schema = '{"visual_prompt":"..."}'
    payload = {
        "model": ollama_model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You write one image-generation prompt for a single book page. "
                    "Return valid JSON only with key visual_prompt. "
                    "The prompt must prioritize the current page's distinctive scene while keeping characters consistent with previous pages. "
                    "Use concrete visual staging and avoid generic cinematic filler."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Style direction: {preset['style']}\n\n"
                    f"Current page full summary: {page_summary.get('full_summary', '')}\n\n"
                    f"Current page condensed visual summary: {page_summary.get('condensed_summary', '')}\n\n"
                    "Current page beats:\n"
                    + "\n".join(f"- {beat}" for beat in page_summary.get("page_beats", []))
                    + "\n\n"
                    + "Key objects:\n"
                    + ("\n".join(f"- {item}" for item in page_summary.get("key_objects", [])) or "- none")
                    + "\n\n"
                    + "Character focus on this page:\n"
                    + ("\n".join(f"- {item}" for item in page_summary.get("character_focus", [])) or "- none")
                    + "\n\n"
                    + "Previous page continuity context:\n"
                    + previous_block
                    + "\n\n"
                    + "Character appearance anchors:\n"
                    + character_block
                    + "\n\n"
                    + "Required prompt sections:\n"
                    + f"- page beat: summarize this page visually in one vivid sentence\n"
                    + f"- continuity anchor: {page_summary.get('continuity_anchor', '') or 'preserve established character identity'}\n"
                    + f"- scene change: {page_summary.get('scene_change', '') or 'show what is visually new on this page'}\n"
                    + f"- setting: {page_summary.get('setting', '')}\n"
                    + f"- location: {page_summary.get('location', '')}\n"
                    + f"- lighting: {page_summary.get('lighting', '')}\n"
                    + f"- mood: {page_summary.get('mood', '')}\n"
                    + f"- camera focus: {page_summary.get('camera_focus', '')}\n"
                    + "\nConstraints:\n"
                    + "- Keep it specific to the current page, not generic.\n"
                    + "- Mention named characters only if they are present.\n"
                    + "- Preserve face, hair, clothing, and silhouette continuity when characters reappear.\n"
                    + "- Prefer concrete props, gestures, staging, and environment changes over boilerplate style words.\n"
                    + "- Include subject, action, setting depth, and one clear focal composition choice.\n"
                    + "- Keep it under 170 words.\n\n"
                    + f"Output format (exact keys): {output_schema}"
                ),
            },
        ],
        "temperature": _read_env_float("BOOKTURES_PROMPT_TEMPERATURE", 0.35),
        "response_format": {"type": "json_object"},
    }

    try:
        response = requests.post(ollama_url, json=payload, timeout=ollama_timeout)
        response.raise_for_status()
        content = _extract_chat_content(response.json())
        parsed = _parse_json_maybe(content)
        if isinstance(parsed, dict):
            visual_prompt = _normalize_inline_text(parsed.get("visual_prompt", ""))
            if visual_prompt and _is_prompt_output_usable(page_summary, visual_prompt):
                return visual_prompt
    except (requests.RequestException, ValueError, KeyError) as exc:
        logger.debug("Ollama prompt composition failed, using fallback: %s", exc)
    return ""


def _fallback_page_summary(
    cleaned: str,
    page_number: int,
    continuity_context: dict,
    characters: list[dict],
) -> dict:
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", cleaned) if part.strip()]
    summary_sentences = _clean_sentence_candidates(sentences, max_items=6)
    condensed_sentences = _clean_sentence_candidates(sentences, max_items=3)
    page_beats = _clean_sentence_candidates(sentences, max_items=MAX_PAGE_BEATS)
    continuity_anchor = continuity_context.get("previous_summary_text", "")
    if not continuity_anchor and characters:
        continuity_anchor = "; ".join(
            f"{character['name']} stays visually consistent"
            for character in characters[:MAX_CHARACTERS_PER_PAGE]
            if character.get("name")
        )
    if not continuity_anchor:
        continuity_anchor = "establish the opening visual identity of the story world"

    return {
        "page_kind": "story",
        "full_summary": " ".join(summary_sentences).strip() or cleaned[:SUMMARY_CONTEXT_LIMIT],
        "condensed_summary": _fallback_visual_scene_summary(cleaned, characters),
        "page_beats": page_beats or [_fallback_visual_scene_summary(cleaned, characters)],
        "key_objects": _extract_key_objects(cleaned),
        "setting": _infer_setting(cleaned),
        "location": _infer_location(cleaned),
        "time_of_day": _infer_time_of_day(cleaned),
        "lighting": _infer_lighting(cleaned),
        "weather": _infer_weather(cleaned),
        "mood": _infer_mood(cleaned),
        "camera_focus": _shot_variation_directive(page_number),
        "character_focus": _build_character_focus_fallback(cleaned, characters),
        "continuity_anchor": continuity_anchor,
        "scene_change": _infer_scene_change(cleaned),
    }


def _fallback_visual_prompt(
    page_summary: dict,
    continuity_context: dict,
    characters: list[dict],
    style_preset: str,
) -> tuple[str, str]:
    preset = STYLE_PRESETS.get(style_preset, STYLE_PRESETS[DEFAULT_STYLE_PRESET])
    sections = [
        preset["style"],
        f"page beat: {page_summary.get('condensed_summary', '')}",
        f"{PROMPT_PIPELINE_MARKER} {page_summary.get('continuity_anchor', '') or continuity_context.get('character_anchor', 'preserve established visual identity')}",
    ]
    if page_summary.get("scene_change"):
        sections.append(f"scene change: {page_summary['scene_change']}")
    if page_summary.get("setting"):
        sections.append(f"setting: {page_summary['setting']}")
    if page_summary.get("location"):
        sections.append(f"location: {page_summary['location']}")
    if page_summary.get("time_of_day"):
        sections.append(f"time of day: {page_summary['time_of_day']}")
    if page_summary.get("lighting"):
        sections.append(f"lighting: {page_summary['lighting']}")
    if page_summary.get("weather") and page_summary.get("weather") != "unspecified":
        sections.append(f"weather: {page_summary['weather']}")
    if page_summary.get("mood"):
        sections.append(f"mood: {page_summary['mood']}")
    if page_summary.get("camera_focus"):
        sections.append(f"camera focus: {page_summary['camera_focus']}")
    if page_summary.get("page_beats"):
        sections.append("page actions: " + "; ".join(page_summary["page_beats"][:3]))
    if page_summary.get("key_objects"):
        sections.append("key objects: " + "; ".join(page_summary["key_objects"][:4]))
    if characters:
        character_bits = []
        for character in characters[:MAX_CHARACTERS_PER_PAGE]:
            name = _normalize_inline_text(character.get("name", ""))
            if not name:
                continue
            profile = _normalize_inline_text(character.get("visual_profile", ""))
            if profile:
                character_bits.append(f"{name} ({profile})")
            else:
                character_bits.append(name)
        if character_bits:
            sections.append("characters present: " + "; ".join(character_bits))
            sections.append("preserve face, hair, outfit, and silhouette continuity for returning characters")
    elif page_summary.get("character_focus"):
        sections.append("character acting: " + "; ".join(page_summary["character_focus"][:3]))

    prompt = ". ".join(section for section in sections if section).strip()
    return _guard_prompt(prompt), preset["negative"]


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


def _normalize_summary(text: str, max_sentences: int = 4) -> str:
    text = _normalize_inline_text(text)
    return _limit_to_n_sentences(text, max_sentences=max_sentences)


def _normalize_inline_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip())


def _normalize_list(items, max_items: int) -> list[str]:
    if not isinstance(items, list):
        return []
    cleaned_items = []
    for item in items:
        value = _normalize_inline_text(item)
        if not value:
            continue
        cleaned_items.append(value)
        if len(cleaned_items) >= max_items:
            break
    return cleaned_items


def _limit_to_n_sentences(text: str, max_sentences: int = 4) -> str:
    if not text:
        return ""
    chunks = re.split(r"(?<=[.!?])\s+", text.strip())
    selected = [chunk.strip() for chunk in chunks[:max_sentences] if chunk.strip()]
    return " ".join(selected).strip()


def _ensure_page_summary_defaults(
    details: dict,
    text: str,
    page_number: int,
    continuity_context: dict,
    characters: list[dict],
) -> dict:
    if not details.get("page_kind"):
        details["page_kind"] = _classify_page_kind(text, page_number)
    if not details.get("full_summary"):
        details["full_summary"] = _fallback_condensed_summary(text)
    if not details.get("condensed_summary"):
        details["condensed_summary"] = _fallback_visual_scene_summary(text, characters)
    if not details.get("page_beats"):
        details["page_beats"] = [details["condensed_summary"]]
    if not details.get("key_objects"):
        details["key_objects"] = _extract_key_objects(text)
    if not details.get("location"):
        details["location"] = _infer_location(text)
    if not details.get("time_of_day"):
        details["time_of_day"] = _infer_time_of_day(text)
    if not details.get("lighting"):
        details["lighting"] = _infer_lighting(text)
    if not details.get("weather"):
        details["weather"] = _infer_weather(text)
    if not details.get("mood"):
        details["mood"] = _infer_mood(text)
    if not details.get("camera_focus"):
        details["camera_focus"] = _shot_variation_directive(page_number)
    if not details.get("continuity_anchor"):
        details["continuity_anchor"] = (
            continuity_context.get("previous_summary_text")
            or continuity_context.get("character_anchor")
            or "preserve the established visual identity for recurring characters and locations"
        )
    if not details.get("scene_change"):
        details["scene_change"] = _infer_scene_change(text)
    if not details.get("character_focus"):
        details["character_focus"] = _build_character_focus_fallback(text, characters)
    return details


def _fallback_condensed_summary(text: str) -> str:
    cleaned = _normalize_inline_text(text)
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", cleaned) if part.strip()]
    return " ".join(sentences[:3]).strip() or cleaned[:500]


def _classify_page_kind(text: str, page_number: int) -> str:
    cleaned = _normalize_inline_text(text)
    lower = cleaned.lower()
    if not cleaned:
        return "blank"
    if page_number <= 3 and ("table of contents" in lower or "contents" in lower):
        return "contents"
    legal_patterns = _read_env_list("BOOKTURES_LEGAL_PAGE_PATTERNS", DEFAULT_LEGAL_PAGE_PATTERNS)
    if any(re.search(pattern, lower) for pattern in legal_patterns):
        return "legal"
    if page_number <= 2 and len(cleaned.split()) <= 12:
        return "title"
    if cleaned.count(". . .") >= 3 or re.search(r"\btable of contents\b", lower):
        return "contents"
    return "story"


def _summarize_non_story_page(text: str, page_number: int, page_kind: str, continuity_context: dict) -> dict:
    if page_kind == "title":
        condensed = "A title page presenting the book name and author in a centered typographic layout."
        setting = "book title page"
        scene_change = "the book opens with formal title typography instead of a narrative scene"
    elif page_kind == "legal":
        condensed = "A legal or disclaimer page composed of dense blocks of publication text."
        setting = "publishing front matter"
        scene_change = "the page is informational front matter rather than story action"
    elif page_kind == "contents":
        condensed = "A table of contents page listing chapters and sections in a structured typographic layout."
        setting = "table of contents page"
        scene_change = "the page presents chapter listings instead of a story moment"
    else:
        condensed = "A blank or nearly blank page with minimal visible content."
        setting = "blank page"
        scene_change = "there is no narrative scene on this page"

    return {
        "page_kind": page_kind,
        "full_summary": condensed,
        "condensed_summary": condensed,
        "page_beats": [condensed],
        "key_objects": ["printed text", "page layout"] if page_kind != "blank" else [],
        "setting": setting,
        "location": "printed book page",
        "time_of_day": "",
        "lighting": "even page lighting",
        "weather": "",
        "mood": "quiet editorial page",
        "camera_focus": "straight-on view of the printed page layout",
        "character_focus": [],
        "continuity_anchor": continuity_context.get("previous_summary_text", "") or "preserve book design continuity across front matter pages",
        "scene_change": scene_change,
    }


def _clean_sentence_candidates(sentences: list[str], max_items: int) -> list[str]:
    cleaned_items: list[str] = []
    for sentence in sentences:
        candidate = _normalize_inline_text(sentence)
        if not candidate:
            continue
        if len(candidate.split()) < 6:
            continue
        if candidate.count(".") > 6:
            continue
        cleaned_items.append(candidate)
        if len(cleaned_items) >= max_items:
            break
    return cleaned_items


def _fallback_visual_scene_summary(text: str, characters: list[dict]) -> str:
    setting = _infer_setting(text)
    mood = _infer_mood(text)
    location = _infer_location(text)
    char_names = [
        _normalize_inline_text(character.get("name", ""))
        for character in characters[:2]
        if _normalize_inline_text(character.get("name", ""))
    ]
    subject = ", ".join(char_names) if char_names else "the central figures"
    key_objects = _extract_key_objects(text)
    prop_text = f" with {', '.join(key_objects[:2])}" if key_objects else ""
    return f"{subject} in {location}, {setting}, rendered with {mood}{prop_text}."


def _infer_setting(text: str) -> str:
    lower = text.lower()
    if _has_any(lower, ["moor", "field", "tor", "road", "garden", "lane", "path"]):
        return "an exposed outdoor environment"
    if _has_any(lower, ["hall", "study", "room", "house", "fireplace", "window", "table"]):
        return "an interior story setting"
    if _has_any(lower, ["carriage", "cab", "street", "london"]):
        return "a city travel scene"
    return "a narrative story setting"


def _extract_key_objects(text: str) -> list[str]:
    lowered = text.lower()
    keywords = [
        "letter", "book", "lamp", "window", "door", "table", "fire", "candle",
        "carriage", "horse", "gun", "knife", "portrait", "mirror", "ring", "chair",
        "stairs", "garden", "rain", "clock", "bag", "paper", "teacup", "bed",
    ]
    found = []
    for keyword in keywords:
        if keyword in lowered:
            found.append(keyword)
        if len(found) >= MAX_KEY_OBJECTS:
            break
    return found


def _build_character_focus_fallback(text: str, characters: list[dict]) -> list[str]:
    focus = []
    for character in characters[:MAX_CHARACTERS_PER_PAGE]:
        name = _normalize_inline_text(character.get("name", ""))
        if not name:
            continue
        focus.append(f"{name} is central to the page action")
    if focus:
        return focus[:MAX_CHARACTER_MOMENTS]
    cleaned = _normalize_inline_text(text)
    if cleaned:
        return [cleaned[:160]]
    return []


def _infer_location(text: str) -> str:
    lower = text.lower()
    if _has_any(lower, ["street", "road", "field", "garden", "moor", "forest", "river"]):
        return "outdoor setting"
    if _has_any(lower, ["room", "house", "hall", "study", "bedroom", "window", "door"]):
        return "interior"
    return "unspecified setting"


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
        return "cold or snowy"
    if _has_any(lower, ["wind", "gust"]):
        return "windy"
    return "unspecified"


def _infer_mood(text: str) -> str:
    lower = text.lower()
    if _has_any(lower, ["fear", "terror", "panic", "dread"]):
        return "tense and fearful"
    if _has_any(lower, ["joy", "smile", "laugh", "warm"]):
        return "warm and hopeful"
    if _has_any(lower, ["anger", "furious", "rage"]):
        return "heated confrontation"
    if _has_any(lower, ["mystery", "strange", "curious", "secret"]):
        return "mysterious and suspenseful"
    return "dramatic narrative tension"


def _infer_scene_change(text: str) -> str:
    lower = text.lower()
    if _has_any(lower, ["suddenly", "at once", "immediately", "burst"]):
        return "a sudden change interrupts the prior rhythm"
    if _has_any(lower, ["entered", "arrived", "came in", "appeared"]):
        return "a new presence changes the staging of the scene"
    if _has_any(lower, ["looked", "watched", "stared", "glanced"]):
        return "the focus shifts to observation and reaction"
    return "the page should clearly show the next visual beat in the story"


def _shot_variation_directive(page_number: int) -> str:
    variants = [
        "wide establishing composition with layered depth",
        "medium shot centered on character interaction",
        "close emotional framing on faces and gesture",
        "over-shoulder viewpoint that emphasizes tension",
        "low-angle composition with dramatic silhouettes",
        "high-angle framing that clarifies spatial relationships",
    ]
    index = max(0, (int(page_number) - 1) % len(variants))
    return variants[index]


def _has_any(text: str, keywords: list[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def _guard_prompt(prompt: str) -> str:
    trimmed = prompt[:MAX_PROMPT_CHARS]
    words = trimmed.split()
    if len(words) <= MAX_PROMPT_WORDS:
        return trimmed
    return " ".join(words[:MAX_PROMPT_WORDS])


def _prompt_matches_current_pipeline(prompt: str) -> bool:
    return PROMPT_PIPELINE_MARKER in (prompt or "").lower()


def _read_env_float(name: str, default: float) -> float:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _read_env_list(name: str, default: list[str]) -> list[str]:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    values = [item.strip() for item in raw.split("||") if item.strip()]
    return values or default


def _is_low_extraction_score(extraction_score: float | None) -> bool:
    if extraction_score is None:
        return False
    threshold = _read_env_float("BOOKTURES_MIN_EXTRACTION_SCORE", 120.0)
    return float(extraction_score) < threshold


def _is_summary_output_usable(source_text: str, details: dict) -> bool:
    min_summary_chars = int(_read_env_float("BOOKTURES_MIN_SUMMARY_CHARS", 80))
    max_copy_ratio = _read_env_float("BOOKTURES_MAX_SUMMARY_COPY_RATIO", 0.92)
    full_summary = _normalize_inline_text(details.get("full_summary") or details.get("summary") or "")
    condensed = _normalize_inline_text(details.get("condensed_summary") or details.get("visual_summary") or "")
    if len(full_summary) < min_summary_chars or len(condensed) < max(40, min_summary_chars // 2):
        return False
    source = _normalize_inline_text(source_text)
    if not source:
        return True
    overlap = _token_overlap_ratio(source, full_summary)
    return overlap < max_copy_ratio


def _is_prompt_output_usable(page_summary: dict, visual_prompt: str) -> bool:
    min_prompt_chars = int(_read_env_float("BOOKTURES_MIN_PROMPT_CHARS", 100))
    max_copy_ratio = _read_env_float("BOOKTURES_MAX_PROMPT_COPY_RATIO", 0.95)
    cleaned_prompt = _normalize_inline_text(visual_prompt)
    if len(cleaned_prompt) < min_prompt_chars:
        return False
    summary_text = _normalize_inline_text(page_summary.get("full_summary", ""))
    if not summary_text:
        return True
    overlap = _token_overlap_ratio(summary_text, cleaned_prompt)
    return overlap < max_copy_ratio


def _token_overlap_ratio(a: str, b: str) -> float:
    a_tokens = {token for token in re.findall(r"[a-z0-9']+", a.lower()) if len(token) > 2}
    b_tokens = {token for token in re.findall(r"[a-z0-9']+", b.lower()) if len(token) > 2}
    if not a_tokens:
        return 0.0
    return len(a_tokens & b_tokens) / max(len(a_tokens), 1)
