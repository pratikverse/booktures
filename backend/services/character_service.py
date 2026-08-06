import os
import json
import logging
import re
from typing import Dict, List, Optional
import spacy
from rapidfuzz import fuzz
from sqlalchemy.orm import Session

from services.pdf_service import ollama_generate
from models import Character, DocumentChunk, page_characters

logger = logging.getLogger(__name__)

try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    logger.warning("spaCy model 'en_core_web_sm' not found. Character extraction will be limited.")
    nlp = None

ALIAS_MATCH_SCORE = 85
OLLAMA_MODEL = os.getenv("OLLAMA_DEFAULT_MODEL", "qwen2.5:7b")
NO_VISUAL_PROFILE = "No visual description available."

HONORIFIC_RE = re.compile(r"^(mr|mrs|ms|miss|dr|prof|sir|lady|lord)\.?\s+", re.I)


def process_book_characters(book_id: int, db: Session):
    """
    Full pipeline to identify, normalize, and profile characters in a book.
    CHARACTER_EXTRACTION_MODE=llm uses a single LLM pass instead of spaCy NER
    (useful on API-only/no-GPU deploys where the transformer NER model isn't installed).
    """
    chunks = db.query(DocumentChunk).filter(DocumentChunk.book_id == book_id).order_by(DocumentChunk.page_number).all()
    full_text = " ".join(c.content for c in chunks)

    mode = os.getenv("CHARACTER_EXTRACTION_MODE", "spacy").strip().lower()
    if mode == "llm":
        _process_characters_llm(book_id, chunks, full_text, db)
        return

    if not nlp:
        logger.error("spaCy NLP engine not loaded.")
        return

    raw_mentions: Dict[str, List[int]] = {}
    for chunk in chunks:
        doc = nlp(chunk.content)
        for ent in doc.ents:
            if ent.label_ == "PERSON":
                name = ent.text.strip()
                if len(name) > 2 and not _is_noise(name):
                    raw_mentions.setdefault(name, []).append(chunk.id)

    canonical_groups = _group_aliases(raw_mentions)

    for main_name, group in canonical_groups.items():
        context = _gather_character_context(full_text, main_name)
        visual_profile = _extract_visual_traits_llm(main_name, context)

        char_obj = Character(
            book_id=book_id,
            name=main_name,
            aliases=", ".join(sorted(group["aliases"])),
            visual_profile=visual_profile,
            mention_count=group["total_mentions"],
        )
        db.add(char_obj)
        db.flush()

        for chunk_id in set(group["chunk_ids"]):
            db.execute(page_characters.insert().values(character_id=char_obj.id, chunk_id=chunk_id))

    db.commit()


def _process_characters_llm(book_id: int, chunks: List[DocumentChunk], full_text: str, db: Session):
    characters = _extract_characters_llm(full_text)
    for c in characters:
        name = (c.get("name") or "").strip()
        if not name:
            continue
        aliases = sorted({name, *[a.strip() for a in c.get("aliases", []) if a and a.strip()]})
        visual_profile = (c.get("visual_profile") or "").strip() or NO_VISUAL_PROFILE
        chunk_ids = _find_chunk_ids(chunks, aliases)

        char_obj = Character(
            book_id=book_id,
            name=name,
            aliases=", ".join(aliases),
            visual_profile=visual_profile,
            mention_count=len(chunk_ids),
        )
        db.add(char_obj)
        db.flush()

        for chunk_id in set(chunk_ids):
            db.execute(page_characters.insert().values(character_id=char_obj.id, chunk_id=chunk_id))

    db.commit()


def _extract_characters_llm(full_text: str) -> List[Dict]:
    """Single-pass LLM character + visual trait extraction, no spaCy required."""
    sample = full_text[:4000]
    if len(full_text) > 8000:
        mid = len(full_text) // 2
        sample += "\n...\n" + full_text[mid:mid + 2000] + "\n...\n" + full_text[-2000:]

    system = (
        "You are a character profiler. Identify main characters and their stable physical "
        "visual traits (hair, eyes, clothing, age). Respond ONLY with valid JSON, no commentary: "
        '[{"name": "...", "aliases": ["..."], "visual_profile": "one concise plain-text sentence, not nested JSON"}]'
    )
    for _ in range(2):
        response = ollama_generate(sample, model=OLLAMA_MODEL, system=system)
        data = _safe_parse_json(response)
        if isinstance(data, list):
            return data
    logger.warning("LLM character extraction failed after retry; no characters found.")
    return []


