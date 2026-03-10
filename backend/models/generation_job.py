from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Float, func

from database import Base


class GenerationJob(Base):
    __tablename__ = "generation_jobs"

    id = Column(Integer, primary_key=True, index=True)
    book_id = Column(Integer, ForeignKey("books.id"), index=True, nullable=False)
    page_id = Column(Integer, ForeignKey("pages.id"), index=True, nullable=True)
    job_type = Column(String, index=True, nullable=False)
    status = Column(String, index=True, nullable=False, default="queued")
    progress = Column(Float, nullable=False, default=0.0)
    payload = Column(Text, nullable=True)
    result = Column(Text, nullable=True)
    attempts = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=3)
    run_after = Column(DateTime, index=True, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
