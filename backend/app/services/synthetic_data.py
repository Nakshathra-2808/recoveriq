import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from app.schemas.recovery import RootCauseCategory
from app.services.supabase_db import db, SupabaseDB


class SyntheticDataGenerator:
    """
    Deterministic Synthetic Payment Dataset Generator.
    Seeds realistic failed transactions covering all 6 core failure categories,
    opt-out conditions, VIP thresholds, and retry limits for testing.
    Reuses existing demo customers to prevent duplicate key constraint violations on repeated runs.
    """

    def __init__(self, database: Optional[SupabaseDB] = None):
        self.db = database or db

    async def generate_demo_batch(
        self,
        merchant_id: str,
        batch_name: str = "Demo Recovery Ingestion Batch",
        count: int = 6
    ) -> Dict[str, Any]:
        """
        Creates a structured synthetic batch with customers, payments, and payment_failures.
        Reuses existing demo customer profiles for the merchant if already seeded.
        """
        batch_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        # 1. Deterministic demo customers definition
        customers_def = [
            {"name": "Aarav Sharma", "email": "aarav.sharma@example.com", "phone": "+919811111111", "opted_out": False},
            {"name": "Priya Patel", "email": "priya.patel@example.com", "phone": "+919822222222", "opted_out": False},
            {"name": "Rohan Verma", "email": "rohan.verma@example.com", "phone": "+919833333333", "opted_out": False},
            {"name": "Ananya Iyer", "email": "ananya.iyer@example.com", "phone": "+919844444444", "opted_out": False},
            {"name": "Vikram Singh (VIP)", "email": "vikram.singh@example.com", "phone": "+919855555555", "opted_out": False},
            {"name": "Kavita Rao (Opted Out)", "email": "kavita.rao@example.com", "phone": "+919866666666", "opted_out": True},
        ]

        created_customers = []
        for i, c_def in enumerate(customers_def):
            ext_id = f"cust_demo_{i+1:03d}"
            # Look up existing customer to make demo runs idempotent
            existing_customer = await self.db.get_customer_by_external_id(ext_id, merchant_id)
            if existing_customer:
                created_customers.append(existing_customer)
            else:
                c_id = str(uuid.uuid4())
                cust_record = {
                    "id": c_id,
                    "merchant_id": merchant_id,
                    "external_customer_id": ext_id,
                    "name": c_def["name"],
                    "email": c_def["email"],
                    "phone": c_def["phone"],
                    "is_opted_out": c_def["opted_out"],
                    "metadata": {"synthetic": True, "tier": "VIP" if "VIP" in c_def["name"] else "STANDARD"}
                }
                c_saved = await self.db.create_customer(cust_record)
                created_customers.append(c_saved)

        # 2. Define synthetic failed payment scenarios
        scenarios = [
            {
                "cause": RootCauseCategory.NETWORK_TIMEOUT,
                "amount": 2499.00,
                "method": "upi",
                "bank": "HDFC",
                "error_code": "GATEWAY_TIMEOUT",
                "error_description": "Network timeout waiting for NPCI response",
                "customer_idx": 0,
            },
            {
                "cause": RootCauseCategory.GATEWAY_ERROR,
                "amount": 4999.00,
                "method": "netbanking",
                "bank": "ICICI",
                "error_code": "BANK_SYSTEM_DOWN",
                "error_description": "Issuing bank host system unavailable (503)",
                "customer_idx": 1,
            },
            {
                "cause": RootCauseCategory.INSUFFICIENT_FUNDS,
                "amount": 1850.00,
                "method": "card",
                "bank": "SBI",
                "error_code": "INSUFFICIENT_FUNDS",
                "error_description": "Customer account balance below order amount",
                "customer_idx": 2,
            },
            {
                "cause": RootCauseCategory.USER_DROPPED,
                "amount": 3200.00,
                "method": "card",
                "bank": "Axis",
                "error_code": "OTP_EXPIRED",
                "error_description": "User did not submit OTP within 180s window",
                "customer_idx": 3,
            },
            {
                "cause": RootCauseCategory.CARD_LIMIT_EXCEEDED,
                "amount": 14500.00,
                "method": "card",
                "bank": "HDFC",
                "error_code": "LIMIT_EXCEEDED",
                "error_description": "Card single transaction limit exceeded",
                "customer_idx": 4,  # VIP customer -> Amount >= 10,000 threshold
            },
            {
                "cause": RootCauseCategory.FRAUD_DECLINE,
                "amount": 8900.00,
                "method": "card",
                "bank": "Unknown",
                "error_code": "RISK_FRAUD_DECLINE",
                "error_description": "High risk score 99; suspected stolen card",
                "customer_idx": 5,  # Opted out customer
            }
        ]

        total_amount = sum(s["amount"] for s in scenarios[:count])

        # 3. Create unique batch record for each demo run
        batch_record = {
            "id": batch_id,
            "merchant_id": merchant_id,
            "name": batch_name,
            "description": f"Synthetic payment recovery test dataset with {min(count, len(scenarios))} transactions.",
            "status": "PROCESSING",
            "total_records": min(count, len(scenarios)),
            "processed_records": 0,
            "metadata": {"total_amount": total_amount, "synthetic": True, "created_at": now.isoformat()}
        }
        await self.db.create_batch(batch_record)

        # 4. Create unique payments & failures
        created_payments = []
        for i in range(min(count, len(scenarios))):
            s = scenarios[i]
            p_id = str(uuid.uuid4())
            f_id = str(uuid.uuid4())
            cust = created_customers[s["customer_idx"]]

            payment_record = {
                "id": p_id,
                "merchant_id": merchant_id,
                "customer_id": cust["id"],
                "batch_id": batch_id,
                "razorpay_payment_id": f"pay_syn_{uuid.uuid4().hex[:12]}",
                "razorpay_order_id": f"order_syn_{uuid.uuid4().hex[:12]}",
                "amount": s["amount"],
                "currency": "INR",
                "status": "failed",
                "method": s["method"],
                "bank": s["bank"],
                "is_international": False,
                "metadata": {"synthetic": True, "test_scenario": s["cause"].value}
            }
            p_saved = await self.db.create_payment(payment_record)

            failure_record = {
                "id": f_id,
                "merchant_id": merchant_id,
                "payment_id": p_id,
                "error_code": s["error_code"],
                "error_description": s["error_description"],
                "error_source": "bank" if s["cause"] == RootCauseCategory.GATEWAY_ERROR else "customer",
                "error_step": "payment_authorization",
                "error_reason": s["cause"].value,
                "root_cause_category": s["cause"].value,
                "failed_at": now.isoformat()
            }
            await self.db.create_payment_failure(failure_record)
            p_saved["failure"] = failure_record
            p_saved["customer"] = cust
            created_payments.append(p_saved)

        return {
            "batch_id": batch_id,
            "batch_name": batch_name,
            "merchant_id": merchant_id,
            "payments": created_payments,
            "total_amount": total_amount
        }


synthetic_generator = SyntheticDataGenerator()
