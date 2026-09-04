import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.v1.endpoints import health, auth, recovery
from app.api.v1.endpoints.health import HealthResponse

logger = logging.getLogger("uvicorn.info")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Safe startup logging (strictly zero secrets printed)
    supabase_status = "CONFIGURED" if settings.SUPABASE_URL and settings.SUPABASE_SERVICE_ROLE_KEY else "LOCAL_MOCK_STORE"
    llm_status = f"{settings.LLM_PROVIDER} (key present)" if settings.LLM_API_KEY else f"{settings.LLM_PROVIDER} (deterministic fallback)"
    razorpay_status = f"{settings.RAZORPAY_ENVIRONMENT} sandbox (key present)" if settings.RAZORPAY_KEY_ID else "simulation only"

    logger.info("==================================================")
    logger.info(f"Starting {settings.PROJECT_NAME} v0.1.0")
    logger.info(f"Environment       : {settings.ENVIRONMENT}")
    logger.info(f"API Prefix        : {settings.API_V1_STR}")
    logger.info(f"Allowed Origins   : {settings.ALLOWED_ORIGINS}")
    logger.info(f"Supabase Backend  : {supabase_status}")
    logger.info(f"AI Diagnosis Layer: {llm_status}")
    logger.info(f"Razorpay Adapter  : {razorpay_status}")
    logger.info("Default Exec Mode : SIMULATION")
    logger.info("==================================================")
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Adaptive AI Revenue Recovery Agent for Razorpay Track 03",
    version="0.1.0",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url=f"{settings.API_V1_STR}/docs",
    redoc_url=f"{settings.API_V1_STR}/redoc",
    lifespan=lifespan,
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

# Direct v1 endpoint router registration
app.include_router(health.router, prefix=settings.API_V1_STR, tags=["Health"])
app.include_router(auth.router, prefix=f"{settings.API_V1_STR}/auth", tags=["Authentication"])
app.include_router(recovery.router, prefix=f"{settings.API_V1_STR}/recovery", tags=["Recovery Engine"])


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
