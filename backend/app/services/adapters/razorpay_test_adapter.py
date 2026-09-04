import logging
import re
from typing import Dict, Any, Optional
from datetime import datetime, timezone
import httpx

from app.core.config import settings
from app.schemas.recovery import ActionType, ExecutionMode
from app.services.adapters import BaseActionAdapter

logger = logging.getLogger(__name__)


class RazorpayTestAdapter(BaseActionAdapter):
    """
    Razorpay Test / Sandbox Action Adapter.
    Executes genuine recovery operations against the official Razorpay Test API (https://api.razorpay.com/v1).
    Strictly forbids production keys or live money movement.
    """

    def __init__(
        self,
        key_id: Optional[str] = None,
        key_secret: Optional[str] = None,
        environment: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
    ):
        self.key_id = key_id if key_id is not None else settings.RAZORPAY_KEY_ID
        self.key_secret = key_secret if key_secret is not None else settings.RAZORPAY_KEY_SECRET
        self.environment = (environment or settings.RAZORPAY_ENVIRONMENT or "test").lower()
        self.base_url = (base_url or settings.RAZORPAY_BASE_URL or "https://api.razorpay.com/v1").rstrip("/")
        self.timeout = timeout if timeout is not None else settings.RAZORPAY_TIMEOUT_SECONDS

    def _validate_credentials(self) -> None:
        """
        Validates that test credentials exist and strictly forbids production keys.
        """
        if not self.key_id or not self.key_secret:
            raise ValueError(
                "Razorpay credentials not configured: RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET must be set to use RAZORPAY_TEST mode."
            )

        if self.environment != "test":
            raise ValueError(
                f"Invalid Razorpay environment '{self.environment}'. Only 'test' environment is permitted."
            )

        if self.key_id.startswith("rzp_live_"):
            raise ValueError(
                "Production Razorpay key (rzp_live_*) detected! RecoverIQ strictly forbids live payment credentials in sandbox/test adapter."
            )

    def _sanitize_error_message(self, error_str: str) -> str:
        """Strips potential secrets from error messages before logging or surfacing."""
        sanitized = error_str
        if self.key_secret:
            sanitized = sanitized.replace(self.key_secret, "[REDACTED_SECRET]")
        if self.key_id:
            sanitized = re.sub(r"rzp_test_[a-zA-Z0-9]+", "rzp_test_***", sanitized)
        return sanitized

    async def create_payment_link(
        self,
        amount_inr: float,
        description: str,
        customer: Optional[Dict[str, Any]] = None,
        notes: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Generates a genuine test payment link via Razorpay Test API (POST /v1/payment_links).
        """
        self._validate_credentials()
        amount_paise = int(round(amount_inr * 100))

        customer = customer or {}
        cust_payload = {
            "name": customer.get("name") or "Retail Customer",
            "email": customer.get("email") or "customer@example.com",
            "contact": customer.get("phone") or "+919876543210",
        }

        payload = {
            "amount": amount_paise,
            "currency": "INR",
            "accept_partial": False,
            "description": description[:255],
            "customer": cust_payload,
            "notify": {
                "sms": True,
                "email": True,
            },
            "reminder_enable": True,
            "notes": notes or {},
        }

        url = f"{self.base_url}/payment_links"
        auth = (self.key_id, self.key_secret)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                resp = await client.post(url, auth=auth, json=payload)
                resp.raise_for_status()
                data = resp.json()
                return {
                    "success": True,
                    "id": data.get("id"),
                    "short_url": data.get("short_url"),
                    "status": data.get("status", "created"),
                    "amount": amount_inr,
                    "raw_response": data,
                }
            except httpx.HTTPStatusError as e:
                err_detail = "HTTP Error"
                try:
                    err_json = e.response.json()
                    err_detail = err_json.get("error", {}).get("description", str(e))
                except Exception:
                    err_detail = str(e)
                clean_err = self._sanitize_error_message(err_detail)
                logger.error(f"Razorpay Payment Link API error: {clean_err}")
                return {
                    "success": False,
                    "error": clean_err,
                    "status_code": e.response.status_code,
                }
            except (httpx.TimeoutException, httpx.ConnectTimeout) as e:
                clean_err = self._sanitize_error_message(f"Razorpay API request timed out ({e})")
                logger.error(clean_err)
                return {
                    "success": False,
                    "error": clean_err,
                    "timeout": True,
                }
            except Exception as e:
                clean_err = self._sanitize_error_message(f"Razorpay connection error: {e}")
                logger.error(clean_err)
                return {
                    "success": False,
                    "error": clean_err,
                }

    async def create_order(
        self,
        amount_inr: float,
        receipt: str,
        notes: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Creates a test order via Razorpay Test API (POST /v1/orders) to initiate a retry session.
        """
        self._validate_credentials()
        amount_paise = int(round(amount_inr * 100))

        payload = {
            "amount": amount_paise,
            "currency": "INR",
            "receipt": receipt[:40],
            "notes": notes or {},
        }

        url = f"{self.base_url}/orders"
        auth = (self.key_id, self.key_secret)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                resp = await client.post(url, auth=auth, json=payload)
                resp.raise_for_status()
                data = resp.json()
                return {
                    "success": True,
                    "id": data.get("id"),
                    "status": data.get("status", "created"),
                    "amount": amount_inr,
                    "currency": data.get("currency", "INR"),
                    "raw_response": data,
                }
            except httpx.HTTPStatusError as e:
                err_detail = "HTTP Error"
                try:
                    err_json = e.response.json()
                    err_detail = err_json.get("error", {}).get("description", str(e))
                except Exception:
                    err_detail = str(e)
                clean_err = self._sanitize_error_message(err_detail)
                logger.error(f"Razorpay Order API error: {clean_err}")
                return {
                    "success": False,
                    "error": clean_err,
                    "status_code": e.response.status_code,
                }
            except (httpx.TimeoutException, httpx.ConnectTimeout) as e:
                clean_err = self._sanitize_error_message(f"Razorpay API request timed out ({e})")
                logger.error(clean_err)
                return {
                    "success": False,
                    "error": clean_err,
                    "timeout": True,
                }
            except Exception as e:
                clean_err = self._sanitize_error_message(f"Razorpay connection error: {e}")
                logger.error(clean_err)
                return {
                    "success": False,
                    "error": clean_err,
                }

    async def execute(
        self,
        case: Dict[str, Any],
        merchant_id: str,
        mode: ExecutionMode = ExecutionMode.RAZORPAY_TEST,
    ) -> Dict[str, Any]:
        """
        Executes the assigned recovery action against Razorpay Test sandbox.
        """
        metadata = case.get("metadata", {})
        action_str = metadata.get("final_action") or metadata.get("proposed_action", "STOP")
        action_type = ActionType(action_str)

        amount = float(case.get("payment", {}).get("amount", 0.0) if case.get("payment") else case.get("amount", 0.0))
        payment_id = case.get("payment_id", "pay_unknown")
        case_id = case.get("id", "case_unknown")
        customer = case.get("customer") or case.get("payment", {}).get("customer", {})
        now_iso = datetime.now(timezone.utc).isoformat()

        # 1. Action: PAYMENT_UPDATE or REMINDER (Generate genuine Razorpay Payment Link)
        if action_type in (ActionType.PAYMENT_UPDATE, ActionType.REMINDER):
            desc = f"RecoverIQ Payment Link for Case {case_id[:8]}"
            notes = {
                "case_id": case_id,
                "merchant_id": merchant_id,
                "original_payment_id": payment_id,
                "action_type": action_type.value,
            }
            res = await self.create_payment_link(amount, desc, customer, notes)
            if res.get("success"):
                return {
                    "action_type": action_type.value,
                    "execution_mode": ExecutionMode.RAZORPAY_TEST.value,
                    "provider": "RAZORPAY_TEST",
                    "status": "COMPLETED",
                    "external_reference": res.get("id"),
                    "payment_link": res.get("short_url"),
                    "simulated": False,
                    "message": f"Razorpay Test Payment Link created: {res.get('id')} ({res.get('short_url')}).",
                    "timestamp": now_iso,
                }
            else:
                return {
                    "action_type": action_type.value,
                    "execution_mode": ExecutionMode.RAZORPAY_TEST.value,
                    "provider": "RAZORPAY_TEST",
                    "status": "FAILED",
                    "external_reference": None,
                    "error": res.get("error"),
                    "simulated": False,
                    "message": f"Razorpay Test Payment Link creation failed: {res.get('error')}",
                    "timestamp": now_iso,
                }

        # 2. Action: RETRY_NOW or RETRY_LATER (Create genuine Razorpay Test Order)
        elif action_type in (ActionType.RETRY_NOW, ActionType.RETRY_LATER):
            receipt_id = f"rec_{case_id[:16]}"
            notes = {
                "case_id": case_id,
                "merchant_id": merchant_id,
                "retry_target_payment_id": payment_id,
                "action_type": action_type.value,
            }
            res = await self.create_order(amount, receipt_id, notes)
            if res.get("success"):
                return {
                    "action_type": action_type.value,
                    "execution_mode": ExecutionMode.RAZORPAY_TEST.value,
                    "provider": "RAZORPAY_TEST",
                    "status": "COMPLETED",
                    "external_reference": res.get("id"),
                    "simulated": False,
                    "message": f"Razorpay Test Order created for retry session: {res.get('id')} ({amount} INR). Note: Direct card recharges require customer 3DS authentication.",
                    "timestamp": now_iso,
                }
            else:
                return {
                    "action_type": action_type.value,
                    "execution_mode": ExecutionMode.RAZORPAY_TEST.value,
                    "provider": "RAZORPAY_TEST",
                    "status": "FAILED",
                    "external_reference": None,
                    "error": res.get("error"),
                    "simulated": False,
                    "message": f"Razorpay Test Order creation failed: {res.get('error')}",
                    "timestamp": now_iso,
                }

        # 3. Action: ESCALATE (Internal operational workflow)
        elif action_type == ActionType.ESCALATE:
            return {
                "action_type": ActionType.ESCALATE.value,
                "execution_mode": ExecutionMode.RAZORPAY_TEST.value,
                "provider": "RAZORPAY_TEST",
                "status": "COMPLETED",
                "external_reference": f"esc_{case_id[:8]}",
                "simulated": True,
                "escalation_tier": "VIP_MERCHANT_OPS",
                "message": f"Case escalated to merchant high-value desk for manual outreach (Amount: {amount} INR).",
                "timestamp": now_iso,
            }

        # 4. Action: STOP (Terminal policy guardrail)
        else:
            return {
                "action_type": ActionType.STOP.value,
                "execution_mode": ExecutionMode.RAZORPAY_TEST.value,
                "provider": "RAZORPAY_TEST",
                "status": "COMPLETED",
                "external_reference": None,
                "simulated": True,
                "terminal_state": True,
                "message": "Recovery terminated by safety policy guardrail.",
                "timestamp": now_iso,
            }
