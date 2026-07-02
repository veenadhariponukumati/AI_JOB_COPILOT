"""FastAPI application entry point.

Production-style REST API for the AI Job Copilot platform.
"""

import traceback
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import time

from src.api.routes.analysis import router as analysis_router
from src.api.routes.quiz import router as quiz_router
from src.api.routes.users import router as users_router, feedback_router
from src.cache.cache_manager import get_cache
from src.core.config import get_settings
from src.core.exceptions import AppException
from src.core.logger import get_logger

settings = get_settings()
logger = get_logger(__name__)

# ─── App Initialization ──────────────────────────────────────────────────────

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AI-powered ATS Resume Optimization Platform with RAG, "
    "hybrid matching, and explainable scoring.",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ─── Middleware ───────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://*.vercel.app", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_timing_header(request: Request, call_next):
    """Add request processing time to response headers."""
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start
    response.headers["X-Process-Time"] = f"{duration:.4f}"
    return response


# ─── Exception Handlers ──────────────────────────────────────────────────────


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    tb = traceback.format_exc()
    logger.error(f"Unhandled 500 on {request.method} {request.url.path}:\n{tb}")
    return JSONResponse(status_code=500, content={"detail": f"{type(exc).__name__}: {exc}"})


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    """Handle custom application exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "message": exc.message,
            "error_code": type(exc).__name__,
        },
    )


# ─── Routes ──────────────────────────────────────────────────────────────────

app.include_router(analysis_router, tags=["Analysis"])
app.include_router(quiz_router, tags=["Quiz"])
app.include_router(users_router, tags=["Users"])
app.include_router(feedback_router, tags=["Feedback"])


# ─── Health & Utility Endpoints ──────────────────────────────────────────────


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "version": settings.APP_VERSION,
        "app": settings.APP_NAME,
    }


@app.get("/metrics/cache")
async def cache_metrics():
    """Get cache performance metrics."""
    cache = get_cache()
    return {
        "success": True,
        "metrics": cache.get_metrics(),
    }


# ─── Lambda Handler (for AWS Lambda deployment) ──────────────────────────────

try:
    from mangum import Mangum
    handler = Mangum(app)
except ImportError:
    # Mangum not installed; running locally
    handler = None
