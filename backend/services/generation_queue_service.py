import json
import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Optional

from database import SessionLocal
from models.generation_job import GenerationJob
from models.page import Page
from services.character_service import build_character_registry
from services.evaluation_service import evaluate_book_prompts
from services.image_generation_service import generate_page_image
from services.prompt_service import build_page_visual_prompt, DEFAULT_STYLE_PRESET

logger = logging.getLogger(__name__)

JOB_BOOK_PIPELINE = "book_pipeline"
JOB_PAGE_IMAGE = "page_image"
JOB_BOOK_EVALUATION = "book_evaluation"
JOB_PAGE_PROMPT = "page_prompt"
JOB_BOOK_IMAGES = "book_images"

JOB_STATUS_QUEUED = "queued"
JOB_STATUS_RUNNING = "running"
JOB_STATUS_PAUSED = "paused"
JOB_STATUS_CANCELED = "canceled"
JOB_STATUS_COMPLETED = "completed"
JOB_STATUS_FAILED = "failed"

_worker_thread: Optional[threading.Thread] = None
_worker_stop_event = threading.Event()
_worker_lock = threading.Lock()


class JobPaused(Exception):
    pass


class JobCanceled(Exception):
    pass


def start_worker():
    global _worker_thread
    with _worker_lock:
        if _worker_thread and _worker_thread.is_alive():
            return
        _worker_stop_event.clear()
        _worker_thread = threading.Thread(
            target=_worker_loop,
            name="booktures-job-worker",
            daemon=True,
        )
        _worker_thread.start()
        logger.info("Generation queue worker started")


def stop_worker():
    _worker_stop_event.set()


