import logging
from typing import List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Query

from app.auth.supabase import get_current_merchant_context, require_roles
from app.schemas.auth import MerchantAuthContext
from app.schemas.recovery import (
    BatchCreateRequest,
    BatchRunResponse,
    RecoveryCaseResponse,
    CaseDetailResponse,
    RecoveryActionResponse,
    RecoveryOutcomeResponse,
    AuditLogResponse,
    RecoveryMetricsResponse,
    ExecutionMode,
    CaseStatus,
)
from app.services.recovery_engine import recovery_engine
from app.services.supabase_db import db
from app.services.synthetic_data import synthetic_generator

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/batches", response_model=BatchRunResponse, summary="Create and execute a recovery batch")
async def create_and_run_batch(
    request: BatchCreateRequest,
    mode: ExecutionMode = Query(ExecutionMode.SIMULATION, description="Execution mode: SIMULATION, RAZORPAY_TEST, or DRY_RUN"),
    auth_context: MerchantAuthContext = Depends(require_roles(["owner", "admin", "operator"]))
) -> BatchRunResponse:
    """
    Creates and processes a recovery batch for the authenticated merchant.
    Seeds synthetic failed transactions if requested and runs the end-to-end recovery pipeline.
    """
    merchant_id = auth_context.merchant_id

    # Seed synthetic batch
    seed_result = await synthetic_generator.generate_demo_batch(
        merchant_id=merchant_id,
        batch_name=request.name,
        count=request.seed_synthetic_count
    )

    batch_id = seed_result["batch_id"]

    # Execute batch recovery and baseline comparison
    run_response = await recovery_engine.run_batch_recovery(
        batch_id=batch_id,
        merchant_id=merchant_id,
        mode=mode,
        run_baseline=True
    )

    return run_response


@router.post("/seed-demo-batch", response_model=BatchRunResponse, summary="Quick seed & execute demo batch")
async def seed_demo_batch(
    mode: ExecutionMode = Query(ExecutionMode.SIMULATION, description="Execution mode: SIMULATION, RAZORPAY_TEST, or DRY_RUN"),
    auth_context: MerchantAuthContext = Depends(require_roles(["owner", "admin", "operator"]))
) -> BatchRunResponse:
    """
    Convenience endpoint for local demos & testing: Seeds 6 diverse failure cases
    and executes the complete 9-stage recovery engine.
    """
    merchant_id = auth_context.merchant_id
    seed_result = await synthetic_generator.generate_demo_batch(
        merchant_id=merchant_id,
        batch_name="Acme Retail Demo Recovery Batch",
        count=6
    )

    return await recovery_engine.run_batch_recovery(
        batch_id=seed_result["batch_id"],
        merchant_id=merchant_id,
        mode=mode,
        run_baseline=True
    )


@router.get("/cases", response_model=List[RecoveryCaseResponse], summary="List recovery cases")
async def list_cases(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by case status"),
    batch_id: Optional[str] = Query(None, description="Filter by batch ID"),
    limit: int = Query(50, ge=1, le=100),
    auth_context: MerchantAuthContext = Depends(get_current_merchant_context)
) -> List[RecoveryCaseResponse]:
    """
    Lists recovery cases for the authenticated merchant.
    """
    merchant_id = auth_context.merchant_id
    cases = await db.list_recovery_cases(
        merchant_id=merchant_id,
        status_filter=status_filter,
        batch_id=batch_id,
        limit=limit
    )

    responses = []
    for c in cases:
        p = c.get("payment") or {}
        cust = c.get("customer") or p.get("customer") or {}
        created_at_val = c.get("created_at")
        updated_at_val = c.get("updated_at")
        resolved_at_val = c.get("resolved_at")

        created_at_dt = datetime.fromisoformat(created_at_val.replace("Z", "+00:00")) if isinstance(created_at_val, str) else datetime.now(timezone.utc)
        updated_at_dt = datetime.fromisoformat(updated_at_val.replace("Z", "+00:00")) if isinstance(updated_at_val, str) else datetime.now(timezone.utc)
        resolved_at_dt = datetime.fromisoformat(resolved_at_val.replace("Z", "+00:00")) if isinstance(resolved_at_val, str) else None

        responses.append(
            RecoveryCaseResponse(
                id=c["id"],
                merchant_id=c["merchant_id"],
                payment_id=c["payment_id"],
                customer_id=cust.get("id"),
                customer_name=cust.get("name"),
                customer_email=cust.get("email"),
                amount=float(p.get("amount", c.get("amount", 0.0))),
                currency=p.get("currency", "INR"),
                status=CaseStatus(c["status"]),
                priority=c.get("priority", "MEDIUM"),
                retry_count=c.get("retry_count", 0),
                communication_count=c.get("communication_count", 0),
                recovered_amount=float(c.get("recovered_amount", 0.0)),
                diagnosis_summary=c.get("diagnosis_summary", {}),
                created_at=created_at_dt,
                updated_at=updated_at_dt,
                resolved_at=resolved_at_dt
            )
        )

    return responses


