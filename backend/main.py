from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from database import engine, Base, ensure_sqlite_schema
from models import (  # ensure models register with Base
    book,
    page,
    character,
    page_character,
    page_asset,
    generation_job,
)
from api.routes import router
from services.generation_queue_service import start_worker, stop_worker
from services.settings_service import apply_env_file

apply_env_file()
Base.metadata.create_all(bind=engine)
ensure_sqlite_schema()

app = FastAPI(title="Booktures Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
_BACKEND_ROOT = Path(__file__).resolve().parent
_IMAGE_DIR = _BACKEND_ROOT / "storage" / "images"
_PDF_DIR = _BACKEND_ROOT / "storage" / "pdfs"
app.mount(
    "/storage/images",
    StaticFiles(directory=str(_IMAGE_DIR), check_dir=False),
    name="storage-images",
)
app.mount(
    "/storage/pdfs",
    StaticFiles(directory=str(_PDF_DIR), check_dir=False),
    name="storage-pdfs",
)


@app.on_event("startup")
def on_startup():
    start_worker()


@app.on_event("shutdown")
def on_shutdown():
    stop_worker()


@app.get("/")
def root():
    return {"status": "Booktures backend running"}
