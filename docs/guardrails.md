# Deterministic Guardrails & Safety Architecture

## Principles
RecoverIQ employs a strict separation between intelligence and execution:
1. **AI / Adaptive Policies Propose**: The adaptive model scores candidate actions based on failure etiology and historical success rates.
2. **Deterministic Guardrails Validate**: Hardcoded, deterministic rules intercept every proposed action before execution.
3. **Controlled Executor Dispatches**: Actions are dispatched only if all guardrail checks pass.
4. **Outcome Verifier Confirms**: The final state is verified against the payment provider to prevent duplicate charges or inconsistent states.

---

## Mandatory Deterministic Guardrail Invariants

### 1. Opt-Out Protection Invariant
- If `customer.is_opted_out = true`, the guardrail engine **immediately overrides any proposed action to `STOP`**.
- No automated SMS, WhatsApp, payment link, or retry communication is ever dispatched to opted-out payers.

### 2. Fraud & Security Lockout Invariant
- If the diagnosed root cause is `FRAUD_DECLINE` (stolen card, risk score 99, fraud alert), the action is **hard-locked to `STOP`**.
- Automated retries on suspected fraudulent transactions are strictly prohibited to safeguard merchant acquiring standing and chargeback ratios.

### 3. Maximum Retry Limits (`max_retries`)
- If `case.retry_count >= policy.max_retries` (default: 3), further automated payment retry attempts are blocked.
- High-value payments are escalated to manual operations; standard payments transition to terminal `STOP`.

### 4. Maximum Communication Limits (`max_communications`)
- If `case.communication_count >= policy.max_communications` (default: 3), further customer reminders or payment update links are blocked to prevent customer harassment and brand fatigue.

### 5. Mandatory Backoff Cooldown (`cooldown_minutes`)
- Immediate retries (`RETRY_NOW`) are blocked if elapsed time since the previous attempt is less than `policy.cooldown_minutes` (default: 60 minutes for gateway errors).
- Actions violating cooldown are automatically converted to `RETRY_LATER` and scheduled for the appropriate delay window.

### 6. Time-of-Day Communication Windows
- Customer contact actions (`REMINDER`, `PAYMENT_UPDATE`) are strictly constrained to allowed hours (default: `09:00:00` - `20:00:00`) and allowed days (e.g., Monday through Friday for VIP policy).
- Out-of-window actions are deferred to the next valid opening.

### 7. VIP & High-Value Order Auto-Escalation (`escalation_threshold_amount`)
- Orders meeting or exceeding `policy.escalation_threshold_amount` (default: ₹10,000 INR) with `auto_escalate_vip = true` are routed directly to high-touch merchant operations (`ESCALATE`) rather than blind algorithmic retries.

### 8. Immutable Audit Trail
- Every guardrail check (passed, failed, or overridden) produces an immutable record in `audit_logs` capturing the check status, proposed action, and override rationale.

---

## Multi-Tenant Security & Access Invariants

1. **Zero Trust of Client Tenancy**: Client applications cannot supply a `merchant_id` to access or manipulate data. Tenancy is derived strictly from verified Supabase JWT claims (`sub`) mapped to active `profiles` records.
2. **Service-Role Key Confinement**: The Supabase Service Role key (`SUPABASE_SERVICE_ROLE_KEY`) is strictly confined to server-side backend services. The React client bundle only contains public anon credentials (`VITE_SUPABASE_ANON_KEY`).
3. **Row-Level Security (RLS)**: PostgreSQL RLS is active across all 13 application tables with `SECURITY DEFINER` resolution functions. Insecure open policies (`USING (true)`) are forbidden.
4. **Role Hierarchy (RBAC)**:
   - `viewer`: Strictly read-only operations.
   - `operator`: Can trigger recovery batches and advance case recovery workflows.
   - `admin` / `owner`: Authorized for policy updates, organization settings, and administrative overrides.
