import logging
import uuid
import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
import httpx
from fastapi import HTTPException, status
from app.core.config import settings

logger = logging.getLogger(__name__)

# Sensible default timeout for PostgREST database operations
DEFAULT_TIMEOUT = httpx.Timeout(20.0, connect=10.0)


class SupabaseDB:
    """
    Asynchronous database client for Supabase PostgreSQL tables via PostgREST.
    Maintains strict multi-tenant scoping on all queries and mutations.
    Provides robust connection retry logic with exponential backoff on transient errors.
    Provides an in-memory test store fallback for hermetic unit testing.
    """

    def __init__(self, http_client: Optional[httpx.AsyncClient] = None, use_mock_store: bool = False):
        self._http_client = http_client
        self.use_mock_store = use_mock_store or not (settings.SUPABASE_URL and settings.SUPABASE_SERVICE_ROLE_KEY)
        # In-memory store keyed by table_name -> list of dict records
        self._mock_db: Dict[str, List[Dict[str, Any]]] = {
            "merchants": [],
            "profiles": [],
            "customers": [],
            "batches": [],
            "payments": [],
            "payment_failures": [],
            "policies": [],
            "recovery_cases": [],
            "recovery_actions": [],
            "recovery_outcomes": [],
            "action_statistics": [],
            "baseline_results": [],
            "audit_logs": [],
        }

    def reset_mock_store(self):
        """Clears in-memory mock store for testing isolation."""
        for key in self._mock_db:
            self._mock_db[key] = []

    def _headers(self) -> Dict[str, str]:
        return {
            "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
            "Accept": "application/json",
        }

    # -------------------------------------------------------------------------
    # ROBUST HTTP RETRY MECHANISM
    # -------------------------------------------------------------------------

    async def _execute_with_retry(
        self,
        method: str,
        url: str,
        operation_name: str,
        headers: Dict[str, str],
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, str]] = None,
        max_retries: int = 3
    ) -> httpx.Response:
        """
        Executes an HTTP request against PostgREST with exponential backoff retries
        specifically for transient connection, timeout, and 5xx gateway errors.
        Permanent 4xx errors (e.g. 400 Bad Request, 409 Conflict) are returned immediately without retrying.
        """
        client = self._http_client or httpx.AsyncClient(timeout=DEFAULT_TIMEOUT)
        close_client = not bool(self._http_client)
        try:
            for attempt in range(max_retries):
                try:
                    res = await client.request(
                        method,
                        url,
                        headers=headers,
                        json=json_data,
                        params=params,
                        timeout=DEFAULT_TIMEOUT
                    )
                    # Transient gateway / upstream server errors
                    if res.status_code in (502, 503, 504) and attempt < max_retries - 1:
                        backoff = 0.2 * (2 ** attempt)
                        logger.warning(
                            f"Transient HTTP {res.status_code} during {operation_name}. Retrying in {backoff:.2f}s (attempt {attempt + 1}/{max_retries})..."
                        )
                        await asyncio.sleep(backoff)
                        continue
                    return res
                except (httpx.TimeoutException, httpx.NetworkError) as e:
                    if attempt < max_retries - 1:
                        backoff = 0.2 * (2 ** attempt)
                        logger.warning(
                            f"Transient network error ({type(e).__name__}) during {operation_name}. Retrying in {backoff:.2f}s (attempt {attempt + 1}/{max_retries})..."
                        )
                        await asyncio.sleep(backoff)
                    else:
                        logger.error(
                            f"Supabase connection failure during {operation_name} after {max_retries} attempts: {type(e).__name__}"
                        )
                        raise HTTPException(
                            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail=f"Database connection timeout during {operation_name}. Please check Supabase network connectivity."
                        )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Database request failed during {operation_name} after {max_retries} attempts."
            )
        finally:
            if close_client:
                await client.aclose()

    # -------------------------------------------------------------------------
    # GENERIC REST HELPERS
    # -------------------------------------------------------------------------

    async def _insert(self, table: str, record: Dict[str, Any]) -> Dict[str, Any]:
        if "id" not in record:
            record["id"] = str(uuid.uuid4())
        if "created_at" not in record:
            record["created_at"] = datetime.now(timezone.utc).isoformat()
        if "updated_at" not in record and table != "audit_logs":
            record["updated_at"] = datetime.now(timezone.utc).isoformat()

        if self.use_mock_store:
            self._mock_db[table].append(dict(record))
            return dict(record)

        url = f"{settings.SUPABASE_URL.rstrip('/')}/rest/v1/{table}"
        res = await self._execute_with_retry("POST", url, f"insert into {table}", self._headers(), json_data=record)
        if res.status_code not in (200, 201):
            err_body = res.text[:300]
            logger.error(f"Error inserting into {table}: HTTP {res.status_code} - {err_body}")
            raise HTTPException(
                status_code=res.status_code if 400 <= res.status_code < 500 else status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Database insert failed on {table}: {err_body}"
            )
        data = res.json()
        return data[0] if isinstance(data, list) and data else record

    async def _select(self, table: str, params: Dict[str, str]) -> List[Dict[str, Any]]:
        if self.use_mock_store:
            records = self._mock_db.get(table, [])
            filtered = []
            for r in records:
                match = True
                for k, v in params.items():
                    field = k.split(".")[0]
                    val = v.replace("eq.", "") if isinstance(v, str) and v.startswith("eq.") else v
                    if str(r.get(field)) != str(val):
                        match = False
                        break
                if match:
                    filtered.append(dict(r))
            return filtered

        url = f"{settings.SUPABASE_URL.rstrip('/')}/rest/v1/{table}"
        res = await self._execute_with_retry("GET", url, f"select from {table}", self._headers(), params=params)
        if res.status_code != 200:
            err_body = res.text[:300]
            logger.error(f"Error selecting from {table}: HTTP {res.status_code} - {err_body}")
            raise HTTPException(
                status_code=res.status_code if 400 <= res.status_code < 500 else status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Database query failed on {table}: {err_body}"
            )
        return res.json()

    async def _update(self, table: str, record_id: str, merchant_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        if self.use_mock_store:
            for r in self._mock_db.get(table, []):
                if str(r.get("id")) == str(record_id) and str(r.get("merchant_id")) == str(merchant_id):
                    r.update(updates)
                    return dict(r)
            return None

        url = f"{settings.SUPABASE_URL.rstrip('/')}/rest/v1/{table}"
        params = {"id": f"eq.{record_id}", "merchant_id": f"eq.{merchant_id}"}
        res = await self._execute_with_retry("PATCH", url, f"update on {table}", self._headers(), json_data=updates, params=params)
        if res.status_code != 200:
            err_body = res.text[:300]
            logger.error(f"Error updating {table}: HTTP {res.status_code} - {err_body}")
            raise HTTPException(
                status_code=res.status_code if 400 <= res.status_code < 500 else status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Database update failed on {table}: {err_body}"
            )
        data = res.json()
        return data[0] if isinstance(data, list) and data else None

    # -------------------------------------------------------------------------
    # DOMAIN SPECIFIC METHODS
    # -------------------------------------------------------------------------

    async def get_default_policy(self, merchant_id: str) -> Dict[str, Any]:
        """Fetches active default recovery policy for merchant."""
        policies = await self._select("policies", {"merchant_id": f"eq.{merchant_id}", "is_default": "eq.true"})
        if policies:
            return policies[0]

        # Fallback default policy if none found
        return {
            "id": "10000000-0000-0000-0000-000000000001",
            "merchant_id": merchant_id,
            "name": "Standard Guarded Policy (Default)",
            "max_retries": 3,
            "max_communications": 3,
            "cooldown_minutes": 60,
            "communication_window_start": "09:00:00",
            "communication_window_end": "20:00:00",
            "allowed_days": ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"],
            "escalation_threshold_amount": 10000.00,
            "auto_escalate_vip": True,
            "respect_opt_out": True,
            "opt_out_action": "STOP",
            "is_active": True,
        }

    async def get_customer(self, customer_id: str, merchant_id: str) -> Optional[Dict[str, Any]]:
        customers = await self._select("customers", {"id": f"eq.{customer_id}", "merchant_id": f"eq.{merchant_id}"})
        return customers[0] if customers else None

    async def get_customer_by_external_id(self, external_customer_id: str, merchant_id: str) -> Optional[Dict[str, Any]]:
        customers = await self._select(
            "customers",
            {"external_customer_id": f"eq.{external_customer_id}", "merchant_id": f"eq.{merchant_id}"}
        )
        return customers[0] if customers else None

    async def create_customer(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return await self._insert("customers", data)

    async def create_batch(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return await self._insert("batches", data)

    async def update_batch(self, batch_id: str, merchant_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return await self._update("batches", batch_id, merchant_id, updates)

    async def get_batch(self, batch_id: str, merchant_id: str) -> Optional[Dict[str, Any]]:
        batches = await self._select("batches", {"id": f"eq.{batch_id}", "merchant_id": f"eq.{merchant_id}"})
        return batches[0] if batches else None

    async def create_payment(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return await self._insert("payments", data)

    async def create_payment_failure(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return await self._insert("payment_failures", data)

    async def get_payment_with_failure(self, payment_id: str, merchant_id: str) -> Optional[Dict[str, Any]]:
        payments = await self._select("payments", {"id": f"eq.{payment_id}", "merchant_id": f"eq.{merchant_id}"})
        if not payments:
            return None
        payment = payments[0]
        failures = await self._select("payment_failures", {"payment_id": f"eq.{payment_id}", "merchant_id": f"eq.{merchant_id}"})
        payment["failure"] = failures[0] if failures else None
        if payment.get("customer_id"):
            payment["customer"] = await self.get_customer(payment["customer_id"], merchant_id)
        return payment

    async def get_unhandled_payment_failures(self, merchant_id: str, batch_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Finds failed payments for this merchant that do not yet have an active recovery case."""
        params = {"merchant_id": f"eq.{merchant_id}", "status": "eq.failed"}
        if batch_id:
            params["batch_id"] = f"eq.{batch_id}"

        payments = await self._select("payments", params)
        cases = await self._select("recovery_cases", {"merchant_id": f"eq.{merchant_id}"})
        existing_payment_ids = {c["payment_id"] for c in cases}

        unhandled = []
        for p in payments:
            if p["id"] not in existing_payment_ids:
                full = await self.get_payment_with_failure(p["id"], merchant_id)
                if full and full.get("failure"):
                    unhandled.append(full)
        return unhandled

    async def create_recovery_case(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return await self._insert("recovery_cases", data)

    async def get_recovery_case(self, case_id: str, merchant_id: str) -> Optional[Dict[str, Any]]:
        cases = await self._select("recovery_cases", {"id": f"eq.{case_id}", "merchant_id": f"eq.{merchant_id}"})
        if not cases:
            return None
        case = cases[0]
        # Attach payment and failure details
        payment = await self.get_payment_with_failure(case["payment_id"], merchant_id)
        case["payment"] = payment
        if payment and payment.get("customer"):
            case["customer"] = payment["customer"]
        return case

    async def update_recovery_case(self, case_id: str, merchant_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return await self._update("recovery_cases", case_id, merchant_id, updates)

    async def list_recovery_cases(
        self,
        merchant_id: str,
        status_filter: Optional[str] = None,
        batch_id: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        params = {"merchant_id": f"eq.{merchant_id}"}
        if status_filter:
            params["status"] = f"eq.{status_filter}"
        if batch_id:
            params["batch_id"] = f"eq.{batch_id}"
        cases = await self._select("recovery_cases", params)
        for c in cases:
            p = await self.get_payment_with_failure(c["payment_id"], merchant_id)
            c["payment"] = p
            if p and p.get("customer"):
                c["customer"] = p["customer"]
        # Sort latest first (created_at descending)
        cases.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return cases[:limit]

    async def create_recovery_action(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return await self._insert("recovery_actions", data)

    async def get_recovery_actions(self, case_id: str, merchant_id: str) -> List[Dict[str, Any]]:
        return await self._select("recovery_actions", {"case_id": f"eq.{case_id}", "merchant_id": f"eq.{merchant_id}"})

    async def create_recovery_outcome(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return await self._insert("recovery_outcomes", data)

    async def get_recovery_outcomes(self, case_id: str, merchant_id: str) -> List[Dict[str, Any]]:
        return await self._select("recovery_outcomes", {"case_id": f"eq.{case_id}", "merchant_id": f"eq.{merchant_id}"})

    async def get_action_statistics(self, merchant_id: str, root_cause_category: Optional[str] = None) -> List[Dict[str, Any]]:
        params = {"merchant_id": f"eq.{merchant_id}"}
        if root_cause_category:
            params["root_cause_category"] = f"eq.{root_cause_category}"
        return await self._select("action_statistics", params)

    async def upsert_action_statistic(
        self,
        merchant_id: str,
        root_cause_category: str,
        action_type: str,
        is_successful: bool,
        recovered_amount: float,
        recovery_time_seconds: int = 0
    ) -> Dict[str, Any]:
        """Increments statistics for (merchant_id, root_cause_category, action_type)."""
        stats = await self._select(
            "action_statistics",
            {"merchant_id": f"eq.{merchant_id}", "root_cause_category": f"eq.{root_cause_category}", "action_type": f"eq.{action_type}"}
        )
        if stats:
            existing = stats[0]
            attempts = existing.get("total_attempts", 0) + 1
            successes = existing.get("successful_recoveries", 0) + (1 if is_successful else 0)
            rate = round(successes / attempts, 4) if attempts > 0 else 0.0
            total_recovered = float(existing.get("total_recovered_amount", 0.0)) + float(recovered_amount)
            avg_time = existing.get("average_recovery_time_seconds", 0.0)
            if is_successful and recovery_time_seconds > 0:
                avg_time = round((avg_time * (successes - 1) + recovery_time_seconds) / successes, 2)

            updates = {
                "total_attempts": attempts,
                "successful_recoveries": successes,
                "success_rate": rate,
                "total_recovered_amount": total_recovered,
                "average_recovery_time_seconds": avg_time,
                "last_updated_at": datetime.now(timezone.utc).isoformat()
            }
            await self._update("action_statistics", existing["id"], merchant_id, updates)
            existing.update(updates)
            return existing
        else:
            new_record = {
                "id": str(uuid.uuid4()),
                "merchant_id": merchant_id,
                "root_cause_category": root_cause_category,
                "action_type": action_type,
                "total_attempts": 1,
                "successful_recoveries": 1 if is_successful else 0,
                "success_rate": 1.0 if is_successful else 0.0,
                "total_recovered_amount": float(recovered_amount),
                "average_recovery_time_seconds": float(recovery_time_seconds),
                "last_updated_at": datetime.now(timezone.utc).isoformat()
            }
            return await self._insert("action_statistics", new_record)

    async def create_baseline_result(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return await self._insert("baseline_results", data)

    async def get_baseline_results_by_batch(self, batch_id: str, merchant_id: str) -> List[Dict[str, Any]]:
        return await self._select("baseline_results", {"batch_id": f"eq.{batch_id}", "merchant_id": f"eq.{merchant_id}"})

    async def create_audit_log(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return await self._insert("audit_logs", data)

    async def get_audit_logs(self, case_id: Optional[str] = None, merchant_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        params = {}
        if merchant_id:
            params["merchant_id"] = f"eq.{merchant_id}"
        if case_id:
            params["case_id"] = f"eq.{case_id}"
        logs = await self._select("audit_logs", params)
        # Sort descending by created_at
        logs.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return logs[:limit]


db = SupabaseDB()
