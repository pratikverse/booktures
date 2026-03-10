import statistics
from typing import Optional

from database import SessionLocal
from models.page import Page
from models.page_evaluation import PageEvaluation
from services.prompt_service import build_page_visual_prompt

DEFAULT_SAMPLE_SIZE = 25


def evaluate_book_prompts(
    book_id: int,
    sample_size: int = DEFAULT_SAMPLE_SIZE,
    force_refresh: bool = False,
) -> dict:
    db = SessionLocal()
    try:
        pages = (
            db.query(Page)
            .filter(Page.book_id == book_id)
            .order_by(Page.page_number.asc())
            .all()
        )
        if not pages:
            return {
                "book_id": book_id,
                "status": "no_pages",
                "sample_size": 0,
                "avg_prompt_quality": 0.0,
                "avg_character_consistency": 0.0,
                "avg_failure_score": 1.0,
            }

        selected_pages = _sample_pages(pages, sample_size)
        quality_scores = []
        consistency_scores = []
        failure_scores = []

        for page in selected_pages:
            prompt_data = build_page_visual_prompt(
                book_id=book_id,
                page_number=page.page_number,
                force_refresh=force_refresh,
            )
            quality = _score_prompt_quality(prompt_data.get("visual_prompt", ""))
            consistency = _score_character_consistency(prompt_data.get("characters", []))
            failure = _score_failure(prompt_data)
            notes = _build_notes(prompt_data)

            db.add(
                PageEvaluation(
                    book_id=book_id,
                    page_id=page.id,
                    page_number=page.page_number,
                    prompt_quality=quality,
                    character_consistency=consistency,
                    failure_score=failure,
                    notes=notes,
                )
            )
            quality_scores.append(quality)
            consistency_scores.append(consistency)
            failure_scores.append(failure)

        db.commit()

        return {
            "book_id": book_id,
            "status": "ok",
            "sample_size": len(selected_pages),
            "avg_prompt_quality": _avg(quality_scores),
            "avg_character_consistency": _avg(consistency_scores),
            "avg_failure_score": _avg(failure_scores),
        }
    finally:
        db.close()


def _sample_pages(pages: list[Page], sample_size: int) -> list[Page]:
    if sample_size <= 0:
        return []
    if len(pages) <= sample_size:
        return pages
    step = max(1, len(pages) // sample_size)
    sampled = pages[::step][:sample_size]
    if pages[-1] not in sampled:
        sampled[-1] = pages[-1]
    return sampled


def _score_prompt_quality(prompt: str) -> float:
    text = (prompt or "").strip()
    if not text:
        return 0.0
    words = text.split()
    if len(words) < 15:
        return 0.35
    if len(words) > 160:
        return 0.55
    has_scene = 1.0 if "scene:" in text.lower() else 0.65
    has_character = 1.0 if "characters:" in text.lower() else 0.7
    return min(1.0, 0.45 + (0.25 * has_scene) + (0.3 * has_character))


def _score_character_consistency(characters: list[dict]) -> float:
    if not characters:
        return 0.4
    confidences = [float(c.get("confidence", 0.0)) for c in characters]
    profiles = [c.get("visual_profile", "") for c in characters]
    with_profile_ratio = sum(1 for p in profiles if p) / max(len(profiles), 1)
    return min(1.0, (_avg(confidences) * 0.7) + (with_profile_ratio * 0.3))


def _score_failure(prompt_data: dict) -> float:
    if prompt_data.get("status") != "ok":
        return 1.0
    prompt = prompt_data.get("visual_prompt", "").strip()
    if not prompt:
        return 1.0
    if len(prompt) < 20:
        return 0.7
    return 0.0


def _build_notes(prompt_data: dict) -> Optional[str]:
    if prompt_data.get("status") != "ok":
        return f"status={prompt_data.get('status')}"
    notes = []
    if not prompt_data.get("characters"):
        notes.append("no_characters")
    if not prompt_data.get("scene_summary"):
        notes.append("no_scene_summary")
    return ", ".join(notes) if notes else None


def _avg(values: list[float]) -> float:
    if not values:
        return 0.0
    return float(round(statistics.fmean(values), 4))
