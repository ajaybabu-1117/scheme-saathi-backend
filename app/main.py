from contextlib import asynccontextmanager

print("1. Starting imports...")

from fastapi import FastAPI
print("2. FastAPI imported")

from fastapi.middleware.cors import CORSMiddleware
print("3. CORS imported")

from app.api.v1.router import api_router
print("4. Router imported")

from app.core.config import get_settings
print("5. Config imported")

from app.core.logging import setup_logging
print("6. Logging imported")

from app.middleware.request_context import RequestContextMiddleware
print("7. Middleware imported")

from app.services.dataset_service import dataset_service
print("8. Dataset service imported")

setup_logging()
print("9. Logging setup complete")

settings = get_settings()
print("10. Settings loaded")


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("11. Application startup")
    yield
    print("12. Application shutdown")


print("13. Creating FastAPI app")

app = FastAPI(
    title="SCHEME SAATHI Backend",
    description="AI-powered government scheme assistant backend for India",
    version="1.0.0",
    lifespan=lifespan,
)

print("14. FastAPI app created")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

print("15. CORS middleware added")

app.add_middleware(RequestContextMiddleware)

print("16. Request context middleware added")

app.include_router(api_router, prefix=settings.api_v1_prefix)

print("17. API router included")


@app.get("/health", tags=["Health"])
def health():
    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.app_env,
    }


print("18. Application initialization complete")
