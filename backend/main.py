from fastapi import FastAPI
from api.routes import router

app = FastAPI(title="Booktures Backend")

app.include_router(router)

@app.get("/")
def root():
    return {"status": "Booktures backend running"}
