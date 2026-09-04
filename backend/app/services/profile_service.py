import logging
from typing import Optional, Dict, Any
import httpx
from fastapi import HTTPException, status
from app.core.config import settings
from app.schemas.auth import MerchantAuthContext

logger = logging.getLogger(__name__)


class ProfileService:
    """
    Resolves authenticated Supabase user ID to user profile and merchant organization.
    Ensures that merchant identity is derived server-side from verified database relationships
    rather than trusting any client-supplied parameters.
    """

    def __init__(self, http_client: Optional[httpx.AsyncClient] = None):
        self._http_client = http_client

    async def get_merchant_context_by_user_id(
        self, user_id: str, email_hint: Optional[str] = None
    ) -> MerchantAuthContext:
        """
        Resolves auth.users.id -> profiles -> merchants.
        """
        # If Supabase service credentials are configured, query via PostgREST
        if settings.SUPABASE_URL and settings.SUPABASE_SERVICE_ROLE_KEY:
            try:
                return await self._fetch_from_supabase(user_id, email_hint)
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error querying Supabase for profile resolution: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to resolve merchant profile from authentication provider."
                )
        
        # When Supabase URL/key is not set (e.g. initial setup without env), reject or raise
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service connection is not configured."
        )

    async def _fetch_from_supabase(
        self, user_id: str, email_hint: Optional[str] = None
    ) -> MerchantAuthContext:
        url = f"{settings.SUPABASE_URL.rstrip('/')}/rest/v1/profiles"
        headers = {
            "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
            "Accept": "application/json",
        }
        params = {
            "id": f"eq.{user_id}",
            "select": "id,merchant_id,email,full_name,role,is_active,merchants(id,name,slug,is_active)"
        }

        client = self._http_client or httpx.AsyncClient(timeout=10.0)
        try:
            response = await client.get(url, headers=headers, params=params)
            if response.status_code != 200:
                logger.error(f"Supabase PostgREST returned {response.status_code}: {response.text}")
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Error communicating with database backend."
                )

            records = response.json()
            if not records:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Authenticated user does not have an associated merchant profile."
                )

            profile_data = records[0]
            if not profile_data.get("is_active", True):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="User profile is deactivated."
                )

            merchant_data = profile_data.get("merchants")
            if not merchant_data or not merchant_data.get("is_active", True):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Merchant organization is inactive or not found."
                )

            return MerchantAuthContext(
                user_id=user_id,
                email=profile_data.get("email") or email_hint or "",
                profile_id=profile_data["id"],
                merchant_id=profile_data["merchant_id"],
                merchant_name=merchant_data.get("name", "Unknown Merchant"),
                role=profile_data.get("role", "viewer"),
                is_active=profile_data.get("is_active", True)
            )
        finally:
            if not self._http_client:
                await client.aclose()


profile_service = ProfileService()
