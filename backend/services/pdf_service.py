import os
import uuid
import pdfplumber
from collections import Counter
import logging
import re
from typing import Any

PDF_STORAGE_PATH = "storage/pdfs"
logger = logging.getLogger(__name__)

ROMAN_NUMERAL_PATTERN = re.compile(r"^[ivxlcdm]+$", re.IGNORECASE)
PAGE_COUNTER_PATTERN = re.compile(
    r"^(page|pg)\.?\s*[\divxlcdm]+$|^[\divxlcdm]+$",
    re.IGNORECASE,
)
SECTION_HEADING_PATTERN = re.compile(
    r"^(chapter|chap|part|book|section|prologue|epilogue)\b[\w\s:.-]*$",
    re.IGNORECASE,
)
MAX_HEADER_FOOTER_LINE_LENGTH = 100
MIN_REPEAT_COUNT = 3
MIN_REPEAT_RATIO = 0.25
OCR_MIN_LENGTH_THRESHOLD = 160
OCR_MIN_TOKEN_THRESHOLD = 30
OCR_RENDER_RESOLUTION = 300
OCR_TESSERACT_CONFIG = "--oem 3 --psm 6"
LIGATURE_REPLACEMENTS = {
    "\ufb00": "ff",
    "\ufb01": "fi",
    "\ufb02": "fl",
    "\ufb03": "ffi",
    "\ufb04": "ffl",
    "\ufb05": "ft",
    "\ufb06": "st",
}

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
    pypdf_pages: list[Any] = []

    try:
        from pypdf import PdfReader  # type: ignore

        reader = PdfReader(pdf_path)
        pypdf_pages = list(reader.pages)
    except Exception as exc:
        logger.debug("pypdf unavailable for %s: %s", pdf_path, exc)

    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            pypdf_page = pypdf_pages[i] if i < len(pypdf_pages) else None
            raw_text = _extract_page_text(page, pypdf_page=pypdf_page)
            lines = _split_lines(raw_text)

            if lines:
                for line in lines[:2]:
                    header_counts[_normalize_running_line(line)] += 1
                for line in lines[-2:]:
                    footer_counts[_normalize_running_line(line)] += 1

            pages.append({
                "page_number": i + 1,
                "lines": lines,
                "raw_text": raw_text
            })

    header_candidates = _select_header_footer_candidates(
        header_counts,
        len(pages),
    )
    footer_candidates = _select_header_footer_candidates(
        footer_counts,
        len(pages),
    )

    cleaned_pages = []
    for page in pages:
        filtered_lines = _filter_page_lines(
            page["lines"],
            header_candidates,
            footer_candidates
        )

        if not filtered_lines and page["lines"]:
            filtered_lines = page["lines"]

        cleaned_text = (
            _reconstruct_text(filtered_lines)
            if filtered_lines
            else _normalize_text(page["raw_text"])
        )
        cleaned_pages.append({
            "page_number": page["page_number"],
            "text": cleaned_text
        })

    return cleaned_pages


def _extract_page_text(page, pypdf_page=None):
    candidates: list[str] = []

    plumber_layout = page.extract_text(layout=True, x_tolerance=1, y_tolerance=1)
    if plumber_layout:
        candidates.append(plumber_layout)

    plumber_plain = page.extract_text(x_tolerance=1, y_tolerance=1)
    if plumber_plain:
        candidates.append(plumber_plain)

    if pypdf_page is not None:
        try:
            pypdf_text = pypdf_page.extract_text() or ""
            if pypdf_text:
                candidates.append(pypdf_text)
        except Exception as exc:
            logger.debug("pypdf extraction failed for page: %s", exc)

    if not candidates:
        words = page.extract_words(use_text_flow=True)
        candidates.append(" ".join(word["text"] for word in words))

    text = _pick_best_text_candidate(candidates)
    if _should_try_ocr(text):
        ocr_text = _extract_page_text_with_ocr(page)
        if _extraction_score(ocr_text) > _extraction_score(text):
            return ocr_text
    return text


def _pick_best_text_candidate(candidates: list[str]) -> str:
    best_text = ""
    best_score = float("-inf")
    for candidate in candidates:
        normalized = _normalize_text(candidate or "")
        score = _extraction_score(normalized)
        if score > best_score:
            best_score = score
            best_text = normalized
    return best_text


def _extract_page_text_with_ocr(page) -> str:
    try:
        import pytesseract  # type: ignore
    except Exception:
        return ""

    try:
        page_image = page.to_image(resolution=OCR_RENDER_RESOLUTION).original
    except Exception as exc:
        logger.debug("OCR render failed for page: %s", exc)
        return ""

    try:
        text = pytesseract.image_to_string(page_image, config=OCR_TESSERACT_CONFIG)
        return text or ""
    except Exception as exc:
        logger.debug("OCR text extraction failed for page: %s", exc)
        return ""


