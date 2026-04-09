from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, func

from database import Base


class PageAsset(Base):
    __tablename__ = "page_assets"

    id = Column(Integer, primary_key=True, index=True)
    book_id = Column(Integer, ForeignKey("books.id"), index=True, nullable=False)
    page_id = Column(Integer, ForeignKey("pages.id"), unique=True, index=True, nullable=False)
    page_number = Column(Integer, index=True, nullable=False)
    scene_summary = Column(Text, nullable=True)
    summary_short = Column(Text, nullable=True)
    continuity_summary = Column(Text, nullable=True)
    visual_prompt = Column(Text, nullable=True)
    prompt_override = Column(Text, nullable=True)
    last_used_prompt = Column(Text, nullable=True)
    negative_prompt = Column(Text, nullable=True)
    style_preset = Column(String, nullable=False, default="storybook")
    image_path = Column(Text, nullable=True)
    image_status = Column(String, nullable=False, default="pending")
    last_error = Column(Text, nullable=True)
    prompt_generated_at = Column(DateTime, nullable=True)
    image_generated_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
