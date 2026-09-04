import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from app.schemas.recovery import (
    RootCauseCategory,
    ActionType,
    ActionCandidate,
    PolicyDecision,
    CaseStatus,
)
from app.services.supabase_db import db, SupabaseDB

logger = logging.getLogger(__name__)

# Calibrated prior recovery probabilities (Beta distribution priors) for cold-start cases
DEFAULT_PRIORS: Dict[RootCauseCategory, Dict[ActionType, float]] = {
    RootCauseCategory.NETWORK_TIMEOUT: {
        ActionType.RETRY_NOW: 0.85,
        ActionType.RETRY_LATER: 0.65,
        ActionType.PAYMENT_UPDATE: 0.40,
        ActionType.REMINDER: 0.30,
        ActionType.ESCALATE: 0.10,
        ActionType.STOP: 0.00,
    },
    RootCauseCategory.GATEWAY_ERROR: {
        ActionType.RETRY_LATER: 0.80,
        ActionType.PAYMENT_UPDATE: 0.60,
        ActionType.RETRY_NOW: 0.35,
        ActionType.REMINDER: 0.40,
        ActionType.ESCALATE: 0.15,
        ActionType.STOP: 0.00,
    },
    RootCauseCategory.INSUFFICIENT_FUNDS: {
        ActionType.REMINDER: 0.72,
        ActionType.PAYMENT_UPDATE: 0.68,
        ActionType.RETRY_LATER: 0.50,
        ActionType.RETRY_NOW: 0.15,
        ActionType.ESCALATE: 0.10,
        ActionType.STOP: 0.00,
    },
    RootCauseCategory.USER_DROPPED: {
        ActionType.PAYMENT_UPDATE: 0.78,
        ActionType.REMINDER: 0.70,
        ActionType.RETRY_LATER: 0.30,
        ActionType.RETRY_NOW: 0.10,
        ActionType.ESCALATE: 0.10,
        ActionType.STOP: 0.00,
    },
    RootCauseCategory.CARD_LIMIT_EXCEEDED: {
        ActionType.PAYMENT_UPDATE: 0.75,
        ActionType.RETRY_LATER: 0.45,
        ActionType.REMINDER: 0.40,
        ActionType.RETRY_NOW: 0.05,
        ActionType.ESCALATE: 0.20,
        ActionType.STOP: 0.00,
    },
    RootCauseCategory.FRAUD_DECLINE: {
        ActionType.STOP: 1.00,
        ActionType.ESCALATE: 0.20,
        ActionType.RETRY_NOW: 0.00,
        ActionType.RETRY_LATER: 0.00,
        ActionType.PAYMENT_UPDATE: 0.00,
        ActionType.REMINDER: 0.00,
    },
    RootCauseCategory.OTHER: {
        ActionType.RETRY_LATER: 0.50,
        ActionType.PAYMENT_UPDATE: 0.50,
        ActionType.REMINDER: 0.35,
        ActionType.RETRY_NOW: 0.25,
        ActionType.ESCALATE: 0.15,
        ActionType.STOP: 0.00,
    }
}


