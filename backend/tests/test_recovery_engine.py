import pytest
import time
import jwt
import httpx
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta
from fastapi import status, HTTPException
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import settings
from app.schemas.auth import MerchantAuthContext
from app.schemas.recovery import (
    RootCauseCategory,
    ActionType,
    ExecutionMode,
    CaseStatus,
    OutcomeType,
    CasePriority,
)
from app.services.supabase_db import db, SupabaseDB
from app.services.detection_service import detection_service
from app.services.diagnosis_service import diagnosis_service
from app.services.policy_engine import policy_engine
from app.policies.guardrail_engine import guardrail_engine
from app.services.executor_service import executor_service
from app.services.outcome_service import outcome_service
from app.services.learning_service import learning_service
from app.services.audit_service import audit_service
from app.services.baseline_service import baseline_service
from app.services.synthetic_data import synthetic_generator
from app.services.recovery_engine import recovery_engine
from app.services.profile_service import profile_service

TEST_MERCHANT_ID = "00000000-0000-0000-0000-000000000001"
OTHER_MERCHANT_ID = "00000000-0000-0000-0000-000000000002"
TEST_USER_ID = "11111111-2222-3333-4444-555555555555"
TEST_USER_EMAIL = "operator@acmeretail.example.com"
TEST_JWT_SECRET = "test-jwt-secret-key-32-chars-long!"


def make_token(merchant_id: str = TEST_MERCHANT_ID, role: str = "operator") -> str:
    payload = {
        "sub": TEST_USER_ID,
        "email": TEST_USER_EMAIL,
        "aud": "authenticated",
        "exp": int(time.time()) + 3600,
        "iat": int(time.time()),
        "role": "authenticated",
    }
    return jwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")


@pytest.fixture(autouse=True)
def setup_db(monkeypatch):
    monkeypatch.setattr(settings, "SUPABASE_JWT_SECRET", TEST_JWT_SECRET)
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://mock.supabase.co")
    monkeypatch.setattr(settings, "SUPABASE_SERVICE_ROLE_KEY", "mock-service-role-key")
    db.use_mock_store = True
    db.reset_mock_store()


@pytest.fixture
def auth_mock():
    mock_context = MerchantAuthContext(
        user_id=TEST_USER_ID,
        email=TEST_USER_EMAIL,
        profile_id=TEST_USER_ID,
        merchant_id=TEST_MERCHANT_ID,
        merchant_name="Acme Retail India",
        role="operator",
        is_active=True
    )
    with patch.object(profile_service, "get_merchant_context_by_user_id", new=AsyncMock(return_value=mock_context)):
        yield mock_context


# -----------------------------------------------------------------------------
# 1. DETECTION TESTS
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_detection_creates_case_with_priority():
    """Verify detection scans failed payments and assigns proper priority."""
    seed = await synthetic_generator.generate_demo_batch(TEST_MERCHANT_ID, count=2)
    payment = seed["payments"][0]

    case = await detection_service.detect_and_create_case(payment["id"], TEST_MERCHANT_ID)
    assert case is not None
    assert case["status"] == CaseStatus.DETECTED.value
    assert case["merchant_id"] == TEST_MERCHANT_ID
    assert case["payment_id"] == payment["id"]

    # Check audit log was created
    logs = await db.get_audit_logs(case_id=case["id"], merchant_id=TEST_MERCHANT_ID)
    assert len(logs) >= 1
    assert logs[0]["event_type"] == "CASE_DETECTED"


# -----------------------------------------------------------------------------
# 2. DIAGNOSIS TESTS
# -----------------------------------------------------------------------------

def test_diagnosis_classification_all_causes():
    """Test deterministic diagnostic classifier on all 6 root causes."""
    cases = [
        ({"error_code": "GATEWAY_TIMEOUT", "root_cause_category": "NETWORK_TIMEOUT"}, RootCauseCategory.NETWORK_TIMEOUT, False),
        ({"error_code": "BANK_SYSTEM_DOWN", "root_cause_category": "GATEWAY_ERROR"}, RootCauseCategory.GATEWAY_ERROR, False),
        ({"error_code": "INSUFFICIENT_FUNDS", "root_cause_category": "INSUFFICIENT_FUNDS"}, RootCauseCategory.INSUFFICIENT_FUNDS, False),
        ({"error_code": "OTP_EXPIRED", "root_cause_category": "USER_DROPPED"}, RootCauseCategory.USER_DROPPED, False),
        ({"error_code": "LIMIT_EXCEEDED", "root_cause_category": "CARD_LIMIT_EXCEEDED"}, RootCauseCategory.CARD_LIMIT_EXCEEDED, False),
        ({"error_code": "RISK_FRAUD_DECLINE", "root_cause_category": "FRAUD_DECLINE"}, RootCauseCategory.FRAUD_DECLINE, True),
    ]

    for failure_data, expected_cause, is_terminal in cases:
        diag = diagnosis_service.diagnose_failure(failure_data, {"amount": 1000.0})
        assert diag.root_cause_category == expected_cause
        assert diag.is_terminal_decline == is_terminal
        assert diag.confidence_score >= 0.85


