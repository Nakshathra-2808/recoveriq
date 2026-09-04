import time
import jwt
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from cryptography.hazmat.primitives.asymmetric import rsa, ec
from fastapi import status, FastAPI, Depends
from fastapi.testclient import TestClient
from jwt.exceptions import PyJWKClientError

from app.main import app
from app.core.config import settings
from app.schemas.auth import AuthenticatedUser, MerchantAuthContext
from app.auth.supabase import (
    get_current_user,
    get_current_merchant_context,
    require_roles,
    verify_supabase_jwt,
    get_jwks_client,
)
from app.services.profile_service import profile_service

TEST_JWT_SECRET = "test-jwt-secret-key-32-chars-long!"
TEST_USER_ID = "11111111-2222-3333-4444-555555555555"
TEST_USER_EMAIL = "owner@acmeretail.example.com"
TEST_MERCHANT_ID = "00000000-0000-0000-0000-000000000001"
TEST_MERCHANT_NAME = "Acme Retail India"

# Generate RSA key pair for testing asymmetric RS256 signing
RSA_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
RSA_PUBLIC_KEY = RSA_PRIVATE_KEY.public_key()
WRONG_RSA_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)

# Generate EC key pair for testing asymmetric ES256 signing
EC_PRIVATE_KEY = ec.generate_private_key(ec.SECP256R1())
EC_PUBLIC_KEY = EC_PRIVATE_KEY.public_key()


def generate_asymmetric_token(
    user_id: str = TEST_USER_ID,
    email: str = TEST_USER_EMAIL,
    private_key=RSA_PRIVATE_KEY,
    algorithm: str = "RS256",
    kid: str = "test-key-id-1",
    expires_in: int = 3600,
    audience: str = "authenticated",
    include_sub: bool = True
) -> str:
    payload = {
        "email": email,
        "aud": audience,
        "exp": int(time.time()) + expires_in,
        "iat": int(time.time()),
        "role": "authenticated",
        "app_metadata": {"provider": "email"},
        "user_metadata": {"full_name": "Acme Owner"}
    }
    if include_sub:
        payload["sub"] = user_id

    headers = {
        "alg": algorithm,
        "typ": "JWT",
        "kid": kid
    }
    return jwt.encode(payload, private_key, algorithm=algorithm, headers=headers)


def generate_symmetric_token(
    user_id: str = TEST_USER_ID,
    email: str = TEST_USER_EMAIL,
    secret: str = TEST_JWT_SECRET,
    expires_in: int = 3600,
    audience: str = "authenticated",
    include_sub: bool = True
) -> str:
    payload = {
        "email": email,
        "aud": audience,
        "exp": int(time.time()) + expires_in,
        "iat": int(time.time()),
        "role": "authenticated",
        "app_metadata": {"provider": "email"},
        "user_metadata": {"full_name": "Acme Owner"}
    }
    if include_sub:
        payload["sub"] = user_id

    return jwt.encode(payload, secret, algorithm="HS256")


@pytest.fixture(autouse=True)
def setup_test_settings(monkeypatch):
    monkeypatch.setattr(settings, "SUPABASE_JWT_SECRET", TEST_JWT_SECRET)
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://mock.supabase.co")
    monkeypatch.setattr(settings, "SUPABASE_SERVICE_ROLE_KEY", "mock-service-role-key")


# -----------------------------------------------------------------------------
# 1. ASYMMETRIC (JWKS) & SYMMETRIC JWT VERIFICATION TESTS
# -----------------------------------------------------------------------------

def test_valid_asymmetric_rs256_token(client: TestClient):
    """Asymmetric RS256 token signed by Supabase JWKS key is verified successfully."""
    token = generate_asymmetric_token(algorithm="RS256", kid="test-key-rsa")

    mock_signing_key = MagicMock()
    mock_signing_key.key = RSA_PUBLIC_KEY

    with patch("jwt.PyJWKClient.get_signing_key_from_jwt", return_value=mock_signing_key):
        mock_context = MerchantAuthContext(
            user_id=TEST_USER_ID,
            email=TEST_USER_EMAIL,
            profile_id=TEST_USER_ID,
            merchant_id=TEST_MERCHANT_ID,
            merchant_name=TEST_MERCHANT_NAME,
            role="owner",
            is_active=True
        )
        with patch.object(profile_service, "get_merchant_context_by_user_id", new=AsyncMock(return_value=mock_context)):
            response = client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {token}"}
            )
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["user_id"] == TEST_USER_ID
            assert data["email"] == TEST_USER_EMAIL
            assert data["merchant_id"] == TEST_MERCHANT_ID


