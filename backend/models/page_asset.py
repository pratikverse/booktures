from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.sql import func
from database import Base

class PageAsset(Base):
    """
    Stores the narrative summaries and generated visual metadata for each page.
    """
    __tablename__ = "page_assets"

    id = Column(Integer, primary_key=True, index=True)
    chunk_id = Column(Integer, ForeignKey("document_chunks.id", ondelete="CASCADE"), unique=True)
    
    visual_summary = Column(Text) # The condensed narrative for the LLM
    key_objects = Column(Text) # Comma-separated list of identified visual assets
    image_prompt = Column(Text) # The final prompt sent to Stable Diffusion
    image_path = Column(String) # Path to the generated illustration
    seed = Column(Integer) # The deterministic seed used for this generation
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())