# Deterministic Guardrails & Safety Architecture

## Principles
RecoverIQ employs a strict separation between intelligence and execution:
1. **AI / Adaptive Policies Propose**: The adaptive model scores candidate actions based on failure etiology and historical success rates.
2. **Deterministic Guardrails Validate**: Hardcoded, deterministic rules intercept every proposed action before execution.
3. **Controlled Executor Dispatches**: Actions are dispatched only if all guardrail checks pass.
4. **Outcome Verifier Confirms**: The final state is verified against the payment provider to prevent duplicate charges or inconsistent states.

## Mandatory Guardrail Invariants
- **Max Retry Threshold**: Never exceed max retry limit (e.g., maximum 3 retries across lifecycle).
- **Minimum Cooldown Interval**: Enforce mandatory backoff window between retry attempts.
- **Terminal State Lockout**: Once an event enters `STOP` or `RESOLVED`, no further automated actions may be scheduled.
- **Amount Thresholds for Escalation**: Payments exceeding defined high-risk value thresholds require merchant escalation rather than automated blind retries.
- **Simulator Transparency**: Any action executed via the simulator adapter is strictly labeled as simulated in the audit trail.