def test_valid_asymmetric_es256_token(client: TestClient):
    """Asymmetric ES256 token signed by Supabase JWKS key is verified successfully."""
    token = generate_asymmetric_token(
        private_key=EC_PRIVATE_KEY,
        algorithm="ES256",
        kid="test-key-ec"
    )

    mock_signing_key = MagicMock()
    mock_signing_key.key = EC_PUBLIC_KEY

    with patch("jwt.PyJWKClient.get_signing_key_from_jwt", return_value=mock_signing_key):
        payload = verify_supabase_jwt(token)
        assert payload["sub"] == TEST_USER_ID
        assert payload["aud"] == "authenticated"


def test_valid_symmetric_hs256_fallback(client: TestClient):
    """Symmetric HS256 tokens are verified using SUPABASE_JWT_SECRET when configured."""
    token = generate_symmetric_token()
    payload = verify_supabase_jwt(token)
    assert payload["sub"] == TEST_USER_ID
    assert payload["email"] == TEST_USER_EMAIL


def test_missing_auth_header_returns_401(client: TestClient):
    """Requests without Authorization header must return 401."""
    response = client.get("/api/v1/auth/me")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "credentials were not provided" in response.json()["detail"]


def test_invalid_asymmetric_signature_returns_401(client: TestClient):
    """Asymmetric token signed with wrong private key must be rejected with 401."""
    token = generate_asymmetric_token(private_key=WRONG_RSA_PRIVATE_KEY, kid="test-key-rsa")

    mock_signing_key = MagicMock()
    mock_signing_key.key = RSA_PUBLIC_KEY  # Public key corresponding to RSA_PRIVATE_KEY, not WRONG_RSA

    with patch("jwt.PyJWKClient.get_signing_key_from_jwt", return_value=mock_signing_key):
        response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Invalid authentication token" in response.json()["detail"]


def test_invalid_symmetric_signature_returns_401(client: TestClient):
    """Symmetric token with mismatched secret must be rejected with 401."""
    token = generate_symmetric_token(secret="wrong-secret-key-that-does-not-match")
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Invalid authentication token" in response.json()["detail"]


def test_expired_asymmetric_jwt_returns_401(client: TestClient):
    """Expired asymmetric token must be rejected with 401."""
    token = generate_asymmetric_token(expires_in=-300, kid="test-key-rsa")

    mock_signing_key = MagicMock()
    mock_signing_key.key = RSA_PUBLIC_KEY

    with patch("jwt.PyJWKClient.get_signing_key_from_jwt", return_value=mock_signing_key):
        response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "expired" in response.json()["detail"].lower()


def test_unsupported_algorithm_rejected_401(client: TestClient):
    """Tokens with disallowed algorithms (e.g. 'none', 'HS512', or arbitrary strings) must be rejected with 401."""
    # Test 'none' algorithm
    none_token = jwt.encode(
        {"sub": TEST_USER_ID, "aud": "authenticated", "exp": int(time.time()) + 3600},
        key="",
        algorithm="none"
    )
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {none_token}"}
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "unsupported algorithm" in response.json()["detail"].lower()


def test_missing_subject_claim_returns_401(client: TestClient):
    """Token missing the 'sub' (subject/user ID) claim must be rejected with 401."""
    token = generate_symmetric_token(include_sub=False)
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "subject" in response.json()["detail"].lower() or "missing" in response.json()["detail"].lower()


def test_invalid_audience_returns_401(client: TestClient):
    """Token with audience other than 'authenticated' must return 401."""
    token = generate_symmetric_token(audience="invalid-audience")
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "audience" in response.json()["detail"].lower()


def test_jwks_signing_key_not_found_returns_401(client: TestClient):
    """When the kid in the token is not present in the JWKS, reject with 401."""
    token = generate_asymmetric_token(kid="non-existent-kid")

    with patch("jwt.PyJWKClient.get_signing_key_from_jwt", side_effect=PyJWKClientError("Key not found")):
        response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "key not found" in response.json()["detail"].lower()


def test_malformed_jwt_returns_401(client: TestClient):
    """Malformed token string must return 401."""
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer not-a-valid-jwt-token"}
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


# -----------------------------------------------------------------------------
# 2. PROFILE & MERCHANT RESOLUTION TESTS
# -----------------------------------------------------------------------------

