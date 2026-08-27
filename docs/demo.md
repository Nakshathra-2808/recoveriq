# RecoverIQ End-to-End Demo Guide

## Target Flow
1. **Merchant Login**: Merchant authenticates via Supabase Auth into the React console.
2. **Failure Ingestion**: Ingests realistic payment failure events (e.g. gateway timeout, insufficient funds, network drop, expired instrument).
3. **Revenue-at-Risk Calculation**: Calculates the financial exposure in ₹.
4. **Diagnosis & Policy Selection**: Root cause diagnosed and mapped to candidate action (`RETRY_NOW`, `RETRY_LATER`, `PAYMENT_UPDATE`, `REMINDER`, `ESCALATE`, `STOP`).
5. **Guardrail Check**: Validates retry counts, cooldown periods, and merchant rules.
6. **Execution & Verification**: Executes action via Razorpay Sandbox or explicit simulator adapter and verifies status.
7. **Audit & Incremental Metric**: Generates auditable log and compares recovered ₹ vs. standard blind retry baseline.
