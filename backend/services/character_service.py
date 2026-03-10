import json
import logging
import re
from collections import Counter
from typing import Iterable, Optional

import spacy
from rapidfuzz import fuzz

from database import SessionLocal
from models.book import Book
from models.character import Character
from models.page import Page
from models.page_character import PageCharacter

logger = logging.getLogger(__name__)
try:
    _nlp = spacy.load("en_core_web_trf")
except Exception:  # pragma: no cover
    logger.info("Falling back to en_core_web_sm")
    _nlp = spacy.load("en_core_web_sm")

ALIAS_MATCH_SCORE = 88
PAGE_LINK_MATCH_SCORE = 90
MIN_TOTAL_MENTIONS = 2
MIN_PAGE_CONFIDENCE = 0.45
TITLE_TOKENS = {"mr", "mrs", "miss", "ms", "sir", "lady", "lord", "dr"}
IGNORE_TOKENS = {"man", "woman", "boy", "girl", "father", "mother", "uncle", "aunt"}
STOP_DESCRIPTOR_WORDS = {
    "very",
    "quite",
    "rather",
    "more",
    "most",
    "little",
    "much",
    "the",
    "a",
    "an",
}
VISUAL_PATTERN = re.compile(
    r"\b(tall|short|slender|stocky|thin|broad|old|young|elderly|bearded|clean-shaven|"
    r"blonde|fair-haired|dark-haired|black-haired|red-haired|blue-eyed|green-eyed|"
    r"scarred|pale|freckled|handsome|beautiful|elegant|ragged|shabby)\b",
    re.IGNORECASE,
)
VISUAL_CONFLICT_GROUPS = [
    {"young", "old", "elderly"},
    {"bearded", "clean-shaven"},
    {"blonde", "dark-haired", "black-haired", "red-haired", "fair-haired"},
]


def build_character_registry(book_id: int):
    logger.info("Starting character registry for book %s", book_id)
    db = SessionLocal()
    try:
        book = db.get(Book, book_id)
        if book is None:
            logger.warning("Cannot build characters; book %s not found", book_id)
            return

        pages = (
            db.query(Page)
            .filter(Page.book_id == book_id)
            .order_by(Page.page_number)
            .all()
        )
        if not pages:
            logger.info("No pages found for book %s", book_id)
            return

        characters = _extract_characters_from_pages(pages)
        characters = _collapse_aliases(characters)
        characters = _filter_characters(characters)

        db.query(PageCharacter).filter(PageCharacter.book_id == book_id).delete()
        db.query(Character).filter(Character.book_id == book_id).delete()

        stored_characters = 0
        page_links = 0
        for entry in characters.values():
            character_record = Character(
                book_id=book_id,
                name=entry["name"],
                aliases=json.dumps(sorted(entry["aliases"])),
                visual_profile=_build_visual_profile(entry["descriptors"]),
                source="ner",
                mention_count=entry["mention_count"],
                first_appearance_page=entry["first_page"],
                external_url=None,
            )
            db.add(character_record)
            db.flush()
            stored_characters += 1

            for page_id, mention in entry["page_mentions"].items():
                confidence = mention["confidence_sum"] / max(mention["mention_count"], 1)
                if confidence < MIN_PAGE_CONFIDENCE:
                    continue
                db.add(
                    PageCharacter(
                        book_id=book_id,
                        page_id=page_id,
                        character_id=character_record.id,
                        mention_count=mention["mention_count"],
                        confidence=min(1.0, confidence),
                    )
                )
                page_links += 1

        db.commit()
        logger.info(
            "Stored %s characters and %s page links for book %s",
            stored_characters,
            page_links,
            book_id,
        )

    except Exception:
        db.rollback()
        logger.exception("Character registry failed for book %s", book_id)
        raise

    finally:
        db.close()


