import pytest
import json
import httpx
from unittest.mock import AsyncMock, MagicMock, patch
from pydantic import ValidationError

from app.core.config import settings
from app.schemas.recovery import (
    RootCauseCategory,
    ActionType,
    AIDiagnosisSource,
    AIDiagnosisResult,
    CaseStatus,
)
from app.services.ai_diagnosis_service import AIDiagnosisService, ai_diagnosis_service
from app.services.diagnosis_service import DiagnosisService
from app.policies.guardrail_engine import GuardrailEngine
from app.services.supabase_db import db

TEST_MERCHANT_ID = "00000000-0000-0000-0000-000000000001"


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch):
    db.use_mock_store = True
    db.reset_mock_store()
    # Seed default merchant & policy
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
# 1. Valid LLM Responses (Gemini & OpenAI Providers)
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_valid_llm_response_gemini():
    service = AIDiagnosisService(provider="gemini", api_key="valid-test-key", model="gemini-1.5-flash")
    
    mock_payload = {
        "diagnosis": "temporary_gateway_failure",
        "failure_type": "NETWORK_TIMEOUT",
        "recommended_action": "RETRY_LATER",
        "reason": "Similar network timeout cases historically recover better after a delayed retry.",
        "confidence": 0.94,
        "source": "LLM"
    }
    
    gemini_resp = {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": json.dumps(mock_payload)}]
                }
            }
        ]
    }

    with patch("httpx.AsyncClient.post") as mock_post:
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: gemini_resp,
            raise_for_status=lambda: None
        )
        
        ctx = service.sanitize_context(
            failure={"error_code": "ETIMEDOUT", "root_cause_category": "NETWORK_TIMEOUT"},
            payment={"amount": 1499.0, "currency": "INR", "method": "card"},
        )
        result = await service.diagnose_failure(ctx, RootCauseCategory.NETWORK_TIMEOUT)

        assert result.source == AIDiagnosisSource.LLM
        assert result.failure_type == RootCauseCategory.NETWORK_TIMEOUT
        assert result.recommended_action == ActionType.RETRY_LATER
        assert result.confidence == 0.94
        assert "network timeout" in result.reason.lower()


@pytest.mark.asyncio
async def test_valid_llm_response_openai():
    service = AIDiagnosisService(provider="openai", api_key="valid-openai-key", model="gpt-4o-mini")
    
    mock_payload = {
        "diagnosis": "insufficient_balance_temporary",
        "failure_type": "INSUFFICIENT_FUNDS",
        "recommended_action": "REMINDER",
        "reason": "Customer account had insufficient balance; reminder link has highest historical recovery.",
        "confidence": 0.91,
        "source": "LLM"
    }
    
    openai_resp = {
        "choices": [
            {
                "message": {"content": json.dumps(mock_payload)}
            }
        ]
    }

    with patch("httpx.AsyncClient.post") as mock_post:
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: openai_resp,
            raise_for_status=lambda: None
        )
        
        ctx = service.sanitize_context(
            failure={"error_code": "INSUFFICIENT_FUNDS", "root_cause_category": "INSUFFICIENT_FUNDS"},
            payment={"amount": 2500.0, "currency": "INR", "method": "upi"},
        )
        result = await service.diagnose_failure(ctx, RootCauseCategory.INSUFFICIENT_FUNDS)

        assert result.source == AIDiagnosisSource.LLM
        assert result.failure_type == RootCauseCategory.INSUFFICIENT_FUNDS
        assert result.recommended_action == ActionType.REMINDER
        assert result.confidence == 0.91


# -----------------------------------------------------------------------------
# 2. Structured Pydantic Model Validation
# -----------------------------------------------------------------------------

def test_structured_response_validation():
    valid = AIDiagnosisResult(
        diagnosis="transient_network_error",
        failure_type=RootCauseCategory.NETWORK_TIMEOUT,
        recommended_action=ActionType.RETRY_NOW,
        reason="Immediate socket reconnection is likely to succeed.",
        confidence=0.88,
        source=AIDiagnosisSource.LLM
    )
    assert valid.confidence == 0.88
    assert valid.recommended_action == ActionType.RETRY_NOW

    # Invalid confidence > 1.0
    with pytest.raises(ValidationError):
        AIDiagnosisResult(
            diagnosis="invalid",
            failure_type=RootCauseCategory.NETWORK_TIMEOUT,
            recommended_action=ActionType.RETRY_NOW,
            reason="test",
            confidence=1.5,
            source=AIDiagnosisSource.LLM
        )

    # Invalid action
    with pytest.raises(ValidationError):
        AIDiagnosisResult(
            diagnosis="invalid",
            failure_type=RootCauseCategory.NETWORK_TIMEOUT,
            recommended_action="ILLEGAL_ACTION",  # type: ignore
            reason="test",
            confidence=0.5,
            source=AIDiagnosisSource.LLM
        )


