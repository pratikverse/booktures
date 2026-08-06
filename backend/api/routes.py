"""
API Routes: Defines the REST endpoints for book management, file uploads,
and content retrieval.
"""

import os
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, BackgroundTasks, Body
from sqlalchemy.orm import Session
from typing import List

from database import get_db, SessionLocal
import models
from services import pdf_service, settings_service
from services.generation_queue_service import GenerationWorker # Import worker for job creation

# Removed prefix to match frontend root-level requests
router = APIRouter(tags=["books"])

MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_MB", "25")) * 1024 * 1024


def _public_storage_url(path: str | None) -> str | None:
    """Normalize DB file paths into browser-accessible /storage URLs."""
    if not path:
        return None

    normalized = path.replace("\\", "/")

    # Already a full URL (e.g. cloud storage provider) - use as-is.
    if normalized.startswith("http://") or normalized.startswith("https://"):
        return normalized

    # Already a public URL path.
    if normalized.startswith("/storage/"):
        return normalized
    if normalized.startswith("storage/"):
        return f"/{normalized}"

    marker = "/storage/"
    idx = normalized.lower().find(marker)
    if idx != -1:
        return normalized[idx:]

    # Fallback for legacy relative records.
    return f"/{normalized.lstrip('/')}"

# --- Library Endpoints ---

@router.get("/books", response_model=List[dict])
def list_books(db: Session = Depends(get_db)):
    """Retrieve all books in the library."""
    books = db.query(models.Book).all()
    return [
        {"id": b.id, "title": b.title, "status": b.status, "progress": b.progress}
        for b in books
    ]

