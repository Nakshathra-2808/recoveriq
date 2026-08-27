# RecoverIQ API Reference

## Base URLs
- Development: `http://localhost:8000`
- API Prefix: `/api/v1`

## Authentication
Protected endpoints require a Bearer token issued by Supabase Auth in the `Authorization` header:
```
Authorization: Bearer <supabase_jwt_token>
```

## Endpoints

### Health Check
- `GET /health` — Root health check
- `GET /api/v1/health` — V1 API health check

**Response:**
```json
{
  "status": "ok",
  "service": "recoveriq-backend",
  "version": "0.1.0"
}
```

### Future Planned Endpoints
- `POST /api/v1/events/payment-failure` — Ingest payment failure events from Razorpay webhooks or batch inputs.
- `POST /api/v1/recovery/diagnose` — Run root cause failure diagnosis.
- `POST /api/v1/recovery/evaluate` — Evaluate adaptive policy action candidates.
- `POST /api/v1/recovery/execute` — Execute guarded recovery action.
- `GET /api/v1/recovery/audit-trail/{case_id}` — Retrieve complete decision and execution audit trail.
- `GET /api/v1/metrics/incremental` — Compare RecoverIQ recovery vs. standard baseline on identical batches.

## Core Schema Enums & State Mappings

### Recovery Case Statuses (`recovery_cases.status`)
- `DETECTED` — Initial failure ingestion.
- `DIAGNOSED` — Root cause diagnosis completed.
- `DECISION_READY` — Policy recommendation prepared.
- `APPROVED` — Action approved (manual or automated).
- `EXECUTING` — Recovery action in flight.
- `RECOVERED` — Payment recovered successfully (Terminal).
- `WAITING` — Cooldown or customer response window active.
- `STOPPED` — Terminated by guardrail or opt-out (Terminal).
- `ESCALATED` — Routed to human merchant operations (Terminal / Manual).
- `FAILED` — All retries exhausted without recovery (Terminal).

### Recovery Action Types (`recovery_actions.action_type`)
- `RETRY_NOW`, `RETRY_LATER`, `PAYMENT_UPDATE`, `REMINDER`, `ESCALATE`, `STOP`

### Execution Modes (`recovery_actions.execution_mode`)
- `RAZORPAY_TEST`, `SIMULATION`, `DRY_RUN`

