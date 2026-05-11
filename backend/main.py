"""
Main Entry Point: Initializes the FastAPI application, mounts middleware/routes,
and manages the application lifespan (startup/shutdown tasks).
"""

import os
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from database import init_db
from services.generation_queue_service import start_worker
from api.routes import router

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Handles startup and shutdown events.
    Ensures the database is initialized and pgvector is enabled.
    """
    print("Initializing database...")
    try:
        # This ensures the DB exists and extensions are enabled before accepting requests
        init_db()
        print("Database initialized successfully.")
    except Exception as e:
        print(f"❌ CRITICAL: Database initialization failed: {e}")
        raise e  # Fail early so you know exactly what's wrong on startup
    
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

# Allow your frontend to talk to the backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount the storage directory so the frontend can access PDFs and Images
if not os.path.exists("storage"):
    os.makedirs("storage")
app.mount("/storage", StaticFiles(directory="storage"), name="storage")

# Include the routes from our api module
app.include_router(router)

@app.get("/")
async def root():
    return {"message": "Welcome to Booktures 2.0 API", "docs": "/docs"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)