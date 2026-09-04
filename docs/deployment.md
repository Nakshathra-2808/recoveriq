# RecoverIQ Production & Cloud Deployment Guide

This guide provides step-by-step instructions for deploying RecoverIQ to free-tier cloud environments:
- **Frontend**: [Vercel](https://vercel.com) (React + TypeScript + Vite SPA)
- **Backend**: [Render](https://render.com) (FastAPI Python Web Service)
- **Database & Auth**: [Supabase](https://supabase.com) (PostgreSQL with RLS & Supabase Auth)

---

## 1. System Topology & Cloud Mapping

```
[ End User Browser ]
       │
       ▼
[ Vercel Frontend ] (https://recoveriq.vercel.app)
       │
       │ Bearer JWT (Supabase Auth) + HTTPS REST
       ▼
[ Render Backend ] (https://recoveriq-backend.onrender.com)
       │
       │ Service Role Auth (PostgREST)
       ▼
[ Supabase Managed Database ] (PostgreSQL + RLS + Auth Engine)
```

---

## 2. Required Environment Variables Matrix

### A. Backend (Render Environment)

| Variable Name | Example Value | Description |
|---|---|---|
| `ENVIRONMENT` | `production` | Deployment environment mode |
| `PROJECT_NAME` | `RecoverIQ Backend` | Application title |
| `API_V1_STR` | `/api/v1` | API version routing prefix |
| `ALLOWED_ORIGINS` | `https://your-app.vercel.app,http://localhost:5173` | Comma-separated CORS origins |
| `SUPABASE_URL` | `https://your-project.supabase.co` | Supabase project API URL |
| `SUPABASE_ANON_KEY` | `eyJ...` | Supabase Anon Public Key |
| `SUPABASE_SERVICE_ROLE_KEY` | `eyJ...` | Supabase Service Role Secret Key |
| `SUPABASE_JWT_SECRET` | `your-jwt-secret-from-supabase` | Supabase JWT Secret (for HS256/JWKS verification) |
| `RAZORPAY_ENVIRONMENT` | `test` | Strictly `test` for sandbox operations |
| `RAZORPAY_KEY_ID` | `rzp_test_xxxx` | Razorpay Test Key ID |
| `RAZORPAY_KEY_SECRET` | `your-rzp-test-secret` | Razorpay Test Key Secret |
| `RAZORPAY_BASE_URL` | `https://api.razorpay.com/v1` | Razorpay API base URL |
| `LLM_PROVIDER` | `gemini` | `gemini`, `openai`, `groq`, or `mock` |
| `LLM_API_KEY` | `AIzaSy...` | Gemini or OpenAI API Key (Optional; fallback engaged if omitted) |
| `LLM_MODEL` | `gemini-1.5-flash` | LLM model identifier |

> **Security Rule**: `SUPABASE_SERVICE_ROLE_KEY`, `RAZORPAY_KEY_SECRET`, `LLM_API_KEY`, and `SUPABASE_JWT_SECRET` must **never** be shared with the frontend or committed to source control.

---

### B. Frontend (Vercel Environment)

| Variable Name | Example Value | Description |
|---|---|---|
| `VITE_API_BASE_URL` | `https://recoveriq-backend.onrender.com` | Deployed backend Render URL |
| `VITE_SUPABASE_URL` | `https://your-project.supabase.co` | Supabase project API URL |
| `VITE_SUPABASE_ANON_KEY` | `eyJ...` | Supabase public anonymous key |

---

## 3. Step-by-Step Deployment Instructions

### Step 1: Supabase Configuration
1. Create a project at [supabase.com](https://supabase.com).
2. Go to **SQL Editor** and run the initial migration script: `supabase/migrations/20260903000001_initial_schema.sql`.
3. In **Authentication -> Users**, create an operator user (e.g. `operator@acmeretail.example.com`).
4. In **SQL Editor**, verify the profile record is connected to `Acme Retail India`:
   ```sql
   INSERT INTO profiles (id, merchant_id, role, full_name)
   SELECT id, '00000000-0000-0000-0000-000000000001', 'operator', 'Acme Operator'
   FROM auth.users WHERE email = 'operator@acmeretail.example.com'
   ON CONFLICT (id) DO NOTHING;
   ```

---

### Step 2: Render Backend Deployment
1. Log in to [Render Dashboard](https://dashboard.render.com).
2. Click **New +** -> **Web Service** -> Connect your GitHub repository (`Nakshathra-2808/recoveriq`).
3. Set the following configuration:
   - **Name**: `recoveriq-backend`
   - **Region**: `Oregon (US West)` or closest
   - **Branch**: `main`
   - **Root Directory**: `backend`
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install --upgrade pip && pip install -r requirements.txt`
   - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Health Check Path**: `/health`
   - **Plan**: `Free`
4. In **Environment Variables**, add the variables listed in Section 2A.
5. Click **Create Web Service**.
6. Once deployed, test the health endpoint: `https://your-backend.onrender.com/health` (should return `{"status": "ok", "service": "recoveriq-backend", "version": "0.1.0"}`).

---

### Step 3: Vercel Frontend Deployment
1. Log in to [Vercel Dashboard](https://vercel.com).
2. Click **Add New...** -> **Project** -> Import `Nakshathra-2808/recoveriq`.
3. Configure the project settings:
   - **Framework Preset**: `Vite`
   - **Root Directory**: `frontend`
   - **Build Command**: `npm run build`
   - **Output Directory**: `dist`
4. In **Environment Variables**, add:
   - `VITE_API_BASE_URL`: `https://your-backend.onrender.com`
   - `VITE_SUPABASE_URL`: `https://your-project.supabase.co`
   - `VITE_SUPABASE_ANON_KEY`: `your-supabase-anon-key`
5. Click **Deploy**.
6. After Vercel deployment completes, copy your Vercel URL (e.g. `https://recoveriq.vercel.app`) and add it to `ALLOWED_ORIGINS` in your **Render** dashboard environment variables.

---

## 4. End-to-End Verification Checklist

- [ ] **Backend Health**: `GET https://your-backend.onrender.com/health` returns `200 OK`.
- [ ] **Frontend Login**: Log in with user credentials; session persists on browser refresh.
- [ ] **Auth Resolution**: `GET /api/v1/auth/me` resolves the operator profile to `Acme Retail India`.
- [ ] **Run Demo Batch**: Clicking "Run Demo Recovery" seeds and processes 6 synthetic failed transactions.
- [ ] **Batch-Scoped Metrics**: Dashboard KPI cards reflect the executed batch recovery metrics and lift calculation.
- [ ] **AI Diagnosis Display**: Opening a case modal displays root cause, AI recommendation, confidence %, and reasoning narrative.
- [ ] **Guardrail Enforcement**: Opted-out customer and fraud decline cases are terminated (`STOP`) with zero unauthorized external retries.
- [ ] **Safe Test Execution**: Gateway operations execute safely under `SIMULATION` or `RAZORPAY_TEST` sandbox mode.
