"""
Database Module: Handles SQLAlchemy engine configuration, session management,
and automatic schema/database initialization.
"""

import os
from sqlalchemy import create_engine, text, exc
from sqlalchemy.engine import url
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

DEFAULT_DB_URL = "postgresql://postgres:rmcf@localhost:5432/booktures"
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_DB_URL)

if DATABASE_URL == DEFAULT_DB_URL:
    print("⚠️ Warning: Using default hardcoded DATABASE_URL. Ensure PostgreSQL password is 'rmcf'.")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    """Dependency for obtaining a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def _ensure_database_exists():
    """Checks if the target database exists, and creates it if it doesn't."""
    target_url = url.make_url(DATABASE_URL)
    db_name = target_url.database

    # Construct a URL to the default 'postgres' database to perform administrative tasks
    admin_url = target_url.set(database="postgres")
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")

    with admin_engine.connect() as conn:
        try:
            # Check if database exists
            result = conn.execute(text("SELECT 1 FROM pg_database WHERE datname = :db_name"), {"db_name": db_name})
            if not result.scalar():
                print(f"Creating database '{db_name}'...")
                conn.execute(text(f'CREATE DATABASE "{db_name}"'))
        except exc.OperationalError as e:
            print(f"ℹ️ Database existence check skipped: {e}")

def init_db():
    """Initializes the database, creating the vector extension and tables."""
    try:
        _ensure_database_exists()
    except Exception as e:
        print(f"⚠️ Could not verify/create database: {e}")

    import models  # Import here to avoid circular dependencies
    Base.metadata.create_all(bind=engine)