# -----------------------------------------------------------------------------
# 3. Deterministic Fallback Scenarios (Resilience)
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_invalid_json_triggers_fallback():
    service = AIDiagnosisService(provider="gemini", api_key="valid-key")

    with patch("httpx.AsyncClient.post") as mock_post:
        # Returns unparseable non-JSON
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"candidates": [{"content": {"parts": [{"text": "Sorry, I cannot process this."}]}}]},
            raise_for_status=lambda: None
        )
        ctx = {"test": "data"}
        result = await service.diagnose_failure(ctx, RootCauseCategory.GATEWAY_ERROR)

        assert result.source == AIDiagnosisSource.DETERMINISTIC_FALLBACK
        assert result.failure_type == RootCauseCategory.GATEWAY_ERROR
        assert result.recommended_action == ActionType.RETRY_LATER
        assert result.confidence > 0.0


@pytest.mark.asyncio
async def test_invalid_action_triggers_fallback():
    service = AIDiagnosisService(provider="gemini", api_key="valid-key")

    with patch("httpx.AsyncClient.post") as mock_post:
        # Returns JSON with an unknown action
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "candidates": [{
                    "content": {
                        "parts": [{
                            "text": json.dumps({
                                "diagnosis": "bad_action",
                                "failure_type": "NETWORK_TIMEOUT",
                                "recommended_action": "HACK_DATABASE",
                                "reason": "invalid action",
                                "confidence": 0.9
                            })
                        }]
                    }
                }]
            },
            raise_for_status=lambda: None
        )
        ctx = {"test": "data"}
        result = await service.diagnose_failure(ctx, RootCauseCategory.NETWORK_TIMEOUT)

        assert result.source == AIDiagnosisSource.DETERMINISTIC_FALLBACK
        assert result.recommended_action == ActionType.RETRY_LATER


@pytest.mark.asyncio
async def test_llm_timeout_triggers_fallback():
    service = AIDiagnosisService(provider="gemini", api_key="valid-key")

    with patch("httpx.AsyncClient.post", side_effect=httpx.ConnectTimeout("Connection timed out")):
        ctx = {"test": "data"}
        result = await service.diagnose_failure(ctx, RootCauseCategory.USER_DROPPED)

        assert result.source == AIDiagnosisSource.DETERMINISTIC_FALLBACK
        assert result.failure_type == RootCauseCategory.USER_DROPPED
        assert result.recommended_action == ActionType.REMINDER


@pytest.mark.asyncio
async def test_missing_api_key_triggers_fallback():
    service = AIDiagnosisService(provider="gemini", api_key="")
    ctx = {"test": "data"}
    result = await service.diagnose_failure(ctx, RootCauseCategory.CARD_LIMIT_EXCEEDED)

    assert result.source == AIDiagnosisSource.DETERMINISTIC_FALLBACK
    assert result.failure_type == RootCauseCategory.CARD_LIMIT_EXCEEDED
    assert result.recommended_action == ActionType.PAYMENT_UPDATE


@pytest.mark.asyncio
async def test_provider_500_error_triggers_fallback():
    service = AIDiagnosisService(provider="gemini", api_key="valid-key")

    with patch("httpx.AsyncClient.post") as mock_post:
        mock_post.return_value = MagicMock(
            status_code=500,
            raise_for_status=MagicMock(side_effect=httpx.HTTPStatusError("500 Internal Server Error", request=MagicMock(), response=MagicMock()))
        )
        ctx = {"test": "data"}
        result = await service.diagnose_failure(ctx, RootCauseCategory.GATEWAY_ERROR)

        assert result.source == AIDiagnosisSource.DETERMINISTIC_FALLBACK
        assert result.failure_type == RootCauseCategory.GATEWAY_ERROR


