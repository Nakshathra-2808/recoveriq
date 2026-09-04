import json
import logging
import re
from typing import Dict, Any, Optional
from datetime import datetime, timezone
import httpx
from pydantic import ValidationError

from app.core.config import settings
from app.schemas.recovery import (
    RootCauseCategory,
    ActionType,
    AIDiagnosisSource,
    AIDiagnosisResult,
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a payment recovery diagnosis assistant.

You diagnose the supplied payment failure context and recommend a possible recovery action.

You do NOT execute payments.
You do NOT authorize payments.
You do NOT override deterministic policies or guardrails.

You must use only the supplied information.
You must not invent customer or payment facts.
If uncertain, return lower confidence.

Return only a valid JSON object with the following structure:
{
  "diagnosis": "<concise description of underlying failure reason, e.g. temporary_gateway_failure>",
  "failure_type": "<one of: NETWORK_TIMEOUT, GATEWAY_ERROR, INSUFFICIENT_FUNDS, USER_DROPPED, CARD_LIMIT_EXCEEDED, FRAUD_DECLINE, SYSTEM_DOWN, AUTHENTICATION_FAILURE, EXPIRED_CARD, OTHER>",
  "recommended_action": "<one of: RETRY_NOW, RETRY_LATER, PAYMENT_UPDATE, REMINDER, ESCALATE, STOP>",
  "reason": "<clear explanation of why this action is recommended>",
  "confidence": <float between 0.0 and 1.0>,
  "source": "LLM"
}

Critical safety constraints:
1. Fraud decline (FRAUD_DECLINE) must NEVER be overridden: recommended_action MUST be STOP.
2. Customer opt-out must NEVER be overridden: recommended_action MUST be STOP.
3. Retry limits, communication limits, cooldown rules, and VIP escalation rules must not be bypassed.
4. Only return valid JSON with no markdown backticks or commentary outside the JSON."""


class AIDiagnosisService:
    """
    LLM-Powered Diagnostic & Explanation Service.
    Produces structured, auditable diagnoses while strictly delegating payment
    execution and final authorization to the deterministic policy and guardrail engines.
    """

    def __init__(
        self,
        provider: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
    ):
        self.provider = (provider or settings.LLM_PROVIDER or "gemini").lower()
        self.api_key = api_key if api_key is not None else settings.LLM_API_KEY
        self.model = model or settings.LLM_MODEL or "gemini-1.5-flash"
        self.base_url = base_url or settings.LLM_API_BASE_URL
        self.timeout = timeout if timeout is not None else settings.LLM_TIMEOUT_SECONDS

    def sanitize_context(
        self,
        failure: Dict[str, Any],
        payment: Dict[str, Any],
        customer: Optional[Dict[str, Any]] = None,
        policy: Optional[Dict[str, Any]] = None,
        action_stats: Optional[list] = None,
        retry_count: int = 0,
        communication_count: int = 0,
    ) -> Dict[str, Any]:
        """
        Builds a strictly sanitized context dictionary.
        NEVER includes raw card numbers, CVVs, passwords, auth tokens, or API keys.
        """
        method = payment.get("method") or "card"
        if isinstance(method, str) and method.startswith("card"):
            clean_method = "card"
        else:
            clean_method = str(method)

        return {
            "failure_info": {
                "error_code": failure.get("error_code") or "UNKNOWN",
                "error_description": failure.get("error_description") or "",
                "error_reason": failure.get("error_reason") or "",
                "error_source": failure.get("error_source") or "gateway",
                "root_cause_hint": failure.get("root_cause_category") or "OTHER",
            },
            "transaction_info": {
                "amount": float(payment.get("amount", 0.0)),
                "currency": payment.get("currency", "INR"),
                "payment_method": clean_method,
                "retry_count": retry_count,
                "communication_count": communication_count,
            },
            "customer_profile": {
                "is_opted_out": bool(customer.get("is_opted_out", False)) if customer else False,
                "is_vip": bool(customer.get("is_vip", False)) if customer else False,
                "total_successful_recoveries": int(customer.get("successful_recoveries_count", 0)) if customer else 0,
            },
            "policy_constraints": {
                "max_retries": int(policy.get("max_retries", 3)) if policy else 3,
                "max_communications": int(policy.get("max_communications", 3)) if policy else 3,
                "escalation_threshold_amount": float(policy.get("escalation_threshold_amount", 10000.0)) if policy else 10000.0,
                "cooldown_minutes": int(policy.get("cooldown_minutes", 60)) if policy else 60,
            },
            "historical_statistics_available": [
                {
                    "action_type": s.get("action_type"),
                    "root_cause": s.get("root_cause_category"),
                    "success_rate": round(float(s.get("success_rate", 0.0)), 2),
                    "attempts": s.get("total_attempts", 0)
                }
                for s in (action_stats or [])[:5]
            ]
        }

    def _extract_json(self, raw_text: str) -> Dict[str, Any]:
        """Extracts and parses JSON from raw LLM output even if surrounded by markdown code blocks."""
        cleaned = raw_text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)
            cleaned = cleaned.strip()

        json_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if json_match:
            cleaned = json_match.group(0)

        return json.loads(cleaned)

    async def _call_gemini(self, prompt: str) -> str:
        """Invokes the Google Gemini REST API."""
        url = self.base_url or f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        params = {"key": self.api_key}
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": f"{SYSTEM_PROMPT}\n\nContext:\n{prompt}"}]
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json"
            }
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(url, params=params, json=payload)
            resp.raise_for_status()
            data = resp.json()
            candidates = data.get("candidates", [])
            if not candidates:
                raise ValueError("Gemini returned empty candidate list")
            part = candidates[0].get("content", {}).get("parts", [{}])[0]
            return part.get("text", "")

    async def _call_openai_compatible(self, prompt: str) -> str:
        """Invokes OpenAI / Groq / OpenAI-compatible REST API."""
        url = self.base_url or "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"}
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            choices = data.get("choices", [])
            if not choices:
                raise ValueError("Provider returned empty choices")
            return choices[0].get("message", {}).get("content", "")

    def get_deterministic_fallback(
        self,
        failure_type: RootCauseCategory,
        fallback_reason: Optional[str] = None,
        custom_action: Optional[ActionType] = None,
        confidence: float = 0.85
    ) -> AIDiagnosisResult:
        """
        Generates a reliable deterministic diagnosis fallback when the LLM is
        offline, unconfigured, times out, or produces invalid output.
        """
        action_map = {
            RootCauseCategory.FRAUD_DECLINE: (ActionType.STOP, 0.98, "High-risk fraud decline flagged. Automated retries strictly prohibited to protect merchant standing."),
            RootCauseCategory.NETWORK_TIMEOUT: (ActionType.RETRY_LATER, 0.94, "Transient gateway socket/network timeout. Delayed retry has high empirical recovery probability."),
            RootCauseCategory.GATEWAY_ERROR: (ActionType.RETRY_LATER, 0.91, "Acquiring bank or downstream gateway degradation. Scheduled backoff retry recommended."),
            RootCauseCategory.INSUFFICIENT_FUNDS: (ActionType.REMINDER, 0.90, "Customer account balance low. Customer payment update link or reminder is optimal."),
            RootCauseCategory.USER_DROPPED: (ActionType.REMINDER, 0.88, "Customer dropped off checkout / OTP timeout. Re-engagement reminder recommended."),
            RootCauseCategory.CARD_LIMIT_EXCEEDED: (ActionType.PAYMENT_UPDATE, 0.89, "Card limit or velocity threshold reached. Alternate payment method collection link recommended."),
            RootCauseCategory.SYSTEM_DOWN: (ActionType.RETRY_LATER, 0.90, "System/bank downtime detected. Backoff retry recommended."),
            RootCauseCategory.AUTHENTICATION_FAILURE: (ActionType.PAYMENT_UPDATE, 0.85, "Authentication/3DS verification failed. Payment link recommended."),
            RootCauseCategory.EXPIRED_CARD: (ActionType.PAYMENT_UPDATE, 0.95, "Card expired. Updated payment method required."),
            RootCauseCategory.OTHER: (ActionType.RETRY_LATER, 0.75, "General failure categorized under standard retry policy."),
        }

        default_action, default_conf, default_reason = action_map.get(
            failure_type,
            (ActionType.RETRY_LATER, 0.75, "Standard deterministic recovery policy applied.")
        )

        return AIDiagnosisResult(
            diagnosis=f"deterministic_{failure_type.value.lower()}_analysis",
            failure_type=failure_type,
            recommended_action=custom_action or default_action,
            reason=fallback_reason or default_reason,
            confidence=round(confidence if custom_action else default_conf, 2),
            source=AIDiagnosisSource.DETERMINISTIC_FALLBACK
        )

    async def diagnose_failure(
        self,
        sanitized_context: Dict[str, Any],
        deterministic_root_cause: RootCauseCategory,
    ) -> AIDiagnosisResult:
        """
        Executes structured AI diagnosis.
        If any step fails (missing key, timeout, malformed JSON, invalid action, constraint violation),
        gracefully falls back to deterministic analysis with source="DETERMINISTIC_FALLBACK".
        """
        # 1. Fallback if no LLM key is configured (Offline mode)
        if not self.api_key or self.provider == "mock":
            logger.info("No LLM API key configured or mock provider selected. Using deterministic fallback.")
            return self.get_deterministic_fallback(deterministic_root_cause)

        prompt_context = json.dumps(sanitized_context, indent=2)

        try:
            # 2. Invoke appropriate provider
            if self.provider == "gemini":
                raw_response = await self._call_gemini(prompt_context)
            elif self.provider in ("openai", "groq"):
                raw_response = await self._call_openai_compatible(prompt_context)
            else:
                logger.warning(f"Unsupported LLM provider '{self.provider}'. Falling back to deterministic analysis.")
                return self.get_deterministic_fallback(deterministic_root_cause)

            # 3. Parse JSON
            parsed_json = self._extract_json(raw_response)
            parsed_json["source"] = "LLM"

            # 4. Validate with Pydantic
            diagnosis_res = AIDiagnosisResult(**parsed_json)

            # 5. Invariant check: Fraud decline cannot recommend retry
            if deterministic_root_cause == RootCauseCategory.FRAUD_DECLINE and diagnosis_res.recommended_action != ActionType.STOP:
                logger.warning("LLM proposed non-STOP action for FRAUD_DECLINE. Overriding to deterministic STOP.")
                return self.get_deterministic_fallback(RootCauseCategory.FRAUD_DECLINE)

            return diagnosis_res

        except (httpx.TimeoutException, httpx.ConnectTimeout) as e:
            logger.warning(f"LLM API request timed out ({e}). Falling back to deterministic diagnosis.")
            return self.get_deterministic_fallback(
                deterministic_root_cause,
                fallback_reason=f"LLM request timed out. Applied deterministic baseline for {deterministic_root_cause.value}."
            )
        except (json.JSONDecodeError, ValidationError) as e:
            logger.warning(f"LLM response validation failed ({e}). Falling back to deterministic diagnosis.")
            return self.get_deterministic_fallback(
                deterministic_root_cause,
                fallback_reason=f"LLM structured schema validation failed. Applied deterministic baseline for {deterministic_root_cause.value}."
            )
        except Exception as e:
            logger.warning(f"Unexpected error in LLM diagnosis ({type(e).__name__}: {e}). Falling back to deterministic diagnosis.")
            return self.get_deterministic_fallback(
                deterministic_root_cause,
                fallback_reason=f"LLM diagnosis service error ({type(e).__name__}). Applied deterministic baseline for {deterministic_root_cause.value}."
            )


ai_diagnosis_service = AIDiagnosisService()
