from typing import Optional, List, Dict, Any
from enum import Enum
from datetime import datetime
from pydantic import BaseModel, Field


class RootCauseCategory(str, Enum):
    NETWORK_TIMEOUT = "NETWORK_TIMEOUT"
    GATEWAY_ERROR = "GATEWAY_ERROR"
    INSUFFICIENT_FUNDS = "INSUFFICIENT_FUNDS"
    USER_DROPPED = "USER_DROPPED"
    CARD_LIMIT_EXCEEDED = "CARD_LIMIT_EXCEEDED"
    FRAUD_DECLINE = "FRAUD_DECLINE"
    SYSTEM_DOWN = "SYSTEM_DOWN"
    AUTHENTICATION_FAILURE = "AUTHENTICATION_FAILURE"
    EXPIRED_CARD = "EXPIRED_CARD"
    OTHER = "OTHER"


class ActionType(str, Enum):
    RETRY_NOW = "RETRY_NOW"
    RETRY_LATER = "RETRY_LATER"
    PAYMENT_UPDATE = "PAYMENT_UPDATE"
    REMINDER = "REMINDER"
    ESCALATE = "ESCALATE"
    STOP = "STOP"


class ExecutionMode(str, Enum):
    RAZORPAY_TEST = "RAZORPAY_TEST"
    SIMULATION = "SIMULATION"
    DRY_RUN = "DRY_RUN"


class CaseStatus(str, Enum):
    DETECTED = "DETECTED"
    DIAGNOSED = "DIAGNOSED"
    DECISION_READY = "DECISION_READY"
    APPROVED = "APPROVED"
    EXECUTING = "EXECUTING"
    RECOVERED = "RECOVERED"
    WAITING = "WAITING"
    STOPPED = "STOPPED"
    ESCALATED = "ESCALATED"
    FAILED = "FAILED"


class OutcomeType(str, Enum):
    RECOVERED = "RECOVERED"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_TERMINAL = "FAILED_TERMINAL"
    NO_RESPONSE = "NO_RESPONSE"
    DISMISSED = "DISMISSED"
    OPTED_OUT = "OPTED_OUT"
    ESCALATED_MANUALLY = "ESCALATED_MANUALLY"


class CasePriority(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AIDiagnosisSource(str, Enum):
    LLM = "LLM"
    DETERMINISTIC_FALLBACK = "DETERMINISTIC_FALLBACK"


class AIDiagnosisResult(BaseModel):
    diagnosis: str
    failure_type: RootCauseCategory
    recommended_action: ActionType
    reason: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    source: AIDiagnosisSource


# -----------------------------------------------------------------------------
# Pipeline Step Schemas
# -----------------------------------------------------------------------------

class DiagnosisResult(BaseModel):
    root_cause_category: RootCauseCategory
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    reasoning: str
    recommended_actions: List[ActionType]
    is_terminal_decline: bool = False
    diagnostic_details: Dict[str, Any] = Field(default_factory=dict)
    ai_diagnosis: Optional[AIDiagnosisResult] = None


class ActionCandidate(BaseModel):
    action_type: ActionType
    score: float
    confidence: float
    historical_success_rate: float
    historical_attempts: int
    reasoning: str


class PolicyDecision(BaseModel):
    selected_action: ActionType
    confidence_score: float
    reasoning: str
    ranked_candidates: List[ActionCandidate]
    used_historical_learning: bool = False


class GuardrailResult(BaseModel):
    allowed: bool
    proposed_action: ActionType
    final_action: ActionType
    is_overridden: bool = False
    override_reason: Optional[str] = None
    checks_passed: Dict[str, bool] = Field(default_factory=dict)
    details: Dict[str, Any] = Field(default_factory=dict)


class ExecutionResult(BaseModel):
    action_id: str
    action_type: ActionType
    execution_mode: ExecutionMode
    status: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    guardrail_check_passed: bool = True
    executed_at: datetime = Field(default_factory=datetime.utcnow)


class OutcomeResult(BaseModel):
    outcome_id: str
    outcome_type: OutcomeType
    is_successful: bool
    recovered_amount: float
    new_payment_id: Optional[str] = None
    recovery_time_seconds: Optional[int] = None
    response_payload: Dict[str, Any] = Field(default_factory=dict)


class LearningUpdateResult(BaseModel):
    merchant_id: str
    root_cause_category: str
    action_type: str
    total_attempts: int
    successful_recoveries: int
    success_rate: float
    total_recovered_amount: float


# -----------------------------------------------------------------------------
# API Request & Response Schemas
# -----------------------------------------------------------------------------

class RecoveryActionResponse(BaseModel):
    id: str
    case_id: str
    action_type: ActionType
    execution_mode: ExecutionMode
    status: str
    sequence_number: int
    scheduled_at: Optional[datetime] = None
    executed_at: Optional[datetime] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    guardrail_check_passed: bool
    ai_confidence_score: Optional[float] = None
    ai_reasoning: Optional[str] = None
    created_at: datetime


class RecoveryOutcomeResponse(BaseModel):
    id: str
    case_id: str
    action_id: str
    outcome_type: OutcomeType
    is_successful: bool
    recovered_amount: float
    new_payment_id: Optional[str] = None
    recovery_time_seconds: Optional[int] = None
    recorded_at: datetime


class AuditLogResponse(BaseModel):
    id: str
    case_id: Optional[str] = None
    action_id: Optional[str] = None
    actor_type: str
    actor_id: Optional[str] = None
    event_type: str
    severity: str
    description: str
    details: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class RecoveryCaseResponse(BaseModel):
    id: str
    merchant_id: str
    payment_id: str
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None
    amount: float
    currency: str = "INR"
    status: CaseStatus
    priority: CasePriority
    retry_count: int
    communication_count: int
    recovered_amount: float
    next_action_due_at: Optional[datetime] = None
    diagnosis_summary: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    resolved_at: Optional[datetime] = None


class CaseDetailResponse(RecoveryCaseResponse):
    actions: List[RecoveryActionResponse] = Field(default_factory=list)
    outcomes: List[RecoveryOutcomeResponse] = Field(default_factory=list)
    audit_logs: List[AuditLogResponse] = Field(default_factory=list)


class BatchCreateRequest(BaseModel):
    name: str = "Demo Recovery Batch"
    description: Optional[str] = "Batch of failed payments for adaptive recovery"
    seed_synthetic_count: int = Field(default=6, ge=1, le=50)


class BatchRunResponse(BaseModel):
    batch_id: str
    merchant_id: str
    name: str
    status: str
    total_records: int
    processed_records: int
    recovered_records: int
    total_amount_at_risk: float
    total_recovered_amount: float
    recovery_rate: float
    baseline_recovered_amount: float
    incremental_revenue: float
    recovery_lift_percentage: float
    cases: List[RecoveryCaseResponse] = Field(default_factory=list)


class RecoveryMetricsResponse(BaseModel):
    merchant_id: str
    total_revenue_at_risk: float
    recoveriq_recovered_revenue: float
    baseline_recovered_revenue: float
    incremental_revenue_recovered: float
    recovery_lift_percentage: float
    total_cases_processed: int
    total_cases_recovered: int
    overall_recovery_rate: float
    success_rate_by_category: Dict[str, float] = Field(default_factory=dict)
    top_recovery_actions: List[Dict[str, Any]] = Field(default_factory=list)
