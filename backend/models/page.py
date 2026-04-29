from sqlalchemy import Column, Integer, Text, ForeignKey, Boolean, Float
from database import Base

class Page(Base):
    __tablename__ = "pages"

    id = Column(Integer, primary_key=True, index=True)
    book_id = Column(Integer, ForeignKey("books.id"))
    page_number = Column(Integer)
    text = Column(Text)
    weak_text = Column(Boolean, nullable=False, default=False)
    extraction_source = Column(Text, nullable=True)
    extraction_score = Column(Float, nullable=True)
