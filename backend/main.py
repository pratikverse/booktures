from fastapi import FastAPI
from database import engine, Base
from models import book, page, character  # ensure models register with Base
from api.routes import router

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Booktures Backend")

app.include_router(router)

@app.get("/")
def root():
    return {"status": "Booktures backend running"}
