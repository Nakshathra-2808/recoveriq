import pytest
import json
import httpx
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.config import settings
from app.schemas.recovery import (
    ActionType,
    ExecutionMode,
    CaseStatus,
    RootCauseCategory,
)
from app.services.adapters.razorpay_test_adapter import RazorpayTestAdapter
from app.services.adapters import DryRunAdapter
from app.services.executor_service import ExecutorService
from app.policies.guardrail_engine import GuardrailEngine
from app.services.recovery_engine import RecoveryEngine
from app.services.supabase_db import db

TEST_MERCHANT_ID = "00000000-0000-0000-0000-000000000001"
TEST_KEY_ID = "rzp_test_1234567890abcdef"
TEST_KEY_SECRET = "test_super_secret_key_xyz"


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch):
    db.use_mock_store = True
    db.reset_mock_store()
    db._mock_db["merchants"].append({
        "id": TEST_MERCHANT_ID,
        "name": "Acme Retail India",
    })
    db._mock_db["policies"].append({
        "id": "pol_001",
        "merchant_id": TEST_MERCHANT_ID,
        "name": "Default Recovery Policy",
        "max_retries": 3,
        "max_communications": 3,
        "cooldown_minutes": 60,
        "escalation_threshold_amount": 10000.0,
        "auto_escalate_vip": True,
        "is_active": True,
    })


# -----------------------------------------------------------------------------
# 1. Credentials & Environment Safety Validation
# -----------------------------------------------------------------------------

def test_missing_credentials_fails_safely():
    adapter = RazorpayTestAdapter(key_id="", key_secret="", environment="test")
    with pytest.raises(ValueError) as excinfo:
        adapter._validate_credentials()
    assert "RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET must be set" in str(excinfo.value)


def test_production_key_strictly_rejected():
    # Attempting to use a live production key
    adapter = RazorpayTestAdapter(key_id="rzp_live_realproductionkey", key_secret="secret", environment="test")
    with pytest.raises(ValueError) as excinfo:
        adapter._validate_credentials()
    assert "Production Razorpay key" in str(excinfo.value)

    # Attempting to use non-test environment
    adapter2 = RazorpayTestAdapter(key_id=TEST_KEY_ID, key_secret=TEST_KEY_SECRET, environment="production")
    with pytest.raises(ValueError) as excinfo:
        adapter2._validate_credentials()
    assert "Only 'test' environment is permitted" in str(excinfo.value)


# -----------------------------------------------------------------------------
# 2. Genuine Razorpay Test API Payment Link Operation
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_razorpay_payment_link_success():
    adapter = RazorpayTestAdapter(key_id=TEST_KEY_ID, key_secret=TEST_KEY_SECRET, environment="test")

    mock_resp_data = {
        "id": "plink_test_001abc",
        "short_url": "https://rzp.io/i/test001",
        "status": "created",
        "amount": 249900,
        "currency": "INR",
        "description": "RecoverIQ Payment Recovery Link",
    }

    with patch("httpx.AsyncClient.post") as mock_post:
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: mock_resp_data,
            raise_for_status=lambda: None
        )

        res = await adapter.create_payment_link(
            amount_inr=2499.00,
            description="RecoverIQ test link",
            customer={"name": "Aarav Sharma", "email": "aarav@example.com", "phone": "+919876543210"}
        )

        assert res["success"] is True
        assert res["id"] == "plink_test_001abc"
        assert res["short_url"] == "https://rzp.io/i/test001"
        assert res["amount"] == 2499.00

        # Verify Basic Auth and Payload sent
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args.kwargs
        assert call_kwargs["auth"] == (TEST_KEY_ID, TEST_KEY_SECRET)
        assert call_kwargs["json"]["amount"] == 249900
        assert call_kwargs["json"]["currency"] == "INR"


