import json
import logging
from pathlib import PurePath
import requests

from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from pydantic import BaseModel

from database import SessionLocal
from models.book import Book
from models.generation_job import GenerationJob
from models.page import Page
from models.page_asset import PageAsset
from services.pdf_service import save_pdf, extract_text_by_page
from services.generation_queue_service import (
    cancel_job,
    enqueue_book_pipeline,
    enqueue_book_images,
    enqueue_page_image,
    pause_job,
    resume_job,
)
from services.image_generation_service import reset_pipeline
from services.settings_service import get_settings, update_settings

router = APIRouter()
logger = logging.getLogger(__name__)


def db_book_exists(book_id: int) -> bool:
    db = SessionLocal()
    try:
        return db.get(Book, book_id) is not None
    finally:
        db.close()


def _page_exists(book_id: int, page_number: int) -> bool:
    db = SessionLocal()
    try:
        return (
            db.query(Page.id)
            .filter(Page.book_id == book_id, Page.page_number == page_number)
            .first()
            is not None
        )
    finally:
        db.close()


def create_book_placeholder(filename: str, source: str) -> Book:
    db = SessionLocal()
    try:
        book_record = Book(title=filename, total_pages=0, source=source)
        db.add(book_record)
        db.commit()
        db.refresh(book_record)
        return book_record
    finally:
        db.close()


def _extract_page_number_from_job(job: GenerationJob, page_lookup: dict[int, Page]) -> int | None:
    page = page_lookup.get(job.page_id) if job.page_id is not None else None
    if page is not None:
        return page.page_number

    payload = getattr(job, "payload", None)
    if not payload:
        return None

    try:
        parsed = json.loads(payload)
    except Exception:
        return None

    page_number = parsed.get("page_number") if isinstance(parsed, dict) else None
    return int(page_number) if page_number is not None else None


def _read_payload(payload: str | None) -> dict:
    if not payload:
        return {}
    try:
        parsed = json.loads(payload)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _build_image_url(image_path: str | None, cache_key=None) -> str | None:
    if not image_path:
        return None
    normalized = PurePath(image_path).as_posix()
    marker = "storage/images/"
    marker_index = normalized.find(marker)
    if marker_index == -1:
        return None
    relative_path = normalized[marker_index + len(marker):]
    url = f"/storage/images/{relative_path}"
    if cache_key:
        if hasattr(cache_key, "timestamp"):
            cache_key = int(cache_key.timestamp())
        cache_value = str(cache_key).replace(":", "").replace(" ", "T")
        url = f"{url}?t={cache_value}"
    return url


def _serialize_book(
    book: Book,
    pages: list[Page],
    assets_by_page_id: dict[int, PageAsset],
    jobs: list[GenerationJob],
) -> dict:
    processed_pages = sum(
        1
        for page in pages
        if assets_by_page_id.get(page.id) is not None
        and assets_by_page_id[page.id].image_status == "generated"
        and assets_by_page_id[page.id].image_path
    )
    failed_pages = sum(
        1
        for page in pages
        if assets_by_page_id.get(page.id) is not None
        and (
            assets_by_page_id[page.id].image_status == "failed"
            or bool(assets_by_page_id[page.id].last_error)
        )
    )
    active_jobs = sum(1 for job in jobs if job.status in {"queued", "running"})
    total_pages = int(book.total_pages or len(pages) or 0)

    if total_pages == 0 or active_jobs > 0 and processed_pages == 0 and failed_pages == 0:
        status = "processing"
    elif total_pages > 0 and processed_pages >= total_pages:
        status = "ready"
    elif failed_pages > 0 and processed_pages == 0 and active_jobs == 0:
        status = "failed"
    elif processed_pages > 0 or failed_pages > 0:
        status = "partial"
    else:
        status = "processing"

    return {
        "id": book.id,
        "title": book.title,
        "page_count": total_pages,
        "processed_pages": processed_pages,
        "status": status,
        "source": book.source,
        "created_at": book.created_at.isoformat() if getattr(book, "created_at", None) else None,
        "updated_at": book.updated_at.isoformat() if getattr(book, "updated_at", None) else None,
    }


