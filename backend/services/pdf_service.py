import os
import uuid
import pdfplumber
from collections import Counter
import re

PDF_STORAGE_PATH = "storage/pdfs"

PREFACE_KEYWORDS = {"preface", "introduction", "acknowledgments", "contents"}
CHAPTER_PATTERN = re.compile(r"^(chapter|chap)\b", re.IGNORECASE)
PAGE_COUNTER_PATTERN = re.compile(r"^(page|pg)\b|\bpage\s+\d+$", re.IGNORECASE)

def save_pdf(file_bytes: bytes, filename: str) -> str:
    os.makedirs(PDF_STORAGE_PATH, exist_ok=True)

    unique_name = f"{uuid.uuid4()}_{filename}"
    file_path = os.path.join(PDF_STORAGE_PATH, unique_name)

    with open(file_path, "wb") as f:
        f.write(file_bytes)

    return file_path


def extract_text_by_page(pdf_path: str):
    pages = []
    header_counts = Counter()
    footer_counts = Counter()

    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            raw_text = _extract_page_text(page)
            lines = _split_lines(raw_text)

            if lines:
                header_counts[lines[0]] += 1
                footer_counts[lines[-1]] += 1

            pages.append({
                "page_number": i + 1,
                "lines": lines,
                "raw_text": raw_text
            })

    header_candidates = _select_header_footer_candidates(header_counts, len(pages))
    footer_candidates = _select_header_footer_candidates(footer_counts, len(pages))

    cleaned_pages = []
    for page in pages:
        filtered_lines = _filter_page_lines(
            page["lines"],
            header_candidates,
            footer_candidates
        )

        if not filtered_lines and page["lines"]:
            filtered_lines = page["lines"]

        cleaned_text = _normalize_text("\n".join(filtered_lines)) if filtered_lines else _normalize_text(page["raw_text"])
        cleaned_pages.append({
            "page_number": page["page_number"],
            "text": cleaned_text
        })

    return cleaned_pages


def _extract_page_text(page):
    # Try to preserve layout and spacing by using the layout-aware extractor first.
    text = page.extract_text(layout=True, x_tolerance=1, y_tolerance=1)
    if not text:
        text = page.extract_text(x_tolerance=1, y_tolerance=1)

    if not text:
        words = page.extract_words(use_text_flow=True)
        text = " ".join(word["text"] for word in words)

    return text or ""


def _split_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _select_header_footer_candidates(counter: Counter, total_pages: int) -> set[str]:
    threshold = max(2, total_pages // 10)
    return {
        line for line, count in counter.items()
        if count >= threshold and _is_noise_line(line)
    }


def _is_noise_line(line: str) -> bool:
    normalized = line.lower().strip()
    if len(normalized) > 80:
        return False
    return bool(CHAPTER_PATTERN.match(normalized) or PAGE_COUNTER_PATTERN.match(normalized))


def _looks_like_page_marker(line: str) -> bool:
    stripped = line.strip().lower()
    if not stripped:
        return False
    if PAGE_COUNTER_PATTERN.match(stripped):
        return True
    if stripped.isdigit():
        return True
    if re.fullmatch(r"[ivxlcdm]+", stripped):
        return True
    return False


def _filter_page_lines(lines: list[str], headers: set[str], footers: set[str]) -> list[str]:
    filtered = list(lines)

    while filtered and filtered[0] in headers:
        filtered.pop(0)
    while filtered and filtered[-1] in footers:
        filtered.pop()

    cleaned = []
    for line in filtered:
        lower = line.lower()
        if (
            _looks_like_page_marker(lower)
            or CHAPTER_PATTERN.match(lower)
            or any(keyword in lower for keyword in PREFACE_KEYWORDS)
        ):
            continue
        if len(line.split()) <= 1 and line.isdigit():
            continue
        cleaned.append(line)

    return cleaned


def _normalize_text(text: str) -> str:
    if not text:
        return ""

    cleaned = re.sub(r"\s+", " ", text.strip())
    cleaned = re.sub(r"([.!?])\s+", r"\1\n", cleaned)
    cleaned = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", cleaned)

    return cleaned
