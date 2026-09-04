import logging
import uuid
import hashlib
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from app.schemas.recovery import (
    ActionType,
    RootCauseCategory,
    OutcomeType,
    OutcomeResult,
    CaseStatus,
)
from app.services.supabase_db import db, SupabaseDB

logger = logging.getLogger(__name__)


class OutcomeService:
    """
    Outcome Verification & Lifecycle Resolution Service.
    Evaluates verifiable recovery outcomes using deterministic simulation models
    grounded in transaction failure attributes and action efficacy.
    """

    def __init__(self, database: Optional[SupabaseDB] = None):
        self.db = database or db

    def evaluate_simulated_outcome(
        self,
        case: Dict[str, Any],
        action_type: ActionType,
        root_cause: RootCauseCategory,
        retry_count: int
    ) -> OutcomeResult:
        """
        Computes a deterministic, reproducible recovery outcome based on failure etiology,
        action compatibility, payment amount, and retry progression.
        """
        amount = float(case.get("payment", {}).get("amount", 0.0) if case.get("payment") else case.get("amount", 0.0))
        payment_id = case.get("payment_id", "pay_default")

        # Deterministic seed from payment_id + retry_count for reproducibility
        hash_val = int(hashlib.md5(f"{payment_id}:{action_type.value}:{retry_count}".encode()).hexdigest()[:8], 16)
        prob_roll = (hash_val % 100) / 100.0

        outcome_id = str(uuid.uuid4())

        # 1. Terminal STOP / FRAUD decline cases
        if action_type == ActionType.STOP or root_cause == RootCauseCategory.FRAUD_DECLINE:
            return OutcomeResult(
                outcome_id=outcome_id,
                outcome_type=OutcomeType.DISMISSED if root_cause != RootCauseCategory.FRAUD_DECLINE else OutcomeType.FAILED_TERMINAL,
                is_successful=False,
                recovered_amount=0.00,
                recovery_time_seconds=0,
                response_payload={"reason": "Recovery terminated by guardrail policy.", "terminal": True}
            )

        # 2. ESCALATE cases
        if action_type == ActionType.ESCALATE:
            # High-touch manual escalation recovers 85% of high value orders
            is_rec = prob_roll < 0.85
            return OutcomeResult(
                outcome_id=outcome_id,
                outcome_type=OutcomeType.RECOVERED if is_rec else OutcomeType.ESCALATED_MANUALLY,
                is_successful=is_rec,
                recovered_amount=amount if is_rec else 0.00,
                new_payment_id=f"pay_rec_esc_{payment_id[-8:]}" if is_rec else None,
                recovery_time_seconds=7200 if is_rec else None,
                response_payload={"escalation_status": "PROCESSED_BY_MERCHANT_OPS", "recovered": is_rec}
            )

        # 3. Base recovery probabilities by Root Cause & Action Pairing
        success_thresholds = {
            (RootCauseCategory.NETWORK_TIMEOUT, ActionType.RETRY_NOW): 0.82,
            (RootCauseCategory.NETWORK_TIMEOUT, ActionType.RETRY_LATER): 0.65,
            (RootCauseCategory.GATEWAY_ERROR, ActionType.RETRY_LATER): 0.80,
            (RootCauseCategory.GATEWAY_ERROR, ActionType.RETRY_NOW): 0.30,
            (RootCauseCategory.GATEWAY_ERROR, ActionType.PAYMENT_UPDATE): 0.60,
            (RootCauseCategory.INSUFFICIENT_FUNDS, ActionType.REMINDER): 0.72,
            (RootCauseCategory.INSUFFICIENT_FUNDS, ActionType.PAYMENT_UPDATE): 0.68,
            (RootCauseCategory.USER_DROPPED, ActionType.PAYMENT_UPDATE): 0.78,
            (RootCauseCategory.USER_DROPPED, ActionType.REMINDER): 0.65,
            (RootCauseCategory.CARD_LIMIT_EXCEEDED, ActionType.PAYMENT_UPDATE): 0.75,
        }

        threshold = success_thresholds.get((root_cause, action_type), 0.50)
        is_successful = prob_roll < threshold

        if is_successful:
            recovery_time = 45 if action_type == ActionType.RETRY_NOW else 1800
            return OutcomeResult(
                outcome_id=outcome_id,
                outcome_type=OutcomeType.RECOVERED,
                is_successful=True,
                recovered_amount=amount,
                new_payment_id=f"pay_sim_{payment_id[-8:]}_{uuid.uuid4().hex[:6]}",
                recovery_time_seconds=recovery_time,
                response_payload={
                    "gateway_status": "captured",
                    "payment_method": "upi" if action_type == ActionType.PAYMENT_UPDATE else "card",
                    "simulated": True
                }
            )
        else:
            is_retryable = retry_count < 3
            return OutcomeResult(
                outcome_id=outcome_id,
                outcome_type=OutcomeType.FAILED_RETRYABLE if is_retryable else OutcomeType.FAILED_TERMINAL,
                is_successful=False,
                recovered_amount=0.00,
                recovery_time_seconds=None,
                response_payload={
                    "gateway_status": "failed",
                    "retryable": is_retryable,
                    "simulated": True
                }
            )

    async def record_case_outcome(
        self,
        case_id: str,
        action_id: str,
        merchant_id: str
    ) -> Optional[OutcomeResult]:
        """
        Evaluates and records verifiable outcome for the latest action executed on a case.
        """
        case = await self.db.get_recovery_case(case_id, merchant_id)
        if not case:
            logger.warning(f"Cannot verify outcome: case {case_id} not found")
            return None

        metadata = case.get("metadata", {})
        diag_dict = case.get("diagnosis_summary", {})
        root_cause = RootCauseCategory(diag_dict.get("root_cause_category", "OTHER"))
        action_str = metadata.get("last_action_type") or metadata.get("final_action", "STOP")
        action_type = ActionType(action_str)
        retry_count = int(case.get("retry_count", 0))

        outcome = self.evaluate_simulated_outcome(case, action_type, root_cause, retry_count)

        now = datetime.now(timezone.utc)
        outcome_record = {
            "id": outcome.outcome_id,
            "merchant_id": merchant_id,
            "case_id": case_id,
            "action_id": action_id,
            "outcome_type": outcome.outcome_type.value,
            "is_successful": outcome.is_successful,
            "recovered_amount": outcome.recovered_amount,
            "new_payment_id": outcome.new_payment_id,
            "response_payload": outcome.response_payload,
            "recovery_time_seconds": outcome.recovery_time_seconds,
            "recorded_at": now.isoformat()
        }

        await self.db.create_recovery_outcome(outcome_record)

        # Update case state based on outcome
        if outcome.is_successful:
            case_status = CaseStatus.RECOVERED.value
            resolved_at = now.isoformat()
        elif outcome.outcome_type == OutcomeType.FAILED_RETRYABLE:
            case_status = CaseStatus.WAITING.value
            resolved_at = None
        elif outcome.outcome_type in (OutcomeType.DISMISSED, OutcomeType.OPTED_OUT):
            case_status = CaseStatus.STOPPED.value
            resolved_at = now.isoformat()
        elif outcome.outcome_type == OutcomeType.ESCALATED_MANUALLY:
            case_status = CaseStatus.ESCALATED.value
            resolved_at = now.isoformat()
        else:
            case_status = CaseStatus.FAILED.value
            resolved_at = now.isoformat()

        await self.db.update_recovery_case(case_id, merchant_id, {
            "status": case_status,
            "recovered_amount": outcome.recovered_amount,
            "resolved_at": resolved_at,
            "metadata": {
                **metadata,
                "latest_outcome_type": outcome.outcome_type.value,
                "is_recovered": outcome.is_successful,
                "new_payment_id": outcome.new_payment_id
            }
        })

        # Record audit log
        await self.db.create_audit_log({
            "merchant_id": merchant_id,
            "case_id": case_id,
            "action_id": action_id,
            "actor_type": "SYSTEM",
            "event_type": "OUTCOME_RECORDED",
            "severity": "INFO" if outcome.is_successful else "WARNING",
            "description": f"Outcome verified: {outcome.outcome_type.value} ({'Recovered ' + str(outcome.recovered_amount) + ' INR' if outcome.is_successful else 'Not recovered'})",
            "details": {
                "outcome_type": outcome.outcome_type.value,
                "is_successful": outcome.is_successful,
                "recovered_amount": outcome.recovered_amount,
                "new_payment_id": outcome.new_payment_id,
                "final_case_status": case_status
            }
        })

        return outcome


outcome_service = OutcomeService()
