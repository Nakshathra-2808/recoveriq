import logging
import uuid
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from app.schemas.recovery import (
    ActionType,
    ExecutionMode,
    ExecutionResult,
    CaseStatus,
)
from app.services.supabase_db import db, SupabaseDB
from app.services.adapters import (
    RetryPaymentAdapter,
    PaymentUpdateAdapter,
    ReminderAdapter,
    EscalationAdapter,
    StopAdapter,
    DryRunAdapter,
    RazorpayTestAdapter,
    BaseActionAdapter,
)

logger = logging.getLogger(__name__)


class ExecutorService:
    """
    Action Execution Orchestrator.
    Dispatches validated recovery actions through controlled adapters:
    - SIMULATION: Safe, high-fidelity deterministic simulation
    - RAZORPAY_TEST: Genuine server-side test sandbox API integration
    - DRY_RUN: Internal evaluation with no external network dispatch
    """

    def __init__(
        self,
        database: Optional[SupabaseDB] = None,
        razorpay_adapter: Optional[RazorpayTestAdapter] = None,
        dry_run_adapter: Optional[DryRunAdapter] = None,
    ):
        self.db = database or db
        self.simulation_adapters: Dict[ActionType, BaseActionAdapter] = {
            ActionType.RETRY_NOW: RetryPaymentAdapter(),
            ActionType.RETRY_LATER: RetryPaymentAdapter(),
            ActionType.PAYMENT_UPDATE: PaymentUpdateAdapter(),
            ActionType.REMINDER: ReminderAdapter(),
            ActionType.ESCALATE: EscalationAdapter(),
            ActionType.STOP: StopAdapter(),
        }
        self.razorpay_adapter = razorpay_adapter or RazorpayTestAdapter()
        self.dry_run_adapter = dry_run_adapter or DryRunAdapter()

    async def execute_case_action(
        self,
        case_id: str,
        merchant_id: str,
        mode: ExecutionMode = ExecutionMode.SIMULATION
    ) -> Optional[ExecutionResult]:
        """
        Executes the approved recovery action for a recovery case according to specified execution mode.
        """
        case = await self.db.get_recovery_case(case_id, merchant_id)
        if not case:
            logger.warning(f"Cannot execute action: case {case_id} not found")
            return None

        metadata = case.get("metadata", {})
        action_str = metadata.get("final_action") or metadata.get("proposed_action", "STOP")
        action_type = ActionType(action_str)

        # Route to appropriate adapter based on execution mode
        if mode == ExecutionMode.RAZORPAY_TEST:
            adapter = self.razorpay_adapter
        elif mode == ExecutionMode.DRY_RUN:
            adapter = self.dry_run_adapter
        else:
            adapter = self.simulation_adapters.get(action_type, self.simulation_adapters[ActionType.STOP])

        action_payload = await adapter.execute(case, merchant_id, mode)

        # Count existing actions to determine sequence number
        existing_actions = await self.db.get_recovery_actions(case_id, merchant_id)
        sequence_number = len(existing_actions) + 1

        action_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        diag_summary = case.get("diagnosis_summary", {})
        ai_reason = metadata.get("ai_reasoning") or diag_summary.get("reason") or diag_summary.get("reasoning") or f"Dispatched {action_type.value} recovery action."
        ai_conf = metadata.get("decision_confidence") or diag_summary.get("confidence") or diag_summary.get("confidence_score") or 0.90

        action_record = {
            "id": action_id,
            "merchant_id": merchant_id,
            "case_id": case_id,
            "action_type": action_type.value,
            "execution_mode": mode.value,
            "status": "COMPLETED",
            "sequence_number": sequence_number,
            "scheduled_at": now.isoformat(),
            "executed_at": now.isoformat(),
            "payload": action_payload,
            "guardrail_check_passed": metadata.get("guardrail_passed", True),
            "guardrail_details": {
                "overridden": metadata.get("guardrail_overridden", False),
                "override_reason": metadata.get("guardrail_override_reason")
            },
            "ai_confidence_score": ai_conf,
            "ai_reasoning": ai_reason
        }

        created_action = await self.db.create_recovery_action(action_record)

        # Update case metrics & execution timestamps
        retry_inc = 1 if action_type in (ActionType.RETRY_NOW, ActionType.RETRY_LATER) else 0
        comm_inc = 1 if action_type in (ActionType.REMINDER, ActionType.PAYMENT_UPDATE) else 0

        next_status = CaseStatus.EXECUTING.value
        if action_type == ActionType.STOP:
            next_status = CaseStatus.STOPPED.value
        elif action_type == ActionType.ESCALATE:
            next_status = CaseStatus.ESCALATED.value

        await self.db.update_recovery_case(case_id, merchant_id, {
            "status": next_status,
            "retry_count": int(case.get("retry_count", 0)) + retry_inc,
            "communication_count": int(case.get("communication_count", 0)) + comm_inc,
            "metadata": {
                **metadata,
                "last_action_id": action_id,
                "last_action_type": action_type.value,
                "last_action_executed_at": now.isoformat(),
            }
        })

        # Record audit log
        await self.db.create_audit_log({
            "merchant_id": merchant_id,
            "case_id": case_id,
            "action_id": action_id,
            "actor_type": "AI_AGENT",
            "event_type": "ACTION_DISPATCHED",
            "severity": "INFO",
            "description": f"Executed action {action_type.value} in {mode.value} mode (Sequence #{sequence_number})",
            "details": {
                "action_type": action_type.value,
                "execution_mode": mode.value,
                "simulated": mode == ExecutionMode.SIMULATION,
                "guardrail_passed": metadata.get("guardrail_passed", True)
            }
        })

        return ExecutionResult(
            action_id=action_id,
            action_type=action_type,
            execution_mode=mode,
            status="COMPLETED",
            payload=action_payload,
            guardrail_check_passed=metadata.get("guardrail_passed", True),
            executed_at=now
        )


executor_service = ExecutorService()
