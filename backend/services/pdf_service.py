import os
import uuid
import logging
import pdfplumber
from pathlib import Path
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

# Configuration
PDF_STORAGE_PATH = os.getenv("PDF_STORAGE_PATH", "storage/pdfs")
MAX_FILE_SIZE = int(os.getenv("MAX_PDF_SIZE_MB", 200)) * 1024 * 1024  # 200MB default
MAX_PAGES = int(os.getenv("MAX_PDF_PAGES", 500))  # Max pages per PDF
ALLOWED_EXTENSIONS = {".pdf"}

def save_pdf(file_bytes: bytes, filename: str) -> Optional[str]:
    """
    Save a PDF file with validation
    
    Args:
        file_bytes: Raw file bytes
        filename: Original filename
        
    Returns:
        File path if successful, None if failed
        
    Raises:
        ValueError: If file validation fails
    """
    try:
        # Validate file size
        if len(file_bytes) > MAX_FILE_SIZE:
            raise ValueError(f"File size exceeds {MAX_FILE_SIZE / 1024 / 1024:.0f}MB limit")
        
        # Validate file extension
        file_ext = Path(filename).suffix.lower()
        if file_ext not in ALLOWED_EXTENSIONS:
            raise ValueError(f"Invalid file type. Only {ALLOWED_EXTENSIONS} allowed")
        
        # Validate it's actually a PDF
        if not file_bytes.startswith(b"%PDF"):
            raise ValueError("File is not a valid PDF")
        
        # Create storage directory
        os.makedirs(PDF_STORAGE_PATH, exist_ok=True)
        
        # Generate unique filename
        unique_name = f"{uuid.uuid4()}_{filename}"
        file_path = os.path.join(PDF_STORAGE_PATH, unique_name)
        
        # Save file
        with open(file_path, "wb") as f:
            f.write(file_bytes)
        
        logger.info(f"PDF saved successfully: {file_path}")
        return file_path
        
    except ValueError as e:
        logger.warning(f"PDF validation failed: {e}")
        raise
    except IOError as e:
        logger.error(f"Failed to save PDF: {e}")
        raise

def extract_text_by_page(pdf_path: str) -> Optional[List[Dict]]:
    """
    Extract text from each page of a PDF
    
    Args:
        pdf_path: Path to the PDF file
        
    Returns:
        List of dicts with page_number and text, or None if failed
    """
    try:
        # Validate file exists
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF not found: {pdf_path}")
        
        pages = []
        
        with pdfplumber.open(pdf_path) as pdf:
            # Check page count
            if len(pdf.pages) > MAX_PAGES:
                raise ValueError(f"PDF exceeds maximum {MAX_PAGES} pages")
            
            logger.info(f"Extracting text from {len(pdf.pages)} pages")
            
            for i, page in enumerate(pdf.pages):
                try:
                    # Extract text
                    text = page.extract_text() or ""
                    
                    # Optional: Extract tables if needed
                    tables = page.extract_tables() or []
                    
                    pages.append({
                        "page_number": i + 1,
                        "text": text.strip(),
                        "has_tables": len(tables) > 0
                    })
                except Exception as e:
                    logger.warning(f"Failed to extract text from page {i + 1}: {e}")
                    pages.append({
                        "page_number": i + 1,
                        "text": "",
                        "error": str(e)
                    })
        
        logger.info(f"Successfully extracted text from {pdf_path}")
        return pages
        
    except FileNotFoundError as e:
        logger.error(f"File error: {e}")
        raise
    except ValueError as e:
        logger.error(f"Validation error: {e}")
        raise
    except Exception as e:
        logger.error(f"Failed to extract text from PDF: {e}")
        raise

def delete_pdf(file_path: str) -> bool:
    """
    Delete a PDF file safely
    
    Args:
        file_path: Path to the PDF file
        
    Returns:
        True if deleted, False otherwise
    """
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"PDF deleted: {file_path}")
            return True
        return False
    except Exception as e:
        logger.error(f"Failed to delete PDF: {e}")
        return False

def get_pdf_info(pdf_path: str) -> Optional[Dict]:
    """
    Get basic info about a PDF
    
    Args:
        pdf_path: Path to the PDF file
        
    Returns:
        Dictionary with metadata
    """
    try:
        with pdfplumber.open(pdf_path) as pdf:
            return {
                "page_count": len(pdf.pages),
                "metadata": pdf.metadata
            }
    except Exception as e:
        logger.error(f"Failed to get PDF info: {e}")
        return None
