import logging
import requests

from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from pydantic import BaseModel

from database import SessionLocal
from models.book import Book
from models.page import Page
from models.page_asset import PageAsset
from services.pdf_service import save_pdf, extract_text_by_page
from services.generation_queue_service import (
    enqueue_book_pipeline,
    enqueue_page_image,
    get_job,
)

router = APIRouter()
logger = logging.getLogger(__name__)


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


class PDFUrlRequest(BaseModel):
    url: str


class PageImageRequest(BaseModel):
    style_preset: str = "storybook"
    force_prompt_refresh: bool = False
    force_regenerate: bool = False


@router.post("/import-pdf")
def import_pdf_from_url(
    data: PDFUrlRequest,
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Booktures PDF Importer)"}
        response = requests.get(data.url, headers=headers, timeout=20)

        if response.status_code != 200:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to download PDF, status code {response.status_code}"
            )

        content_type = response.headers.get("Content-Type", "")
        if "pdf" not in content_type.lower():
            raise HTTPException(
                status_code=400,
                detail="URL does not point to a PDF file"
            )

        filename = data.url.split("/")[-1] or "imported.pdf"
        pdf_path = save_pdf(response.content, filename)
        book_record = create_book_placeholder(filename, source="web")
        background_tasks.add_task(finalize_book_pages, book_record.id, pdf_path)

        return {
            "source": "web",
            "filename": filename,
            "status": "processing",
            "book_id": book_record.id,
            "total_pages": None,
        }

    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=400, detail=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
                "visual_prompt": None,
                "negative_prompt": None,
                "style_preset": None,
                "image_path": None,
                "image_status": "pending",
                "last_error": None,
            }
        return {
            "book_id": book_id,
            "page_number": page_number,
            "status": "ok",
            "scene_summary": asset.scene_summary,
            "visual_prompt": asset.visual_prompt,
            "negative_prompt": asset.negative_prompt,
            "style_preset": asset.style_preset,
            "image_path": asset.image_path,
            "image_status": asset.image_status,
            "last_error": asset.last_error,
        }
    finally:
        db.close()


@router.get("/jobs/{job_id}")
def get_generation_job(job_id: int):
    data = get_job(job_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return data
