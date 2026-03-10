from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# SQLite for development (Postgres later)
DATABASE_URL = "sqlite:///./booktures.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
)

# Session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

# Base class for models
Base = declarative_base()


def ensure_sqlite_schema():
    """Perform lightweight SQLite schema evolution for local development."""
    if not DATABASE_URL.startswith("sqlite"):
        return

    with engine.begin() as conn:
        table_rows = conn.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        tables = {row[0] for row in table_rows}

        if "characters" in tables:
            column_rows = conn.exec_driver_sql("PRAGMA table_info(characters)").fetchall()
            columns = {row[1] for row in column_rows}
            if "aliases" not in columns:
                conn.exec_driver_sql("ALTER TABLE characters ADD COLUMN aliases TEXT")
            if "visual_profile" not in columns:
                conn.exec_driver_sql("ALTER TABLE characters ADD COLUMN visual_profile TEXT")

        if "page_characters" not in tables:
            conn.exec_driver_sql(
                """
                CREATE TABLE page_characters (
                    id INTEGER NOT NULL PRIMARY KEY,
                    book_id INTEGER NOT NULL,
                    page_id INTEGER NOT NULL,
                    character_id INTEGER NOT NULL,
                    mention_count INTEGER NOT NULL DEFAULT 0,
                    confidence FLOAT NOT NULL DEFAULT 0.0,
                    FOREIGN KEY(book_id) REFERENCES books (id),
                    FOREIGN KEY(page_id) REFERENCES pages (id),
                    FOREIGN KEY(character_id) REFERENCES characters (id)
                )
                """
            )
            conn.exec_driver_sql(
                "CREATE INDEX ix_page_characters_book_id ON page_characters (book_id)"
            )
            conn.exec_driver_sql(
                "CREATE INDEX ix_page_characters_page_id ON page_characters (page_id)"
            )
            conn.exec_driver_sql(
                "CREATE INDEX ix_page_characters_character_id ON page_characters (character_id)"
            )


# Dependency for FastAPI routes
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
