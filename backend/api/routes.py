from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel
import requests

from services.pdf_service import save_pdf, extract_text_by_page

router = APIRouter()


# -------------------------
# Health Check
# -------------------------
@router.get("/health")
def health_check():
    return {"message": "Backend is healthy"}


# -------------------------
# Local PDF Upload
# -------------------------
@router.post("/upload-pdf")
async def upload_pdf(file: UploadFile = File(...)):
    try:
        file_bytes = await file.read()

        pdf_path = save_pdf(file_bytes, file.filename)
        pages = extract_text_by_page(pdf_path)

        return {
            "source": "local",
            "filename": file.filename,
            "total_pages": len(pages)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Local uploads and web imports have different input formats, but both are normalized into a single file-based pipeline to keep downstream processing consistent.

# -------------------------
# Web PDF Import
# -------------------------
class PDFUrlRequest(BaseModel):
    url: str


@router.post("/import-pdf")
def import_pdf_from_url(data: PDFUrlRequest):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Booktures PDF Importer)"
        }

        response = requests.get(
            data.url,
            headers=headers,
            stream=True,
            timeout=20
        )

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
        pages = extract_text_by_page(pdf_path)

        return {
            "source": "web",
            "filename": filename,
            "total_pages": len(pages)
        }

    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=400, detail=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
