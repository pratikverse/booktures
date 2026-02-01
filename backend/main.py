from fastapi import FastAPI
from api.routes import router

#for databases
from database import engine, Base
from models.book import Book
from models.page import Page
from models.character import Character

# Create tables in the database
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Booktures Backend")

app.include_router(router)

@app.get("/")
def root():
    return {"status": "Booktures backend running"}
