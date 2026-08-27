-- ============================================================================
-- RecoverIQ Database Schema Migration
-- Migration: 20260827140000_initial_recoveriq_schema.sql
-- Description: Production-ready PostgreSQL schema for RecoverIQ Master V2
-- Tables:
--   1. merchants
--   2. profiles
--   3. customers
--   4. batches
--   5. payments
--   6. payment_failures
--   7. policies
--   8. recovery_cases
--   9. recovery_actions
--   10. recovery_outcomes
--   11. action_statistics
--   12. baseline_results
--   13. audit_logs
-- ============================================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================================
-- 0. AUTOMATED UPDATED_AT TRIGGER FUNCTION
-- ============================================================================
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- 1. MERCHANTS (Multi-tenant root organization)
-- ============================================================================
CREATE TABLE IF NOT EXISTS merchants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(100) UNIQUE NOT NULL,
    currency VARCHAR(3) NOT NULL DEFAULT 'INR',
    timezone VARCHAR(50) NOT NULL DEFAULT 'Asia/Kolkata',
    is_active BOOLEAN NOT NULL DEFAULT true,
    settings JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

DROP TRIGGER IF EXISTS trg_merchants_updated_at ON merchants;
CREATE TRIGGER trg_merchants_updated_at
    BEFORE UPDATE ON merchants
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ============================================================================
-- 2. PROFILES (User accounts linked to Supabase Auth and Merchant tenant)
-- ============================================================================
CREATE TABLE IF NOT EXISTS profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    merchant_id UUID NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
    email VARCHAR(255) NOT NULL,
    full_name VARCHAR(255),
    role VARCHAR(50) NOT NULL DEFAULT 'admin' CHECK (role IN ('owner', 'admin', 'operator', 'viewer')),
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

DROP TRIGGER IF EXISTS trg_profiles_updated_at ON profiles;
CREATE TRIGGER trg_profiles_updated_at
    BEFORE UPDATE ON profiles
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ============================================================================
-- 3. CUSTOMERS (End customers associated with merchant payments)
-- ============================================================================
CREATE TABLE IF NOT EXISTS customers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    merchant_id UUID NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
    external_customer_id VARCHAR(255),
    name VARCHAR(255),
    email VARCHAR(255),
    phone VARCHAR(50),
    is_opted_out BOOLEAN NOT NULL DEFAULT false,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_customers_merchant_external UNIQUE (merchant_id, external_customer_id)
);

DROP TRIGGER IF EXISTS trg_customers_updated_at ON customers;
CREATE TRIGGER trg_customers_updated_at
    BEFORE UPDATE ON customers
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ============================================================================
-- 4. BATCHES (Groups of payments/recovery processing for benchmark runs)
-- ============================================================================
CREATE TABLE IF NOT EXISTS batches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    merchant_id UUID NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    status VARCHAR(50) NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED', 'CANCELLED')),
    total_records INTEGER NOT NULL DEFAULT 0 CHECK (total_records >= 0),
    processed_records INTEGER NOT NULL DEFAULT 0 CHECK (processed_records >= 0),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

DROP TRIGGER IF EXISTS trg_batches_updated_at ON batches;
CREATE TRIGGER trg_batches_updated_at
    BEFORE UPDATE ON batches
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ============================================================================
-- 5. PAYMENTS (Transactions ingested from webhooks or batch files)
-- Note: Sensitive credentials (card numbers, CVV, OTP) are NOT stored.
-- ============================================================================
CREATE TABLE IF NOT EXISTS payments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    merchant_id UUID NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
    customer_id UUID REFERENCES customers(id) ON DELETE SET NULL,
    batch_id UUID REFERENCES batches(id) ON DELETE SET NULL,
    razorpay_payment_id VARCHAR(255),
    razorpay_order_id VARCHAR(255),
    razorpay_invoice_id VARCHAR(255),
    amount DECIMAL(14, 2) NOT NULL CHECK (amount >= 0),
    currency VARCHAR(3) NOT NULL DEFAULT 'INR',
    status VARCHAR(50) NOT NULL CHECK (status IN ('created', 'authorized', 'captured', 'refunded', 'failed')),
    method VARCHAR(50) CHECK (method IS NULL OR method IN ('card', 'upi', 'netbanking', 'wallet', 'emi', 'nach', 'bank_transfer', 'other')),
    bank VARCHAR(100),
    wallet VARCHAR(100),
    vpa VARCHAR(255),
    card_network VARCHAR(50) CHECK (card_network IS NULL OR card_network IN ('visa', 'mastercard', 'rupay', 'amex', 'diners', 'maestro', 'other')),
    card_type VARCHAR(50) CHECK (card_type IS NULL OR card_type IN ('credit', 'debit', 'prepaid', 'other')),
    card_issuer VARCHAR(100),
    card_last4 VARCHAR(4),
    is_international BOOLEAN NOT NULL DEFAULT false,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

