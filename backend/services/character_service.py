import logging
import re
from typing import Iterable, Optional
from urllib.parse import quote

import json
import requests
import spacy
from bs4 import BeautifulSoup
from rapidfuzz import fuzz
from collections import Counter

from database import SessionLocal
from models.book import Book
from models.character import Character
from models.page import Page

logger = logging.getLogger(__name__)
try:
    _nlp = spacy.load("en_core_web_trf")
except Exception:  # pragma: no cover
    logger.info("Falling back to en_core_web_sm")
    _nlp = spacy.load("en_core_web_sm")

MATCH_THRESHOLD = 70
MIN_NER_MENTIONS = 2
MIN_TOTAL_MENTIONS = 3
CANONICAL_SOURCES = {"web", "web-search", "ner+web"}
ALIAS_MATCH_SCORE = 85
IGNORE_TOKENS = {"mr", "mrs", "ms", "sir", "lady", "lord", "god", "man"}
TITLE_TOKENS = {"mr", "mrs", "miss", "ms", "sir", "lady", "lord", "dr"}
DDG_SEARCH_URL = "https://duckduckgo.com/html/"
SEARCH_RESULT_LIMIT = 3
NAME_PATTERN = re.compile(r"[A-Z][a-z]+(?:[''\-][A-Z][a-z]+)*(?:\s+[A-Z][a-z]+(?:[''\-][A-Z][a-z]+)*)+")
SEARCH_HEADERS = {"User-Agent": "Booktures Character Extractor/1.0"}


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

        ner_chars = _extract_characters_from_pages(pages)
        web_chars = _extract_characters_from_web(book.title)
        merged = _merge_character_sets(ner_chars, web_chars)
        merged = _collapse_aliases(merged)
        merged = _filter_merged_characters(merged)

        db.query(Character).filter(Character.book_id == book_id).delete()
        for char in merged.values():
            db.add(Character(
                book_id=book_id,
                name=char["name"],
                source=char["source"],
                mention_count=char["mention_count"],
                first_appearance_page=char["first_page"],
                external_url=char.get("external_url")
            ))
        db.commit()
        logger.info("Stored %s characters for book %s", len(merged), book_id)

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

            name = ent.text.strip()
            normalized = _normalize_name(name)
            if not normalized:
                continue

            entry = entries.setdefault(normalized, {
                "name": name,
                "mention_count": 0,
                "first_page": None,
                "source": "ner",
                "external_url": None,
            })

            entry["mention_count"] += 1
            if entry["first_page"] is None or (page.page_number and page.page_number < entry["first_page"]):
                entry["first_page"] = page.page_number

    return entries


WIKI_SEARCH_URL = "https://en.wikipedia.org/w/api.php?action=opensearch&search={query}&limit=1&format=json"


def _extract_characters_from_web(title: str) -> dict[str, dict]:
    names, source_url = _extract_characters_from_search(title)
    if names:
        return _build_web_entries(names, source_url, source="web-search")

    summary, url = _fetch_wikipedia_summary(title)
    if not summary:
        logger.info("No web enrichment data found for %s", title)
        return {}

    doc = _nlp(summary)
    entries: dict[str, dict] = {}

    for ent in doc.ents:
        if ent.label_ != "PERSON":
            continue
        name = ent.text.strip()
        normalized = _normalize_name(name)
        if not normalized:
            continue
        entry = entries.setdefault(normalized, {
            "name": name,
            "mention_count": 0,
            "first_page": None,
            "source": "web",
            "external_url": url
        })
        entry["mention_count"] += 1

    return entries


def _extract_characters_from_search(title: str) -> tuple[list[str], Optional[str]]:
    query = f"{title} characters"
    urls = _fetch_search_urls(query, SEARCH_RESULT_LIMIT)
    if not urls:
        return [], None

    logger.info("DuckDuckGo returned %s candidate links for %s", len(urls), title)
    name_counter = Counter()
    for url in urls:
        text = _fetch_web_text(url)
        if not text:
            continue
        name_counter.update(NAME_PATTERN.findall(text))

    if not name_counter:
        return [], None

    most_common = [name for name, _ in name_counter.most_common(25)]
    return most_common, urls[0]


def _fetch_search_urls(query: str, limit: int) -> list[str]:
    try:
        response = requests.get(DDG_SEARCH_URL, params={"q": query}, headers=SEARCH_HEADERS, timeout=8)
        if response.status_code != 200:
            logger.debug("DuckDuckGo search failed (%s) for %s", response.status_code, query)
            return []

        soup = BeautifulSoup(response.text, "lxml")
        anchors = soup.select(".result__a")
        urls = []
        for anchor in anchors:
            href = anchor.get("href")
            if href and href.startswith("http"):
                urls.append(href)
            if len(urls) >= limit:
                break
        return urls

    except requests.RequestException as exc:
        logger.warning("DuckDuckGo search error for %s: %s", query, exc)
        return []


def _fetch_web_text(url: str) -> str:
    try:
        resp = requests.get(url, headers=SEARCH_HEADERS, timeout=8)
        if resp.status_code != 200:
            return ""
        soup = BeautifulSoup(resp.text, "lxml")
        fragments = []
        for tag in soup.select("li, p, h2, h3, h4"):
            text = tag.get_text(" ", strip=True)
            if text:
                fragments.append(text)
        return " ".join(fragments)
    except requests.RequestException:
        return ""


