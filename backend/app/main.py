from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.v1.router import api_router
from app.api.v1.endpoints.health import HealthResponse

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Adaptive AI Revenue Recovery Agent for Razorpay Track 03",
    version="0.1.0",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url=f"{settings.API_V1_STR}/docs",
    redoc_url=f"{settings.API_V1_STR}/redoc",
)

# Set up CORS middleware
if settings.ALLOWED_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Include API v1 router
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def root_health_check() -> HealthResponse:
    """
    Root level health check endpoint.
    """
    return HealthResponse(
        status="ok",
        service="recoveriq-backend",
        version="0.1.0"
    )


@app.get("/", tags=["Root"])
async def root():
    return {
        "message": "Welcome to RecoverIQ Backend API",
        "docs": f"{settings.API_V1_STR}/docs",
        "health": "/health"
    }