DROP TRIGGER IF EXISTS trg_payments_updated_at ON payments;
CREATE TRIGGER trg_payments_updated_at
    BEFORE UPDATE ON payments
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ============================================================================
-- 6. PAYMENT_FAILURES (Detailed failure attributes for root cause diagnosis)
-- ============================================================================
CREATE TABLE IF NOT EXISTS payment_failures (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    merchant_id UUID NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
    payment_id UUID NOT NULL REFERENCES payments(id) ON DELETE CASCADE,
    error_code VARCHAR(100),
    error_description TEXT,
    error_source VARCHAR(100) CHECK (error_source IS NULL OR error_source IN ('customer', 'gateway', 'bank', 'business', 'internal', 'other')),
    error_step VARCHAR(100) CHECK (error_step IS NULL OR error_step IN ('payment_initiation', 'payment_authentication', 'payment_authorization', 'payment_capture', 'other')),
    error_reason VARCHAR(100),
    root_cause_category VARCHAR(100) CHECK (root_cause_category IS NULL OR root_cause_category IN ('INSUFFICIENT_FUNDS', 'NETWORK_TIMEOUT', 'AUTHENTICATION_FAILURE', 'EXPIRED_CARD', 'CARD_LIMIT_EXCEEDED', 'SYSTEM_DOWN', 'USER_DROPPED', 'GATEWAY_ERROR', 'FRAUD_DECLINE', 'OTHER')),
    diagnostic_details JSONB NOT NULL DEFAULT '{}'::jsonb,
    failed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

DROP TRIGGER IF EXISTS trg_payment_failures_updated_at ON payment_failures;
CREATE TRIGGER trg_payment_failures_updated_at
    BEFORE UPDATE ON payment_failures
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ============================================================================
-- 7. POLICIES (Recovery guardrails, limits, thresholds, and business rules)
-- ============================================================================
CREATE TABLE IF NOT EXISTS policies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    merchant_id UUID NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    is_default BOOLEAN NOT NULL DEFAULT false,
    is_active BOOLEAN NOT NULL DEFAULT true,
    max_retries INTEGER NOT NULL DEFAULT 3 CHECK (max_retries >= 0 AND max_retries <= 10),
    max_communications INTEGER NOT NULL DEFAULT 3 CHECK (max_communications >= 0 AND max_communications <= 10),
    cooldown_minutes INTEGER NOT NULL DEFAULT 60 CHECK (cooldown_minutes >= 0),
    communication_window_start TIME NOT NULL DEFAULT '09:00:00',
    communication_window_end TIME NOT NULL DEFAULT '20:00:00',
    allowed_days JSONB NOT NULL DEFAULT '["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]'::jsonb,
    escalation_threshold_amount DECIMAL(14, 2) NOT NULL DEFAULT 10000.00 CHECK (escalation_threshold_amount >= 0),
    auto_escalate_vip BOOLEAN NOT NULL DEFAULT true,
    respect_opt_out BOOLEAN NOT NULL DEFAULT true,
    opt_out_action VARCHAR(50) NOT NULL DEFAULT 'STOP' CHECK (opt_out_action IN ('STOP', 'ESCALATE')),
    rules JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

DROP TRIGGER IF EXISTS trg_policies_updated_at ON policies;
CREATE TRIGGER trg_policies_updated_at
    BEFORE UPDATE ON policies
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ============================================================================
-- 8. RECOVERY_CASES (V2 State Machine lifecycle tracking for failed payments)
-- ============================================================================
CREATE TABLE IF NOT EXISTS recovery_cases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    merchant_id UUID NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
    payment_id UUID NOT NULL REFERENCES payments(id) ON DELETE CASCADE,
    failure_id UUID REFERENCES payment_failures(id) ON DELETE SET NULL,
    policy_id UUID REFERENCES policies(id) ON DELETE SET NULL,
    batch_id UUID REFERENCES batches(id) ON DELETE SET NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'DETECTED' CHECK (status IN (
        'DETECTED',
        'DIAGNOSED',
        'DECISION_READY',
        'APPROVED',
        'EXECUTING',
        'RECOVERED',
        'WAITING',
        'STOPPED',
        'ESCALATED',
        'FAILED'
    )),
    priority VARCHAR(20) NOT NULL DEFAULT 'MEDIUM' CHECK (priority IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    retry_count INTEGER NOT NULL DEFAULT 0 CHECK (retry_count >= 0),
    communication_count INTEGER NOT NULL DEFAULT 0 CHECK (communication_count >= 0),
    recovered_amount DECIMAL(14, 2) NOT NULL DEFAULT 0.00 CHECK (recovered_amount >= 0),
    next_action_due_at TIMESTAMPTZ,
    diagnosis_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    resolved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

DROP TRIGGER IF EXISTS trg_recovery_cases_updated_at ON recovery_cases;
CREATE TRIGGER trg_recovery_cases_updated_at
    BEFORE UPDATE ON recovery_cases
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ============================================================================
-- 9. RECOVERY_ACTIONS (Planned and executed recovery actions)
-- ============================================================================
CREATE TABLE IF NOT EXISTS recovery_actions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    merchant_id UUID NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
    case_id UUID NOT NULL REFERENCES recovery_cases(id) ON DELETE CASCADE,
    action_type VARCHAR(50) NOT NULL CHECK (action_type IN (
        'RETRY_NOW',
        'RETRY_LATER',
        'PAYMENT_UPDATE',
        'REMINDER',
        'ESCALATE',
        'STOP'
    )),
    execution_mode VARCHAR(50) NOT NULL DEFAULT 'DRY_RUN' CHECK (execution_mode IN (
        'RAZORPAY_TEST',
        'SIMULATION',
        'DRY_RUN'
    )),
    status VARCHAR(50) NOT NULL DEFAULT 'PENDING' CHECK (status IN (
        'PENDING',
        'SCHEDULED',
        'EXECUTING',
        'COMPLETED',
        'FAILED',
        'CANCELLED',
        'SKIPPED'
    )),
    sequence_number INTEGER NOT NULL DEFAULT 1 CHECK (sequence_number >= 1),
    scheduled_at TIMESTAMPTZ,
    executed_at TIMESTAMPTZ,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    guardrail_check_passed BOOLEAN NOT NULL DEFAULT true,
    guardrail_details JSONB NOT NULL DEFAULT '{}'::jsonb,
    ai_confidence_score DECIMAL(5, 4) CHECK (ai_confidence_score IS NULL OR (ai_confidence_score >= 0.0000 AND ai_confidence_score <= 1.0000)),
    ai_reasoning TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

DROP TRIGGER IF EXISTS trg_recovery_actions_updated_at ON recovery_actions;
CREATE TRIGGER trg_recovery_actions_updated_at
    BEFORE UPDATE ON recovery_actions
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ============================================================================
-- 10. RECOVERY_OUTCOMES (Verifiable outcome results for executed recovery actions)
-- ============================================================================
CREATE TABLE IF NOT EXISTS recovery_outcomes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    merchant_id UUID NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
    case_id UUID NOT NULL REFERENCES recovery_cases(id) ON DELETE CASCADE,
    action_id UUID NOT NULL REFERENCES recovery_actions(id) ON DELETE CASCADE,
    outcome_type VARCHAR(50) NOT NULL CHECK (outcome_type IN (
        'RECOVERED',
        'FAILED_RETRYABLE',
        'FAILED_TERMINAL',
        'NO_RESPONSE',
        'DISMISSED',
        'OPTED_OUT',
        'ESCALATED_MANUALLY'
    )),
    is_successful BOOLEAN NOT NULL DEFAULT false,
    recovered_amount DECIMAL(14, 2) NOT NULL DEFAULT 0.00 CHECK (recovered_amount >= 0),
    new_payment_id VARCHAR(255),
    response_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    recovery_time_seconds INTEGER CHECK (recovery_time_seconds IS NULL OR recovery_time_seconds >= 0),
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

DROP TRIGGER IF EXISTS trg_recovery_outcomes_updated_at ON recovery_outcomes;
CREATE TRIGGER trg_recovery_outcomes_updated_at
    BEFORE UPDATE ON recovery_outcomes
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ============================================================================
-- 11. ACTION_STATISTICS (Aggregated historical performance by category & action)
-- ============================================================================
CREATE TABLE IF NOT EXISTS action_statistics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    merchant_id UUID NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
    root_cause_category VARCHAR(100) NOT NULL,
    action_type VARCHAR(50) NOT NULL CHECK (action_type IN (
        'RETRY_NOW',
        'RETRY_LATER',
        'PAYMENT_UPDATE',
        'REMINDER',
        'ESCALATE',
        'STOP'
    )),
    total_attempts INTEGER NOT NULL DEFAULT 0 CHECK (total_attempts >= 0),
    successful_recoveries INTEGER NOT NULL DEFAULT 0 CHECK (successful_recoveries >= 0),
    success_rate DECIMAL(5, 4) NOT NULL DEFAULT 0.0000 CHECK (success_rate >= 0.0000 AND success_rate <= 1.0000),
    average_recovery_time_seconds DECIMAL(10, 2) NOT NULL DEFAULT 0.00 CHECK (average_recovery_time_seconds >= 0),
    total_recovered_amount DECIMAL(14, 2) NOT NULL DEFAULT 0.00 CHECK (total_recovered_amount >= 0),
    last_updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_action_stats_merchant_cause_action UNIQUE (merchant_id, root_cause_category, action_type)
);

DROP TRIGGER IF EXISTS trg_action_statistics_updated_at ON action_statistics;
CREATE TRIGGER trg_action_statistics_updated_at
    BEFORE UPDATE ON action_statistics
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ============================================================================
-- 12. BASELINE_RESULTS (Fixed-strategy comparison benchmark records)
-- ============================================================================
CREATE TABLE IF NOT EXISTS baseline_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    merchant_id UUID NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
    batch_id UUID NOT NULL REFERENCES batches(id) ON DELETE CASCADE,
    case_id UUID REFERENCES recovery_cases(id) ON DELETE CASCADE,
    strategy_name VARCHAR(100) NOT NULL DEFAULT 'FIXED_RETRY_STANDARD',
    is_recovered BOOLEAN NOT NULL DEFAULT false,
    total_attempts INTEGER NOT NULL DEFAULT 0 CHECK (total_attempts >= 0),
    recovered_amount DECIMAL(14, 2) NOT NULL DEFAULT 0.00 CHECK (recovered_amount >= 0),
    execution_log JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

DROP TRIGGER IF EXISTS trg_baseline_results_updated_at ON baseline_results;
CREATE TRIGGER trg_baseline_results_updated_at
    BEFORE UPDATE ON baseline_results
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ============================================================================
-- 13. AUDIT_LOGS (Immutable event log for actions, decisions, and overrides)
-- ============================================================================
CREATE TABLE IF NOT EXISTS audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    merchant_id UUID NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
    case_id UUID REFERENCES recovery_cases(id) ON DELETE SET NULL,
    action_id UUID REFERENCES recovery_actions(id) ON DELETE SET NULL,
    actor_type VARCHAR(50) NOT NULL DEFAULT 'SYSTEM' CHECK (actor_type IN ('SYSTEM', 'AI_AGENT', 'USER', 'WEBHOOK')),
    actor_id VARCHAR(255),
    event_type VARCHAR(100) NOT NULL,
    severity VARCHAR(20) NOT NULL DEFAULT 'INFO' CHECK (severity IN ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')),
    description TEXT NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================================
-- INDEXES FOR HIGH QUERY PERFORMANCE
-- ============================================================================

-- Merchants
CREATE INDEX IF NOT EXISTS idx_merchants_slug ON merchants (slug);
CREATE INDEX IF NOT EXISTS idx_merchants_is_active ON merchants (is_active);

-- Profiles
CREATE INDEX IF NOT EXISTS idx_profiles_merchant_id ON profiles (merchant_id);
CREATE INDEX IF NOT EXISTS idx_profiles_email ON profiles (email);
CREATE INDEX IF NOT EXISTS idx_profiles_role ON profiles (role);

-- Customers
CREATE INDEX IF NOT EXISTS idx_customers_merchant_id ON customers (merchant_id);
CREATE INDEX IF NOT EXISTS idx_customers_external_id ON customers (merchant_id, external_customer_id);
CREATE INDEX IF NOT EXISTS idx_customers_email ON customers (merchant_id, email);
CREATE INDEX IF NOT EXISTS idx_customers_phone ON customers (merchant_id, phone);

-- Batches
CREATE INDEX IF NOT EXISTS idx_batches_merchant_id ON batches (merchant_id);
CREATE INDEX IF NOT EXISTS idx_batches_status ON batches (merchant_id, status);
CREATE INDEX IF NOT EXISTS idx_batches_created_at ON batches (merchant_id, created_at DESC);

-- Payments
CREATE INDEX IF NOT EXISTS idx_payments_merchant_id ON payments (merchant_id);
CREATE INDEX IF NOT EXISTS idx_payments_customer_id ON payments (customer_id);
CREATE INDEX IF NOT EXISTS idx_payments_batch_id ON payments (batch_id);
CREATE INDEX IF NOT EXISTS idx_payments_razorpay_payment_id ON payments (razorpay_payment_id);
CREATE INDEX IF NOT EXISTS idx_payments_razorpay_order_id ON payments (razorpay_order_id);
CREATE INDEX IF NOT EXISTS idx_payments_status ON payments (merchant_id, status);
CREATE INDEX IF NOT EXISTS idx_payments_method ON payments (merchant_id, method);
CREATE INDEX IF NOT EXISTS idx_payments_created_at ON payments (merchant_id, created_at DESC);

-- Payment Failures
CREATE INDEX IF NOT EXISTS idx_payment_failures_merchant_id ON payment_failures (merchant_id);
CREATE INDEX IF NOT EXISTS idx_payment_failures_payment_id ON payment_failures (payment_id);
CREATE INDEX IF NOT EXISTS idx_payment_failures_error_code ON payment_failures (error_code);
CREATE INDEX IF NOT EXISTS idx_payment_failures_root_cause ON payment_failures (merchant_id, root_cause_category);
CREATE INDEX IF NOT EXISTS idx_payment_failures_failed_at ON payment_failures (merchant_id, failed_at DESC);

-- Policies
CREATE INDEX IF NOT EXISTS idx_policies_merchant_id ON policies (merchant_id);
CREATE INDEX IF NOT EXISTS idx_policies_is_default ON policies (merchant_id, is_default);
CREATE INDEX IF NOT EXISTS idx_policies_is_active ON policies (merchant_id, is_active);

-- Recovery Cases
CREATE INDEX IF NOT EXISTS idx_recovery_cases_merchant_id ON recovery_cases (merchant_id);
CREATE INDEX IF NOT EXISTS idx_recovery_cases_payment_id ON recovery_cases (payment_id);
CREATE INDEX IF NOT EXISTS idx_recovery_cases_failure_id ON recovery_cases (failure_id);
CREATE INDEX IF NOT EXISTS idx_recovery_cases_policy_id ON recovery_cases (policy_id);
CREATE INDEX IF NOT EXISTS idx_recovery_cases_batch_id ON recovery_cases (batch_id);
CREATE INDEX IF NOT EXISTS idx_recovery_cases_status ON recovery_cases (merchant_id, status);
CREATE INDEX IF NOT EXISTS idx_recovery_cases_priority ON recovery_cases (merchant_id, priority);
CREATE INDEX IF NOT EXISTS idx_recovery_cases_next_action ON recovery_cases (status, next_action_due_at) WHERE status IN ('DETECTED', 'DIAGNOSED', 'DECISION_READY', 'APPROVED', 'WAITING');
CREATE INDEX IF NOT EXISTS idx_recovery_cases_created_at ON recovery_cases (merchant_id, created_at DESC);

-- Recovery Actions
CREATE INDEX IF NOT EXISTS idx_recovery_actions_merchant_id ON recovery_actions (merchant_id);
CREATE INDEX IF NOT EXISTS idx_recovery_actions_case_id ON recovery_actions (case_id);
CREATE INDEX IF NOT EXISTS idx_recovery_actions_action_type ON recovery_actions (merchant_id, action_type);
CREATE INDEX IF NOT EXISTS idx_recovery_actions_status ON recovery_actions (merchant_id, status);
CREATE INDEX IF NOT EXISTS idx_recovery_actions_scheduled ON recovery_actions (status, scheduled_at) WHERE status IN ('PENDING', 'SCHEDULED');
CREATE INDEX IF NOT EXISTS idx_recovery_actions_created_at ON recovery_actions (merchant_id, created_at DESC);

-- Recovery Outcomes
CREATE INDEX IF NOT EXISTS idx_recovery_outcomes_merchant_id ON recovery_outcomes (merchant_id);
CREATE INDEX IF NOT EXISTS idx_recovery_outcomes_case_id ON recovery_outcomes (case_id);
CREATE INDEX IF NOT EXISTS idx_recovery_outcomes_action_id ON recovery_outcomes (action_id);
CREATE INDEX IF NOT EXISTS idx_recovery_outcomes_type ON recovery_outcomes (merchant_id, outcome_type);
CREATE INDEX IF NOT EXISTS idx_recovery_outcomes_success ON recovery_outcomes (merchant_id, is_successful);
CREATE INDEX IF NOT EXISTS idx_recovery_outcomes_recorded_at ON recovery_outcomes (merchant_id, recorded_at DESC);

-- Action Statistics
CREATE INDEX IF NOT EXISTS idx_action_statistics_merchant ON action_statistics (merchant_id);
CREATE INDEX IF NOT EXISTS idx_action_statistics_lookup ON action_statistics (merchant_id, root_cause_category, action_type);

-- Baseline Results
CREATE INDEX IF NOT EXISTS idx_baseline_results_merchant_id ON baseline_results (merchant_id);
CREATE INDEX IF NOT EXISTS idx_baseline_results_batch_id ON baseline_results (batch_id);
CREATE INDEX IF NOT EXISTS idx_baseline_results_case_id ON baseline_results (case_id);
CREATE INDEX IF NOT EXISTS idx_baseline_results_strategy ON baseline_results (merchant_id, strategy_name);

-- Audit Logs
CREATE INDEX IF NOT EXISTS idx_audit_logs_merchant_id ON audit_logs (merchant_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_case_id ON audit_logs (case_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_action_id ON audit_logs (action_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_event_type ON audit_logs (merchant_id, event_type);
CREATE INDEX IF NOT EXISTS idx_audit_logs_severity ON audit_logs (merchant_id, severity);
CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs (merchant_id, created_at DESC);

-- ============================================================================
-- ROW LEVEL SECURITY (RLS) INITIAL CONFIGURATION
-- ============================================================================
-- In accordance with Stage 2A specifications:
-- 1. Enable RLS on all tenant tables to prevent unintended public data exposure.
-- 2. By default in Supabase PostgreSQL, enabling RLS without policies denies all
--    anon and standard authenticated queries, while allowing bypass by service_role.
-- 3. Detailed per-tenant policies matching auth.uid() -> profiles.merchant_id
--    will be implemented in Stage 2B (Authentication & Authorization).
-- ============================================================================

ALTER TABLE merchants ENABLE ROW LEVEL SECURITY;
ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE customers ENABLE ROW LEVEL SECURITY;
ALTER TABLE batches ENABLE ROW LEVEL SECURITY;
ALTER TABLE payments ENABLE ROW LEVEL SECURITY;
ALTER TABLE payment_failures ENABLE ROW LEVEL SECURITY;
ALTER TABLE policies ENABLE ROW LEVEL SECURITY;
ALTER TABLE recovery_cases ENABLE ROW LEVEL SECURITY;
ALTER TABLE recovery_actions ENABLE ROW LEVEL SECURITY;
ALTER TABLE recovery_outcomes ENABLE ROW LEVEL SECURITY;
ALTER TABLE action_statistics ENABLE ROW LEVEL SECURITY;
ALTER TABLE baseline_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;
