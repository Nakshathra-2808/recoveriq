-- ============================================================================
-- RecoverIQ Seed Reference Data
-- Seed: 001_demo_reference_data.sql
-- Description: Non-sensitive reference configuration and default policies.
-- Note: Synthetic payment datasets and outcomes will be generated in a later stage.
-- ============================================================================

-- 1. Create Default Demo Merchant
INSERT INTO merchants (id, name, slug, currency, timezone, is_active, settings)
VALUES (
    '00000000-0000-0000-0000-000000000001',
    'Acme Retail India',
    'acme-retail',
    'INR',
    'Asia/Kolkata',
    true,
    '{"support_email": "support@acmeretail.example.com", "webhook_retry_enabled": true}'::jsonb
)
ON CONFLICT (id) DO NOTHING;

-- 2. Default Guarded Recovery Policies for Demo Merchant
INSERT INTO policies (
    id,
    merchant_id,
    name,
    description,
    is_default,
    is_active,
    max_retries,
    max_communications,
    cooldown_minutes,
    communication_window_start,
    communication_window_end,
    allowed_days,
    escalation_threshold_amount,
    auto_escalate_vip,
    respect_opt_out,
    opt_out_action,
    rules
)
VALUES (
    '10000000-0000-0000-0000-000000000001',
    '00000000-0000-0000-0000-000000000001',
    'Standard Guarded Policy (Default)',
    'Standard production recovery policy with strict customer contact guardrails and cooldown windows.',
    true,
    true,
    3,
    3,
    60,
    '09:00:00',
    '20:00:00',
    '["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]'::jsonb,
    10000.00,
    true,
    true,
    'STOP',
    '{"enable_ai_diagnosis": true, "enable_adaptive_retry_timing": true, "max_consecutive_failures": 2}'::jsonb
),
(
    '10000000-0000-0000-0000-000000000002',
    '00000000-0000-0000-0000-000000000001',
    'High-Value VIP & Enterprise Policy',
    'Conservative policy with low communication frequency and rapid escalation for high-value orders.',
    false,
    true,
    2,
    2,
    120,
    '10:00:00',
    '19:00:00',
    '["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY"]'::jsonb,
    5000.00,
    true,
    true,
    'ESCALATE',
    '{"enable_ai_diagnosis": true, "vip_dedicated_agent": true, "escalate_on_first_failure": false}'::jsonb
)
ON CONFLICT (id) DO NOTHING;

-- 3. Initial Baseline Action Statistics (Calibrated Priors)
INSERT INTO action_statistics (
    id,
    merchant_id,
    root_cause_category,
    action_type,
    total_attempts,
    successful_recoveries,
    success_rate,
    average_recovery_time_seconds,
    total_recovered_amount
)
VALUES
(
    '20000000-0000-0000-0000-000000000001',
    '00000000-0000-0000-0000-000000000001',
    'NETWORK_TIMEOUT',
    'RETRY_NOW',
    100,
    72,
    0.7200,
    15.50,
    144000.00
),
(
    '20000000-0000-0000-0000-000000000002',
    '00000000-0000-0000-0000-000000000001',
    'GATEWAY_ERROR',
    'RETRY_LATER',
    100,
    58,
    0.5800,
    3600.00,
    116000.00
),
(
    '20000000-0000-0000-0000-000000000003',
    '00000000-0000-0000-0000-000000000001',
    'INSUFFICIENT_FUNDS',
    'PAYMENT_UPDATE',
    100,
    41,
    0.4100,
    7200.00,
    82000.00
),
(
    '20000000-0000-0000-0000-000000000004',
    '00000000-0000-0000-0000-000000000001',
    'USER_DROPPED',
    'REMINDER',
    100,
    35,
    0.3500,
    1800.00,
    70000.00
),
(
    '20000000-0000-0000-0000-000000000005',
    '00000000-0000-0000-0000-000000000001',
    'CARD_LIMIT_EXCEEDED',
    'ESCALATE',
    50,
    26,
    0.5200,
    14400.00,
    260000.00
),
(
    '20000000-0000-0000-0000-000000000006',
    '00000000-0000-0000-0000-000000000001',
    'FRAUD_DECLINE',
    'STOP',
    50,
    0,
    0.0000,
    0.00,
    0.00
)
ON CONFLICT (merchant_id, root_cause_category, action_type) DO NOTHING;
