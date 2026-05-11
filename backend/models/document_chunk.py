"""
DocumentChunk Model: Stores extracted text, metadata for illustrations (summaries, characters, scenes),
and the path to the generated illustration.
"""
from sqlalchemy import Column, Integer, Text, String, ForeignKey, DateTime
from sqlalchemy.sql import func
from database import Base

class DocumentChunk(Base):
    """
    Stores chunks of text extracted from PDFs, along with their generated summaries,
    character/scene metadata, and illustration paths.
    """
    __tablename__ = "document_chunks"

    id = Column(Integer, primary_key=True, index=True)
    # Relationship to the main Book record
    book_id = Column(Integer, ForeignKey("books.id", ondelete="CASCADE"))
    page_number = Column(Integer)
    content = Column(Text)
    # New columns for character-consistent illustration pipeline
    summary = Column(Text, nullable=True)       # Per-page narrative summary
    characters = Column(Text, nullable=True)    # Key characters identified on page
    scenes = Column(Text, nullable=True)        # Scene descriptions
    illustration_path = Column(String, nullable=True) # Path to the generated image
    created_at = Column(DateTime(timezone=True), server_default=func.now())