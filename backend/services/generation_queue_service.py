import threading
import time
from database import SessionLocal
from models import Job, Book, DocumentChunk, Character, PageAsset
from services import pdf_service
from services import character_service
from services import prompt_service
from services.image_generation_service import image_service # Renamed from illustration_service
import logging

logger = logging.getLogger(__name__)

class GenerationWorker(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.running = True

    def run(self):
        while self.running:
            db = SessionLocal()
            try:
                # Claim the oldest queued job
                job = db.query(Job).filter(Job.status == "queued").order_by(Job.created_at).first()
                
                if job:
                    job.status = "running"
                    db.commit()
                    
                    self._execute_job(job, db)
                    
                db.close()
            except Exception as e:
                logger.error(f"Worker Error: {e}")
            
            time.sleep(5) # Poll every 5 seconds

    def _execute_job(self, job, db):
        try:
            if job.job_type == "book_pipeline":
                self._run_analysis_pipeline(job, db)
            elif job.job_type == "image_generation":
                self._run_image_pipeline(job, db)
            else:
                raise Exception(f"Unknown job type: {job.job_type}")
        except Exception as e:
            logger.error(f"Job failed: {e}")
            job.status = "failed"
            job.status_note = str(e)
            book = db.query(Book).filter(Book.id == job.book_id).first()
            if book:
                book.status = "failed"
                book.progress = 0.0
            db.commit()

    def _run_analysis_pipeline(self, job, db):
        book = db.query(Book).filter(Book.id == job.book_id).first()
        if not book:
            raise Exception("Book not found")

        job.status_note = "Extracting text from PDF..."
        book.status = "processing"
        job.progress = 0.05
        book.progress = 0.05
        db.commit()
        
        pages = pdf_service.extract_text_by_page(book.file_path)
        chunks = []
        for page in pages:
            chunk = DocumentChunk(book_id=book.id, page_number=page["page_number"], content=page["text"])
            db.add(chunk)
            chunks.append(chunk)
        db.commit()

        job.status_note = "Building Character Visual Bible..."
        job.progress = 0.2
        book.progress = 0.2
        db.commit()
        character_service.process_book_characters(book.id, db)
        characters = db.query(Character).filter(Character.book_id == book.id).all()
        visual_bible = "\n".join([f"- {c.name}: {c.visual_profile}" for c in characters]) or "No characters identified."

        for i, chunk in enumerate(chunks):
            # Check for cancellation or pause status
            db.refresh(job)
            if job.status == "cancelled":
                logger.info(f"Aborting Job {job.id}: User cancelled.")
                return
            
            while job.status == "paused":
                time.sleep(2)
                db.refresh(job)
                if job.status == "cancelled":
                    return

            job.progress = 0.2 + (0.8 * (i / len(chunks)))
            book.progress = job.progress
            job.status_note = f"Analyzing page {chunk.page_number}/{len(chunks)}..."
            db.commit()
            
            prev_page_assets = db.query(PageAsset).join(DocumentChunk).filter(
                DocumentChunk.book_id == book.id, DocumentChunk.page_number < chunk.page_number
            ).order_by(DocumentChunk.page_number.desc()).limit(3).all()
            previous_summaries_text = " ".join([pa.visual_summary for pa in prev_page_assets])

            page_summary = prompt_service.generate_page_summary(chunk.content, previous_summaries_text)
            page_metadata = character_service.extract_page_metadata(chunk.content)
            image_prompt = prompt_service.generate_illustration_prompt(page_summary, visual_bible, page_metadata.get("scene", ""))
            
            chunk.summary = page_summary
            chunk.characters = page_metadata.get("characters")
            chunk.scenes = page_metadata.get("scene")
            db.add(chunk)

            page_asset = PageAsset(
                chunk_id=chunk.id, visual_summary=page_summary,
                image_prompt=image_prompt, image_path=None, seed=chunk.id
            )
            db.add(page_asset)
            db.commit()

        job.status = "completed"
        book.status = "analyzed"
        book.progress = 1.0
        db.commit()

    def _run_image_pipeline(self, job, db):
        book = db.query(Book).filter(Book.id == job.book_id).first()
        if not book: raise Exception("Book not found")

        job.status_note = "Starting image generation..."
        book.status = "generating_images"
        db.commit()

        # Reconstruct the Visual Bible from stored characters for prompt context
        characters = db.query(Character).filter(Character.book_id == book.id).all()
        visual_bible = "\n".join([f"- {c.name}: {c.visual_profile}" for c in characters]) or "No characters identified."

        assets = db.query(PageAsset).join(DocumentChunk).filter(DocumentChunk.book_id == book.id).all()
        for i, asset in enumerate(assets):
            # Check for cancellation or pause status
            db.refresh(job)
            if job.status == "cancelled":
                logger.info(f"Aborting Image Generation Job {job.id}: User cancelled.")
                return

            while job.status == "paused":
                time.sleep(2)
                db.refresh(job)
                if job.status == "cancelled":
                    return

            chunk = db.query(DocumentChunk).filter(DocumentChunk.id == asset.chunk_id).first()
            job.progress = (i / len(assets))
            book.progress = job.progress
            job.status_note = f"Rendering illustration for page {chunk.page_number if chunk else '?'}/{len(assets)}..."
            db.commit()

            # Step 2a: Generate the prompt now if it hasn't been created or manually overridden
            if not asset.image_prompt:
                asset.image_prompt = prompt_service.generate_illustration_prompt(
                    asset.visual_summary, 
                    visual_bible, 
                    chunk.scenes or ""
                )
            if not asset.image_path:
                img_path = image_service.render_page_image(asset.image_prompt, book.id, chunk.page_number, asset.seed)
                if img_path:
                    asset.image_path = img_path
                    chunk.illustration_path = img_path
                    db.add(asset)
                    db.add(chunk)
                    db.commit()

        job.status = "completed"
        book.status = "completed"
        book.progress = 1.0
        db.commit()

def start_worker():
    worker = GenerationWorker()
    worker.start()
    return worker