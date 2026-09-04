import logging
import uuid
import hashlib
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from app.schemas.recovery import RootCauseCategory
from app.services.supabase_db import db, SupabaseDB

logger = logging.getLogger(__name__)


class BaselineService:
    """
    Standard Fixed-Strategy Benchmark Engine.
    Simulates standard, naive payment recovery (immediate fixed retry without adaptive timing,
    channel switching, or Bayesian learning) on identical batches to measure true incremental lift.
    """

    def __init__(self, database: Optional[SupabaseDB] = None):
        self.db = database or db

    def evaluate_fixed_baseline(
        self,
        payment: Dict[str, Any],
        failure: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Executes standard fixed 1-attempt baseline logic:
        - NETWORK_TIMEOUT: single immediate retry (50% baseline success)
        - GATEWAY_ERROR: single immediate retry (25% baseline success, usually fails due to lack of backoff)
        - INSUFFICIENT_FUNDS: single static reminder (35% baseline success)
        - USER_DROPPED: generic email (30% baseline success)
        - CARD_LIMIT_EXCEEDED: immediate retry (0% baseline success, fails without method change)
        - FRAUD_DECLINE: STOP (0% baseline success)
        """
        amount = float(payment.get("amount", 0.0))
        payment_id = payment.get("id", "pay_default")
        root_cause = failure.get("root_cause_category", "OTHER")

        hash_val = int(hashlib.md5(f"baseline:{payment_id}:{root_cause}".encode()).hexdigest()[:8], 16)
        prob_roll = (hash_val % 100) / 100.0

        baseline_rates = {
            RootCauseCategory.NETWORK_TIMEOUT.value: 0.50,
            RootCauseCategory.GATEWAY_ERROR.value: 0.25,
            RootCauseCategory.INSUFFICIENT_FUNDS.value: 0.35,
            RootCauseCategory.USER_DROPPED.value: 0.30,
            RootCauseCategory.CARD_LIMIT_EXCEEDED.value: 0.05,
            RootCauseCategory.FRAUD_DECLINE.value: 0.00,
        }

        success_prob = baseline_rates.get(root_cause, 0.20)
        is_recovered = prob_roll < success_prob
        recovered_amt = amount if is_recovered else 0.00

        return {
            "strategy_name": "FIXED_STANDARD_RETRY",
            "is_recovered": is_recovered,
            "total_attempts": 1 if root_cause != RootCauseCategory.FRAUD_DECLINE.value else 0,
            "recovered_amount": recovered_amt,
            "execution_log": {
                "root_cause": root_cause,
                "strategy": "Naive single attempt without backoff or adaptive channels",
                "simulated": True,
                "recovered": is_recovered
            }
        }

    async def run_baseline_for_batch(
        self,
        batch_id: str,
        merchant_id: str,
        payments: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Runs the baseline recovery benchmark for all payments in a batch and saves baseline_results.
        """
        results = []
        for p in payments:
            failure = p.get("failure", {})
            baseline_eval = self.evaluate_fixed_baseline(p, failure)

            result_id = str(uuid.uuid4())
            record = {
                "id": result_id,
                "merchant_id": merchant_id,
                "batch_id": batch_id,
                "case_id": None,
                "strategy_name": baseline_eval["strategy_name"],
                "is_recovered": baseline_eval["is_recovered"],
                "total_attempts": baseline_eval["total_attempts"],
                "recovered_amount": baseline_eval["recovered_amount"],
                "execution_log": baseline_eval["execution_log"],
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            created = await self.db.create_baseline_result(record)
            results.append(created)

        return results

    def calculate_benchmark_metrics(
        self,
        total_risk: float,
        recoveriq_recovered: float,
        baseline_recovered: float,
        total_cases: int,
        recovered_cases: int
    ) -> Dict[str, Any]:
        """Calculates revenue lift and comparison metrics."""
        incremental_revenue = round(max(0.0, recoveriq_recovered - baseline_recovered), 2)
        
        if baseline_recovered > 0:
            recovery_lift_pct = round(((recoveriq_recovered - baseline_recovered) / baseline_recovered) * 100.0, 2)
        elif recoveriq_recovered > 0:
            recovery_lift_pct = 100.0
        else:
            recovery_lift_pct = 0.0

        overall_recovery_rate = round((recovered_cases / total_cases), 4) if total_cases > 0 else 0.0

        return {
            "total_revenue_at_risk": round(total_risk, 2),
            "recoveriq_recovered_revenue": round(recoveriq_recovered, 2),
            "baseline_recovered_revenue": round(baseline_recovered, 2),
            "incremental_revenue_recovered": incremental_revenue,
            "recovery_lift_percentage": recovery_lift_pct,
            "total_cases_processed": total_cases,
            "total_cases_recovered": recovered_cases,
            "overall_recovery_rate": overall_recovery_rate
        }


baseline_service = BaselineService()