def _serialize_page(
    page: Page,
    asset: PageAsset | None,
    active_page_jobs: set[int],
) -> dict:
    if asset is not None and asset.image_status == "generated" and asset.image_path:
        status = "image_ready"
    elif asset is not None and (asset.image_status == "failed" or asset.last_error):
        status = "failed"
    elif page.page_number in active_page_jobs:
        status = "image_queued"
    else:
        status = "prompt_ready"

    generated_at = asset.image_generated_at if asset is not None else None
    return {
        "page_number": page.page_number,
        "book_id": page.book_id,
        "text_excerpt": (page.text or "").strip(),
        "prompt": (asset.prompt_override or asset.visual_prompt) if asset is not None else None,
        "image_url": _build_image_url(
            asset.image_path,
            getattr(asset, "image_generated_at", None) or getattr(asset, "updated_at", None),
        ) if asset is not None else None,
        "status": status,
        "last_generated_at": generated_at.isoformat() if generated_at else None,
        "error_message": asset.last_error if asset is not None else None,
    }


def _serialize_job(job: GenerationJob, book_lookup: dict[int, Book], page_lookup: dict[int, Page]) -> dict:
    book = book_lookup.get(job.book_id)
    page_number = _extract_page_number_from_job(job, page_lookup)
    is_page_job = job.job_type == "page_image"

    return {
        "id": job.id,
        "book_id": job.book_id,
        "book_title": book.title if book is not None else f"Book {job.book_id}",
        "type": "single_page" if is_page_job else "full_book",
        "status": job.status,
        "progress": int(round(float(job.progress or 0.0) * 100)),
        "started_at": (job.started_at or job.created_at).isoformat() if (job.started_at or job.created_at) else None,
        "updated_at": (job.updated_at or job.created_at).isoformat() if (job.updated_at or job.created_at) else None,
        "error_message": job.last_error,
        "page_number": page_number,
        "payload": _read_payload(job.payload),
        "result": _read_payload(job.result),
    }


def finalize_book_pages(book_id: int, pdf_path: str):
    logger.info("Starting page extraction for book %s", book_id)
    pages = extract_text_by_page(pdf_path)
    db = SessionLocal()
    try:
        book_record = db.get(Book, book_id)
        if book_record is None:
            logger.error("Book %s missing when persisting pages", book_id)
            return

        for page_data in pages:
            page_record = Page(
                book_id=book_id,
                page_number=page_data["page_number"],
                text=page_data["text"],
            )
            db.add(page_record)

        book_record.total_pages = len(pages)
        db.commit()
        logger.info("Persisted %s pages for book %s", len(pages), book_id)

    except Exception:
        db.rollback()
        logger.exception("Failed to persist pages for book %s", book_id)
        raise

    finally:
        db.close()

    logger.info("Queueing book pipeline for book %s", book_id)
    try:
        enqueue_book_pipeline(book_id)
    except Exception:
        logger.exception("Book pipeline enqueue failed for book %s", book_id)


@router.get("/health")
def health_check():
    return {"message": "Backend is healthy"}


@router.get("/books")
def list_books():
    db = SessionLocal()
    try:
        books = db.query(Book).order_by(Book.id.desc()).all()
        if not books:
            return []

        book_ids = [book.id for book in books]
        pages = db.query(Page).filter(Page.book_id.in_(book_ids)).all()
        assets = db.query(PageAsset).filter(PageAsset.book_id.in_(book_ids)).all()
        jobs = db.query(GenerationJob).filter(GenerationJob.book_id.in_(book_ids)).all()

        pages_by_book_id: dict[int, list[Page]] = {}
        for page in pages:
            pages_by_book_id.setdefault(page.book_id, []).append(page)

        assets_by_page_id = {asset.page_id: asset for asset in assets}
        jobs_by_book_id: dict[int, list[GenerationJob]] = {}
        for job in jobs:
            jobs_by_book_id.setdefault(job.book_id, []).append(job)

        return [
            _serialize_book(
                book=book,
                pages=pages_by_book_id.get(book.id, []),
                assets_by_page_id=assets_by_page_id,
                jobs=jobs_by_book_id.get(book.id, []),
            )
            for book in books
        ]
    finally:
        db.close()


@router.get("/books/{book_id}")
def get_book(book_id: int):
    db = SessionLocal()
    try:
        book = db.get(Book, book_id)
        if book is None:
            raise HTTPException(status_code=404, detail="Book not found")

        pages = db.query(Page).filter(Page.book_id == book_id).all()
        assets = db.query(PageAsset).filter(PageAsset.book_id == book_id).all()
        jobs = db.query(GenerationJob).filter(GenerationJob.book_id == book_id).all()
        assets_by_page_id = {asset.page_id: asset for asset in assets}

        return _serialize_book(book=book, pages=pages, assets_by_page_id=assets_by_page_id, jobs=jobs)
    finally:
        db.close()


