"""
Authentication module for Supabase JWT verification and multi-tenant authorization.
Validates bearer tokens issued by Supabase Auth using JWKS (JSON Web Key Set) for
asymmetric signing keys (e.g., ES256, RS256) with secure symmetric fallback (HS256).
Resolves the authenticated user's merchant profile without trusting client-supplied identifiers.
"""
from typing import Optional, Dict, Any, List, Callable
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from jwt.exceptions import (
    ExpiredSignatureError,
    InvalidTokenError,
    InvalidAudienceError,
    PyJWKClientError,
)

from app.core.config import settings
from app.schemas.auth import AuthenticatedUser, MerchantAuthContext
from app.services.profile_service import profile_service

security = HTTPBearer(auto_error=False)

# Explicitly permitted cryptographic algorithms for Supabase tokens.
# Prevents algorithm confusion and forbids insecure algorithms like 'none' or wildcard matching.
ALLOWED_ASYMMETRIC_ALGORITHMS = ["ES256", "RS256", "ES384", "RS384", "ES512", "RS512"]
ALLOWED_SYMMETRIC_ALGORITHMS = ["HS256"]
ALLOWED_ALGORITHMS = ALLOWED_ASYMMETRIC_ALGORITHMS + ALLOWED_SYMMETRIC_ALGORITHMS

_jwks_client: Optional[jwt.PyJWKClient] = None
_cached_jwks_url: Optional[str] = None


def get_jwks_client() -> Optional[jwt.PyJWKClient]:
    """
    Returns a cached PyJWKClient configured with the Supabase project's JWKS endpoint.
    Caches signing keys and JWK sets in-memory with automatic TTL expiration to avoid
    redundant network round-trips on every request.
    """
    global _jwks_client, _cached_jwks_url

    jwks_url = settings.SUPABASE_JWKS_URL or (
        f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1/.well-known/jwks.json"
        if settings.SUPABASE_URL else None
    )

    if not jwks_url:
        return None

    if _jwks_client is None or _cached_jwks_url != jwks_url:
        _cached_jwks_url = jwks_url
        _jwks_client = jwt.PyJWKClient(
            uri=jwks_url,
            cache_keys=True,
            max_cached_keys=16,
            cache_jwk_set=True,
            lifespan=300,  # Cache JWKS for 5 minutes
            timeout=10.0
        )

    return _jwks_client


def verify_supabase_jwt(token: str) -> Dict[str, Any]:
    """
    Decodes and cryptographically verifies a Supabase access token (JWT).
    1. Inspects the JWT header to determine the signing algorithm and key ID (kid).
    2. Uses the project's JWKS endpoint for asymmetric signing keys (ES256, RS256, etc.).
    3. Falls back securely to SUPABASE_JWT_SECRET if symmetric HS256 is configured.
    4. Validates signature, expiration (exp), audience ('authenticated'), and subject (sub).
    """
    try:
        header = jwt.get_unverified_header(token)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication token: malformed header ({str(e)})",
            headers={"WWW-Authenticate": "Bearer"},
        )

    alg = header.get("alg")
    if not alg or alg not in ALLOWED_ALGORITHMS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication token: unsupported algorithm '{alg}'",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        if alg in ALLOWED_ASYMMETRIC_ALGORITHMS:
            jwks_client = get_jwks_client()
            if not jwks_client:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Supabase URL is not configured on this server for JWKS verification."
                )

            try:
                signing_key = jwks_client.get_signing_key_from_jwt(token)
                verification_key = signing_key.key
            except PyJWKClientError as e:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=f"Invalid authentication token: verification key not found ({str(e)})",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            payload = jwt.decode(
                token,
                verification_key,
                algorithms=[alg],
                audience="authenticated",
                options={"require": ["exp", "sub", "aud"]}
            )

        elif alg in ALLOWED_SYMMETRIC_ALGORITHMS:
            if not settings.SUPABASE_JWT_SECRET:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Supabase authentication secret is not configured for symmetric verification."
                )

            payload = jwt.decode(
                token,
                settings.SUPABASE_JWT_SECRET,
                algorithms=["HS256"],
                audience="authenticated",
                options={"require": ["exp", "sub", "aud"]}
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid authentication token: algorithm '{alg}' is not permitted.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not payload.get("sub"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token claims: subject identifier missing",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return payload

    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has expired.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except InvalidAudienceError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token: audience claim must be 'authenticated'.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> AuthenticatedUser:
    """
    FastAPI dependency to extract and verify the current authenticated Supabase user.
    Rejects missing or invalid tokens with HTTP 401.
    """
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = verify_supabase_jwt(credentials.credentials)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token claims: subject identifier missing",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return AuthenticatedUser(
        id=user_id,
        email=payload.get("email"),
        app_metadata=payload.get("app_metadata", {}),
        user_metadata=payload.get("user_metadata", {}),
        raw_claims=payload
    )


async def get_current_merchant_context(
    current_user: AuthenticatedUser = Depends(get_current_user)
) -> MerchantAuthContext:
    """
    FastAPI dependency that securely resolves the authenticated user's merchant organization.
    Flow: auth.users.id -> profiles.id -> profiles.merchant_id -> merchants.
    Guarantees that tenant context is determined strictly server-side.
    """
    return await profile_service.get_merchant_context_by_user_id(
        user_id=current_user.id,
        email_hint=current_user.email
    )


def require_roles(allowed_roles: List[str]) -> Callable:
    """
    Dependency factory to enforce Role-Based Access Control (RBAC).
    Allowed roles in RecoverIQ: 'owner', 'admin', 'operator', 'viewer'.
    """
    async def role_checker(
        auth_context: MerchantAuthContext = Depends(get_current_merchant_context)
    ) -> MerchantAuthContext:
        if auth_context.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"User role '{auth_context.role}' does not have permission for this operation. Required: {allowed_roles}"
            )
        return auth_context

    return role_checker