@router.get("/cases/{case_id}", response_model=CaseDetailResponse, summary="Get recovery case details")
async def get_case_detail(
    case_id: str,
    auth_context: MerchantAuthContext = Depends(get_current_merchant_context)
) -> CaseDetailResponse:
    """
    Returns complete case details including failure diagnosis, actions, outcomes, and audit trail.
    """
    merchant_id = auth_context.merchant_id
    case = await db.get_recovery_case(case_id, merchant_id)
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Recovery case {case_id} not found."
        )

    actions = await db.get_recovery_actions(case_id, merchant_id)
    outcomes = await db.get_recovery_outcomes(case_id, merchant_id)
    audit_logs = await db.get_audit_logs(case_id=case_id, merchant_id=merchant_id)

    p = case.get("payment") or {}
    cust = case.get("customer") or p.get("customer") or {}

    created_at_val = case.get("created_at")
    updated_at_val = case.get("updated_at")
    resolved_at_val = case.get("resolved_at")

    created_at_dt = datetime.fromisoformat(created_at_val.replace("Z", "+00:00")) if isinstance(created_at_val, str) else datetime.now(timezone.utc)
    updated_at_dt = datetime.fromisoformat(updated_at_val.replace("Z", "+00:00")) if isinstance(updated_at_val, str) else datetime.now(timezone.utc)
    resolved_at_dt = datetime.fromisoformat(resolved_at_val.replace("Z", "+00:00")) if isinstance(resolved_at_val, str) else None

    action_resps = [
        RecoveryActionResponse(
            id=a["id"],
            case_id=a["case_id"],
            action_type=a["action_type"],
            execution_mode=a.get("execution_mode", "SIMULATION"),
            status=a.get("status", "COMPLETED"),
            sequence_number=a.get("sequence_number", 1),
            scheduled_at=datetime.fromisoformat(a["scheduled_at"].replace("Z", "+00:00")) if a.get("scheduled_at") else None,
            executed_at=datetime.fromisoformat(a["executed_at"].replace("Z", "+00:00")) if a.get("executed_at") else None,
            payload=a.get("payload", {}),
            guardrail_check_passed=a.get("guardrail_check_passed", True),
            ai_confidence_score=a.get("ai_confidence_score"),
            ai_reasoning=a.get("ai_reasoning"),
            created_at=datetime.fromisoformat(a["created_at"].replace("Z", "+00:00")) if a.get("created_at") else datetime.now(timezone.utc)
        )
        for a in actions
    ]

    outcome_resps = [
        RecoveryOutcomeResponse(
            id=o["id"],
            case_id=o["case_id"],
            action_id=o["action_id"],
            outcome_type=o["outcome_type"],
            is_successful=o["is_successful"],
            recovered_amount=float(o.get("recovered_amount", 0.0)),
            new_payment_id=o.get("new_payment_id"),
            recovery_time_seconds=o.get("recovery_time_seconds"),
            recorded_at=datetime.fromisoformat(o["recorded_at"].replace("Z", "+00:00")) if o.get("recorded_at") else datetime.now(timezone.utc)
        )
        for o in outcomes
    ]

    audit_resps = [
        AuditLogResponse(
            id=al["id"],
            case_id=al.get("case_id"),
            action_id=al.get("action_id"),
            actor_type=al.get("actor_type", "SYSTEM"),
            actor_id=al.get("actor_id"),
            event_type=al["event_type"],
            severity=al.get("severity", "INFO"),
            description=al["description"],
            details=al.get("details", {}),
            created_at=datetime.fromisoformat(al["created_at"].replace("Z", "+00:00")) if al.get("created_at") else datetime.now(timezone.utc)
        )
        for al in audit_logs
    ]

    return CaseDetailResponse(
        id=case["id"],
        merchant_id=case["merchant_id"],
        payment_id=case["payment_id"],
        customer_id=cust.get("id"),
        customer_name=cust.get("name"),
        customer_email=cust.get("email"),
        amount=float(p.get("amount", case.get("amount", 0.0))),
        currency=p.get("currency", "INR"),
        status=CaseStatus(case["status"]),
        priority=case.get("priority", "MEDIUM"),
        retry_count=case.get("retry_count", 0),
        communication_count=case.get("communication_count", 0),
        recovered_amount=float(case.get("recovered_amount", 0.0)),
        diagnosis_summary=case.get("diagnosis_summary", {}),
        created_at=created_at_dt,
        updated_at=updated_at_dt,
        resolved_at=resolved_at_dt,
        actions=action_resps,
        outcomes=outcome_resps,
        audit_logs=audit_resps
    )


