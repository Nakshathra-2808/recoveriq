from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


@router.get("/health", response_model=HealthResponse, summary="Health Check")
async def health_check() -> HealthResponse:
    """
    Returns the health status of the backend service.
    """
    return HealthResponse(
        status="ok",
        service="recoveriq-backend",
        version="0.1.0"
    )
