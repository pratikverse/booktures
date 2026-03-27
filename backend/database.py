import os
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base

# SQLite for development (Postgres later).
# Anchor the default DB file to this repository directory so startup CWD does not
# accidentally create/use a different SQLite file.
_DEFAULT_SQLITE_PATH = (Path(__file__).resolve().parent / "booktures.db").as_posix()
DATABASE_URL = os.getenv("BOOKTURES_DATABASE_URL", f"sqlite:///{_DEFAULT_SQLITE_PATH}")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 30}
)

# Session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

# Base class for models
Base = declarative_base()


if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA synchronous=NORMAL;")
        cursor.execute("PRAGMA busy_timeout=30000;")
        cursor.close()


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