@router.get("/books/{book_id}/pages")
def list_book_pages(book_id: int):
    db = SessionLocal()
    try:
        book = db.get(Book, book_id)
        if book is None:
            raise HTTPException(status_code=404, detail="Book not found")

        pages = (
            db.query(Page)
            .filter(Page.book_id == book_id)
            .order_by(Page.page_number.asc())
            .all()
        )
        page_ids = [page.id for page in pages]
        assets = (
            db.query(PageAsset)
            .filter(PageAsset.page_id.in_(page_ids))
            .all()
            if page_ids
            else []
        )
        jobs = (
            db.query(GenerationJob)
            .filter(GenerationJob.book_id == book_id, GenerationJob.status.in_(("queued", "running", "paused")))
            .all()
        )

        page_lookup = {page.id: page for page in pages}
        active_page_jobs = {
            page_number
            for job in jobs
            for page_number in [_extract_page_number_from_job(job, page_lookup)]
            if page_number is not None
        }
        assets_by_page_id = {asset.page_id: asset for asset in assets}

        return [
            _serialize_page(page=page, asset=assets_by_page_id.get(page.id), active_page_jobs=active_page_jobs)
            for page in pages
        ]
    finally:
        db.close()


@router.post("/upload-pdf")
async def upload_pdf(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    try:
        file_bytes = await file.read()
        pdf_path = save_pdf(file_bytes, file.filename)
        book_record = create_book_placeholder(file.filename, source="local")
        background_tasks.add_task(finalize_book_pages, book_record.id, pdf_path)

        return {
            "source": "local",
            "filename": file.filename,
            "status": "processing",
            "book_id": book_record.id,
            "total_pages": None,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class PageImageRequest(BaseModel):
    style_preset: str = "storybook"
    force_prompt_refresh: bool = False
    force_regenerate: bool = False


class BookImagesRequest(BaseModel):
    style_preset: str = "storybook"
    force_prompt_refresh: bool = False
    force_regenerate: bool = False


class SettingsPayload(BaseModel):
    ollama_url: str
    model_name: str
    timeout: int
    image_model: str
    image_width: int
    image_height: int
    image_steps: int
    image_guidance: float


class PromptOverridePayload(BaseModel):
    prompt_override: str | None = None


@router.get("/settings")
def read_settings():
    return get_settings()


@router.put("/settings")
def write_settings(body: SettingsPayload):
    if body.timeout < 10 or body.timeout > 600:
        raise HTTPException(status_code=400, detail="Timeout must be between 10 and 600 seconds")
    if body.image_width < 256 or body.image_width > 2048:
        raise HTTPException(status_code=400, detail="Image width must be between 256 and 2048")
    if body.image_height < 256 or body.image_height > 2048:
        raise HTTPException(status_code=400, detail="Image height must be between 256 and 2048")
    if body.image_steps < 1 or body.image_steps > 100:
        raise HTTPException(status_code=400, detail="Image steps must be between 1 and 100")
    if body.image_guidance < 0 or body.image_guidance > 20:
        raise HTTPException(status_code=400, detail="Image guidance must be between 0 and 20")

    saved = update_settings(body.model_dump())
    reset_pipeline()
    return saved


@router.post("/books/{book_id}/pages/{page_number}/generate-image")
def queue_page_image(book_id: int, page_number: int, body: PageImageRequest):
    if not _page_exists(book_id, page_number):
        raise HTTPException(status_code=404, detail="Page not found")
    job_id = enqueue_page_image(
        book_id=book_id,
        page_number=page_number,
        style_preset=body.style_preset,
        force_prompt_refresh=body.force_prompt_refresh,
        force_regenerate=body.force_regenerate,
    )
    return {"status": "queued", "job_id": job_id, "book_id": book_id, "page_number": page_number}


@router.post("/books/{book_id}/generate-images")
def queue_book_images(book_id: int, body: BookImagesRequest):
    if not db_book_exists(book_id):
        raise HTTPException(status_code=404, detail="Book not found")
    job_id = enqueue_book_images(
        book_id=book_id,
        style_preset=body.style_preset,
        force_prompt_refresh=body.force_prompt_refresh,
        force_regenerate=body.force_regenerate,
    )
    return {"status": "queued", "job_id": job_id, "book_id": book_id}


@router.get("/books/{book_id}/pages/{page_number}/asset")
def get_page_asset(book_id: int, page_number: int):
    db = SessionLocal()
    try:
        page = (
            db.query(Page)
            .filter(Page.book_id == book_id, Page.page_number == page_number)
            .first()
        )
        if page is None:
            raise HTTPException(status_code=404, detail="Page not found")
        asset = db.query(PageAsset).filter(PageAsset.page_id == page.id).one_or_none()
        if asset is None:
            return {
                "book_id": book_id,
                "page_number": page_number,
                "status": "missing",
                "scene_summary": None,
                "summary_short": None,
                "continuity_summary": None,
                "visual_prompt": None,
                "prompt_override": None,
                "effective_prompt": None,
                "last_used_prompt": None,
                "prompt_source": "auto",
                "negative_prompt": None,
                "style_preset": None,
                "image_path": None,
                "image_url": None,
                "image_status": "pending",
                "last_error": None,
            }
        return {
            "book_id": book_id,
            "page_number": page_number,
            "status": "ok",
            "scene_summary": asset.scene_summary,
            "summary_short": getattr(asset, "summary_short", None),
            "continuity_summary": getattr(asset, "continuity_summary", None),
            "visual_prompt": asset.visual_prompt,
            "prompt_override": asset.prompt_override,
            "effective_prompt": asset.prompt_override or asset.visual_prompt,
            "last_used_prompt": asset.last_used_prompt,
            "prompt_source": "custom" if asset.prompt_override else "auto",
            "negative_prompt": asset.negative_prompt,
            "style_preset": asset.style_preset,
            "image_path": asset.image_path,
            "image_url": _build_image_url(
                asset.image_path,
                getattr(asset, "image_generated_at", None) or getattr(asset, "updated_at", None),
            ),
            "image_status": asset.image_status,
            "last_error": asset.last_error,
        }
    finally:
        db.close()


@router.put("/books/{book_id}/pages/{page_number}/prompt")
def update_page_prompt(book_id: int, page_number: int, body: PromptOverridePayload):
    db = SessionLocal()
    try:
        page = (
            db.query(Page)
            .filter(Page.book_id == book_id, Page.page_number == page_number)
            .first()
        )
        if page is None:
            raise HTTPException(status_code=404, detail="Page not found")

        asset = db.query(PageAsset).filter(PageAsset.page_id == page.id).one_or_none()
        if asset is None:
            asset = PageAsset(book_id=book_id, page_id=page.id, page_number=page_number)

        prompt_override = (body.prompt_override or "").strip()
        asset.prompt_override = prompt_override or None
        db.add(asset)
        db.commit()
        db.refresh(asset)

        return {
            "book_id": book_id,
            "page_number": page_number,
            "status": "ok",
            "scene_summary": asset.scene_summary,
            "summary_short": getattr(asset, "summary_short", None),
            "continuity_summary": getattr(asset, "continuity_summary", None),
            "visual_prompt": asset.visual_prompt,
            "prompt_override": asset.prompt_override,
            "effective_prompt": asset.prompt_override or asset.visual_prompt,
            "last_used_prompt": asset.last_used_prompt,
            "prompt_source": "custom" if asset.prompt_override else "auto",
            "negative_prompt": asset.negative_prompt,
            "style_preset": asset.style_preset,
            "image_path": asset.image_path,
            "image_url": _build_image_url(
                asset.image_path,
                getattr(asset, "image_generated_at", None) or getattr(asset, "updated_at", None),
            ),
            "image_status": asset.image_status,
            "last_error": asset.last_error,
        }
    finally:
        db.close()


@router.get("/jobs")
def list_generation_jobs():
    db = SessionLocal()
    try:
        jobs = db.query(GenerationJob).order_by(GenerationJob.updated_at.desc(), GenerationJob.id.desc()).all()
        if not jobs:
            return []

        book_ids = sorted({job.book_id for job in jobs})
        page_ids = sorted({job.page_id for job in jobs if job.page_id is not None})
        books = db.query(Book).filter(Book.id.in_(book_ids)).all() if book_ids else []
        pages = db.query(Page).filter(Page.id.in_(page_ids)).all() if page_ids else []

        book_lookup = {book.id: book for book in books}
        page_lookup = {page.id: page for page in pages}

        return [_serialize_job(job, book_lookup, page_lookup) for job in jobs]
    finally:
        db.close()


@router.get("/jobs/{job_id}")
def get_generation_job(job_id: int):
    db = SessionLocal()
    try:
        job = db.get(GenerationJob, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")

        book = db.get(Book, job.book_id)
        page = db.get(Page, job.page_id) if job.page_id is not None else None
        return _serialize_job(
            job=job,
            book_lookup={book.id: book} if book is not None else {},
            page_lookup={page.id: page} if page is not None else {},
        )
    finally:
        db.close()


@router.post("/jobs/{job_id}/pause")
def pause_generation_job(job_id: int):
    try:
        job = pause_job(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/jobs/{job_id}/resume")
def resume_generation_job(job_id: int):
    try:
        job = resume_job(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/jobs/{job_id}/cancel")
def cancel_generation_job(job_id: int):
    try:
        job = cancel_job(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job
