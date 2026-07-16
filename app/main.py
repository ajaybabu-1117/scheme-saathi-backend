from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.middleware.request_context import RequestContextMiddleware

# Initialize logging and settings
setup_logging()
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup and shutdown events.
    Put future initialization code here:
    - Database connections
    - Redis connection
    - Firebase initialization
    - Background jobs
    - Scheduled tasks
    """

    print("🚀 SCHEME SAATHI Backend started successfully")

    # Example:
    # await redis_service.connect()
    # await notification_service.start()

    yield

    print("🛑 SCHEME SAATHI Backend shutting down")

    # Example:
    # await redis_service.disconnect()


app = FastAPI(
    title="SCHEME SAATHI Backend",
    description="AI-powered Government Scheme Assistant for India",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request context middleware
app.add_middleware(RequestContextMiddleware)

# Register all API routes
app.include_router(
    api_router,
    prefix=settings.api_v1_prefix,
)


@app.get("/", tags=["Root"])
def root():
    """
    Root endpoint.
    Useful for Render health checks and browser testing.
    """
    return {
        "message": "🚀 SCHEME SAATHI Backend is running",
        "version": "1.0.0",
        "environment": settings.app_env,
        "docs": "/docs",
        "health": "/health",
        "api_prefix": settings.api_v1_prefix,
    }


@app.get("/health", tags=["Health"])
def health():
    """
    Health check endpoint.
    """
    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.app_env,
        "version": "1.0.0",
    }