# -----------------------------------------------------------------------------
# 4. Security Invariants (Fraud & Opt-Out cannot be overridden)
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fraud_decline_cannot_be_overridden_by_llm():
    service = AIDiagnosisService(provider="gemini", api_key="valid-key")

    # Suppose an adversarial or hallucinating LLM suggests RETRY_NOW on fraud decline
    hallucinated_resp = {
        "diagnosis": "suspected_fraud_but_retry",
        "failure_type": "FRAUD_DECLINE",
        "recommended_action": "RETRY_NOW",
        "reason": "Retry anyway.",
        "confidence": 0.99,
        "source": "LLM"
    }

    with patch("httpx.AsyncClient.post") as mock_post:
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"candidates": [{"content": {"parts": [{"text": json.dumps(hallucinated_resp)}]}}]},
            raise_for_status=lambda: None
        )
        ctx = {"root_cause": "FRAUD_DECLINE"}
        result = await service.diagnose_failure(ctx, RootCauseCategory.FRAUD_DECLINE)

        # Must be forced to STOP
        assert result.recommended_action == ActionType.STOP


@pytest.mark.asyncio
async def test_guardrail_authoritative_over_ai_recommendation():
    """Even if AI recommends RETRY_NOW, guardrails must stop on opt-out, fraud, or retry limits."""
    guardrails = GuardrailEngine(database=db)
    
    # 1. Customer opted-out
    case = {
        "id": "case_opt_out",
        "payment": {"amount": 1000.0},
        "diagnosis_summary": {"root_cause_category": "NETWORK_TIMEOUT"},
        "retry_count": 0,
    }
    policy = {"max_retries": 3, "cooldown_minutes": 60}
    customer = {"id": "cust_1", "is_opted_out": True}

    res = guardrails.validate_action(ActionType.RETRY_NOW, case, policy, customer)
    assert res.final_action == ActionType.STOP
    assert res.is_overridden is True
    assert "opted out" in res.override_reason.lower()

    # 2. Hard Fraud decline
    case_fraud = {
        "id": "case_fraud",
        "payment": {"amount": 5000.0},
        "diagnosis_summary": {"root_cause_category": "FRAUD_DECLINE"},
        "retry_count": 0,
    }
    res_fraud = guardrails.validate_action(ActionType.RETRY_NOW, case_fraud, policy, customer={"is_opted_out": False})
    assert res_fraud.final_action == ActionType.STOP
    assert res_fraud.is_overridden is True


# -----------------------------------------------------------------------------
# 5. Integration: Persistence in Diagnosis Summary & Audit Log
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ai_reasoning_persisted_in_case_and_audit():
    diag_svc = DiagnosisService(database=db)

    # Seed payment and failure in mock store
    payment_id = "pay_ai_001"
    failure_id = "fail_ai_001"
    case_id = "case_ai_001"

    db._mock_db["payments"].append({
        "id": payment_id,
        "merchant_id": TEST_MERCHANT_ID,
        "amount": 2999.00,
        "currency": "INR",
        "method": "card",
        "status": "FAILED",
    })
    failure_record = {
        "id": failure_id,
        "payment_id": payment_id,
        "merchant_id": TEST_MERCHANT_ID,
        "error_code": "GATEWAY_TIMEOUT",
        "error_description": "Downstream acquiring bank timed out",
        "error_source": "gateway",
        "root_cause_category": "NETWORK_TIMEOUT",
    }
    db._mock_db["payment_failures"].append(failure_record)
    db._mock_db["recovery_cases"].append({
        "id": case_id,
        "merchant_id": TEST_MERCHANT_ID,
        "payment_id": payment_id,
        "status": "DETECTED",
        "priority": "MEDIUM",
        "retry_count": 0,
        "communication_count": 0,
        "recovered_amount": 0.0,
        "created_at": "2026-09-04T12:00:00Z",
        "payment": {
            "id": payment_id,
            "amount": 2999.00,
            "currency": "INR",
            "method": "card",
            "failure": failure_record,
        }
    })

    result = await diag_svc.diagnose_case(case_id, TEST_MERCHANT_ID)
    assert result is not None
    assert result.root_cause_category == RootCauseCategory.NETWORK_TIMEOUT

    # Verify updated case
    updated_case = await db.get_recovery_case(case_id, TEST_MERCHANT_ID)
    assert updated_case["status"] == CaseStatus.DIAGNOSED.value
    summary = updated_case["diagnosis_summary"]
    assert summary["source"] in ("LLM", "DETERMINISTIC_FALLBACK")
    assert "recommended_action" in summary
    assert "confidence" in summary
    assert "reason" in summary

    # Verify audit log was recorded
    audit_logs = await db.get_audit_logs(case_id=case_id, merchant_id=TEST_MERCHANT_ID)
    assert len(audit_logs) >= 1
    diag_log = audit_logs[0]
    assert diag_log["actor_type"] == "AI_AGENT"
    assert diag_log["event_type"] == "FAILURE_DIAGNOSED"
    assert "details" in diag_log