def enqueue_job(
    book_id: int,
    job_type: str,
    payload: dict | None = None,
    page_id: Optional[int] = None,
    max_attempts: int = 3,
) -> int:
    db = SessionLocal()
    try:
        job = GenerationJob(
            book_id=book_id,
            page_id=page_id,
            job_type=job_type,
            payload=json.dumps(payload or {}),
            status=JOB_STATUS_QUEUED,
            progress=0.0,
            attempts=0,
            max_attempts=max_attempts,
            run_after=datetime.utcnow(),
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        return job.id
    finally:
        db.close()


def enqueue_book_pipeline(book_id: int, style_preset: str = DEFAULT_STYLE_PRESET) -> int:
    return enqueue_job(
        book_id=book_id,
        job_type=JOB_BOOK_PIPELINE,
        payload={"style_preset": style_preset},
        max_attempts=2,
    )


def enqueue_page_prompt(
    book_id: int,
    page_number: int,
    style_preset: str = DEFAULT_STYLE_PRESET,
    force_refresh: bool = False,
) -> int:
    return enqueue_job(
        book_id=book_id,
        job_type=JOB_PAGE_PROMPT,
        payload={
            "page_number": page_number,
            "style_preset": style_preset,
            "force_refresh": force_refresh,
        },
        max_attempts=2,
    )


def enqueue_page_image(
    book_id: int,
    page_number: int,
    style_preset: str = DEFAULT_STYLE_PRESET,
    force_prompt_refresh: bool = False,
    force_regenerate: bool = False,
) -> int:
    return enqueue_job(
        book_id=book_id,
        job_type=JOB_PAGE_IMAGE,
        payload={
            "page_number": page_number,
            "style_preset": style_preset,
            "force_prompt_refresh": force_prompt_refresh,
            "force_regenerate": force_regenerate,
        },
        max_attempts=3,
    )


def enqueue_book_evaluation(book_id: int, sample_size: int = 25) -> int:
    sample_size = max(5, min(sample_size, 30))
    return enqueue_job(
        book_id=book_id,
        job_type=JOB_BOOK_EVALUATION,
        payload={"sample_size": sample_size},
        max_attempts=2,
    )


def enqueue_book_images(
    book_id: int,
    style_preset: str = DEFAULT_STYLE_PRESET,
    force_prompt_refresh: bool = False,
    force_regenerate: bool = False,
) -> int:
    return enqueue_job(
        book_id=book_id,
        job_type=JOB_BOOK_IMAGES,
        payload={
            "style_preset": style_preset,
            "force_prompt_refresh": force_prompt_refresh,
            "force_regenerate": force_regenerate,
        },
        max_attempts=2,
    )


def get_job(job_id: int) -> Optional[dict]:
    db = SessionLocal()
    try:
        job = db.get(GenerationJob, job_id)
        if job is None:
            return None
        return _serialize_job(job)
    finally:
        db.close()


def pause_job(job_id: int) -> Optional[dict]:
    db = SessionLocal()
    try:
        job = db.get(GenerationJob, job_id)
        if job is None:
            return None

        payload = _read_payload(job.payload)
        now = datetime.utcnow()

        if job.status == JOB_STATUS_QUEUED:
            job.status = JOB_STATUS_PAUSED
            job.run_after = None
            payload.pop("pause_requested", None)
            payload.pop("cancel_requested", None)
        elif job.status == JOB_STATUS_RUNNING:
            payload["pause_requested"] = True
            payload.pop("cancel_requested", None)
        elif job.status == JOB_STATUS_PAUSED:
            return _serialize_job(job)
        else:
            raise ValueError(f"Cannot pause job in status '{job.status}'")

        job.payload = json.dumps(payload)
        job.updated_at = now
        db.add(job)
        db.commit()
        db.refresh(job)
        return _serialize_job(job)
    finally:
        db.close()


def resume_job(job_id: int) -> Optional[dict]:
    db = SessionLocal()
    try:
        job = db.get(GenerationJob, job_id)
        if job is None:
            return None
        if job.status != JOB_STATUS_PAUSED:
            raise ValueError(f"Cannot resume job in status '{job.status}'")

        payload = _read_payload(job.payload)
        payload.pop("pause_requested", None)
        payload.pop("cancel_requested", None)

        job.status = JOB_STATUS_QUEUED
        job.run_after = datetime.utcnow()
        job.completed_at = None
        job.payload = json.dumps(payload)
        job.updated_at = datetime.utcnow()
        db.add(job)
        db.commit()
        db.refresh(job)
        return _serialize_job(job)
    finally:
        db.close()


def cancel_job(job_id: int) -> Optional[dict]:
    db = SessionLocal()
    try:
        job = db.get(GenerationJob, job_id)
        if job is None:
            return None

        payload = _read_payload(job.payload)
        now = datetime.utcnow()

        if job.status in {JOB_STATUS_QUEUED, JOB_STATUS_PAUSED}:
            job.status = JOB_STATUS_CANCELED
            job.run_after = None
            job.completed_at = now
            payload.pop("pause_requested", None)
            payload.pop("cancel_requested", None)
        elif job.status == JOB_STATUS_RUNNING:
            payload["cancel_requested"] = True
            payload.pop("pause_requested", None)
        elif job.status == JOB_STATUS_CANCELED:
            return _serialize_job(job)
        else:
            raise ValueError(f"Cannot cancel job in status '{job.status}'")

        job.payload = json.dumps(payload)
        job.updated_at = now
        db.add(job)
        db.commit()
        db.refresh(job)
        return _serialize_job(job)
    finally:
        db.close()


def _worker_loop():
    while not _worker_stop_event.is_set():
        job = _claim_next_job()
        if job is None:
            time.sleep(1.0)
            continue
        _run_job(job.id)


def _claim_next_job() -> Optional[GenerationJob]:
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        job = (
            db.query(GenerationJob)
            .filter(GenerationJob.status == JOB_STATUS_QUEUED)
            .filter((GenerationJob.run_after.is_(None)) | (GenerationJob.run_after <= now))
            .order_by(GenerationJob.created_at.asc())
            .first()
        )
        if job is None:
            return None
        job.status = JOB_STATUS_RUNNING
        if job.started_at is None:
            job.started_at = now
        job.updated_at = now
        db.add(job)
        db.commit()
        db.refresh(job)
        return job
    finally:
        db.close()


def _run_job(job_id: int):
    job: Optional[GenerationJob] = None
    payload: dict = {}
    try:
        db = SessionLocal()
        try:
            job = db.get(GenerationJob, job_id)
            if job is None:
                return
            payload = _read_payload(job.payload)
            book_id = job.book_id
            page_id = job.page_id
            job_type = job.job_type
        finally:
            db.close()

        # Run long work outside of any open job-tracking transaction.
        temp_job = GenerationJob(id=job_id, book_id=book_id, page_id=page_id, job_type=job_type)
        _check_job_control(job_id)
        result = _dispatch_job(temp_job, payload)

        db = SessionLocal()
        try:
            job = db.get(GenerationJob, job_id)
            if job is None:
                return
            if job.status in {JOB_STATUS_PAUSED, JOB_STATUS_CANCELED}:
                return
            job.status = JOB_STATUS_COMPLETED
            job.progress = 1.0
            job.result = json.dumps(result)
            job.completed_at = datetime.utcnow()
            job.last_error = None
            db.add(job)
            db.commit()
        finally:
            db.close()
    except JobPaused:
        _mark_job_paused(job_id)
    except JobCanceled:
        _mark_job_canceled(job_id)
    except Exception as exc:
        _mark_job_failure(job_id, str(exc))


def _dispatch_job(job: GenerationJob, payload: dict) -> dict:
    if job.job_type == JOB_BOOK_PIPELINE:
        style_preset = payload.get("style_preset", DEFAULT_STYLE_PRESET)
        _update_job_progress(job.id, 0.05, "building_character_registry")
        build_character_registry(job.book_id)
        _check_job_control(job.id)
        _update_job_progress(job.id, 0.35, "caching_page_prompts")

        db = SessionLocal()
        try:
            pages = (
                db.query(Page)
                .filter(Page.book_id == job.book_id)
                .order_by(Page.page_number.asc())
                .all()
            )
        finally:
            db.close()

        total = max(len(pages), 1)
        for idx, page in enumerate(pages, start=1):
            _check_job_control(job.id)
            build_page_visual_prompt(
                book_id=job.book_id,
                page_number=page.page_number,
                style_preset=style_preset,
                force_refresh=False,
            )
            progress = 0.35 + (0.6 * (idx / total))
            _update_job_progress(job.id, progress, f"prompt_cached_page_{page.page_number}")
            _check_job_control(job.id)
        return {"book_id": job.book_id, "pages_processed": len(pages)}

    if job.job_type == JOB_PAGE_PROMPT:
        _check_job_control(job.id)
        page_number = int(payload["page_number"])
        style_preset = payload.get("style_preset", DEFAULT_STYLE_PRESET)
        force_refresh = bool(payload.get("force_refresh", False))
        data = build_page_visual_prompt(
            book_id=job.book_id,
            page_number=page_number,
            style_preset=style_preset,
            force_refresh=force_refresh,
        )
        _check_job_control(job.id)
        return {"book_id": job.book_id, "page_number": page_number, "prompt_status": data.get("status")}

    if job.job_type == JOB_PAGE_IMAGE:
        _check_job_control(job.id)
        page_number = int(payload["page_number"])
        style_preset = payload.get("style_preset", DEFAULT_STYLE_PRESET)
        result = generate_page_image(
            book_id=job.book_id,
            page_number=page_number,
            style_preset=style_preset,
            force_prompt_refresh=bool(payload.get("force_prompt_refresh", False)),
            force_regenerate=bool(payload.get("force_regenerate", False)),
        )
        _check_job_control(job.id)
        return result

    if job.job_type == JOB_BOOK_EVALUATION:
        _check_job_control(job.id)
        sample_size = int(payload.get("sample_size", 25))
        result = evaluate_book_prompts(book_id=job.book_id, sample_size=sample_size, force_refresh=False)
        _check_job_control(job.id)
        return result

    if job.job_type == JOB_BOOK_IMAGES:
        style_preset = payload.get("style_preset", DEFAULT_STYLE_PRESET)
        force_prompt_refresh = bool(payload.get("force_prompt_refresh", False))
        force_regenerate = bool(payload.get("force_regenerate", False))
        db = SessionLocal()
        try:
            pages = (
                db.query(Page)
                .filter(Page.book_id == job.book_id)
                .order_by(Page.page_number.asc())
                .all()
            )
        finally:
            db.close()

        total = max(len(pages), 1)
        generated = 0
        failed = 0
        for idx, page in enumerate(pages, start=1):
            _check_job_control(job.id)
            result = generate_page_image(
                book_id=job.book_id,
                page_number=page.page_number,
                style_preset=style_preset,
                force_prompt_refresh=force_prompt_refresh,
                force_regenerate=force_regenerate,
            )
            status = result.get("status")
            if status in {"generated", "already_generated"}:
                generated += 1
            elif status in {"failed", "prompt_unavailable", "not_found"}:
                failed += 1
            progress = idx / total
            _update_job_progress(job.id, progress, f"page_{page.page_number}_{status}")
            _check_job_control(job.id)

        return {
            "book_id": job.book_id,
            "total_pages": len(pages),
            "generated": generated,
            "failed": failed,
        }

    raise ValueError(f"Unsupported job_type: {job.job_type}")


def _mark_job_failure(job_id: int, error: str):
    db = SessionLocal()
    try:
        job = db.get(GenerationJob, job_id)
        if job is None:
            return
        if job.status in {JOB_STATUS_PAUSED, JOB_STATUS_CANCELED}:
            return
        job.attempts = int(job.attempts or 0) + 1
        job.last_error = error[:2000]
        job.updated_at = datetime.utcnow()

        if job.attempts < job.max_attempts:
            delay = min(60, 2 ** job.attempts)
            job.status = JOB_STATUS_QUEUED
            job.run_after = datetime.utcnow() + timedelta(seconds=delay)
        else:
            job.status = JOB_STATUS_FAILED
            job.completed_at = datetime.utcnow()
        db.add(job)
        db.commit()
    finally:
        db.close()


def _mark_job_paused(job_id: int):
    db = SessionLocal()
    try:
        job = db.get(GenerationJob, job_id)
        if job is None:
            return
        payload = _read_payload(job.payload)
        payload.pop("pause_requested", None)
        payload.pop("cancel_requested", None)
        job.status = JOB_STATUS_PAUSED
        job.run_after = None
        job.completed_at = None
        job.payload = json.dumps(payload)
        job.updated_at = datetime.utcnow()
        db.add(job)
        db.commit()
    finally:
        db.close()


def _mark_job_canceled(job_id: int):
    db = SessionLocal()
    try:
        job = db.get(GenerationJob, job_id)
        if job is None:
            return
        payload = _read_payload(job.payload)
        payload.pop("pause_requested", None)
        payload.pop("cancel_requested", None)
        job.status = JOB_STATUS_CANCELED
        job.run_after = None
        job.completed_at = datetime.utcnow()
        job.payload = json.dumps(payload)
        job.updated_at = datetime.utcnow()
        db.add(job)
        db.commit()
    finally:
        db.close()


def _update_job_progress(job_id: int, progress: float, status_note: Optional[str] = None):
    db = SessionLocal()
    try:
        job = db.get(GenerationJob, job_id)
        if job is None:
            return
        job.progress = min(0.99, max(0.0, progress))
        if status_note:
            payload = _read_payload(job.payload)
            payload["status_note"] = status_note
            job.payload = json.dumps(payload)
        job.updated_at = datetime.utcnow()
        db.add(job)
        db.commit()
    finally:
        db.close()


def _check_job_control(job_id: int):
    db = SessionLocal()
    try:
        job = db.get(GenerationJob, job_id)
        if job is None:
            raise JobCanceled()
        if job.status == JOB_STATUS_CANCELED:
            raise JobCanceled()
        if job.status == JOB_STATUS_PAUSED:
            raise JobPaused()

        payload = _read_payload(job.payload)
        if payload.get("cancel_requested"):
            raise JobCanceled()
        if payload.get("pause_requested"):
            raise JobPaused()
    finally:
        db.close()


def _read_payload(payload: Optional[str]) -> dict:
    if not payload:
        return {}
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _serialize_job(job: GenerationJob) -> dict:
    return {
        "id": job.id,
        "book_id": job.book_id,
        "page_id": job.page_id,
        "job_type": job.job_type,
        "status": job.status,
        "progress": float(job.progress or 0.0),
        "attempts": int(job.attempts or 0),
        "max_attempts": int(job.max_attempts or 0),
        "payload": _read_payload(job.payload),
        "result": _read_payload(job.result),
        "last_error": job.last_error,
        "run_after": job.run_after.isoformat() if job.run_after else None,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }
