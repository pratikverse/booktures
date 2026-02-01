# responsible for saving pdf files to storage/pdfs (both locally and on server)
# extract text page-by-page

import os

#uuid generates unique identifiers for each pdf 
import uuid

import pdfplumber

PDF_STORAGE_PATH = "storage/pdfs"

def save_pdf(file_bytes: bytes, filename: str) -> str:
    os.makedirs(PDF_STORAGE_PATH, exist_ok=True)

    unique_name = f"{uuid.uuid4()}_{filename}"
    file_path = os.path.join(PDF_STORAGE_PATH, unique_name)

    with open(file_path, "wb") as f:
        f.write(file_bytes)

    return file_path


def extract_text_by_page(pdf_path: str):
    pages = []

    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            pages.append({
                "page_number": i + 1,
                "text": text
            })

    return pages
