"""
app/main.py
FastAPI application factory with all middleware, routes, and lifecycle hooks.
"""
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.core.config import settings
from app.core.logging import setup_logging, get_logger
from app.api.routes import download, auth, history
from app.services.cache import close_redis

# ── Initialize logging first ──────────────────────────────
setup_logging()
logger = get_logger(__name__)

# ── Rate limiter ──────────────────────────────────────────
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[f"{settings.rate_limit_requests_per_minute}/minute"],
    storage_uri=settings.redis_url,
)


# ── App lifecycle ──────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("startup", env=settings.app_env, version="1.0.0")
    Path(settings.temp_dir).mkdir(parents=True, exist_ok=True)

    # Auto create all database tables on startup
    try:
        from app.db.session import engine, Base
        from app.db import models  # noqa — registers all models
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("database_tables_created_successfully")
    except Exception as e:
        logger.error(f"database_setup_error: {e}")

    yield

    # Shutdown
    await close_redis()
    logger.info("shutdown")


# ── FastAPI app ────────────────────────────────────────────
app = FastAPI(
    title="Smart Media Fetcher API",
    description="Production-grade universal media downloader API.",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# ── Rate Limiting ──────────────────────────────────────────
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── CORS ──────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)

# ── Security headers ───────────────────────────────────────
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"]  = "nosniff"
    response.headers["X-Frame-Options"]         = "DENY"
    response.headers["X-XSS-Protection"]        = "1; mode=block"
    response.headers["Referrer-Policy"]         = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"]      = "geolocation=(), microphone=(), camera=()"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    # Remove server info
    response.headers.pop("server", None)
    response.headers.pop("x-powered-by", None)
    return response

# ── Request logging ────────────────────────────────────────
@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info("request_start",
                method=request.method,
                path=request.url.path,
                ip=request.client.host if request.client else "unknown")
    response = await call_next(request)
    logger.info("request_end",
                method=request.method,
                path=request.url.path,
                status=response.status_code)
    return response

# ── Global exception handler ───────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("unhandled_exception",
                 path=request.url.path,
                 error=str(exc),
                 exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred. Please try again."},
    )

# ── API Routes ─────────────────────────────────────────────
app.include_router(download.router, prefix=settings.api_v1_prefix)
app.include_router(auth.router,     prefix=settings.api_v1_prefix)
app.include_router(history.router,  prefix=settings.api_v1_prefix)

# ── Health check ───────────────────────────────────────────
@app.get("/health", tags=["system"])
async def health_check():
    return {"status": "ok", "service": settings.app_name, "version": "1.0.0"}

# ── Serve frontend ─────────────────────────────────────────
frontend_dir = Path(__file__).parent.parent.parent / "frontend"
if frontend_dir.exists():
    app.mount(
        "/static",
        StaticFiles(directory=str(frontend_dir / "static")),
        name="static",
    )
    templates = Jinja2Templates(directory=str(frontend_dir / "templates"))

    @app.get("/", include_in_schema=False)
    async def serve_index(request: Request):
        return templates.TemplateResponse("index.html", {"request": request})

    @app.get("/downloads", include_in_schema=False)
    async def serve_downloads(request: Request):
        return templates.TemplateResponse("downloads.html", {"request": request})

    @app.get("/settings", include_in_schema=False)
    async def serve_settings(request: Request):
        return templates.TemplateResponse("settings.html", {"request": request})

    @app.get("/faq", include_in_schema=False)
    async def serve_faq(request: Request):
        return templates.TemplateResponse("faq.html", {"request": request})
