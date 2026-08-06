"""
Main Entry Point: Initializes the FastAPI application, mounts middleware/routes,
and manages the application lifespan (startup/shutdown tasks).
"""

import os
import logging
import uvicorn
from fastapi import FastAPI, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from database import init_db
from services.generation_queue_service import start_worker
from services.settings_service import load_persisted_settings
from api.routes import router
from api.limiter import limiter
from api.auth import require_api_key

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Handles startup and shutdown events.
    Ensures the database is initialized and pgvector is enabled.
    """
    logger.info("Initializing database...")
    try:
        # This ensures the DB exists and extensions are enabled before accepting requests
        init_db()
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.critical(f"Database initialization failed: {e}")
        raise e  # Fail early so you know exactly what's wrong on startup

    load_persisted_settings()

    # Start the background generation worker
    start_worker()

    yield
    # Shutdown logic goes here if needed

app = FastAPI(
    title="Booktures API",
    description="Advanced PDF processing and vector storage service.",
    version="2.0.0",
    lifespan=lifespan
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# Allow your frontend to talk to the backend.
# NOTE: allow_credentials=True is invalid together with a wildcard origin per the
# CORS spec (browsers will reject it), so origins must be listed explicitly.
_allowed_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:8080,http://127.0.0.1:8080").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount the storage directory so the frontend can access PDFs and Images
if not os.path.exists("storage"):
    os.makedirs("storage")
app.mount("/storage", StaticFiles(directory="storage"), name="storage")

# Include the routes from our api module
app.include_router(router, dependencies=[Depends(require_api_key)])

@app.get("/")
async def root():
    return {"message": "Welcome to Booktures 2.0 API", "docs": "/docs"}

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/ready")
async def ready():
    from sqlalchemy import text as _text
    from database import engine
    try:
        with engine.connect() as conn:
            conn.execute(_text("SELECT 1"))
        return {"status": "ready"}
    except Exception as e:
        return {"status": "not_ready", "error": str(e)}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)