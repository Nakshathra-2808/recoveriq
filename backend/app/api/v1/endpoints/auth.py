from fastapi import APIRouter, Depends
from app.auth.supabase import get_current_merchant_context
from app.schemas.auth import MerchantAuthContext, UserProfileResponse

router = APIRouter()


@router.get("/me", response_model=UserProfileResponse, summary="Get current authenticated user profile")
async def get_me(
    auth_context: MerchantAuthContext = Depends(get_current_merchant_context)
) -> UserProfileResponse:
    """
    Returns verified identity and merchant tenancy information for the authenticated user.
    Never returns secrets, tokens, or hashes.
    """
    return UserProfileResponse(
        user_id=auth_context.user_id,
        email=auth_context.email,
        merchant_id=auth_context.merchant_id,
        merchant_name=auth_context.merchant_name,
        role=auth_context.role
    )
