import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from app.schemas.recovery import (
    ExecutionMode,
    CaseStatus,
    BatchRunResponse,
    RecoveryMetricsResponse,
    RecoveryCaseResponse,
)
from app.services.supabase_db import db, SupabaseDB
from app.services.detection_service import detection_service, DetectionService
from app.services.diagnosis_service import diagnosis_service, DiagnosisService
from app.services.policy_engine import policy_engine, PolicyEngine
from app.policies.guardrail_engine import guardrail_engine, GuardrailEngine
from app.services.executor_service import executor_service, ExecutorService
from app.services.outcome_service import outcome_service, OutcomeService
from app.services.learning_service import learning_service, LearningService
from app.services.audit_service import audit_service, AuditService
from app.services.baseline_service import baseline_service, BaselineService
from app.services.synthetic_data import synthetic_generator, SyntheticDataGenerator

logger = logging.getLogger(__name__)


class RecoveryEngine:
    """
    RecoverIQ Master Revenue Recovery Pipeline.
    Orchestrates the 9-stage closed-loop recovery workflow:
    DETECT -> DIAGNOSE -> CHOOSE -> GUARD -> EXECUTE -> VERIFY -> LEARN -> AUDIT -> MEASURE.
    """

    def __init__(
        self,
        database: Optional[SupabaseDB] = None,
        detection: Optional[DetectionService] = None,
        diagnosis: Optional[DiagnosisService] = None,
        policy: Optional[PolicyEngine] = None,
        guardrail: Optional[GuardrailEngine] = None,
        executor: Optional[ExecutorService] = None,
        outcome: Optional[OutcomeService] = None,
        learning: Optional[LearningService] = None,
        audit: Optional[AuditService] = None,
        baseline: Optional[BaselineService] = None,
        synthetic: Optional[SyntheticDataGenerator] = None,
    ):
        self.db = database or db
        self.detection = detection or detection_service
        self.diagnosis = diagnosis or diagnosis_service
        self.policy = policy or policy_engine
        self.guardrail = guardrail or guardrail_engine
        self.executor = executor or executor_service
        self.outcome = outcome or outcome_service
        self.learning = learning or learning_service
        self.audit = audit or audit_service
        self.baseline = baseline or baseline_service
        self.synthetic = synthetic or synthetic_generator

    async def run_single_case_pipeline(
        self,
        case_id: str,
        merchant_id: str,
        mode: ExecutionMode = ExecutionMode.SIMULATION
    ) -> Dict[str, Any]:
        """
        Executes an end-to-end recovery cycle for a single recovery case.
        """
        # Step 1: Diagnosis
        diag_res = await self.diagnosis.diagnose_case(case_id, merchant_id)
        if not diag_res:
            raise ValueError(f"Diagnosis failed for case {case_id}")

        # Step 2: Adaptive Action Selection
        decision_res = await self.policy.decide_for_case(case_id, merchant_id)
        if not decision_res:
            raise ValueError(f"Action selection failed for case {case_id}")

        # Step 3: Deterministic Guardrails
        guard_res = await self.guardrail.guard_case(case_id, merchant_id)
        if not guard_res:
            raise ValueError(f"Guardrail check failed for case {case_id}")

        # Step 4: Action Execution
        exec_res = await self.executor.execute_case_action(case_id, merchant_id, mode)
        if not exec_res:
            raise ValueError(f"Action execution failed for case {case_id}")

        # Step 5: Outcome Verification
        outcome_res = await self.outcome.record_case_outcome(case_id, exec_res.action_id, merchant_id)
        if not outcome_res:
            raise ValueError(f"Outcome recording failed for case {case_id}")

        # Step 6: Continuous Learning Update
        outcome_dict = {
            "is_successful": outcome_res.is_successful,
            "recovered_amount": outcome_res.recovered_amount,
            "recovery_time_seconds": outcome_res.recovery_time_seconds
        }
        await self.learning.update_statistics_from_outcome(case_id, exec_res.action_id, outcome_dict, merchant_id)

        # Return updated case record
        updated_case = await self.db.get_recovery_case(case_id, merchant_id)
        return updated_case or {}

    async def run_batch_recovery(
        self,
        batch_id: str,
        merchant_id: str,
        mode: ExecutionMode = ExecutionMode.SIMULATION,
        run_baseline: bool = True
    ) -> BatchRunResponse:
        """
        Runs the complete recovery pipeline across all failed payments in a batch,
        executes comparative baseline benchmarking, and calculates incremental lift.
        """
        batch = await self.db.get_batch(batch_id, merchant_id)
        if not batch:
            raise ValueError(f"Batch {batch_id} not found for merchant")

        # 1. Detect and create recovery cases for unhandled payments in batch
        await self.detection.scan_and_create_cases(merchant_id, batch_id)

        # Also collect any existing cases in this batch
        all_cases = await self.db._select("recovery_cases", {"batch_id": f"eq.{batch_id}", "merchant_id": f"eq.{merchant_id}"})

        # 2. Run RecoverIQ pipeline on each case
        processed_cases = []
        total_risk = 0.0
        total_recovered = 0.0
        recovered_count = 0

        try:
            for c in all_cases:
                case_id = c["id"]
                updated = await self.run_single_case_pipeline(case_id, merchant_id, mode)
                processed_cases.append(updated)

                amt = float(updated.get("payment", {}).get("amount", 0.0) if updated.get("payment") else updated.get("amount", 0.0))
                rec_amt = float(updated.get("recovered_amount", 0.0))
                total_risk += amt
                total_recovered += rec_amt
                if updated.get("status") == CaseStatus.RECOVERED.value:
                    recovered_count += 1
        except Exception as e:
            logger.error(f"Error executing recovery batch {batch_id}: {e}", exc_info=True)
            try:
                await self.db.update_batch(batch_id, merchant_id, {
                    "status": "FAILED",
                    "processed_records": len(processed_cases),
                    "metadata": {
                        **batch.get("metadata", {}),
                        "error": str(e),
                        "failed_at": datetime.now(timezone.utc).isoformat()
                    }
                })
            except Exception:
                pass
            raise

        # 3. Run baseline comparison
        batch_payments = await self.db._select("payments", {"batch_id": f"eq.{batch_id}", "merchant_id": f"eq.{merchant_id}"})
        full_payments = []
        for bp in batch_payments:
            full_p = await self.db.get_payment_with_failure(bp["id"], merchant_id)
            if full_p:
                full_payments.append(full_p)

        baseline_results = await self.baseline.run_baseline_for_batch(batch_id, merchant_id, full_payments)
        baseline_recovered = sum(float(b.get("recovered_amount", 0.0)) for b in baseline_results)

        # 4. Compute metrics
        metrics = self.baseline.calculate_benchmark_metrics(
            total_risk=total_risk,
            recoveriq_recovered=total_recovered,
            baseline_recovered=baseline_recovered,
            total_cases=len(processed_cases),
            recovered_cases=recovered_count
        )

        # 5. Update batch status
        await self.db.update_batch(batch_id, merchant_id, {
            "status": "COMPLETED",
            "processed_records": len(processed_cases),
            "metadata": {
                **batch.get("metadata", {}),
                "total_recovered_amount": total_recovered,
                "baseline_recovered_amount": baseline_recovered,
                "incremental_revenue": metrics["incremental_revenue_recovered"],
                "recovery_lift_percentage": metrics["recovery_lift_percentage"],
                "completed_at": datetime.now(timezone.utc).isoformat()
            }
        })

        case_responses = []
        for pc in processed_cases:
            p = pc.get("payment") or {}
            cust = pc.get("customer") or p.get("customer") or {}
            created_at_val = pc.get("created_at")
            updated_at_val = pc.get("updated_at")
            created_at_dt = datetime.fromisoformat(created_at_val.replace("Z", "+00:00")) if isinstance(created_at_val, str) else datetime.now(timezone.utc)
            updated_at_dt = datetime.fromisoformat(updated_at_val.replace("Z", "+00:00")) if isinstance(updated_at_val, str) else datetime.now(timezone.utc)
            resolved_at_val = pc.get("resolved_at")
            resolved_at_dt = datetime.fromisoformat(resolved_at_val.replace("Z", "+00:00")) if isinstance(resolved_at_val, str) else None

            case_responses.append(
                RecoveryCaseResponse(
                    id=pc["id"],
                    merchant_id=pc["merchant_id"],
                    payment_id=pc["payment_id"],
                    customer_id=cust.get("id"),
                    customer_name=cust.get("name"),
                    customer_email=cust.get("email"),
                    amount=float(p.get("amount", pc.get("amount", 0.0))),
                    currency=p.get("currency", "INR"),
                    status=CaseStatus(pc["status"]),
                    priority=pc.get("priority", "MEDIUM"),
                    retry_count=pc.get("retry_count", 0),
                    communication_count=pc.get("communication_count", 0),
                    recovered_amount=float(pc.get("recovered_amount", 0.0)),
                    diagnosis_summary=pc.get("diagnosis_summary", {}),
                    created_at=created_at_dt,
                    updated_at=updated_at_dt,
                    resolved_at=resolved_at_dt
                )
            )

        return BatchRunResponse(
            batch_id=batch_id,
            merchant_id=merchant_id,
            name=batch.get("name", "Recovery Batch"),
            status="COMPLETED",
            total_records=len(processed_cases),
            processed_records=len(processed_cases),
            recovered_records=recovered_count,
            total_amount_at_risk=metrics["total_revenue_at_risk"],
            total_recovered_amount=metrics["recoveriq_recovered_revenue"],
            recovery_rate=metrics["overall_recovery_rate"],
            baseline_recovered_amount=metrics["baseline_recovered_revenue"],
            incremental_revenue=metrics["incremental_revenue_recovered"],
            recovery_lift_percentage=metrics["recovery_lift_percentage"],
            cases=case_responses
        )

    async def get_metrics_summary(self, merchant_id: str, batch_id: Optional[str] = None) -> RecoveryMetricsResponse:
        """
        Aggregates real recovery metrics across merchant cases and baseline results.
        If batch_id is provided, scopes the metrics to that specific batch.
        """
        case_params = {"merchant_id": f"eq.{merchant_id}"}
        baseline_params = {"merchant_id": f"eq.{merchant_id}"}
        if batch_id:
            case_params["batch_id"] = f"eq.{batch_id}"
            baseline_params["batch_id"] = f"eq.{batch_id}"

        all_cases = await self.db._select("recovery_cases", case_params)
        all_baselines = await self.db._select("baseline_results", baseline_params)
        all_stats = await self.db.get_action_statistics(merchant_id)

        total_risk = 0.0
        recoveriq_recovered = 0.0
        recovered_count = 0

        for c in all_cases:
            p = await self.db.get_payment_with_failure(c["payment_id"], merchant_id)
            amt = float(p.get("amount", 0.0) if p else c.get("amount", 0.0))
            rec = float(c.get("recovered_amount", 0.0))
            total_risk += amt
            recoveriq_recovered += rec
            if c.get("status") == CaseStatus.RECOVERED.value:
                recovered_count += 1

        baseline_recovered = sum(float(b.get("recovered_amount", 0.0)) for b in all_baselines)

        benchmark = self.baseline.calculate_benchmark_metrics(
            total_risk=total_risk,
            recoveriq_recovered=recoveriq_recovered,
            baseline_recovered=baseline_recovered,
            total_cases=len(all_cases),
            recovered_cases=recovered_count
        )

        # Group stats by category
        category_rates = {}
        for s in all_stats:
            cat = s.get("root_cause_category", "OTHER")
            category_rates[cat] = float(s.get("success_rate", 0.0))

        top_actions = [
            {
                "action": s.get("action_type"),
                "category": s.get("root_cause_category"),
                "success_rate": float(s.get("success_rate", 0.0)),
                "attempts": int(s.get("total_attempts", 0)),
                "total_recovered": float(s.get("total_recovered_amount", 0.0))
            }
            for s in sorted(all_stats, key=lambda x: float(x.get("total_recovered_amount", 0.0)), reverse=True)[:5]
        ]

        return RecoveryMetricsResponse(
            merchant_id=merchant_id,
            total_revenue_at_risk=benchmark["total_revenue_at_risk"],
            recoveriq_recovered_revenue=benchmark["recoveriq_recovered_revenue"],
            baseline_recovered_revenue=benchmark["baseline_recovered_revenue"],
            incremental_revenue_recovered=benchmark["incremental_revenue_recovered"],
            recovery_lift_percentage=benchmark["recovery_lift_percentage"],
            total_cases_processed=benchmark["total_cases_processed"],
            total_cases_recovered=benchmark["total_cases_recovered"],
            overall_recovery_rate=benchmark["overall_recovery_rate"],
            success_rate_by_category=category_rates,
            top_recovery_actions=top_actions
        )


recovery_engine = RecoveryEngine()