def test_authenticated_user_resolves_profile_and_merchant(client: TestClient):
    """Valid JWT resolves authenticated user's profile and merchant on /api/v1/auth/me."""
    token = generate_symmetric_token()

    mock_context = MerchantAuthContext(
        user_id=TEST_USER_ID,
        email=TEST_USER_EMAIL,
        profile_id=TEST_USER_ID,
        merchant_id=TEST_MERCHANT_ID,
        merchant_name=TEST_MERCHANT_NAME,
        role="owner",
        is_active=True
    )

    with patch.object(profile_service, "get_merchant_context_by_user_id", new=AsyncMock(return_value=mock_context)):
        response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["user_id"] == TEST_USER_ID
        assert data["email"] == TEST_USER_EMAIL
        assert data["merchant_id"] == TEST_MERCHANT_ID
        assert data["merchant_name"] == TEST_MERCHANT_NAME
        assert data["role"] == "owner"


def test_user_without_profile_returns_403(client: TestClient):
    """Authenticated user without a corresponding profile record is blocked."""
    token = generate_symmetric_token(user_id="99999999-9999-9999-9999-999999999999")

    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.json = lambda: []

    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=mock_response)):
        response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "does not have an associated merchant profile" in response.json()["detail"]


def test_inactive_merchant_returns_403(client: TestClient):
    """Authenticated user whose merchant is deactivated is denied access."""
    token = generate_symmetric_token()

    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.json = lambda: [{
        "id": TEST_USER_ID,
        "merchant_id": TEST_MERCHANT_ID,
        "email": TEST_USER_EMAIL,
        "role": "owner",
        "is_active": True,
        "merchants": {
            "id": TEST_MERCHANT_ID,
            "name": TEST_MERCHANT_NAME,
            "is_active": False
        }
    }]

    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=mock_response)):
        response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "inactive" in response.json()["detail"].lower()


# -----------------------------------------------------------------------------
# 3. TENANT ISOLATION & IMPERSONATION RESISTANCE
# -----------------------------------------------------------------------------

def test_client_cannot_impersonate_arbitrary_merchant_id(client: TestClient):
    """
    Passing an arbitrary merchant_id via headers, params, or body does not override
    the server-side resolved merchant tenancy.
    """
    token = generate_symmetric_token()
    malicious_merchant_id = "99999999-9999-9999-9999-999999999999"

    mock_context = MerchantAuthContext(
        user_id=TEST_USER_ID,
        email=TEST_USER_EMAIL,
        profile_id=TEST_USER_ID,
        merchant_id=TEST_MERCHANT_ID,  # True resolved merchant
        merchant_name=TEST_MERCHANT_NAME,
        role="owner",
        is_active=True
    )

    with patch.object(profile_service, "get_merchant_context_by_user_id", new=AsyncMock(return_value=mock_context)):
        response = client.get(
            f"/api/v1/auth/me?merchant_id={malicious_merchant_id}",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Merchant-ID": malicious_merchant_id
            }
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["merchant_id"] == TEST_MERCHANT_ID
        assert data["merchant_id"] != malicious_merchant_id


# -----------------------------------------------------------------------------
# 4. ROLE-BASED ACCESS CONTROL (RBAC) TESTS
# -----------------------------------------------------------------------------

def test_viewer_permission_enforcement(client: TestClient):
    """
    Verifies that 'viewer' role is permitted for read-only access but rejected
    for operator/admin write endpoints via require_roles.
    """
    token = generate_symmetric_token()

    viewer_context = MerchantAuthContext(
        user_id=TEST_USER_ID,
        email="viewer@acmeretail.example.com",
        profile_id=TEST_USER_ID,
        merchant_id=TEST_MERCHANT_ID,
        merchant_name=TEST_MERCHANT_NAME,
        role="viewer",
        is_active=True
    )

    # Test viewer on /auth/me (Read allowed)
    with patch.object(profile_service, "get_merchant_context_by_user_id", new=AsyncMock(return_value=viewer_context)):
        response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["role"] == "viewer"

    # Test custom test router requiring operator or above
    test_app = FastAPI()

    @test_app.post("/test-write", dependencies=[Depends(require_roles(["owner", "admin", "operator"]))])
    def write_endpoint():
        return {"status": "success"}

    test_client = TestClient(test_app)

    with patch.object(profile_service, "get_merchant_context_by_user_id", new=AsyncMock(return_value=viewer_context)):
        write_res = test_client.post(
            "/test-write",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert write_res.status_code == status.HTTP_403_FORBIDDEN
        assert "does not have permission" in write_res.json()["detail"]
