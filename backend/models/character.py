from sqlalchemy import Column, Integer, String, ForeignKey, Text
from database import Base


class Character(Base):
    __tablename__ = "characters"

    id = Column(Integer, primary_key=True, index=True)
    book_id = Column(Integer, ForeignKey("books.id"), index=True)
    name = Column(String, index=True)
    source = Column(String, default="ner")  # e.g., "ner", "web", or "ner+web"
    mention_count = Column(Integer, default=0)
    first_appearance_page = Column(Integer, nullable=True)
    external_url = Column(String, nullable=True)
    aliases = Column(Text, nullable=True)  # JSON-encoded alias list
    visual_profile = Column(Text, nullable=True)
