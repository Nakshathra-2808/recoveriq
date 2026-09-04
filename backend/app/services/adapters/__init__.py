import uuid
from typing import Dict, Any
from datetime import datetime, timezone
from app.schemas.recovery import ActionType, ExecutionMode, ExecutionResult


class BaseActionAdapter:
    """Base interface for all recovery action executors."""
    async def execute(self, case: Dict[str, Any], merchant_id: str, mode: ExecutionMode = ExecutionMode.SIMULATION) -> Dict[str, Any]:
        raise NotImplementedError


class RetryPaymentAdapter(BaseActionAdapter):
    """Executes or simulates payment retry."""
    async def execute(self, case: Dict[str, Any], merchant_id: str, mode: ExecutionMode = ExecutionMode.SIMULATION) -> Dict[str, Any]:
        amount = float(case.get("payment", {}).get("amount", 0.0) if case.get("payment") else case.get("amount", 0.0))
        payment_id = case.get("payment_id", "pay_unknown")
        
        return {
            "action_type": ActionType.RETRY_NOW.value,
            "execution_mode": mode.value,
            "simulated": mode == ExecutionMode.SIMULATION,
            "retry_target_payment_id": payment_id,
            "retry_amount": amount,
            "gateway_dispatch_status": "QUEUED_TO_GATEWAY",
            "message": f"Simulated payment retry dispatched for {payment_id} ({amount} INR)."
        }


class PaymentUpdateAdapter(BaseActionAdapter):
    """Generates smart fallback payment link."""
    async def execute(self, case: Dict[str, Any], merchant_id: str, mode: ExecutionMode = ExecutionMode.SIMULATION) -> Dict[str, Any]:
        payment_id = case.get("payment_id", "pay_unknown")
        customer = case.get("customer", {})
        customer_email = customer.get("email") if customer else "customer@example.com"
        
        fallback_link = f"https://pay.recoveriq.example.com/checkout/{payment_id}?fallback=true"
        return {
            "action_type": ActionType.PAYMENT_UPDATE.value,
            "execution_mode": mode.value,
            "simulated": mode == ExecutionMode.SIMULATION,
            "payment_link": fallback_link,
            "channels": ["SMS", "EMAIL"],
            "recipient": customer_email,
            "message": f"Payment update link generated and delivered to customer {customer_email}."
        }


class ReminderAdapter(BaseActionAdapter):
    """Dispatches gentle reminder notification."""
    async def execute(self, case: Dict[str, Any], merchant_id: str, mode: ExecutionMode = ExecutionMode.SIMULATION) -> Dict[str, Any]:
        customer = case.get("customer", {})
        customer_phone = customer.get("phone") if customer else "+919876543210"
        
        return {
            "action_type": ActionType.REMINDER.value,
            "execution_mode": mode.value,
            "simulated": mode == ExecutionMode.SIMULATION,
            "channel": "WHATSAPP_SMS",
            "recipient_phone": customer_phone,
            "notification_template": "recoveriq_gentle_reminder_v1",
            "message": f"Recovery reminder dispatched to {customer_phone}."
        }


class EscalationAdapter(BaseActionAdapter):
    """Flags high-value case for manual merchant intervention."""
    async def execute(self, case: Dict[str, Any], merchant_id: str, mode: ExecutionMode = ExecutionMode.SIMULATION) -> Dict[str, Any]:
        amount = float(case.get("payment", {}).get("amount", 0.0) if case.get("payment") else case.get("amount", 0.0))
        
        return {
            "action_type": ActionType.ESCALATE.value,
            "execution_mode": mode.value,
            "simulated": mode == ExecutionMode.SIMULATION,
            "escalation_tier": "VIP_MERCHANT_OPS",
            "assigned_team": "Acme Retail Account Management",
            "flagged_amount": amount,
            "message": f"Case escalated to manual merchant operations (Amount: {amount} INR)."
        }


class StopAdapter(BaseActionAdapter):
    """Halts recovery case."""
    async def execute(self, case: Dict[str, Any], merchant_id: str, mode: ExecutionMode = ExecutionMode.SIMULATION) -> Dict[str, Any]:
        return {
            "action_type": ActionType.STOP.value,
            "execution_mode": mode.value,
            "provider": "SIMULATION",
            "simulated": True,
            "terminal_state": True,
            "message": "Recovery terminated by policy guardrail."
        }


class DryRunAdapter(BaseActionAdapter):
    """Performs dry-run action evaluation without any external network dispatch."""
    async def execute(self, case: Dict[str, Any], merchant_id: str, mode: ExecutionMode = ExecutionMode.DRY_RUN) -> Dict[str, Any]:
        metadata = case.get("metadata", {})
        action_str = metadata.get("final_action") or metadata.get("proposed_action", "STOP")
        action_type = ActionType(action_str)

        return {
            "action_type": action_type.value,
            "execution_mode": ExecutionMode.DRY_RUN.value,
            "provider": "DRY_RUN",
            "status": "COMPLETED",
            "external_reference": None,
            "simulated": True,
            "message": f"Dry-run evaluation for {action_type.value} completed without external network dispatch.",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }


# Lazy import for RazorpayTestAdapter to prevent circular dependencies
from app.services.adapters.razorpay_test_adapter import RazorpayTestAdapter