def _extract_characters_from_pages(pages: Iterable[Page]) -> dict[str, dict]:
    entries: dict[str, dict] = {}

    for page in pages:
        if not page.text:
            continue
        doc = _nlp(page.text)
        for ent in doc.ents:
            if ent.label_ != "PERSON":
                continue

            raw_name = ent.text.strip()
            normalized = _normalize_name(raw_name)
            if not normalized:
                continue

            entry = entries.setdefault(
                normalized,
                {
                    "name": raw_name,
                    "aliases": {raw_name},
                    "alias_norms": {normalized},
                    "mention_count": 0,
                    "first_page": None,
                    "descriptors": Counter(),
                    "page_mentions": {},
                },
            )

            if len(raw_name) > len(entry["name"]):
                entry["name"] = raw_name
            entry["aliases"].add(raw_name)
            entry["alias_norms"].add(normalized)
            entry["mention_count"] += 1
            entry["first_page"] = _earliest_page(entry["first_page"], page.page_number)

            for descriptor in _extract_visual_descriptors(ent.sent.text):
                entry["descriptors"][descriptor] += 1

            mention = entry["page_mentions"].setdefault(
                page.id,
                {"mention_count": 0, "confidence_sum": 0.0},
            )
            mention["mention_count"] += 1
            mention["confidence_sum"] += _estimate_mention_confidence(raw_name)

    return entries


def _collapse_aliases(characters: dict[str, dict]) -> dict[str, dict]:
    pending = dict(characters)
    collapsed: dict[str, dict] = {}
    while pending:
        norm, entry = max(pending.items(), key=lambda item: item[1]["mention_count"])
        pending.pop(norm, None)
        for other_norm, other in list(pending.items()):
            if _match_alias(entry, other) < ALIAS_MATCH_SCORE:
                continue
            pending.pop(other_norm, None)
            entry["mention_count"] += other["mention_count"]
            entry["first_page"] = _earliest_page(entry["first_page"], other["first_page"])
            entry["aliases"].update(other["aliases"])
            entry["alias_norms"].update(other["alias_norms"])
            entry["descriptors"].update(other["descriptors"])
            _merge_page_mentions(entry["page_mentions"], other["page_mentions"])
            if len(other["name"]) > len(entry["name"]):
                entry["name"] = other["name"]
        collapsed[norm] = entry
    return collapsed


def _match_alias(primary: dict, secondary: dict) -> float:
    best = fuzz.token_set_ratio(primary["name"], secondary["name"])
    for alias_a in primary["aliases"]:
        for alias_b in secondary["aliases"]:
            score = fuzz.token_set_ratio(alias_a, alias_b)
            if score > best:
                best = score
    return best


def _merge_page_mentions(primary: dict, secondary: dict):
    for page_id, mention in secondary.items():
        existing = primary.setdefault(page_id, {"mention_count": 0, "confidence_sum": 0.0})
        existing["mention_count"] += mention["mention_count"]
        existing["confidence_sum"] += mention["confidence_sum"]


def _filter_characters(characters: dict[str, dict]) -> dict[str, dict]:
    filtered: dict[str, dict] = {}
    for norm, entry in characters.items():
        if not entry["name"] or len(entry["name"]) < 3:
            continue
        words = entry["name"].split()
        if len(words) > 5:
            continue
        if any(word.lower() in IGNORE_TOKENS for word in words):
            continue
        if entry["mention_count"] < MIN_TOTAL_MENTIONS:
            continue
        filtered[norm] = entry
    return filtered


def _extract_visual_descriptors(sentence: str) -> list[str]:
    cleaned = sentence.replace("\n", " ").strip()
    if not cleaned:
        return []

    descriptors = []
    for match in VISUAL_PATTERN.findall(cleaned):
        token = match.lower().strip()
        if token and token not in STOP_DESCRIPTOR_WORDS:
            descriptors.append(token)
    return descriptors


def _build_visual_profile(descriptors: Counter) -> Optional[str]:
    if not descriptors:
        return None
    top_descriptors = _select_visual_descriptors(descriptors, max_traits=3)
    if not top_descriptors:
        return None
    return ", ".join(top_descriptors)


