# RecoverIQ Execution Adapters & Razorpay Sandbox Specification

RecoverIQ supports three controlled execution modes designed for safe revenue recovery operations without risk of unintended live financial transactions or data leaks.

---

## 1. Execution Modes

| Mode | Identifier | Description | External Network Calls |
|---|---|---|---|
| **Simulation Mode** (Default) | `SIMULATION` | High-fidelity, reproducible sandbox for hackathon demonstrations, regression tests, and zero-dependency local runs. | None (Simulated Gateway Responses) |
| **Razorpay Test Mode** | `RAZORPAY_TEST` | Genuine server-side integration with official Razorpay Test / Sandbox APIs (`https://api.razorpay.com/v1`). | Real HTTPS to Razorpay Test Endpoints |
| **Dry Run Mode** | `DRY_RUN` | Evaluates diagnosis, Bayesian policy scoring, and safety guardrails without dispatching any payment action. | None |

---

## 2. Environment Configuration

To enable `RAZORPAY_TEST` mode, configure the following backend environment variables in `backend/.env`:

```env
# Razorpay Test Configuration (Backend-Only)
RAZORPAY_ENVIRONMENT=test
RAZORPAY_KEY_ID=rzp_test_yourKeyId
RAZORPAY_KEY_SECRET=yourKeySecret
RAZORPAY_BASE_URL=https://api.razorpay.com/v1
RAZORPAY_TIMEOUT_SECONDS=5.0
```

> **Security Invariant**: `RAZORPAY_KEY_SECRET` and API credentials are kept strictly on the backend. They are never sent to the frontend or included in audit logs.

---

## 3. Genuine Razorpay Test API Operations

When `RAZORPAY_TEST` mode is active, RecoverIQ dispatches genuine HTTPS requests using HTTP Basic Authentication (`(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET)`):

### A. Payment Links API (`POST /v1/payment_links`)
- **Triggered for**: `PAYMENT_UPDATE` and `REMINDER` actions.
- **Genuine API payload**:
  - `amount`: Transaction amount in paise (e.g., `249900` for ₹2,499.00).
  - `currency`: `"INR"`.
  - `description`: Contextual case recovery description.
  - `customer`: Name, sanitized email, and contact phone.
  - `notify`: `{"sms": true, "email": true}`.
  - `reminder_enable`: `true`.
  - `notes`: Key-value metadata containing `case_id`, `merchant_id`, and `action_type`.
- **Response**: Yields genuine Razorpay payment link identifier (`plink_xxx`) and hosted checkout URL (`https://rzp.io/i/xxx`).

### B. Orders API (`POST /v1/orders`)
- **Triggered for**: `RETRY_NOW` and `RETRY_LATER` actions.
- **Genuine API payload**:
  - `amount`: Order amount in paise.
  - `currency`: `"INR"`.
  - `receipt`: Unique case receipt identifier (`rec_case_xxx`).
  - `notes`: Key-value metadata with original failed payment ID and retry parameters.
- **Response**: Yields genuine Razorpay Order identifier (`order_xxx`).

---

## 4. Safety Limitations & Simulated Operations

### A. Direct Card Auto-Recharge Limitation
- **Context**: In Indian payment processing (RBI guidelines) and Razorpay test/production infrastructure, server-side direct debit of card numbers without 3DS OTP or e-mandate pre-authorization is not permitted for one-time transactions.
- **Implementation**: In `RAZORPAY_TEST` mode, `RETRY_NOW` and `RETRY_LATER` create a genuine Razorpay **Order** to initialize the retry checkout session. The automated capture verification is simulated in test mode.

### B. Internal Merchant Operations
- `ESCALATE`: Routes to internal merchant VIP operations; no external gateway call is necessary.
- `STOP`: Halts recovery case permanently due to fraud decline, customer opt-out, or policy constraint; no external gateway call is made.

### C. Live Credentials Forbidden
- The adapter strictly validates that `RAZORPAY_ENVIRONMENT == "test"` and that `RAZORPAY_KEY_ID` does not start with `rzp_live_`. Any attempt to configure live production credentials in test mode immediately raises an exception.
