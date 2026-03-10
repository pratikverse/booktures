from fastapi import FastAPI
from database import engine, Base, ensure_sqlite_schema
from models import (  # ensure models register with Base
    book,
    page,
    character,
    page_character,
    page_asset,
    generation_job,
    page_evaluation,
)
from api.routes import router
from services.generation_queue_service import start_worker, stop_worker

Base.metadata.create_all(bind=engine)
ensure_sqlite_schema()

app = FastAPI(title="Booktures Backend")

app.include_router(router)


@app.on_event("startup")
def on_startup():
    start_worker()


@app.on_event("shutdown")
def on_shutdown():
    stop_worker()


@app.get("/")
def root():
    return {"status": "Booktures backend running"}