# Changed path from /books/upload to /upload-pdf to match frontend logs
@router.post("/upload-pdf", response_model=dict)
async def upload_book(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    Uploads a PDF/Image, saves it, and queues a background job for processing.
    """
    allowed_extensions = {".pdf", ".jpg", ".jpeg", ".png"}
    if not any(file.filename.lower().endswith(ext) for ext in allowed_extensions):
        raise HTTPException(status_code=400, detail=f"Unsupported file type. Allowed: {', '.join(allowed_extensions)}")

    # Read file content in chunks so oversized uploads are rejected before
    # the whole file is buffered in memory.
    content = bytearray()
    while chunk := await file.read(1024 * 1024):
        content.extend(chunk)
        if len(content) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail=f"File exceeds {MAX_UPLOAD_BYTES // (1024*1024)}MB limit.")
    content = bytes(content)
    try:
        file_path = pdf_service.save_pdf(content, file.filename)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save PDF: {str(e)}")

    # Register the metadata in the DB before processing text
    clean_title = os.path.splitext(file.filename)[0]
    db_book = models.Book(title=clean_title, file_path=file_path, status="queued", progress=0.0)
    db.add(db_book)
    db.commit()
    db.refresh(db_book)

    # 3. Create a Job for the Generation Queue
    new_job = models.Job(book_id=db_book.id, job_type="book_pipeline", status="queued", status_note="Book queued for processing.")
    db.add(new_job)
    db.commit()

    return {
        "id": db_book.id,
        "title": db_book.title,
        "status": db_book.status,
        "message": "File uploaded and processing queued."
    }

@router.get("/books/{book_id}")
def get_book_details(book_id: int, db: Session = Depends(get_db)):
    """Retrieve the metadata for an uploaded book."""
    db_book = db.query(models.Book).filter(models.Book.id == book_id).first()
    if not db_book:
        raise HTTPException(status_code=404, detail="Book not found")
    
    # Extract the filename from the absolute path stored in DB
    filename = os.path.basename(db_book.file_path)

    return {
        "id": db_book.id, 
        "title": db_book.title, 
        "file_path": f"storage/pdfs/{filename}", # Relative path for web access
        "status": db_book.status
    }

@router.get("/books/{book_id}/content")
def get_book_content(book_id: int, db: Session = Depends(get_db)):
    """Retrieve the extracted text content for a book along with assets."""
    chunks_with_assets = db.query(models.DocumentChunk, models.PageAsset).\
        outerjoin(models.PageAsset, models.DocumentChunk.id == models.PageAsset.chunk_id).\
        filter(models.DocumentChunk.book_id == book_id).order_by(models.DocumentChunk.page_number).all()
    
    if not chunks_with_assets:
        return {"book_id": book_id, "status": "processing or no content found", "pages": []}

    return {
        "book_id": book_id,
        "total_pages": len(chunks_with_assets),
        "pages": [
            {
                "page": chunk.page_number,
                "content": chunk.content,
                "summary": chunk.summary,
                "characters": chunk.characters,
                "scenes": chunk.scenes,
                "illustration_url": _public_storage_url(chunk.illustration_path),
                "image_prompt": asset.image_prompt if asset else None # Added image_prompt
            } for chunk, asset in chunks_with_assets
        ]
    }

@router.get("/books/{book_id}/characters", response_model=List[dict])
def get_book_characters(book_id: int, db: Session = Depends(get_db)):
    """Retrieve character consistency metadata for a book."""
    chars = db.query(models.Character).filter(models.Character.book_id == book_id).all()
    if not chars:
        return []

    result = []
    for c in chars:
        page_numbers = sorted({appearance.page_number for appearance in c.appearances if appearance.page_number is not None})
        result.append({
            "id": c.id,
            "book_id": c.book_id,
            "name": c.name,
            "aliases": c.aliases,
            "visual_profile": c.visual_profile,
            "mention_count": c.mention_count,
            "page_numbers": page_numbers
        })
    return result

@router.post("/books/{book_id}/generate-images", response_model=dict)
def trigger_image_generation(book_id: int, db: Session = Depends(get_db)):
    """Trigger image generation for a book that has already been analyzed."""
    book = db.query(models.Book).filter(models.Book.id == book_id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    
    if book.status not in ["analyzed", "completed"]:
        raise HTTPException(status_code=400, detail="Book must be analyzed before generating images.")

    # Create a new job for image generation
    new_job = models.Job(book_id=book_id, job_type="image_generation", status="queued", status_note="Image generation queued.")
    db.add(new_job)
    db.commit()

    return {
        "message": "Image generation job queued successfully."
    }

# --- Job Management Endpoints ---

@router.get("/jobs", response_model=List[dict])
def list_jobs(db: Session = Depends(get_db)):
    """Retrieve all background jobs and their statuses."""
    job_labels = {
        "book_pipeline": "Processing Book",
        "image_generation": "Generating Images"
    }
    # Join Job with Book to include the book title in the response
    results = db.query(models.Job, models.Book.title).outerjoin(
        models.Book, models.Job.book_id == models.Book.id
    ).order_by(models.Job.created_at.desc()).all()

    return [
        {
            "id": j.id,
            "book_id": j.book_id,
            "book_title": title,
            "type": j.job_type,
            "label": job_labels.get(j.job_type, j.job_type),
            "status": j.status,
            "note": j.status_note,
            "progress": j.progress,
            "created_at": j.created_at
        } for j, title in results
    ]

@router.post("/jobs/{job_id}/action")
def manage_job(job_id: int, action: str = Body(..., embed=True), db: Session = Depends(get_db)):
    """Pause, Resume, or Cancel a job."""
    job = db.query(models.Job).filter(models.Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if action == "cancel":
        job.status = "cancelled"
    elif action == "pause":
        job.status = "paused"
    elif action == "resume":
        job.status = "queued"
    elif action == "retry":
        if job.status not in ["failed", "cancelled"]:
            raise HTTPException(status_code=400, detail="Only failed/cancelled jobs can be retried")
        job.status = "queued"
        job.progress = 0.0
        job.status_note = "Retry requested by user."
    else:
        raise HTTPException(status_code=400, detail="Invalid action")

    db.commit()
    return {"message": f"Job {action}ed successfully."}

# --- Settings Endpoints ---

@router.get("/settings")
def get_settings():
    """Get current AI configuration."""
    # Return flat structure expected by frontend lib/api.ts
    return {
        "ollama_url": pdf_service.OLLAMA_BASE_URL,
        "model_name": pdf_service.OLLAMA_DEFAULT_MODEL,
        "timeout": int(pdf_service.OLLAMA_TIMEOUT_SECONDS),
        "image_mode": os.getenv("IMAGE_PRESET", "balanced"),
        "image_model": os.getenv("DIFFUSION_MODEL", "segmind/SSD-1B"),
        "image_width": int(os.getenv("IMAGE_WIDTH", "768")),
        "image_height": int(os.getenv("IMAGE_HEIGHT", "768")),
        "image_steps": int(os.getenv("IMAGE_STEPS", "12")),
        "image_guidance": float(os.getenv("IMAGE_GUIDANCE", "8.0")),
        "imageStyle": os.getenv("IMAGE_STYLE", "storybook") # Support camelCase from Shadcn frontend
    }

@router.get("/settings/ollama-models")
def get_ollama_models_standalone():
    """Standalone endpoint for fetching available models."""
    return {"models": settings_service.get_available_ollama_models(pdf_service.OLLAMA_BASE_URL)}

@router.put("/settings")
def update_settings(config: dict = Body(...)):
    """Update AI configuration (persisted to .env)."""
    # Map frontend keys to backend environment variables
    mappings = {
        "ollama_url": "OLLAMA_BASE_URL",
        "model_name": "OLLAMA_DEFAULT_MODEL",
        "timeout": "OLLAMA_TIMEOUT_SECONDS",
        "image_mode": "IMAGE_PRESET",
        "image_model": "DIFFUSION_MODEL",
        "image_width": "IMAGE_WIDTH",
        "image_height": "IMAGE_HEIGHT",
        "image_steps": "IMAGE_STEPS",
        "image_guidance": "IMAGE_GUIDANCE",
        "imageStyle": "IMAGE_STYLE" # Support camelCase from Shadcn Settings.tsx
    }

    for frontend_key, env_key in mappings.items():
        if frontend_key in config:
            val = str(config[frontend_key])
            settings_service.update_setting(env_key, val)
            os.environ[env_key] = val  # Update current process environment for the worker

    return get_settings()