def _select_visual_descriptors(descriptors: Counter, max_traits: int) -> list[str]:
    selected: list[str] = []
    for descriptor, _ in descriptors.most_common(12):
        if _conflicts_with_selected(descriptor, selected):
            continue
        selected.append(descriptor)
        if len(selected) >= max_traits:
            break
    return selected


def _conflicts_with_selected(candidate: str, selected: list[str]) -> bool:
    for group in VISUAL_CONFLICT_GROUPS:
        if candidate not in group:
            continue
        if any(existing in group for existing in selected):
            return True
    return False


def _estimate_mention_confidence(name: str) -> float:
    tokens = [tok for tok in name.split() if tok]
    confidence = 0.55 + (0.08 * min(len(tokens), 3))
    if any(tok.isupper() for tok in tokens):
        confidence += 0.05
    return min(1.0, confidence)


def _earliest_page(a: Optional[int], b: Optional[int]) -> Optional[int]:
    if a is None:
        return b
    if b is None:
        return a
    return min(a, b)


def _normalize_name(name: str) -> str:
    name = re.sub(r"'s\b", "", name)
    cleaned = re.sub(r"[^\w\s\-']", "", name)
    cleaned = re.sub(r"\s+", " ", cleaned)
    stripped = _strip_titles(cleaned).strip()
    if not stripped:
        return ""
    tokens = stripped.split()
    if any(tok.lower() in IGNORE_TOKENS for tok in tokens):
        return ""
    return stripped.lower()


def _strip_titles(name: str) -> str:
    tokens = [tok for tok in name.split() if tok.lower().strip(".") not in TITLE_TOKENS]
    return " ".join(tokens)


def resolve_page_characters(page: Page, characters: list[Character]) -> list[dict]:
    """Fallback linker for pages without persisted page_character rows."""
    if not page.text:
        return []

    doc = _nlp(page.text)
    mentions: dict[int, dict] = {}
    character_aliases = _build_character_alias_index(characters)

    for ent in doc.ents:
        if ent.label_ != "PERSON":
            continue
        normalized = _normalize_name(ent.text)
        if not normalized:
            continue
        best_character_id, best_score = _best_character_match(normalized, character_aliases)
        if best_character_id is None or best_score < PAGE_LINK_MATCH_SCORE:
            continue

        mention = mentions.setdefault(
            best_character_id,
            {"mention_count": 0, "confidence_sum": 0.0},
        )
        mention["mention_count"] += 1
        mention["confidence_sum"] += best_score / 100.0

    resolved = []
    for character in characters:
        mention = mentions.get(character.id)
        if not mention:
            continue
        confidence = mention["confidence_sum"] / mention["mention_count"]
        if confidence < MIN_PAGE_CONFIDENCE:
            continue
        resolved.append(
            {
                "character_id": character.id,
                "name": character.name,
                "mention_count": mention["mention_count"],
                "confidence": min(1.0, confidence),
                "visual_profile": character.visual_profile or "",
            }
        )
    return resolved


def _build_character_alias_index(characters: list[Character]) -> dict[int, list[str]]:
    alias_index: dict[int, list[str]] = {}
    for character in characters:
        aliases = _read_aliases(character.aliases)
        aliases.append(character.name)
        normalized_aliases = []
        for alias in aliases:
            normalized = _normalize_name(alias)
            if normalized:
                normalized_aliases.append(normalized)
        alias_index[character.id] = normalized_aliases
    return alias_index


def _best_character_match(
    normalized_name: str,
    character_aliases: dict[int, list[str]],
) -> tuple[Optional[int], float]:
    best_character_id: Optional[int] = None
    best_score = 0.0
    for character_id, aliases in character_aliases.items():
        for alias in aliases:
            score = fuzz.token_set_ratio(normalized_name, alias)
            if score > best_score:
                best_score = score
                best_character_id = character_id
    return best_character_id, best_score


def _read_aliases(raw_aliases: Optional[str]) -> list[str]:
    if not raw_aliases:
        return []
    try:
        aliases = json.loads(raw_aliases)
    except json.JSONDecodeError:
        return []
    if not isinstance(aliases, list):
        return []
    return [str(alias) for alias in aliases if alias]
