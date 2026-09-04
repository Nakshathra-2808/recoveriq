from typing import Optional, Dict, Any
from pydantic import BaseModel, EmailStr, Field


class AuthenticatedUser(BaseModel):
    id: str = Field(..., description="Supabase Auth User UUID (sub claim)")
    email: Optional[str] = Field(None, description="User email address")
    app_metadata: Dict[str, Any] = Field(default_factory=dict)
    user_metadata: Dict[str, Any] = Field(default_factory=dict)
    raw_claims: Dict[str, Any] = Field(default_factory=dict)


class MerchantAuthContext(BaseModel):
    user_id: str = Field(..., description="Supabase Auth user ID")
    email: str = Field(..., description="User email address")
    profile_id: str = Field(..., description="Profile record ID")
    merchant_id: str = Field(..., description="Resolved tenant merchant ID")
    merchant_name: str = Field(..., description="Merchant business name")
    role: str = Field(..., description="User role in merchant (owner, admin, operator, viewer)")
    is_active: bool = Field(default=True, description="Active status of profile")


class UserProfileResponse(BaseModel):
    user_id: str = Field(..., description="Authenticated user ID")
    email: str = Field(..., description="Authenticated user email")
    merchant_id: str = Field(..., description="Resolved merchant ID")
    merchant_name: str = Field(..., description="Resolved merchant name")
    role: str = Field(..., description="Role within merchant organization")
