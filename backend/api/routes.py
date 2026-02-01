from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from pydantic import BaseModel, HttpUrl
import requests

#importing save and extract functions from pdf_service.py
from services.pdf_service import save_pdf, extract_text_by_page

#sqlalchemy imports
from sqlalchemy.orm import Session
from database import get_db
from models.book import Book
from models.page import Page

router = APIRouter()

#local pdf upload endpoint
@router.post("/upload-pdf")
async def upload_pdf(file: UploadFile = File(...), db: Session = Depends(get_db)):
    try:
        #tries to pull the raw bytes into memory
        file_bytes = await file.read()

        pdf_path = save_pdf(file_bytes, file.filename)
        pages = extract_text_by_page(pdf_path)


        # create book

        book = Book(
            title=file.filename,
            total_pages=len(pages),
            source="local"
        )
        db.add(book)
        db.commit()
        db.refresh(book)

        # create pages
        for page in pages:
            db_page = Page(
                book_id=book.id,
                page_number = page["page_number"],
                text = page["text"],
            )
            db.add(db_page)
        db.commit()

        return {
            "book_id": book.id,
            "title": book.title,
            "total_pages": book.total_pages,
            "source": book.source
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Local uploads and web imports have different input formats, but both are normalized into a single file-based pipeline to keep downstream processing consistent.

# -------------------------
# Web PDF Import
# -------------------------

#making url strictly string so that we can validate it
class PDFUrlRequest(BaseModel):
    url: HttpUrl


@router.post("/import-pdf")
def import_pdf_from_url(data: PDFUrlRequest, db: Session = Depends(get_db)):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Booktures PDF Importer)"
        }

        response = requests.get(
            str(data.url),

            headers=headers,
            stream=True,
            timeout=60
        )

        if response.status_code != 200:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to download PDF, status code {response.status_code}"
            )

        content_type = response.headers.get("Content-Type", "")
        #checking if the content type contains pdf
        is_pdf_content_type = "pdf" in content_type.lower()
        #strictly checks for pdf magic bytes

        # magic bytes -  first 5 bytes of a  file, acts as a a signature to identify what kind of file it is as anyone can change the extension of a file but not the magic bytes
        is_pdf_magic_bytes = file_content[:5] == b"%PDF-"


        if not is_pdf_content_type and not is_pdf_magic_bytes:
            raise HTTPException(
                status_code=400,
                detail="URL does not point to a PDF file"
            )

        parsed_url = urlparse(str(data.url))
        filename = os.path.basename(parsed_url.path) or "imported.pdf"
        

        pdf_path = save_pdf(response.content, filename)
        pages = extract_text_by_page(pdf_path)

        #same logic as local upload to save book and pages to db
        book = Book(
            title=filename,
            total_pages=len(pages),
            source="web"
        )
        db.add(book)
        db.commit()
        db.refresh(book)

        # create pages
        for page in pages:
            db_page = Page(
                book_id=book.id,
                page_number = page["page_number"],
                text = page["text"],
            )
            db.add(db_page)
        db.commit()

        return {
            "book_id": book.id,
            "title": book.title,
            "total_pages": book.total_pages,
            "source": book.source
        }

    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=400, detail=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/books/{book_id}/pages/{page_number}")
def get_page(
    book_id: int,
    page_number: int,
    db: Session = Depends(get_db)
):
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
