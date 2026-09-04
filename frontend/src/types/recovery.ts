export type CaseStatus =
  | 'DETECTED'
  | 'DIAGNOSED'
  | 'DECISION_READY'
  | 'APPROVED'
  | 'EXECUTING'
  | 'RECOVERED'
  | 'WAITING'
  | 'STOPPED'
  | 'ESCALATED'
  | 'FAILED';

export type CasePriority = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';

export type RootCauseCategory =
  | 'NETWORK_TIMEOUT'
  | 'GATEWAY_ERROR'
  | 'INSUFFICIENT_FUNDS'
  | 'USER_DROPPED'
  | 'CARD_LIMIT_EXCEEDED'
  | 'FRAUD_DECLINE'
  | 'SYSTEM_DOWN'
  | 'AUTHENTICATION_FAILURE'
  | 'EXPIRED_CARD'
  | 'OTHER';

export type ActionType =
  | 'RETRY_NOW'
  | 'RETRY_LATER'
  | 'PAYMENT_UPDATE'
  | 'REMINDER'
  | 'ESCALATE'
  | 'STOP';

export type OutcomeType =
  | 'RECOVERED'
  | 'FAILED_RETRYABLE'
  | 'FAILED_TERMINAL'
  | 'NO_RESPONSE'
  | 'DISMISSED'
  | 'OPTED_OUT'
  | 'ESCALATED_MANUALLY';

export interface RecoveryMetrics {
  merchant_id: string;
  total_revenue_at_risk: number;
  recoveriq_recovered_revenue: number;
  baseline_recovered_revenue: number;
  incremental_revenue_recovered: number;
  recovery_lift_percentage: number;
  total_cases_processed: number;
  total_cases_recovered: number;
  overall_recovery_rate: number;
  success_rate_by_category: Record<string, number>;
  top_recovery_actions: Array<{
    action: string;
    category: string;
    success_rate: number;
    attempts: number;
    total_recovered: number;
  }>;
}

export interface AIDiagnosisData {
  diagnosis?: string;
  failure_type?: RootCauseCategory | string;
  recommended_action?: ActionType | string;
  reason?: string;
  confidence?: number;
  source?: 'LLM' | 'DETERMINISTIC_FALLBACK' | string;
}

export interface DiagnosisSummary {
  root_cause_category?: RootCauseCategory | string;
  confidence_score?: number;
  reasoning?: string;
  recommended_actions?: string[];
  is_terminal_decline?: boolean;
  diagnosed_at?: string;
  details?: Record<string, unknown>;
  source?: 'LLM' | 'DETERMINISTIC_FALLBACK' | string;
  failure_type?: RootCauseCategory | string;
  recommended_action?: ActionType | string;
  diagnosis?: string;
  reason?: string;
  confidence?: number;
  ai_diagnosis?: AIDiagnosisData;
}

export interface RecoveryCase {
  id: string;
  merchant_id: string;
  payment_id: string;
  customer_id?: string | null;
  customer_name?: string | null;
  customer_email?: string | null;
  amount: number;
  currency: string;
  status: CaseStatus;
  priority: CasePriority;
  retry_count: number;
  communication_count: number;
  recovered_amount: number;
  diagnosis_summary: DiagnosisSummary;
  created_at: string;
  updated_at: string;
  resolved_at?: string | null;
}

export interface RecoveryAction {
  id: string;
  case_id: string;
  action_type: ActionType | string;
  execution_mode: string;
  status: string;
  sequence_number: number;
  scheduled_at?: string | null;
  executed_at?: string | null;
  payload: Record<string, unknown>;
  guardrail_check_passed: boolean;
  ai_confidence_score?: number | null;
  ai_reasoning?: string | null;
  created_at: string;
}

export interface RecoveryOutcome {
  id: string;
  case_id: string;
  action_id: string;
  outcome_type: OutcomeType | string;
  is_successful: boolean;
  recovered_amount: number;
  new_payment_id?: string | null;
  recovery_time_seconds?: number | null;
  recorded_at: string;
}

export interface AuditLog {
  id: string;
  case_id?: string | null;
  action_id?: string | null;
  actor_type: string;
  actor_id?: string | null;
  event_type: string;
  severity: string;
  description: string;
  details: Record<string, unknown>;
  created_at: string;
}

export interface CaseDetail extends RecoveryCase {
  actions: RecoveryAction[];
  outcomes: RecoveryOutcome[];
  audit_logs: AuditLog[];
}

export interface BatchRunResult {
  batch_id: string;
  merchant_id: string;
  name: string;
  status: string;
  total_records: number;
  processed_records: number;
  recovered_records: number;
  total_amount_at_risk: number;
  total_recovered_amount: number;
  recovery_rate: number;
  baseline_recovered_amount: number;
  incremental_revenue: number;
  recovery_lift_percentage: number;
  cases: RecoveryCase[];
}
