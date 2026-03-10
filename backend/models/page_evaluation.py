from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey, func

from database import Base


class PageEvaluation(Base):
    __tablename__ = "page_evaluations"

    id = Column(Integer, primary_key=True, index=True)
    book_id = Column(Integer, ForeignKey("books.id"), index=True, nullable=False)
    page_id = Column(Integer, ForeignKey("pages.id"), index=True, nullable=False)
    page_number = Column(Integer, index=True, nullable=False)
    prompt_quality = Column(Float, nullable=False, default=0.0)
    character_consistency = Column(Float, nullable=False, default=0.0)
    failure_score = Column(Float, nullable=False, default=0.0)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
