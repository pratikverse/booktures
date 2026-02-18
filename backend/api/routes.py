from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, status
from sqlalchemy.orm import Session
from database import SessionLocal
from services.pdf_service import save_pdf, extract_text_by_page, delete_pdf, get_pdf_info
from models.book import Book
from models.page import Page
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

# Define get_db here
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/upload-pdf")
async def upload_pdf(
    file: UploadFile = File(...),
    book_id: int = None,
    title: str = None,
    author: str = None,
    db: Session = Depends(get_db)
):
    """
    Upload a PDF and extract text from all pages
    """
    try:
        # Validate file
        if not file.filename.endswith('.pdf'):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only PDF files are allowed"
            )
        
        logger.info(f"Processing PDF upload: {file.filename}")
        
        # Read file bytes
        file_bytes = await file.read()
        
        # Save PDF to disk
        try:
            pdf_path = save_pdf(file_bytes, file.filename)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e)
            )
        except IOError as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to save PDF file"
            )
        
        # Extract text from pages
        try:
            pages_data = extract_text_by_page(pdf_path)
        except Exception as e:
            logger.error(f"Failed to extract text: {e}")
            delete_pdf(pdf_path)
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Failed to extract text from PDF"
            )
        
        # If no book_id provided, create a new book
        if not book_id:
            new_book = Book(
                title=title or file.filename,
                author=author or "Unknown",
                total_pages=len(pages_data),
                description=f"Uploaded from {file.filename}"
            )
            db.add(new_book)
            db.commit()
            db.refresh(new_book)
            book_id = new_book.id
            logger.info(f"Created new book with ID {book_id}")
        else:
            # Validate existing book
            book = db.query(Book).filter(Book.id == book_id).first()
            if not book:
                delete_pdf(pdf_path)
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Book with ID {book_id} not found"
                )
        
        # Save pages to database
        saved_pages = []
        try:
            for page_data in pages_data:
                new_page = Page(
                    book_id=book_id,
                    page_number=page_data["page_number"],
                    text=page_data["text"],
                    pdf_path=pdf_path
                )
                db.add(new_page)
                saved_pages.append(page_data)
            
            db.commit()
            logger.info(f"Saved {len(saved_pages)} pages to database")
            
        except Exception as e:
            db.rollback()
            delete_pdf(pdf_path)
            logger.error(f"Failed to save pages to database: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to save pages to database"
            )
        
        # Get PDF metadata
        pdf_info = get_pdf_info(pdf_path)
        
        return {
            "status": "success",
            "filename": file.filename,
            "book_id": book_id,
            "pdf_path": pdf_path,
            "total_pages": len(pages_data),
            "pages_with_errors": sum(1 for p in pages_data if "error" in p),
            "metadata": pdf_info,
            "message": f"Successfully uploaded and extracted {len(pages_data)} pages"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during PDF upload: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred"
        )
    
@router.get("/pdf/{pdf_id}")
async def get_pdf(pdf_id: int, db: Session = Depends(get_db)):
    """
    Get all pages from a PDF
    
    Args:
        pdf_id: Book ID (PDF) to retrieve
        db: Database session
        
    Returns:
        List of all pages with extracted text
    """
    try:
        book = db.query(Book).filter(Book.id == pdf_id).first()
        
        if not book:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"PDF with ID {pdf_id} not found"
            )
        
        pages = db.query(Page).filter(Page.book_id == pdf_id).order_by(Page.page_number).all()
        
        return {
            "status": "success",
            "book_id": pdf_id,
            "total_pages": len(pages),
            "pages": [
                {
                    "page_id": p.id,
                    "page_number": p.page_number,
                    "text": p.text
                }
                for p in pages
            ]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving PDF: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve PDF"
        )

@router.delete("/pdf/{pdf_id}")
async def delete_uploaded_pdf(pdf_id: int, db: Session = Depends(get_db)):
    """
    Delete a PDF and all its extracted pages
    
    Args:
        pdf_id: Book ID (PDF) to delete
        db: Database session
        
    Returns:
        Success message
    """
    try:
        book = db.query(Book).filter(Book.id == pdf_id).first()
        
        if not book:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"PDF with ID {pdf_id} not found"
            )
        
        # Get pages to find PDF path
        pages = db.query(Page).filter(Page.book_id == pdf_id).all()
        
        # Delete from disk (if pdf_path is stored in Page model)
        if pages and hasattr(pages[0], 'pdf_path'):
            delete_pdf(pages[0].pdf_path)
        
        # Delete from database
        for page in pages:
            db.delete(page)
        
        db.delete(book)
        db.commit()
        
        logger.info(f"Deleted PDF {pdf_id} and all associated pages")
        
        return {
            "status": "success",
            "message": f"PDF {pdf_id} and {len(pages)} pages deleted"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting PDF: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete PDF"
        )