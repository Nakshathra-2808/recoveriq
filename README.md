# RecoverIQ — Adaptive AI Revenue Recovery Agent

[![CI Pipeline](https://github.com/Nakshathra-2808/recoveriq/actions/workflows/ci.yml/badge.svg)](https://github.com/Nakshathra-2808/recoveriq/actions)

RecoverIQ is an Adaptive AI Revenue Recovery Agent developed for **Razorpay Track 03**. It focuses strictly on failed/degraded payment recovery by identifying payment degradation root causes, dynamically choosing the optimal recovery action, enforcing deterministic server-side guardrails, and tracking incremental revenue (₹) recovered over standard retry baselines.

---

## 🎯 Architecture & Flow

```
Merchant Login
  └──> Supabase Auth (JWT)
        └──> React Console (Tailwind CSS)
              └──> FastAPI Modular Monolith Backend
                    ├──> Failure Event Ingestion & Revenue-at-Risk Calculation
                    ├──> Root Cause Diagnosis (Gateway / Bank / Instrument / Transient)
                    ├──> Adaptive Policy Selection (Scored Historical Outcomes)
                    ├──> Deterministic Server-Side Guardrails (Hard Limits & Cooldowns)
                    ├──> Controlled Action Executor (Razorpay Sandbox / Simulator Adapter)
                    ├──> Outcome Verification & Audit Trail Logging
                    └──> Incremental ₹ Recovered Dashboard Reporting (vs Baseline)
```

---

## 📁 Repository Structure

```
recoveriq/
├── backend/
│   ├── app/
│   │   ├── api/          # API routers and endpoints (/api/v1)
│   │   ├── auth/         # Supabase JWT validation and auth dependencies
│   │   ├── core/         # Settings and configurations
│   │   ├── models/       # Database models
│   │   ├── schemas/      # Pydantic request/response schemas
│   │   ├── services/     # Core business logic services
│   │   ├── policies/     # Adaptive recovery policies & guardrails
│   │   ├── agents/       # AI reasoning and decision scoring
│   │   └── main.py       # FastAPI application entrypoint
│   ├── tests/            # Pytest test suite
│   ├── requirements.txt  # Python backend dependencies
│   └── .env.example      # Backend environment template
│
├── frontend/
│   ├── src/
│   │   ├── auth/         # Supabase auth context and client
│   │   ├── pages/        # Router pages (Login, Dashboard, 404)
│   │   ├── components/   # UI components and layout
│   │   ├── services/     # Backend API client
│   │   └── types/        # TypeScript interfaces
│   ├── package.json      # Node.js dependencies and scripts
│   ├── vite.config.ts    # Vite bundler configuration
│   ├── tailwind.config.js# Tailwind CSS configuration
│   └── .env.example      # Frontend environment template
│
├── supabase/
│   ├── migrations/       # SQL schema migrations
│   └── seed/             # Initial seed data
│
├── data/
│   └── synthetic/        # Synthetic payment failure batches
│
├── docs/
│   ├── architecture.md   # System architecture and flow
│   ├── api.md            # API endpoint specifications
│   ├── guardrails.md     # Deterministic safety rules
│   └── demo.md           # End-to-end demo execution guide
│
├── .github/
│   └── workflows/        # GitHub Actions CI
├── .gitignore
├── README.md
└── docker-compose.yml
```

---

## 🚀 Getting Started (Independent Execution)

### 1. Backend Setup

```bash
cd backend
python -m venv .venv

# On Windows (PowerShell):
.venv\Scripts\Activate.ps1
# On Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env

# Run FastAPI server:
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
Backend health check is accessible at `http://localhost:8000/health` and Swagger UI at `http://localhost:8000/api/v1/docs`.

### 2. Frontend Setup

```bash
cd frontend
npm install
cp .env.example .env

# Run Vite dev server:
npm run dev
```
Frontend console is accessible at `http://localhost:5173`.

---

## 🛡️ Recovery Actions & Guardrails
RecoverIQ supports six core actions:
- `RETRY_NOW`: Immediate retry for transient network hiccups.
- `RETRY_LATER`: Scheduled retry with exponential cooldown for bank/gateway degradation.
- `PAYMENT_UPDATE`: Payment method switch link sent to buyer.
- `REMINDER`: Contextual customer nudge.
- `ESCALATE`: Flagged for manual merchant intervention for high-value transactions.
- `STOP`: Absolute terminal state to guarantee no over-retrying or duplicate charges.
