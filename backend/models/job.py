from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Float
from sqlalchemy.sql import func
from database import Base

class Job(Base):
    """
    Queue management for long-running AI tasks.
    """
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    book_id = Column(Integer, ForeignKey("books.id", ondelete="CASCADE"))
    job_type = Column(String) # e.g., 'book_pipeline', 'image_regeneration'
    status = Column(String, default="queued") # queued, running, completed, failed
    progress = Column(Float, default=0.0)
    status_note = Column(Text) # Traceback or current step info
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())