# -----------------------------------------------------------------------------
# 3. ADAPTIVE ACTION SELECTION TESTS
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_adaptive_policy_ranking_and_learning():
    """Test candidate scoring using statistical priors and learning."""
    # NETWORK_TIMEOUT should prioritize RETRY_NOW in cold start
    decision = await policy_engine.select_action(
        case={},
        merchant_id=TEST_MERCHANT_ID,
        root_cause=RootCauseCategory.NETWORK_TIMEOUT,
        retry_count=0
    )
    assert decision.selected_action == ActionType.RETRY_NOW
    assert decision.confidence_score >= 0.80

    # USER_DROPPED should prioritize PAYMENT_UPDATE
    decision_drop = await policy_engine.select_action(
        case={},
        merchant_id=TEST_MERCHANT_ID,
        root_cause=RootCauseCategory.USER_DROPPED,
        retry_count=0
    )
    assert decision_drop.selected_action in (ActionType.PAYMENT_UPDATE, ActionType.REMINDER)


# -----------------------------------------------------------------------------
# 4. DETERMINISTIC GUARDRAIL TESTS
# -----------------------------------------------------------------------------

def test_guardrail_opt_out_enforces_stop():
    """Customer opt-out must override any action to STOP."""
    policy = {"max_retries": 3, "max_communications": 3, "cooldown_minutes": 60, "escalation_threshold_amount": 10000.0}
    customer = {"id": "c1", "is_opted_out": True}
    case = {"amount": 500.0, "retry_count": 0, "communication_count": 0}

    res = guardrail_engine.validate_action(ActionType.RETRY_NOW, case, policy, customer)
    assert res.final_action == ActionType.STOP
    assert res.is_overridden is True
    assert "opted out" in res.override_reason.lower()


def test_guardrail_fraud_decline_enforces_stop():
    """Hard fraud decline must be STOPPED."""
    policy = {"max_retries": 3, "max_communications": 3, "cooldown_minutes": 60, "escalation_threshold_amount": 10000.0}
    case = {"amount": 500.0, "retry_count": 0, "communication_count": 0, "diagnosis_summary": {"root_cause_category": "FRAUD_DECLINE"}}

    res = guardrail_engine.validate_action(ActionType.RETRY_NOW, case, policy, None)
    assert res.final_action == ActionType.STOP
    assert "fraud" in res.override_reason.lower()


def test_guardrail_max_retries_limit():
    """Exceeding max retries must escalate or stop."""
    policy = {"max_retries": 3, "max_communications": 3, "cooldown_minutes": 60, "escalation_threshold_amount": 10000.0}
    case = {"amount": 500.0, "retry_count": 3, "communication_count": 0}

    res = guardrail_engine.validate_action(ActionType.RETRY_NOW, case, policy, None)
    assert res.final_action in (ActionType.STOP, ActionType.ESCALATE)
    assert res.is_overridden is True


def test_guardrail_max_communications_limit():
    """Exceeding max communications must prevent another reminder."""
    policy = {"max_retries": 3, "max_communications": 2, "cooldown_minutes": 60, "escalation_threshold_amount": 10000.0}
    case = {"amount": 500.0, "retry_count": 0, "communication_count": 2}

    res = guardrail_engine.validate_action(ActionType.REMINDER, case, policy, None)
    assert res.final_action != ActionType.REMINDER
    assert res.is_overridden is True


def test_guardrail_high_value_escalation():
    """Payments exceeding threshold must escalate."""
    policy = {"max_retries": 3, "max_communications": 3, "cooldown_minutes": 60, "escalation_threshold_amount": 10000.0, "auto_escalate_vip": True}
    case = {"amount": 15000.0, "retry_count": 0, "communication_count": 0}

    res = guardrail_engine.validate_action(ActionType.RETRY_NOW, case, policy, None)
    assert res.final_action == ActionType.ESCALATE
    assert res.is_overridden is True


