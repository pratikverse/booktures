from sqlalchemy import Column, Integer, Float, ForeignKey

from database import Base


class PageCharacter(Base):
    __tablename__ = "page_characters"

    id = Column(Integer, primary_key=True, index=True)
    book_id = Column(Integer, ForeignKey("books.id"), index=True, nullable=False)
    page_id = Column(Integer, ForeignKey("pages.id"), index=True, nullable=False)
    character_id = Column(Integer, ForeignKey("characters.id"), index=True, nullable=False)
    mention_count = Column(Integer, default=0, nullable=False)
    confidence = Column(Float, default=0.0, nullable=False)
