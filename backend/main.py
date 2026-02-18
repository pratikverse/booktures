from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
from database import engine, Base, SessionLocal
from api.routes import router

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create tables on startup
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Booktures Backend",
    description="Backend for Booktures - Book character tracking",
    version="1.0.0"
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Change to specific domains in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routes
app.include_router(router)

@app.get("/", tags=["Health"])
def health_check():
    """Check if the API is running"""
    return {
        "status": "Booktures backend running",
        "version": "1.0.0"
    }

@app.get("/health/db", tags=["Health"])
def db_health_check():
    """Check database connectivity"""
    try:
        db = SessionLocal()
        db.execute("SELECT 1")
        db.close()
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return {"status": "unhealthy", "database": "disconnected", "error": str(e)}

@app.on_event("startup")
async def startup_event():
    logger.info("Booktures backend starting up")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Booktures backend shutting down")