import logging
import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from app.services.supabase_db import db, SupabaseDB
from app.schemas.recovery import CasePriority, CaseStatus

logger = logging.getLogger(__name__)


class DetectionService:
    """
    Detects failed payments for the authenticated merchant and initializes recovery cases.
    Evaluates failure severity, payment amount, and customer history to assign initial priority.
    """

    def __init__(self, database: Optional[SupabaseDB] = None):
        self.db = database or db

    def calculate_priority(self, amount: float, customer: Optional[Dict[str, Any]] = None) -> CasePriority:
        """Assigns priority based on business value and customer attributes."""
        if amount >= 25000.00:
            return CasePriority.CRITICAL
        elif amount >= 10000.00:
            return CasePriority.HIGH
        elif amount >= 2000.00:
            return CasePriority.MEDIUM
        return CasePriority.LOW

    async def detect_and_create_case(
        self,
        payment_id: str,
        merchant_id: str,
        batch_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Creates a new recovery_case for a specific failed payment.
        Guarantees that a payment has at most one active recovery case.
        """
        payment = await self.db.get_payment_with_failure(payment_id, merchant_id)
        if not payment or not payment.get("failure"):
            logger.warning(f"Cannot detect recovery case: payment {payment_id} has no failure record")
            return None

        # Check if case already exists for this payment
        existing = await self.db._select("recovery_cases", {"payment_id": f"eq.{payment_id}", "merchant_id": f"eq.{merchant_id}"})
        if existing:
            return existing[0]

        policy = await self.db.get_default_policy(merchant_id)
        amount = float(payment.get("amount", 0.0))
        customer = payment.get("customer")
        priority = self.calculate_priority(amount, customer)

        case_id = str(uuid.uuid4())
        case_data = {
            "id": case_id,
            "merchant_id": merchant_id,
            "payment_id": payment_id,
            "failure_id": payment["failure"]["id"],
            "policy_id": policy.get("id"),
            "batch_id": batch_id or payment.get("batch_id"),
            "status": CaseStatus.DETECTED.value,
            "priority": priority.value,
            "retry_count": 0,
            "communication_count": 0,
            "recovered_amount": 0.00,
            "diagnosis_summary": {},
            "metadata": {
                "detected_at": datetime.now(timezone.utc).isoformat(),
                "initial_error_code": payment["failure"].get("error_code"),
                "initial_root_cause": payment["failure"].get("root_cause_category"),
                "amount": amount,
                "currency": payment.get("currency", "INR")
            }
        }

        created_case = await self.db.create_recovery_case(case_data)

        # Record audit log
        await self.db.create_audit_log({
            "merchant_id": merchant_id,
            "case_id": case_id,
            "actor_type": "SYSTEM",
            "event_type": "CASE_DETECTED",
            "severity": "INFO",
            "description": f"Recovery case detected for failed payment {payment_id} ({amount} INR, {payment['failure'].get('root_cause_category')})",
            "details": {
                "priority": priority.value,
                "error_code": payment["failure"].get("error_code"),
                "error_reason": payment["failure"].get("error_reason"),
            }
        })

        return created_case

    async def scan_and_create_cases(
        self,
        merchant_id: str,
        batch_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Scans all unhandled payment failures for this merchant and creates recovery cases."""
        unhandled = await self.db.get_unhandled_payment_failures(merchant_id, batch_id)
        created = []
        for p in unhandled:
            case = await self.detect_and_create_case(p["id"], merchant_id, batch_id)
            if case:
                created.append(case)
        return created


detection_service = DetectionService()