# -----------------------------------------------------------------------------
# 5. EXECUTION, OUTCOME, LEARNING & BENCHMARK TESTS
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_full_single_case_pipeline_cycle():
    """Executes the entire 9-stage pipeline on a single case."""
    seed = await synthetic_generator.generate_demo_batch(TEST_MERCHANT_ID, count=1)
    payment = seed["payments"][0]

    case = await detection_service.detect_and_create_case(payment["id"], TEST_MERCHANT_ID)
    updated_case = await recovery_engine.run_single_case_pipeline(case["id"], TEST_MERCHANT_ID, ExecutionMode.SIMULATION)

    assert updated_case["status"] in (CaseStatus.RECOVERED.value, CaseStatus.WAITING.value, CaseStatus.STOPPED.value, CaseStatus.FAILED.value)

    # Check actions and outcomes
    actions = await db.get_recovery_actions(case["id"], TEST_MERCHANT_ID)
    assert len(actions) == 1
    assert actions[0]["execution_mode"] == "SIMULATION"

    outcomes = await db.get_recovery_outcomes(case["id"], TEST_MERCHANT_ID)
    assert len(outcomes) == 1

    # Check statistics learning
    stats = await db.get_action_statistics(TEST_MERCHANT_ID)
    assert len(stats) >= 1
    assert stats[0]["total_attempts"] >= 1


@pytest.mark.asyncio
async def test_batch_recovery_and_baseline_comparison():
    """Runs batch recovery, executes baseline benchmark, and checks lift metrics."""
    seed = await synthetic_generator.generate_demo_batch(TEST_MERCHANT_ID, count=6)
    batch_id = seed["batch_id"]

    run_res = await recovery_engine.run_batch_recovery(batch_id, TEST_MERCHANT_ID, ExecutionMode.SIMULATION)

    assert run_res.total_records == 6
    assert run_res.processed_records == 6
    assert run_res.total_amount_at_risk > 0
    assert run_res.total_recovered_amount >= 0
    assert run_res.status == "COMPLETED"

    # Baseline results were created
    baselines = await db.get_baseline_results_by_batch(batch_id, TEST_MERCHANT_ID)
    assert len(baselines) == 6


# -----------------------------------------------------------------------------
# 6. IDEMPOTENT DEMO SEEDING & HTTP RELIABILITY TESTS
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_repeated_demo_batch_seeding_idempotent():
    """Verify repeated calls to generate_demo_batch reuse existing customers without duplicate key errors."""
    # First seed run
    run1 = await synthetic_generator.generate_demo_batch(TEST_MERCHANT_ID, count=6)
    assert len(run1["payments"]) == 6
    assert len(db._mock_db["customers"]) == 6

    # Second seed run (must reuse same 6 customers, not create 6 duplicates)
    run2 = await synthetic_generator.generate_demo_batch(TEST_MERCHANT_ID, count=6)
    assert len(run2["payments"]) == 6
    assert len(db._mock_db["customers"]) == 6  # Customer count remains 6

    # Batches and payments are unique
    assert run1["batch_id"] != run2["batch_id"]
    run1_pay_ids = {p["id"] for p in run1["payments"]}
    run2_pay_ids = {p["id"] for p in run2["payments"]}
    assert run1_pay_ids.isdisjoint(run2_pay_ids)


@pytest.mark.asyncio
async def test_supabase_transient_timeout_retry_success():
    """Verify that transient ConnectTimeout is retried with backoff and succeeds."""
    mock_client = AsyncMock()
    # 1st attempt: raises ConnectTimeout; 2nd attempt: returns 200 OK
    mock_client.request = AsyncMock(
        side_effect=[
            httpx.ConnectTimeout("Connection timed out"),
            MagicMock(status_code=200, json=lambda: [{"id": "1", "status": "ok"}], text='[{"id":"1"}]')
        ]
    )

    test_db = SupabaseDB(http_client=mock_client, use_mock_store=False)
    res = await test_db._execute_with_retry(
        method="GET",
        url="https://mock.supabase.co/rest/v1/health",
        operation_name="test_retry",
        headers={"apikey": "test"},
        max_retries=3
    )

    assert res.status_code == 200
    assert mock_client.request.call_count == 2


@pytest.mark.asyncio
async def test_supabase_permanent_4xx_not_retried():
    """Verify that permanent 4xx client error (e.g. 409 Conflict) is returned immediately without retry."""
    mock_client = AsyncMock()
    mock_client.request = AsyncMock(
        return_value=MagicMock(
            status_code=409,
            text='{"code":"23505","message":"duplicate key value violates unique constraint"}'
        )
    )

    test_db = SupabaseDB(http_client=mock_client, use_mock_store=False)
    res = await test_db._execute_with_retry(
        method="POST",
        url="https://mock.supabase.co/rest/v1/customers",
        operation_name="test_conflict",
        headers={"apikey": "test"},
        json_data={"external_customer_id": "cust_001"},
        max_retries=3
    )

    # 409 returned immediately on first attempt (call_count == 1)
    assert res.status_code == 409
    assert mock_client.request.call_count == 1


# -----------------------------------------------------------------------------
# 7. TENANT ISOLATION & API ENDPOINT SECURITY TESTS
# -----------------------------------------------------------------------------