def _find_chunk_ids(chunks: List[DocumentChunk], names: List[str]) -> List[int]:
    ids = []
    lowered = [n.lower() for n in names if n]
    for chunk in chunks:
        text_lower = chunk.content.lower()
        if any(n in text_lower for n in lowered):
            ids.append(chunk.id)
    return ids


def _is_noise(name: str) -> bool:
    noise_words = {"author", "project gutenberg", "chapter", "illustration", "page"}
    return any(word in name.lower() for word in noise_words)


def _normalize_name(name: str) -> str:
    return HONORIFIC_RE.sub("", name).strip()


def _group_aliases(mentions: Dict[str, List[int]]) -> Dict[str, Dict]:
    """Union-find alias grouping (order-independent), honorific-insensitive."""
    names = list(mentions.keys())
    parent = {n: n for n in names}

    def find(n):
        while parent[n] != n:
            parent[n] = parent[parent[n]]
            n = parent[n]
        return n

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    normalized = {n: _normalize_name(n) for n in names}
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if fuzz.partial_ratio(normalized[a], normalized[b]) > ALIAS_MATCH_SCORE:
                union(a, b)

    groups: Dict[str, Dict] = {}
    for n in names:
        root = find(n)
        g = groups.setdefault(root, {"aliases": set(), "chunk_ids": [], "total_mentions": 0})
        g["aliases"].add(n)
        g["chunk_ids"].extend(mentions[n])
        g["total_mentions"] += len(mentions[n])

    # Key each group by its most-mentioned alias for a readable canonical name.
    return {max(g["aliases"], key=lambda a: len(mentions[a])): g for g in groups.values()}


def _gather_character_context(text: str, name: str, window: int = 200, max_snippets: int = 10) -> str:
    """Samples mentions spread across the whole book, not just the first few."""
    mentions = [m.start() for m in re.finditer(re.escape(name), text)]
    if not mentions:
        return ""
    if len(mentions) <= max_snippets:
        picks = mentions
    else:
        step = len(mentions) / max_snippets
        picks = [mentions[int(i * step)] for i in range(max_snippets)]
    snippets = [text[max(0, s - window):min(len(text), s + window)] for s in picks]
    return "... ".join(snippets)


def _extract_visual_traits_llm(name: str, context: str) -> str:
    if not context.strip():
        logger.warning(f"No context found for character '{name}'; using fallback description.")
        return NO_VISUAL_PROFILE

    prompt = f"Extract stable physical visual traits for character '{name}' from context:\n\n{context}"
    system = "Describe physical traits (hair, age, clothing). Be highly concise."

    result = ollama_generate(prompt, model=OLLAMA_MODEL, system=system)
    if not result.strip():
        result = ollama_generate(prompt, model=OLLAMA_MODEL, system=system)  # one retry
    if not result.strip():
        logger.warning(f"LLM returned no visual profile for '{name}' after retry.")
        return NO_VISUAL_PROFILE
    return result


def extract_page_metadata(page_text: str) -> Dict[str, str]:
    """Extracts key characters and scene description from a single page's text, as JSON."""
    prompt = (
        "Identify characters present and the primary scene/setting in this text. "
        'Respond ONLY with valid JSON in this exact shape: '
        '{"characters": ["name1", "name2"], "scene": "short description"}'
    )
    for _ in range(2):
        response = ollama_generate(f"{prompt}\n\nText: {page_text[:2000]}", model=OLLAMA_MODEL)
        data = _safe_parse_json(response)
        if isinstance(data, dict):
            chars = ", ".join(data.get("characters") or []) or "Unknown"
            scene = (data.get("scene") or "").strip() or "Standard setting"
            return {"characters": chars, "scene": scene}

    logger.warning("Failed to parse page metadata JSON after retry; using fallback.")
    return {"characters": "Unknown", "scene": "Standard setting"}


def _safe_parse_json(raw: str):
    cleaned = re.sub(r"```(?:json)?|```", "", raw).strip()
    try:
        return json.loads(cleaned)
    except Exception:
        return None
