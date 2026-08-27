# RecoverIQ Architecture Specification

## Overview
RecoverIQ is an Adaptive AI Revenue Recovery Agent built for Razorpay Track 03. It specializes strictly in recovering failed and degraded payments through root cause diagnosis, adaptive policy selection, deterministic server-side guardrails, and verifiable outcome tracking.

## System Topology (Modular Monolith)

```
[ Merchant Web Console ] (React + TypeScript + Tailwind CSS)
           │
           │ Supabase Auth (JWT) / REST API
           ▼
[ FastAPI Backend Application ]
   ├── API Layer (/api/v1)
   ├── Auth Middleware (Supabase JWT Verification)
   ├── Diagnosis Service (Error & Gateway Classification)
   ├── Adaptive Policy Engine (Statistical Action Scoring)
   ├── Server-Side Guardrails (Deterministic Safety Limits)
   ├── Action Executor (Razorpay Sandbox / Simulator Adapter)
   └── Outcome Verifier & Audit Logger
           │
           ▼
[ Supabase PostgreSQL ] (RLS Enabled)
   ├── merchant_accounts
   ├── payment_failures
   ├── recovery_actions
   ├── recovery_audit_logs
   └── policy_success_stats
```

## Core Recovery Actions
1. `RETRY_NOW` — Immediate transient error retry.
2. `RETRY_LATER` — Scheduled retry after gateway degradation cooldown.
3. `PAYMENT_UPDATE` — Prompt customer to switch payment method (e.g. UPI / Card fallback).
4. `REMINDER` — Notification sent via preferred communication channel.
5. `ESCALATE` — Flag for high-value manual merchant intervention.
6. `STOP` — Explicit terminal state to prevent customer harassment or duplicate charges.

## Guardrail Rules & Boundaries
- Non-bypassable server-side enforcement.
- Hard limits on retry attempts per invoice/payment.
- Explicit cooldown windows.
- No direct LLM mutation of financial state or execution of external payment calls.
