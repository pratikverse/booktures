from sqlalchemy import Column, Integer, Text, ForeignKey
from database import Base


class Page(Base):
    __tablename__ = "pages"

    id = Column(Integer, primary_key=True, index=True)
    book_id = Column(Integer, ForeignKey("books.id"))
    page_number = Column(Integer)
    text = Column(Text)