def _should_try_ocr(text: str) -> bool:
    normalized = _normalize_text(text)
    if not normalized:
        return True

    tokens = normalized.split()
    if len(normalized) < OCR_MIN_LENGTH_THRESHOLD:
        return True
    if len(tokens) < OCR_MIN_TOKEN_THRESHOLD:
        return True

    alpha_tokens = sum(1 for token in tokens if re.search(r"[A-Za-z]{2,}", token))
    return (alpha_tokens / max(len(tokens), 1)) < 0.45


def _extraction_score(text: str) -> float:
    if not text:
        return 0.0
    normalized = _normalize_text(text)
    if not normalized:
        return 0.0

    tokens = normalized.split()
    alpha_tokens = sum(1 for token in tokens if re.search(r"[A-Za-z]{2,}", token))
    words = re.findall(r"[A-Za-z]{2,}", normalized)
    bad_chars = len(re.findall(r"[^A-Za-z0-9\s.,;:!?'\-\"()\[\]]", normalized))
    bad_ratio = bad_chars / max(len(normalized), 1)
    single_letter_ratio = sum(1 for token in tokens if len(token) == 1 and token.isalpha()) / max(len(tokens), 1)
    weird_spacing_penalty = len(re.findall(r"\b[A-Za-z]\s+[A-Za-z]\b", normalized))
    broken_hyphen_penalty = len(re.findall(r"\w+-\s+\w", normalized))

    return (
        len(words) * 1.0
        + alpha_tokens * 0.5
        + min(len(normalized), 3000) * 0.02
        - bad_ratio * 50
        - single_letter_ratio * 80
        - weird_spacing_penalty * 0.8
        - broken_hyphen_penalty * 0.5
    )


def _split_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _select_header_footer_candidates(counter: Counter, total_pages: int) -> set[str]:
    threshold = max(MIN_REPEAT_COUNT, int(total_pages * MIN_REPEAT_RATIO))
    return {
        line for line, count in counter.items()
        if count >= threshold and _is_likely_running_header_footer(line)
    }


def _normalize_running_line(line: str) -> str:
    normalized = line.lower().strip()
    normalized = re.sub(r"\s+", " ", normalized)
    # Make "page 1" and "page 2" map to the same signature.
    normalized = re.sub(r"\b\d+\b", "#", normalized)
    normalized = re.sub(r"\b[ivxlcdm]+\b", "#", normalized)
    return normalized


def _is_likely_running_header_footer(line: str) -> bool:
    normalized = line.strip()
    if not normalized:
        return False
    if len(normalized) > MAX_HEADER_FOOTER_LINE_LENGTH:
        return False
    if _looks_like_page_marker(normalized):
        return True
    if SECTION_HEADING_PATTERN.match(normalized):
        return True
    words = normalized.split()
    if 1 <= len(words) <= 12 and normalized == normalized.upper():
        return True
    # Likely running headers/footers such as "Book Title | Author Name".
    if 1 <= len(words) <= 10 and re.search(r"[|/:-]", normalized):
        return True
    return False


def _looks_like_page_marker(line: str) -> bool:
    stripped = line.strip().lower()
    if not stripped:
        return False
    if PAGE_COUNTER_PATTERN.fullmatch(stripped):
        return True
    if ROMAN_NUMERAL_PATTERN.fullmatch(stripped):
        return True
    if re.fullmatch(r"-\s*[\divxlcdm]+\s*-", stripped):
        return True
    return False


def _filter_page_lines(lines: list[str], headers: set[str], footers: set[str]) -> list[str]:
    filtered = list(lines)

    while filtered and _normalize_running_line(filtered[0]) in headers:
        filtered.pop(0)
    while filtered and _normalize_running_line(filtered[-1]) in footers:
        filtered.pop()

    cleaned = []
    for index, line in enumerate(filtered):
        if _looks_like_page_marker(line):
            continue
        if index < 2 and _is_likely_running_header_footer(line):
            continue
        if index >= max(0, len(filtered) - 2) and _is_likely_running_header_footer(line):
            continue
        if len(line.split()) <= 1 and line.strip().isdigit():
            continue
        cleaned.append(line)

    return cleaned


def _reconstruct_text(lines: list[str]) -> str:
    if not lines:
        return ""

    merged_lines: list[str] = []
    index = 0
    while index < len(lines):
        current = lines[index].strip()
        if not current:
            index += 1
            continue
        while (
            current.endswith("-")
            and index + 1 < len(lines)
            and lines[index + 1][:1].islower()
        ):
            current = current[:-1] + lines[index + 1].lstrip()
            index += 1
        merged_lines.append(current)
        index += 1

    return _normalize_text(" ".join(merged_lines))


def _normalize_text(text: str) -> str:
    if not text:
        return ""

    cleaned = text.strip()
    for source, target in LIGATURE_REPLACEMENTS.items():
        cleaned = cleaned.replace(source, target)
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"(?<=\w)-\s+(?=\w)", "", cleaned)
    cleaned = re.sub(r"\s+([,.;:!?])", r"\1", cleaned)
    cleaned = re.sub(r"([(\[{])\s+", r"\1", cleaned)
    cleaned = re.sub(r"\s+([)\]}])", r"\1", cleaned)
    cleaned = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", cleaned)

    return cleaned
