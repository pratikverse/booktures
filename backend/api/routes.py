import logging
import requests

from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from pydantic import BaseModel

from database import SessionLocal
from models.book import Book
from models.page import Page
from services.pdf_service import save_pdf, extract_text_by_page
from services.character_service import build_character_registry

router = APIRouter()
logger = logging.getLogger(__name__)


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

    logger.info("Scheduling character registry for book %s", book_id)
    try:
        build_character_registry(book_id)
    except Exception:
        logger.exception("Character enrichment failed for book %s", book_id)


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


@router.get("/books/{book_id}/pages/{page_number}")
def get_page(book_id: int, page_number: int):
    db = SessionLocal()
    try:
        page = (
            db.query(Page)
            .filter(Page.book_id == book_id, Page.page_number == page_number)
            .first()
        )

        if not page:
            raise HTTPException(status_code=404, detail="Page not found")

        return {
            "book_id": book_id,
            "page_number": page.page_number,
            "text": page.text
        }

    finally:
        db.close()