def test_unauthenticated_recovery_endpoints_return_401(client: TestClient):
    """Unauthenticated access to recovery endpoints is blocked with 401."""
    assert client.get("/api/v1/recovery/cases").status_code == status.HTTP_401_UNAUTHORIZED
    assert client.get("/api/v1/recovery/metrics").status_code == status.HTTP_401_UNAUTHORIZED
    assert client.post("/api/v1/recovery/batches", json={"name": "test"}).status_code == status.HTTP_401_UNAUTHORIZED


def test_authenticated_batch_seed_and_metrics_flow(client: TestClient, auth_mock):
    """Authenticated merchant can seed demo batch and query metrics."""
    token = make_token(TEST_MERCHANT_ID, "operator")

    # 1. Seed demo batch
    seed_res = client.post(
        "/api/v1/recovery/seed-demo-batch",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert seed_res.status_code == status.HTTP_200_OK
    data = seed_res.json()
    assert data["total_records"] == 6
    assert data["merchant_id"] == TEST_MERCHANT_ID

    # 2. List cases
    cases_res = client.get(
        "/api/v1/recovery/cases",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert cases_res.status_code == status.HTTP_200_OK
    cases = cases_res.json()
    assert len(cases) == 6

    # 3. Get case detail
    case_id = cases[0]["id"]
    detail_res = client.get(
        f"/api/v1/recovery/cases/{case_id}",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert detail_res.status_code == status.HTTP_200_OK
    detail = detail_res.json()
    assert detail["id"] == case_id
    assert len(detail["actions"]) >= 1
    assert len(detail["outcomes"]) >= 1
    assert len(detail["audit_logs"]) >= 1

    # 4. Get metrics summary
    metrics_res = client.get(
        "/api/v1/recovery/metrics",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert metrics_res.status_code == status.HTTP_200_OK
    metrics = metrics_res.json()
    assert metrics["merchant_id"] == TEST_MERCHANT_ID
    assert metrics["total_revenue_at_risk"] > 0
    assert metrics["total_cases_processed"] == 6


def test_batch_scoped_metrics_consistency(client: TestClient, auth_mock):
    """Verify that querying metrics with batch_id scopes exclusively to that batch."""
    token = make_token(TEST_MERCHANT_ID, "operator")

    # Seed Batch 1
    res1 = client.post(
        "/api/v1/recovery/seed-demo-batch",
        headers={"Authorization": f"Bearer {token}"}
    )
    batch1_data = res1.json()
    batch1_id = batch1_data["batch_id"]

    # Seed Batch 2
    res2 = client.post(
        "/api/v1/recovery/seed-demo-batch",
        headers={"Authorization": f"Bearer {token}"}
    )
    batch2_data = res2.json()
    batch2_id = batch2_data["batch_id"]

    assert batch1_id != batch2_id

    # Query metrics specifically for Batch 2
    metrics2_res = client.get(
        f"/api/v1/recovery/metrics?batch_id={batch2_id}",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert metrics2_res.status_code == status.HTTP_200_OK
    metrics2 = metrics2_res.json()

    # Metrics for Batch 2 match Batch 2 exactly (6 cases), not the combined 12 cases
    assert metrics2["total_cases_processed"] == 6
    assert metrics2["total_revenue_at_risk"] == batch2_data["total_amount_at_risk"]
    assert metrics2["recoveriq_recovered_revenue"] == batch2_data["total_recovered_amount"]
    assert metrics2["recovery_lift_percentage"] == batch2_data["recovery_lift_percentage"]

    # Query metrics for ALL batches (lifetime)
    all_metrics_res = client.get(
        "/api/v1/recovery/metrics",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert all_metrics_res.status_code == status.HTTP_200_OK
    all_metrics = all_metrics_res.json()
    assert all_metrics["total_cases_processed"] == 12

    # Query cases specifically for Batch 2
    cases_b2_res = client.get(
        f"/api/v1/recovery/cases?batch_id={batch2_id}",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert cases_b2_res.status_code == status.HTTP_200_OK
    cases_b2 = cases_b2_res.json()
    assert len(cases_b2) == 6


def test_cross_merchant_case_access_forbidden(client: TestClient, auth_mock):
    """Merchant A cannot access Merchant B's case detail."""
    # Seed case belonging to OTHER_MERCHANT_ID
    other_case_id = "case_other_merchant_999"
    db._mock_db["recovery_cases"].append({
        "id": other_case_id,
        "merchant_id": OTHER_MERCHANT_ID,
        "payment_id": "pay_other",
        "status": "DETECTED",
        "amount": 5000.0,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    })

    token = make_token(TEST_MERCHANT_ID, "operator")
    res = client.get(
        f"/api/v1/recovery/cases/{other_case_id}",
        headers={"Authorization": f"Bearer {token}"}
    )
    # Must return 404 because query filters by merchant_id
    assert res.status_code == status.HTTP_404_NOT_FOUND
