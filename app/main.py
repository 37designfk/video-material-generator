"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router as api_router
from app.api.auth_routes import router as auth_router
from app.config import get_settings
from app.models.job import init_db
from app.utils.logger import get_logger, setup_logging

# Initialize logging
setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan handler.

    Sets up resources on startup and cleans up on shutdown.
    """
    # Startup
    settings = get_settings()
    settings.ensure_directories()

    # Initialize database
    try:
        init_db()
        logger.info("database_initialized")
    except Exception as e:
        logger.warning("database_init_failed", error=str(e))

    logger.info(
        "application_started",
        storage_base=str(settings.storage_base_path),
        api_port=settings.api_port,
    )

    yield

    # Shutdown
    logger.info("application_shutdown")


# Create FastAPI application
app = FastAPI(
    title="Video Material Generator API",
    description="Generate HTML learning materials from video content with AI-powered transcription and OCR.",
    version="0.2.0",
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router, prefix="/api", tags=["api"])
app.include_router(auth_router, prefix="/api", tags=["auth"])

# Mount static files for UI
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/", include_in_schema=False)
async def root():
    """Redirect root to UI."""
    settings = get_settings()
    if settings.require_auth:
        return RedirectResponse(url="/static/login.html")
    return RedirectResponse(url="/static/index.html")


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
    )
