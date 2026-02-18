from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
import os

# 1. Use environment variables
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./booktures.db")

# 2. Engine configuration
# check_same_thread is only needed for SQLite
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    DATABASE_URL, 
    connect_args=connect_args,
    echo=False # Set to True to see SQL logs in the terminal
)

# 3. Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 4. Modern Base class
class Base(DeclarativeBase):
    pass