# -----------------------------------------------------------------------------
# 3. Genuine Razorpay Test API Order Operation
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_razorpay_order_success():
    adapter = RazorpayTestAdapter(key_id=TEST_KEY_ID, key_secret=TEST_KEY_SECRET, environment="test")

    mock_resp_data = {
        "id": "order_test_999xyz",
        "status": "created",
        "amount": 149900,
        "currency": "INR",
        "receipt": "rec_case_001",
    }

    with patch("httpx.AsyncClient.post") as mock_post:
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: mock_resp_data,
            raise_for_status=lambda: None
        )

        res = await adapter.create_order(
            amount_inr=1499.00,
            receipt="rec_case_001",
            notes={"case_id": "case_001"}
        )

        assert res["success"] is True
        assert res["id"] == "order_test_999xyz"
        assert res["status"] == "created"
        assert res["amount"] == 1499.00


# -----------------------------------------------------------------------------
# 4. Error & Timeout Handling (Resilience & Redaction)
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_razorpay_timeout_handled_safely():
    adapter = RazorpayTestAdapter(key_id=TEST_KEY_ID, key_secret=TEST_KEY_SECRET, environment="test")

    with patch("httpx.AsyncClient.post", side_effect=httpx.ConnectTimeout("Connection timed out")):
        res = await adapter.create_payment_link(amount_inr=1000.0, description="Test timeout")
        assert res["success"] is False
        assert "timed out" in res["error"].lower()
        # Verify secret is not in the error string
        assert TEST_KEY_SECRET not in res["error"]


@pytest.mark.asyncio
async def test_razorpay_4xx_error_handled_safely():
    adapter = RazorpayTestAdapter(key_id=TEST_KEY_ID, key_secret=TEST_KEY_SECRET, environment="test")

    mock_err_response = MagicMock(
        status_code=400,
        json=lambda: {
            "error": {
                "code": "BAD_REQUEST_ERROR",
                "description": "Customer phone number invalid"
            }
        }
    )

    with patch("httpx.AsyncClient.post") as mock_post:
        mock_post.return_value = mock_err_response
        mock_err_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "400 Bad Request",
            request=MagicMock(),
            response=mock_err_response
        )

        res = await adapter.create_payment_link(amount_inr=1000.0, description="Invalid phone")
        assert res["success"] is False
        assert "phone number invalid" in res["error"].lower()
        assert TEST_KEY_SECRET not in res["error"]


@pytest.mark.asyncio
async def test_razorpay_5xx_error_handled_safely():
    adapter = RazorpayTestAdapter(key_id=TEST_KEY_ID, key_secret=TEST_KEY_SECRET, environment="test")

    mock_500_response = MagicMock(
        status_code=500,
        json=lambda: {"error": {"description": "Internal server degradation"}}
    )

    with patch("httpx.AsyncClient.post") as mock_post:
        mock_post.return_value = mock_500_response
        mock_500_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "500 Internal Server Error",
            request=MagicMock(),
            response=mock_500_response
        )

        res = await adapter.create_order(amount_inr=500.0, receipt="rec_001")
        assert res["success"] is False
        assert "internal server degradation" in res["error"].lower()


