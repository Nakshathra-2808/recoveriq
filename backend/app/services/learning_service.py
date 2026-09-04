import logging
from typing import Dict, Any, Optional
from app.schemas.recovery import LearningUpdateResult
from app.services.supabase_db import db, SupabaseDB

logger = logging.getLogger(__name__)


class LearningService:
    """
    Continuous Learning & Bayesian Statistics Update Service.
    Feeds back verified action outcomes into empirical action_statistics records
    strictly partitioned by merchant organization.
    """

    def __init__(self, database: Optional[SupabaseDB] = None):
        self.db = database or db

    async def update_statistics_from_outcome(
        self,
        case_id: str,
        action_id: str,
        outcome: Dict[str, Any],
        merchant_id: str
    ) -> Optional[LearningUpdateResult]:
        """
        Updates action_statistics for (merchant_id, root_cause_category, action_type).
        """
        case = await self.db.get_recovery_case(case_id, merchant_id)
        if not case:
            logger.warning(f"Cannot update learning: case {case_id} not found")
            return None

        diag_dict = case.get("diagnosis_summary", {})
        root_cause = diag_dict.get("root_cause_category", "OTHER")

        actions = await self.db.get_recovery_actions(case_id, merchant_id)
        action_type = "RETRY_NOW"
        for a in actions:
            if a.get("id") == action_id:
                action_type = a.get("action_type", "RETRY_NOW")
                break

        is_successful = bool(outcome.get("is_successful", False))
        recovered_amount = float(outcome.get("recovered_amount", 0.0))
        recovery_time = int(outcome.get("recovery_time_seconds") or 0)

        # Incrementally update stats in database
        updated_stat = await self.db.upsert_action_statistic(
            merchant_id=merchant_id,
            root_cause_category=root_cause,
            action_type=action_type,
            is_successful=is_successful,
            recovered_amount=recovered_amount,
            recovery_time_seconds=recovery_time
        )

        result = LearningUpdateResult(
            merchant_id=merchant_id,
            root_cause_category=root_cause,
            action_type=action_type,
            total_attempts=updated_stat["total_attempts"],
            successful_recoveries=updated_stat["successful_recoveries"],
            success_rate=updated_stat["success_rate"],
            total_recovered_amount=updated_stat["total_recovered_amount"]
        )

        # Record audit log
        await self.db.create_audit_log({
            "merchant_id": merchant_id,
            "case_id": case_id,
            "action_id": action_id,
            "actor_type": "AI_AGENT",
            "event_type": "LEARNING_UPDATED",
            "severity": "INFO",
            "description": f"Updated learning statistics for {root_cause} + {action_type}: {result.success_rate*100:.1f}% success rate across {result.total_attempts} attempts.",
            "details": {
                "root_cause": root_cause,
                "action_type": action_type,
                "attempts": result.total_attempts,
                "successes": result.successful_recoveries,
                "new_success_rate": result.success_rate,
                "total_recovered": result.total_recovered_amount
            }
        })

        return result


learning_service = LearningService()
