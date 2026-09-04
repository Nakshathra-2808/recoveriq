# RecoverIQ API Reference

## Base URLs
- Development: `http://localhost:8000`
- API Prefix: `/api/v1`

## Authentication & Authorization

All protected endpoints require a valid Supabase access token (JWT) passed in the standard `Authorization` header:

```http
Authorization: Bearer <supabase_jwt_access_token>
```

### JWT Verification Method
- **Key Discovery**: Backend verifies JWTs using the Supabase project's JWKS endpoint (`/auth/v1/.well-known/jwks.json`) matching the token's `kid` header.
- **Allowed Algorithms**: Strictly whitelisted to `ES256`, `RS256`, `ES384`, `RS384`, `ES512`, `RS512` (asymmetric), and `HS256` (symmetric fallback). Wildcard algorithms and insecure modes (`none`) are blocked.
- **Key Caching**: Public keys and JWKS sets are cached in memory (5-minute TTL) for zero per-request network overhead.
- **Required Claims**: `exp` (expiration), `sub` (user UUID), and `aud = "authenticated"`.

### Authentication Errors:
- `401 Unauthorized`: Missing `Authorization` header, invalid JWT signature, expired token, unsupported algorithm, missing `sub` claim, or invalid audience.
- `403 Forbidden`: Authenticated user lacks an active profile, associated merchant organization is deactivated, or user's role lacks permissions for the requested operation.
- `503 Service Unavailable`: Backend server has not configured Supabase authentication URL or database service keys.

---

## Endpoints

### 1. Health Checks

#### Root Health Check
- `GET /health`
- **Response (`200 OK`)**:
  ```json
  {
    "status": "ok",
    "service": "recoveriq-backend",
    "version": "0.1.0"
  }
  ```

#### API V1 Health Check
- `GET /api/v1/health`

---

### 2. Authentication & Identity Endpoints

#### Get Current Authenticated User & Merchant Profile
- `GET /api/v1/auth/me`
- **Authentication**: Required (`Bearer <JWT>`)
- **Response (`200 OK`)**:
  ```json
  {
    "user_id": "11111111-2222-3333-4444-555555555555",
    "email": "merchant@acmeretail.example.com",
    "merchant_id": "00000000-0000-0000-0000-000000000001",
    "merchant_name": "Acme Retail India",
    "role": "owner"
  }
  ```

---

### 3. Recovery Engine Endpoints (`/api/v1/recovery`)

#### Create and Run Recovery Batch
- `POST /api/v1/recovery/batches`
- **Permissions**: `owner`, `admin`, `operator`
- **Request Body**:
  ```json
  {
    "name": "September Ingestion Batch",
    "description": "Failed payment recovery batch",
    "seed_synthetic_count": 6
  }
  ```
- **Response (`200 OK`)**: `BatchRunResponse` containing processed cases, total recovered amount, baseline recovery, incremental lift %, and case statuses.

#### Quick Seed & Execute Demo Batch
- `POST /api/v1/recovery/seed-demo-batch`
- **Permissions**: `owner`, `admin`, `operator`
- **Description**: Convenience endpoint for demo and local development. Ingests 6 diverse synthetic payment failures and runs the full 9-stage recovery engine.

#### List Recovery Cases
- `GET /api/v1/recovery/cases`
- **Query Parameters**:
  - `status` (optional): Filter by case status (`DETECTED`, `DIAGNOSED`, `DECISION_READY`, `APPROVED`, `EXECUTING`, `RECOVERED`, `WAITING`, `STOPPED`, `ESCALATED`, `FAILED`)
  - `limit` (optional, default 50)
- **Response (`200 OK`)**: Array of `RecoveryCaseResponse`.

#### Get Recovery Case Details
- `GET /api/v1/recovery/cases/{case_id}`
- **Description**: Returns detailed case record including payment failure diagnostics, executed actions, verifiable outcomes, and immutable audit logs.
- **Response (`200 OK`)**: `CaseDetailResponse`.

#### Execute Recovery Step on Single Case
- `POST /api/v1/recovery/cases/{case_id}/run`
- **Permissions**: `owner`, `admin`, `operator`
- **Description**: Advances a single case through the next recovery cycle.
- **Response (`200 OK`)**: `RecoveryCaseResponse`.

#### Get Recovery Benchmark Metrics
- `GET /api/v1/recovery/metrics`
- **Description**: Returns aggregated metrics comparing RecoverIQ recovery vs. standard fixed baseline.
- **Response (`200 OK`)**:
  ```json
  {
    "merchant_id": "00000000-0000-0000-0000-000000000001",
    "total_revenue_at_risk": 35948.00,
    "recoveriq_recovered_revenue": 25198.00,
    "baseline_recovered_revenue": 8748.00,
    "incremental_revenue_recovered": 16450.00,
    "recovery_lift_percentage": 188.04,
    "total_cases_processed": 6,
    "total_cases_recovered": 4,
    "overall_recovery_rate": 0.6667,
    "success_rate_by_category": {
      "NETWORK_TIMEOUT": 0.85,
      "GATEWAY_ERROR": 0.80,
      "INSUFFICIENT_FUNDS": 0.72,
      "USER_DROPPED": 0.78
    },
    "top_recovery_actions": []
  }
  ```

---

## Core Schema Enums & State Mappings

### Root Cause Categories (`payment_failures.root_cause_category`)
- `NETWORK_TIMEOUT`, `GATEWAY_ERROR`, `INSUFFICIENT_FUNDS`, `USER_DROPPED`, `CARD_LIMIT_EXCEEDED`, `FRAUD_DECLINE`, `SYSTEM_DOWN`, `AUTHENTICATION_FAILURE`, `EXPIRED_CARD`, `OTHER`

### Recovery Action Types (`recovery_actions.action_type`)
- `RETRY_NOW`, `RETRY_LATER`, `PAYMENT_UPDATE`, `REMINDER`, `ESCALATE`, `STOP`

### Execution Modes (`recovery_actions.execution_mode`)
- `RAZORPAY_TEST`, `SIMULATION`, `DRY_RUN`

### Recovery Case Statuses (`recovery_cases.status`)
- `DETECTED`, `DIAGNOSED`, `DECISION_READY`, `APPROVED`, `EXECUTING`, `RECOVERED`, `WAITING`, `STOPPED`, `ESCALATED`, `FAILED`
