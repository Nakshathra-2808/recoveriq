import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone, time
from app.schemas.recovery import (
    ActionType,
    RootCauseCategory,
    GuardrailResult,
    CaseStatus,
)
from app.services.supabase_db import db, SupabaseDB

logger = logging.getLogger(__name__)


class GuardrailEngine:
    """
    Deterministic Safety & Policy Guardrail Engine.
    Intercepts and rigorously verifies every proposed recovery action against hardcoded
    business constraints and merchant policy configurations before dispatch.
    Cannot be bypassed by AI proposals.
    """

    def __init__(self, database: Optional[SupabaseDB] = None):
        self.db = database or db

    def _is_within_communication_window(
        self,
        current_dt: datetime,
        start_str: str = "09:00:00",
        end_str: str = "20:00:00",
        allowed_days: Optional[list] = None
    ) -> bool:
        """Verifies if the current time and day are within allowed customer contact hours."""
        if allowed_days:
            day_name = current_dt.strftime("%A").upper()
            if day_name not in allowed_days:
                return False

        try:
            start_parts = [int(p) for p in start_str.split(":")]
            end_parts = [int(p) for p in end_str.split(":")]
            start_time = time(start_parts[0], start_parts[1], start_parts[2] if len(start_parts) > 2 else 0)
            end_time = time(end_parts[0], end_parts[1], end_parts[2] if len(end_parts) > 2 else 0)
            
            cur_time = current_dt.time()
            return start_time <= cur_time <= end_time
        except Exception as e:
            logger.warning(f"Error parsing communication window times: {e}")
            return True

    def validate_action(
        self,
        proposed_action: ActionType,
        case: Dict[str, Any],
        policy: Dict[str, Any],
        customer: Optional[Dict[str, Any]] = None,
        now_dt: Optional[datetime] = None
    ) -> GuardrailResult:
        """
        Executes all deterministic safety checks against the proposed recovery action.
        """
        now = now_dt or datetime.now(timezone.utc)
        checks_passed: Dict[str, bool] = {}
        amount = float(case.get("payment", {}).get("amount", 0.0) if case.get("payment") else case.get("amount", 0.0))
        retry_count = int(case.get("retry_count", 0))
        communication_count = int(case.get("communication_count", 0))
        diag_dict = case.get("diagnosis_summary", {})
        root_cause_str = diag_dict.get("root_cause_category", "OTHER")

        # ---------------------------------------------------------------------
        # 1. OPT-OUT INVARIANT: Customers opted-out must NEVER receive actions/messages
        # ---------------------------------------------------------------------
        if customer and customer.get("is_opted_out", False):
            checks_passed["opt_out_check"] = False
            return GuardrailResult(
                allowed=True,  # Allowed to execute terminal STOP
                proposed_action=proposed_action,
                final_action=ActionType.STOP,
                is_overridden=proposed_action != ActionType.STOP,
                override_reason="Customer has opted out of automated communications. Halting recovery.",
                checks_passed=checks_passed,
                details={"customer_id": customer.get("id"), "is_opted_out": True}
            )
        checks_passed["opt_out_check"] = True

        # ---------------------------------------------------------------------
        # 2. FRAUD PROTECTION INVARIANT: Hard fraud declines must be STOPPED
        # ---------------------------------------------------------------------
        if root_cause_str == RootCauseCategory.FRAUD_DECLINE.value:
            checks_passed["fraud_check"] = False
            return GuardrailResult(
                allowed=True,
                proposed_action=proposed_action,
                final_action=ActionType.STOP,
                is_overridden=proposed_action != ActionType.STOP,
                override_reason="Hard fraud decline detected. Automated retries forbidden by risk policy.",
                checks_passed=checks_passed,
                details={"root_cause": root_cause_str}
            )
        checks_passed["fraud_check"] = True

        # ---------------------------------------------------------------------
        # 3. HIGH-VALUE ESCALATION INVARIANT
        # ---------------------------------------------------------------------
        threshold = float(policy.get("escalation_threshold_amount", 10000.00))
        if policy.get("auto_escalate_vip", True) and amount >= threshold:
            if proposed_action not in (ActionType.ESCALATE, ActionType.STOP):
                # For very high value orders, override automated retries to high-touch merchant escalation
                checks_passed["high_value_escalation"] = True
                return GuardrailResult(
                    allowed=True,
                    proposed_action=proposed_action,
                    final_action=ActionType.ESCALATE,
                    is_overridden=True,
                    override_reason=f"Payment amount ({amount} INR) meets or exceeds high-value escalation threshold ({threshold} INR). Routing to manual operations.",
                    checks_passed=checks_passed,
                    details={"amount": amount, "threshold": threshold}
                )
        checks_passed["high_value_escalation"] = True

        # ---------------------------------------------------------------------
        # 4. MAX RETRY LIMIT INVARIANT
        # ---------------------------------------------------------------------
        max_retries = int(policy.get("max_retries", 3))
        if proposed_action in (ActionType.RETRY_NOW, ActionType.RETRY_LATER):
            if retry_count >= max_retries:
                checks_passed["max_retries_check"] = False
                final_act = ActionType.ESCALATE if amount >= 5000.00 else ActionType.STOP
                return GuardrailResult(
                    allowed=True,
                    proposed_action=proposed_action,
                    final_action=final_act,
                    is_overridden=True,
                    override_reason=f"Maximum retry limit ({max_retries}) reached. Terminal state enforced.",
                    checks_passed=checks_passed,
                    details={"retry_count": retry_count, "max_retries": max_retries}
                )
        checks_passed["max_retries_check"] = True

        # ---------------------------------------------------------------------
        # 5. MAX COMMUNICATION LIMIT INVARIANT
        # ---------------------------------------------------------------------
        max_comms = int(policy.get("max_communications", 3))
        if proposed_action in (ActionType.REMINDER, ActionType.PAYMENT_UPDATE):
            if communication_count >= max_comms:
                checks_passed["max_communications_check"] = False
                return GuardrailResult(
                    allowed=True,
                    proposed_action=proposed_action,
                    final_action=ActionType.RETRY_LATER if retry_count < max_retries else ActionType.STOP,
                    is_overridden=True,
                    override_reason=f"Customer communication limit ({max_comms}) reached. Preventing notification fatigue.",
                    checks_passed=checks_passed,
                    details={"communication_count": communication_count, "max_communications": max_comms}
                )
        checks_passed["max_communications_check"] = True

        # ---------------------------------------------------------------------
        # 6. COMMUNICATION WINDOW & ALLOWED DAYS INVARIANT
        # ---------------------------------------------------------------------
        if proposed_action in (ActionType.REMINDER, ActionType.PAYMENT_UPDATE):
            window_start = policy.get("communication_window_start", "09:00:00")
            window_end = policy.get("communication_window_end", "20:00:00")
            allowed_days = policy.get("allowed_days", [])
            in_window = self._is_within_communication_window(now, window_start, window_end, allowed_days)
            checks_passed["communication_window_check"] = in_window
            if not in_window:
                return GuardrailResult(
                    allowed=True,
                    proposed_action=proposed_action,
                    final_action=ActionType.RETRY_LATER,
                    is_overridden=True,
                    override_reason=f"Current time ({now.strftime('%H:%M:%S')}) is outside allowed communication window ({window_start} - {window_end}) or day. Deferred.",
                    checks_passed=checks_passed,
                    details={"window_start": window_start, "window_end": window_end}
                )
        else:
            checks_passed["communication_window_check"] = True

        # ---------------------------------------------------------------------
        # 7. COOLDOWN PERIOD INVARIANT
        # ---------------------------------------------------------------------
        cooldown_mins = int(policy.get("cooldown_minutes", 60))
        last_action_time_str = case.get("metadata", {}).get("last_action_executed_at")
        if last_action_time_str and proposed_action == ActionType.RETRY_NOW:
            try:
                last_dt = datetime.fromisoformat(last_action_time_str.replace("Z", "+00:00"))
                elapsed_mins = (now - last_dt).total_seconds() / 60.0
                if elapsed_mins < cooldown_mins:
                    checks_passed["cooldown_check"] = False
                    return GuardrailResult(
                        allowed=True,
                        proposed_action=proposed_action,
                        final_action=ActionType.RETRY_LATER,
                        is_overridden=True,
                        override_reason=f"Mandatory cooldown interval of {cooldown_mins} minutes has not elapsed ({elapsed_mins:.1f} mins elapsed).",
                        checks_passed=checks_passed,
                        details={"cooldown_minutes": cooldown_mins, "elapsed_minutes": elapsed_mins}
                    )
            except Exception as e:
                logger.warning(f"Error parsing last_action_executed_at: {e}")
        checks_passed["cooldown_check"] = True

        # All checks passed! Action approved without modification.
        return GuardrailResult(
            allowed=True,
            proposed_action=proposed_action,
            final_action=proposed_action,
            is_overridden=False,
            override_reason=None,
            checks_passed=checks_passed,
            details={"status": "APPROVED"}
        )

    async def guard_case(self, case_id: str, merchant_id: str) -> Optional[GuardrailResult]:
        """
        Applies guardrails to the case's proposed action and transitions to APPROVED, STOPPED, or ESCALATED.
        """
        case = await self.db.get_recovery_case(case_id, merchant_id)
        if not case:
            return None

        policy = await self.db.get_default_policy(merchant_id)
        customer = case.get("customer")
        proposed_action_str = case.get("metadata", {}).get("proposed_action", "STOP")
        proposed_action = ActionType(proposed_action_str)

        guard_res = self.validate_action(proposed_action, case, policy, customer)

        # Transition status based on guardrail result
        if guard_res.final_action == ActionType.STOP:
            next_status = CaseStatus.STOPPED.value
        elif guard_res.final_action == ActionType.ESCALATE:
            next_status = CaseStatus.ESCALATED.value
        else:
            next_status = CaseStatus.APPROVED.value

        await self.db.update_recovery_case(case_id, merchant_id, {
            "status": next_status,
            "metadata": {
                **case.get("metadata", {}),
                "final_action": guard_res.final_action.value,
                "guardrail_passed": guard_res.allowed,
                "guardrail_overridden": guard_res.is_overridden,
                "guardrail_override_reason": guard_res.override_reason,
            }
        })

        # Record audit log
        await self.db.create_audit_log({
            "merchant_id": merchant_id,
            "case_id": case_id,
            "actor_type": "SYSTEM",
            "event_type": "GUARDRAIL_CHECK",
            "severity": "WARNING" if guard_res.is_overridden else "INFO",
            "description": f"Guardrail evaluation: {guard_res.final_action.value} ({'Overridden: ' + guard_res.override_reason if guard_res.is_overridden else 'Approved'})",
            "details": {
                "proposed_action": proposed_action.value,
                "final_action": guard_res.final_action.value,
                "checks": guard_res.checks_passed,
                "override_reason": guard_res.override_reason
            }
        })

        return guard_res


guardrail_engine = GuardrailEngine()
