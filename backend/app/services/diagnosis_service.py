import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from app.schemas.recovery import (
    RootCauseCategory,
    ActionType,
    DiagnosisResult,
    CaseStatus,
    AIDiagnosisResult,
    AIDiagnosisSource,
)
from app.services.supabase_db import db, SupabaseDB
from app.services.ai_diagnosis_service import ai_diagnosis_service, AIDiagnosisService

logger = logging.getLogger(__name__)


class DiagnosisService:
    """
    Diagnostic Classifier & AI Explanation Layer for payment failures.
    Analyzes error codes, gateway responses, failure steps, and transaction metadata
    using deterministic rules combined with a secure, structured LLM explanation layer.
    """

    def __init__(
        self,
        database: Optional[SupabaseDB] = None,
        ai_service: Optional[AIDiagnosisService] = None,
    ):
        self.db = database or db
        self.ai = ai_service or ai_diagnosis_service

    def diagnose_failure(self, failure: Dict[str, Any], payment: Dict[str, Any]) -> DiagnosisResult:
        """
        Maps raw gateway failure fields to a structured diagnosis result.
        """
        error_code = (failure.get("error_code") or "").upper()
        error_desc = (failure.get("error_description") or "").upper()
        error_reason = (failure.get("error_reason") or "").upper()
        error_source = (failure.get("error_source") or "").lower()
        root_cause_hint = failure.get("root_cause_category")

        # 1. Check FRAUD_DECLINE (Highest risk / terminal security decline)
        if (
            root_cause_hint == "FRAUD_DECLINE"
            or "FRAUD" in error_code
            or "RISK" in error_code
            or "STOLEN" in error_desc
            or "SUSPICIOUS" in error_desc
        ):
            return DiagnosisResult(
                root_cause_category=RootCauseCategory.FRAUD_DECLINE,
                confidence_score=0.98,
                reasoning="Security system flagged transaction for high fraud risk or stolen card. Automated retries prohibited.",
                recommended_actions=[ActionType.STOP],
                is_terminal_decline=True,
                diagnostic_details={"error_code": error_code, "risk_tier": "HIGH"}
            )

        # 2. Check NETWORK_TIMEOUT (Transient network/socket timeout)
        if (
            root_cause_hint == "NETWORK_TIMEOUT"
            or "TIMEOUT" in error_code
            or "SOCKET" in error_code
            or "TIME_OUT" in error_desc
            or "GATEWAY_TIMEOUT" in error_code
        ):
            return DiagnosisResult(
                root_cause_category=RootCauseCategory.NETWORK_TIMEOUT,
                confidence_score=0.94,
                reasoning="Transient connection timeout between payment gateway and issuing bank. High probability of immediate retry recovery.",
                recommended_actions=[ActionType.RETRY_NOW, ActionType.RETRY_LATER],
                is_terminal_decline=False,
                diagnostic_details={"error_code": error_code, "retry_recommended": True}
            )

        # 3. Check GATEWAY_ERROR (Acquiring bank or gateway outage / 5xx)
        if (
            root_cause_hint == "GATEWAY_ERROR"
            or "GATEWAY_ERROR" in error_code
            or "BANK_DOWN" in error_code
            or "SYSTEM_DOWN" in error_code
            or "INTERNAL_ERROR" in error_code
            or error_source in ("gateway", "bank") and "DOWN" in error_desc
        ):
            return DiagnosisResult(
                root_cause_category=RootCauseCategory.GATEWAY_ERROR,
                confidence_score=0.91,
                reasoning="Downstream bank node or gateway degradation. Requires backoff cooldown before retry.",
                recommended_actions=[ActionType.RETRY_LATER, ActionType.PAYMENT_UPDATE],
                is_terminal_decline=False,
                diagnostic_details={"error_code": error_code, "suggested_cooldown_minutes": 60}
            )

        # 4. Check INSUFFICIENT_FUNDS (Customer account balance low)
        if (
            root_cause_hint == "INSUFFICIENT_FUNDS"
            or "INSUFFICIENT_FUNDS" in error_code
            or "LOW_BALANCE" in error_code
            or "FUNDS" in error_desc
        ):
            return DiagnosisResult(
                root_cause_category=RootCauseCategory.INSUFFICIENT_FUNDS,
                confidence_score=0.92,
                reasoning="Payer account has insufficient funds. Customer reminder or alternate payment method link is optimal.",
                recommended_actions=[ActionType.REMINDER, ActionType.PAYMENT_UPDATE, ActionType.RETRY_LATER],
                is_terminal_decline=False,
                diagnostic_details={"error_code": error_code, "suggested_action": "PAYMENT_UPDATE"}
            )

        # 5. Check CARD_LIMIT_EXCEEDED (Card monthly/daily velocity limit)
        if (
            root_cause_hint == "CARD_LIMIT_EXCEEDED"
            or "LIMIT_EXCEEDED" in error_code
            or "MAX_AMOUNT" in error_code
            or "VELOCITY" in error_desc
        ):
            return DiagnosisResult(
                root_cause_category=RootCauseCategory.CARD_LIMIT_EXCEEDED,
                confidence_score=0.90,
                reasoning="Payer card spending or transaction velocity limit exceeded. Payment update to UPI/Netbanking recommended.",
                recommended_actions=[ActionType.PAYMENT_UPDATE, ActionType.RETRY_LATER],
                is_terminal_decline=False,
                diagnostic_details={"error_code": error_code}
            )

        # 6. Check USER_DROPPED (Checkout abandoned, OTP expired/cancelled)
        if (
            root_cause_hint == "USER_DROPPED"
            or "USER_DROPPED" in error_code
            or "OTP_EXPIRED" in error_code
            or "ABANDONED" in error_code
            or "CANCELLED" in error_desc
        ):
            return DiagnosisResult(
                root_cause_category=RootCauseCategory.USER_DROPPED,
                confidence_score=0.88,
                reasoning="User abandoned checkout session or timed out on OTP entry. Re-engagement reminder link is effective.",
                recommended_actions=[ActionType.PAYMENT_UPDATE, ActionType.REMINDER],
                is_terminal_decline=False,
                diagnostic_details={"error_code": error_code}
            )

        # Default fallback categorization
        return DiagnosisResult(
            root_cause_category=RootCauseCategory.GATEWAY_ERROR if error_source in ("gateway", "bank") else RootCauseCategory.OTHER,
            confidence_score=0.75,
            reasoning=f"General failure classified under {error_source or 'standard'} error patterns.",
            recommended_actions=[ActionType.RETRY_LATER, ActionType.PAYMENT_UPDATE],
            is_terminal_decline=False,
            diagnostic_details={"error_code": error_code, "error_reason": error_reason}
        )

    async def diagnose_case(self, case_id: str, merchant_id: str) -> Optional[DiagnosisResult]:
        """
        Executes diagnosis on a recovery case, runs structured AI diagnosis with deterministic fallback,
        updates case state, and creates an immutable audit log.
        """
        case = await self.db.get_recovery_case(case_id, merchant_id)
        if not case or not case.get("payment") or not case["payment"].get("failure"):
            logger.warning(f"Cannot diagnose case {case_id}: missing payment or failure data")
            return None

        failure = case["payment"]["failure"]
        payment = case["payment"]
        customer = case.get("customer") or payment.get("customer")
        retry_count = int(case.get("retry_count", 0))
        communication_count = int(case.get("communication_count", 0))

        # 1. Deterministic baseline classification
        deterministic_diagnosis = self.diagnose_failure(failure, payment)

        # 2. Gather auxiliary context for AI
        policy = await self.db.get_default_policy(merchant_id)
        action_stats = await self.db.get_action_statistics(merchant_id, deterministic_diagnosis.root_cause_category.value)

        # 3. Sanitize context (never send keys, passwords, card numbers)
        sanitized_ctx = self.ai.sanitize_context(
            failure=failure,
            payment=payment,
            customer=customer,
            policy=policy,
            action_stats=action_stats,
            retry_count=retry_count,
            communication_count=communication_count,
        )

        # 4. Invoke AI diagnosis (with automatic deterministic fallback if unconfigured or error)
        ai_res = await self.ai.diagnose_failure(
            sanitized_context=sanitized_ctx,
            deterministic_root_cause=deterministic_diagnosis.root_cause_category,
        )

        # 5. Build combined structured diagnosis
        diagnosis = DiagnosisResult(
            root_cause_category=ai_res.failure_type,
            confidence_score=ai_res.confidence,
            reasoning=ai_res.reason,
            recommended_actions=[ai_res.recommended_action],
            is_terminal_decline=ai_res.failure_type == RootCauseCategory.FRAUD_DECLINE or deterministic_diagnosis.is_terminal_decline,
            diagnostic_details={
                **deterministic_diagnosis.diagnostic_details,
                "ai_diagnosis_name": ai_res.diagnosis,
                "ai_source": ai_res.source.value,
            },
            ai_diagnosis=ai_res,
        )

        summary_dict = {
            "root_cause_category": diagnosis.root_cause_category.value,
            "confidence_score": diagnosis.confidence_score,
            "reasoning": diagnosis.reasoning,
            "recommended_actions": [a.value for a in diagnosis.recommended_actions],
            "is_terminal_decline": diagnosis.is_terminal_decline,
            "diagnosed_at": datetime.now(timezone.utc).isoformat(),
            "details": diagnosis.diagnostic_details,
            # Structured AI fields
            "source": ai_res.source.value,
            "failure_type": ai_res.failure_type.value,
            "recommended_action": ai_res.recommended_action.value,
            "diagnosis": ai_res.diagnosis,
            "reason": ai_res.reason,
            "confidence": ai_res.confidence,
        }

        # Update case record
        await self.db.update_recovery_case(case_id, merchant_id, {
            "status": CaseStatus.DIAGNOSED.value,
            "diagnosis_summary": summary_dict
        })

        # Record audit log
        await self.db.create_audit_log({
            "merchant_id": merchant_id,
            "case_id": case_id,
            "actor_type": "AI_AGENT",
            "event_type": "FAILURE_DIAGNOSED",
            "severity": "INFO" if not diagnosis.is_terminal_decline else "WARNING",
            "description": f"AI diagnosis ({ai_res.source.value}): {ai_res.failure_type.value} -> {ai_res.recommended_action.value} (Confidence: {ai_res.confidence * 100:.1f}%)",
            "details": summary_dict
        })

        return diagnosis


diagnosis_service = DiagnosisService()
