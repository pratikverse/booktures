from fastapi import FastAPI
from database import engine, Base, ensure_sqlite_schema
from models import book, page, character, page_character  # ensure models register with Base
from api.routes import router

Base.metadata.create_all(bind=engine)
ensure_sqlite_schema()

app = FastAPI(title="Booktures Backend")

app.include_router(router)

@app.get("/")
def root():
    return {"status": "Booktures backend running"}