# -----------------------------------------------------------------------------
# 5. Full Adapter Execution Routing (PAYMENT_UPDATE, RETRY_LATER, ESCALATE, STOP)
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_adapter_execute_action_routing():
    adapter = RazorpayTestAdapter(key_id=TEST_KEY_ID, key_secret=TEST_KEY_SECRET, environment="test")

    # 1. PAYMENT_UPDATE
    case_link = {
        "id": "case_link_01",
        "payment_id": "pay_01",
        "payment": {"amount": 2999.0},
        "customer": {"name": "Test Payer", "email": "payer@example.com"},
        "metadata": {"proposed_action": "PAYMENT_UPDATE"}
    }
    with patch.object(adapter, "create_payment_link", new=AsyncMock(return_value={"success": True, "id": "plink_123", "short_url": "https://rzp.io/i/123"})):
        exec_res = await adapter.execute(case_link, TEST_MERCHANT_ID, ExecutionMode.RAZORPAY_TEST)
        assert exec_res["status"] == "COMPLETED"
        assert exec_res["provider"] == "RAZORPAY_TEST"
        assert exec_res["external_reference"] == "plink_123"
        assert exec_res["payment_link"] == "https://rzp.io/i/123"
        assert exec_res["simulated"] is False

    # 2. ESCALATE (Internal merchant VIP ops)
    case_esc = {
        "id": "case_esc_01",
        "payment": {"amount": 15000.0},
        "metadata": {"proposed_action": "ESCALATE"}
    }
    exec_esc = await adapter.execute(case_esc, TEST_MERCHANT_ID, ExecutionMode.RAZORPAY_TEST)
    assert exec_esc["status"] == "COMPLETED"
    assert exec_esc["action_type"] == "ESCALATE"
    assert exec_esc["simulated"] is True

    # 3. STOP (Terminal policy stop)
    case_stop = {
        "id": "case_stop_01",
        "metadata": {"proposed_action": "STOP"}
    }
    exec_stop = await adapter.execute(case_stop, TEST_MERCHANT_ID, ExecutionMode.RAZORPAY_TEST)
    assert exec_stop["status"] == "COMPLETED"
    assert exec_stop["action_type"] == "STOP"
    assert exec_stop["terminal_state"] is True


# -----------------------------------------------------------------------------
# 6. Dry Run Adapter Validation
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dry_run_performs_no_external_requests():
    dry_adapter = DryRunAdapter()
    case = {
        "id": "case_dry_01",
        "payment": {"amount": 5000.0},
        "metadata": {"proposed_action": "RETRY_LATER"}
    }

    with patch("httpx.AsyncClient.post") as mock_post:
        res = await dry_adapter.execute(case, TEST_MERCHANT_ID, ExecutionMode.DRY_RUN)
        assert res["execution_mode"] == "DRY_RUN"
        assert res["provider"] == "DRY_RUN"
        assert res["status"] == "COMPLETED"
        assert res["simulated"] is True
        assert "without external network dispatch" in res["message"]
        # Zero HTTP calls made
        mock_post.assert_not_called()


# -----------------------------------------------------------------------------
# 7. Guardrail Authority with Razorpay Test Mode
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_guardrails_enforce_stop_before_razorpay_adapter():
    """Even in RAZORPAY_TEST mode, hard fraud decline or opt-out halts before external dispatch."""
    guardrails = GuardrailEngine(database=db)
    executor = ExecutorService(
        database=db,
        razorpay_adapter=RazorpayTestAdapter(key_id=TEST_KEY_ID, key_secret=TEST_KEY_SECRET, environment="test")
    )

    case_id = "case_fraud_rzp"
    payment_id = "pay_fraud_rzp"
    
    db._mock_db["payments"].append({
        "id": payment_id,
        "merchant_id": TEST_MERCHANT_ID,
        "amount": 5000.0,
        "currency": "INR",
        "status": "FAILED"
    })
    db._mock_db["recovery_cases"].append({
        "id": case_id,
        "merchant_id": TEST_MERCHANT_ID,
        "payment_id": payment_id,
        "status": "DETECTED",
        "priority": "HIGH",
        "retry_count": 0,
        "communication_count": 0,
        "diagnosis_summary": {"root_cause_category": "FRAUD_DECLINE"},
        "metadata": {"proposed_action": "RETRY_NOW"}
    })

    # Run guardrails
    guard_res = await guardrails.guard_case(case_id, TEST_MERCHANT_ID)
    assert guard_res.final_action == ActionType.STOP

    # Execute action
    with patch("httpx.AsyncClient.post") as mock_post:
        exec_res = await executor.execute_case_action(case_id, TEST_MERCHANT_ID, ExecutionMode.RAZORPAY_TEST)
        assert exec_res.action_type == ActionType.STOP
        # Verify no external charge or order attempt was dispatched
        mock_post.assert_not_called()