@router.post("/cases/{case_id}/run", response_model=RecoveryCaseResponse, summary="Execute recovery step on case")
async def run_case_step(
    case_id: str,
    mode: ExecutionMode = Query(ExecutionMode.SIMULATION, description="Execution mode: SIMULATION, RAZORPAY_TEST, or DRY_RUN"),
    auth_context: MerchantAuthContext = Depends(require_roles(["owner", "admin", "operator"]))
) -> RecoveryCaseResponse:
    """
    Executes the next recovery cycle on a single recovery case.
    """
    merchant_id = auth_context.merchant_id
    updated = await recovery_engine.run_single_case_pipeline(
        case_id=case_id,
        merchant_id=merchant_id,
        mode=mode
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Recovery case {case_id} not found."
        )

    p = updated.get("payment") or {}
    cust = updated.get("customer") or p.get("customer") or {}

    created_at_val = updated.get("created_at")
    updated_at_val = updated.get("updated_at")
    resolved_at_val = updated.get("resolved_at")

    return RecoveryCaseResponse(
        id=updated["id"],
        merchant_id=updated["merchant_id"],
        payment_id=updated["payment_id"],
        customer_id=cust.get("id"),
        customer_name=cust.get("name"),
        customer_email=cust.get("email"),
        amount=float(p.get("amount", updated.get("amount", 0.0))),
        currency=p.get("currency", "INR"),
        status=CaseStatus(updated["status"]),
        priority=updated.get("priority", "MEDIUM"),
        retry_count=updated.get("retry_count", 0),
        communication_count=updated.get("communication_count", 0),
        recovered_amount=float(updated.get("recovered_amount", 0.0)),
        diagnosis_summary=updated.get("diagnosis_summary", {}),
        created_at=datetime.fromisoformat(created_at_val.replace("Z", "+00:00")) if isinstance(created_at_val, str) else datetime.now(timezone.utc),
        updated_at=datetime.fromisoformat(updated_at_val.replace("Z", "+00:00")) if isinstance(updated_at_val, str) else datetime.now(timezone.utc),
        resolved_at=datetime.fromisoformat(resolved_at_val.replace("Z", "+00:00")) if isinstance(resolved_at_val, str) else None
    )


@router.get("/metrics", response_model=RecoveryMetricsResponse, summary="Get recovery benchmark metrics")
async def get_metrics(
    batch_id: Optional[str] = Query(None, description="Optional batch ID to scope metrics to a specific batch"),
    auth_context: MerchantAuthContext = Depends(get_current_merchant_context)
) -> RecoveryMetricsResponse:
    """
    Returns real computed metrics for the authenticated merchant:
    Revenue at Risk, RecoverIQ Recovered, Baseline Recovered, Incremental Lift, Success Rates.
    Optionally scoped to a specific batch_id.
    """
    merchant_id = auth_context.merchant_id
    return await recovery_engine.get_metrics_summary(merchant_id=merchant_id, batch_id=batch_id)