def _fetch_wikipedia_summary(title: str) -> tuple[Optional[str], Optional[str]]:
    slug = quote(title.replace(" ", "_"))
    summary, url = _fetch_summary_for_slug(slug)
    if summary:
        return summary, url

    logger.debug("Primary summary missing for %s, trying search", title)
    alternate = _search_wikipedia_slug(title)
    if not alternate:
        return None, None

    return _fetch_summary_for_slug(alternate)


def _fetch_summary_for_slug(slug: str) -> tuple[Optional[str], Optional[str]]:
    api_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{slug}"
    headers = {"User-Agent": "Booktures Character Extractor"}

    try:
        response = requests.get(api_url, headers=headers, timeout=10)
        if response.status_code != 200:
            logger.debug("Wikipedia summary request failed for slug %s (%s)", slug, response.status_code)
            return None, None
        data = response.json()
        extract = data.get("extract", "")
        page_url = data.get("content_urls", {}).get("desktop", {}).get("page")
        return extract, page_url

    except requests.RequestException as exc:
        logger.warning("Wikipedia fetch failed for slug %s: %s", slug, exc)
        return None, None


def _search_wikipedia_slug(title: str) -> Optional[str]:
    query = quote(title)
    search_url = WIKI_SEARCH_URL.format(query=query)
    try:
        resp = requests.get(search_url, timeout=5)
        if resp.status_code != 200:
            return None
        data = resp.json()
        if len(data) >= 2 and data[1]:
            return quote(data[1][0].replace(" ", "_"))
    except requests.RequestException as exc:
        logger.warning("Wikipedia search failed for %s: %s", title, exc)
    return None


def _merge_character_sets(primary: dict[str, dict], secondary: dict[str, dict]) -> dict[str, dict]:
    merged = {**primary}

    for norm, secondary_entry in secondary.items():
        best_match = None
        best_score = 0

        for existing_norm, entry in merged.items():
            score = fuzz.token_sort_ratio(secondary_entry["name"], entry["name"])
            if score > best_score:
                best_score = score
                best_match = existing_norm

        if best_score >= MATCH_THRESHOLD and best_match:
            entry = merged[best_match]
            entry["mention_count"] += secondary_entry["mention_count"]
            entry["source"] = "ner+web"
            entry["external_url"] = secondary_entry.get("external_url") or entry.get("external_url")
        else:
            merged[norm] = secondary_entry

    return merged


def _build_web_entries(names: list[str], source_url: Optional[str], source: str) -> dict[str, dict]:
    entries: dict[str, dict] = {}
    for name in names:
        normalized = _normalize_name(name)
        if not normalized:
            continue
        entry = entries.setdefault(normalized, {
            "name": name,
            "mention_count": 0,
            "first_page": None,
            "source": source,
            "external_url": source_url
        })
        entry["mention_count"] += 1
    return entries


def _collapse_aliases(characters: dict[str, dict]) -> dict[str, dict]:
    pending = dict(characters)
    collapsed: dict[str, dict] = {}
    while pending:
        norm, entry = max(pending.items(), key=lambda item: item[1]["mention_count"])
        pending.pop(norm, None)
        duplicates = []
        for other_norm, other in list(pending.items()):
            score = fuzz.token_sort_ratio(entry["name"], other["name"])
            if score >= ALIAS_MATCH_SCORE:
                duplicates.append((other_norm, other))
        for other_norm, other in duplicates:
            pending.pop(other_norm, None)
            entry["mention_count"] += other["mention_count"]
            entry["first_page"] = _earliest_page(entry.get("first_page"), other.get("first_page"))
            entry["source"] = (
                "ner+web"
                if entry["source"] in CANONICAL_SOURCES or other["source"] in CANONICAL_SOURCES
                else entry["source"]
            )
            if len(other["name"]) > len(entry["name"]):
                entry["name"] = other["name"]
        collapsed[norm] = entry
    return collapsed


def _earliest_page(a: Optional[int], b: Optional[int]) -> Optional[int]:
    if a is None:
        return b
    if b is None:
        return a
    return min(a, b)


def _filter_merged_characters(characters: dict[str, dict]) -> dict[str, dict]:
    filtered: dict[str, dict] = {}
    for norm, entry in characters.items():
        if not entry["name"] or len(entry["name"]) < 3:
            continue
        words = entry["name"].split()
        if any(word.lower() in IGNORE_TOKENS for word in words):
            continue
        if entry["source"] == "ner" and entry["mention_count"] < MIN_NER_MENTIONS:
            continue
        if entry["mention_count"] < MIN_TOTAL_MENTIONS and entry["source"] not in CANONICAL_SOURCES:
            continue
        filtered[norm] = entry
    return filtered


def _normalize_name(name: str) -> str:
    cleaned = re.sub(r"[^\w\s]", "", name)
    cleaned = re.sub(r"\s+", " ", cleaned)
    stripped = _strip_titles(cleaned)
    return stripped.strip().lower()


def _strip_titles(name: str) -> str:
    tokens = [tok for tok in name.split() if tok.lower() not in TITLE_TOKENS]
    return " ".join(tokens)