class PolicyEngine:
    """
    Adaptive Action Selector for payment recovery.
    Combines calibrated statistical priors with merchant-specific historical learning
    from the action_statistics table via Bayesian smoothing.
    """

    def __init__(self, database: Optional[SupabaseDB] = None):
        self.db = database or db

    async def select_action(
        self,
        case: Dict[str, Any],
        merchant_id: str,
        root_cause: RootCauseCategory,
        retry_count: int = 0
    ) -> PolicyDecision:
        """
        Evaluates and ranks all candidate recovery actions using historical data and priors.
        """
        # 1. Terminal fraud decline short-circuit
        if root_cause == RootCauseCategory.FRAUD_DECLINE:
            candidate = ActionCandidate(
                action_type=ActionType.STOP,
                score=1.0,
                confidence=1.0,
                historical_success_rate=0.0,
                historical_attempts=0,
                reasoning="Immediate stop due to fraud decline."
            )
            return PolicyDecision(
                selected_action=ActionType.STOP,
                confidence_score=1.0,
                reasoning="Hard fraud decline detected. Automated retries prohibited to protect merchant risk score.",
                ranked_candidates=[candidate],
                used_historical_learning=False
            )

        # 2. Query historical statistics for this merchant and root cause
        stats_records = await self.db.get_action_statistics(merchant_id, root_cause.value)
        stats_map = {r["action_type"]: r for r in stats_records}

        candidates: List[ActionCandidate] = []
        priors = DEFAULT_PRIORS.get(root_cause, DEFAULT_PRIORS[RootCauseCategory.OTHER])

        used_historical = False
        all_actions = [
            ActionType.RETRY_NOW,
            ActionType.RETRY_LATER,
            ActionType.PAYMENT_UPDATE,
            ActionType.REMINDER,
            ActionType.ESCALATE,
            ActionType.STOP,
        ]

        for action in all_actions:
            prior_rate = priors.get(action, 0.10)
            stat = stats_map.get(action.value)

            if stat and stat.get("total_attempts", 0) >= 3:
                # Bayesian update: weight prior + observed evidence
                attempts = stat["total_attempts"]
                successes = stat.get("successful_recoveries", 0)
                # Alpha & Beta pseudo-counts for prior smoothing
                alpha = prior_rate * 5.0
                beta = (1.0 - prior_rate) * 5.0
                smoothed_rate = (successes + alpha) / (attempts + alpha + beta)
                confidence = min(0.98, 0.70 + (attempts / 50.0) * 0.28)
                reason = f"Learned from {attempts} historical attempts with {stat.get('success_rate', 0.0)*100:.1f}% empirical success rate."
                used_historical = True
            else:
                smoothed_rate = prior_rate
                confidence = 0.80
                reason = f"Calibrated prior baseline for {root_cause.value}."

            # Dynamic penalty for repeated attempts of the same action
            if action == ActionType.RETRY_NOW and retry_count > 0:
                smoothed_rate *= 0.5  # Immediate retry less effective after initial failure
            elif action == ActionType.RETRY_LATER and retry_count > 1:
                smoothed_rate *= 0.8

            candidates.append(
                ActionCandidate(
                    action_type=action,
                    score=round(smoothed_rate, 4),
                    confidence=round(confidence, 4),
                    historical_success_rate=round(stat.get("success_rate", 0.0), 4) if stat else 0.0,
                    historical_attempts=stat.get("total_attempts", 0) if stat else 0,
                    reasoning=reason
                )
            )

        # Sort candidate actions descending by score
        candidates.sort(key=lambda c: c.score, reverse=True)
        top_candidate = candidates[0]

        decision = PolicyDecision(
            selected_action=top_candidate.action_type,
            confidence_score=top_candidate.confidence,
            reasoning=f"Selected {top_candidate.action_type.value} with recovery score {top_candidate.score:.2f} ({top_candidate.reasoning})",
            ranked_candidates=candidates,
            used_historical_learning=used_historical
        )

        return decision

    async def decide_for_case(self, case_id: str, merchant_id: str) -> Optional[PolicyDecision]:
        """
        Runs adaptive action selection on a diagnosed recovery case and transitions to DECISION_READY.
        """
        case = await self.db.get_recovery_case(case_id, merchant_id)
        if not case or not case.get("diagnosis_summary"):
            logger.warning(f"Cannot decide policy for case {case_id}: missing diagnosis summary")
            return None

        diag_dict = case["diagnosis_summary"]
        root_cause = RootCauseCategory(diag_dict.get("root_cause_category", "OTHER"))
        retry_count = case.get("retry_count", 0)

        decision = await self.select_action(case, merchant_id, root_cause, retry_count)

        # Update case metadata with proposed decision
        await self.db.update_recovery_case(case_id, merchant_id, {
            "status": CaseStatus.DECISION_READY.value,
            "metadata": {
                **case.get("metadata", {}),
                "proposed_action": decision.selected_action.value,
                "decision_confidence": decision.confidence_score,
                "used_learning": decision.used_historical_learning,
            }
        })

        # Record audit log
        await self.db.create_audit_log({
            "merchant_id": merchant_id,
            "case_id": case_id,
            "actor_type": "AI_AGENT",
            "event_type": "ACTION_RECOMMENDED",
            "severity": "INFO",
            "description": f"Adaptive policy engine recommended action: {decision.selected_action.value} (Score: {decision.ranked_candidates[0].score:.2f})",
            "details": {
                "selected_action": decision.selected_action.value,
                "confidence": decision.confidence_score,
                "ranked_candidates": [
                    {"action": c.action_type.value, "score": c.score, "attempts": c.historical_attempts}
                    for c in decision.ranked_candidates[:3]
                ]
            }
        })

        return decision


policy_engine = PolicyEngine()
