from sqlalchemy import Column, Integer, String, Text, ForeignKey, Table
from sqlalchemy.orm import relationship
from database import Base

# Association table for Character-to-Page mapping
page_characters = Table(
    "page_characters",
    Base.metadata,
    Column("character_id", Integer, ForeignKey("characters.id", ondelete="CASCADE")),
    Column("chunk_id", Integer, ForeignKey("document_chunks.id", ondelete="CASCADE"))
)

class Character(Base):
    """
    Registry for story characters and their stable visual descriptors.
    """
    __tablename__ = "characters"

    id = Column(Integer, primary_key=True, index=True)
    book_id = Column(Integer, ForeignKey("books.id", ondelete="CASCADE"))
    name = Column(String, index=True)
    aliases = Column(Text) # Comma-separated list of known aliases
    visual_profile = Column(Text) # The 'Visual Bible' snippet for this character
    mention_count = Column(Integer, default=1)

    # Relationship to the chunks where they appear
    appearances = relationship("DocumentChunk", secondary=page_characters, backref="character_mentions")