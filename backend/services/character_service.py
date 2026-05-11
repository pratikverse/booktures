import os
import logging
import re
from typing import Dict, List
import spacy
from rapidfuzz import fuzz
from sqlalchemy.orm import Session

from services.pdf_service import ollama_generate
from models import Character, DocumentChunk, page_characters

logger = logging.getLogger(__name__)

# Load spaCy model for NER (Named Entity Recognition)
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    logger.warning("spaCy model 'en_core_web_sm' not found. Character extraction will be limited.")
    nlp = None

ALIAS_MATCH_SCORE = 85
OLLAMA_MODEL = os.getenv("OLLAMA_DEFAULT_MODEL", "qwen2.5:7b")

def process_book_characters(book_id: int, db: Session):
    """
    Full pipeline to identify, normalize, and profile characters in a book.
    Analyzes all pages to find PERSON entities and builds visual descriptors.
    """
    if not nlp:
        logger.error("spaCy NLP engine not loaded.")
        return

    chunks = db.query(DocumentChunk).filter(DocumentChunk.book_id == book_id).order_by(DocumentChunk.page_number).all()
    
    # 1. Extraction: Find all PERSON entities and track their locations
    raw_mentions: Dict[str, List[int]] = {}
    full_text = ""

    for chunk in chunks:
        full_text += chunk.content + " "
        doc = nlp(chunk.content)
        for ent in doc.ents:
            if ent.label_ == "PERSON":
                name = ent.text.strip()
                if len(name) > 2 and not _is_noise(name):
                    if name not in raw_mentions:
                        raw_mentions[name] = []
                    raw_mentions[name].append(chunk.id)

    # 2. Collapse: Group aliases using fuzzy matching (e.g., 'Sherlock' -> 'Sherlock Holmes')
    canonical_groups = _group_aliases(raw_mentions)

    # 3. Profiling & Persistence
    for main_name, group in canonical_groups.items():
        # Gather context around mentions to extract physical traits
        context = _gather_character_context(full_text, main_name)
        visual_profile = _extract_visual_traits_llm(main_name, context)

        char_obj = Character(
            book_id=book_id,
            name=main_name,
            aliases=", ".join(group["aliases"]),
            visual_profile=visual_profile,
            mention_count=group["total_mentions"]
        )
        db.add(char_obj)
        db.flush() # Populate ID

        # Map characters to the specific pages where they appear
        unique_chunk_ids = set(group["chunk_ids"])
        for chunk_id in unique_chunk_ids:
            db.execute(page_characters.insert().values(character_id=char_obj.id, chunk_id=chunk_id))
    
    db.commit()

def _is_noise(name: str) -> bool:
    noise_words = {"author", "project gutenberg", "chapter", "illustration", "page"}
    return any(word in name.lower() for word in noise_words)

def _group_aliases(mentions: Dict[str, List[int]]) -> Dict[str, Dict]:
    """Uses fuzzy matching to merge name variations into a primary identity."""
    sorted_names = sorted(mentions.keys(), key=len, reverse=True)
    groups = {}

    for name in sorted_names:
        matched = False
        for canonical in groups:
            if fuzz.partial_ratio(name, canonical) > ALIAS_MATCH_SCORE:
                groups[canonical]["aliases"].add(name)
                groups[canonical]["chunk_ids"].extend(mentions[name])
                groups[canonical]["total_mentions"] += len(mentions[name])
                matched = True
                break
        if not matched:
            groups[name] = {
                "aliases": {name},
                "chunk_ids": mentions[name],
                "total_mentions": len(mentions[name])
            }
    return groups

def _gather_character_context(text: str, name: str, window: int = 200) -> str:
    """Extracts text snippets surrounding character mentions to find descriptors."""
    mentions = [m.start() for m in re.finditer(re.escape(name), text)]
    snippets = []
    for start in mentions[:8]: # Sample first 8 mentions for visual profiling
        snippets.append(text[max(0, start-window) : min(len(text), start+window)])
    return "... ".join(snippets)

def _extract_visual_traits_llm(name: str, context: str) -> str:
    prompt = f"Extract stable physical visual traits for character '{name}' from context:\n\n{context}"
    system = "Describe physical traits (hair, age, clothing). Be highly concise."
    return ollama_generate(prompt, model=OLLAMA_MODEL, system=system)

def generate_visual_bible(full_text: str) -> str:
    """
    Generates a 'Visual Bible' for the book by extracting consistent character traits.
    """
    system_prompt = "You are a character profiler. Extract stable physical traits (hair, eyes, clothing, age) for main characters. Be concise and consistent. Format as a list."
    user_prompt = f"Analyze the following text and create a visual bible for its characters:\n\n{full_text[:5000]}"
    return ollama_generate(user_prompt, model=OLLAMA_MODEL, system=system_prompt)

def extract_page_metadata(page_text: str) -> Dict[str, str]:
    """
    Extracts key characters and scene descriptions from a single page's text.
    Used by the generation worker to populate per-page metadata.
    """
    prompt = (
        "Identify characters present and the primary scene/setting in this text. "
        "Format your response exactly as: Characters: [list], Scene: [description]"
    )
    # We process a sample to stay within context windows while getting the gist of the scene
    response = ollama_generate(f"{prompt}\n\nText: {page_text[:2000]}", model=OLLAMA_MODEL)
    
    # Simple parsing logic to separate characters from the scene description
    parts = response.split("Scene:", 1)
    chars = parts[0].replace("Characters:", "").strip() if "Characters:" in parts[0] else "Unknown"
    scene = parts[1].strip() if len(parts) > 1 else "Standard setting"
    
    return {"characters": chars, "scene": scene}