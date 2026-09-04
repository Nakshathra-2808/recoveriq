import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from app.services.supabase_db import db, SupabaseDB

logger = logging.getLogger(__name__)


class AuditService:
    """
    Immutable Audit Trail Service.
    Guarantees that every recovery event, safety guardrail check, dispatch,
    and financial recovery is logged permanently with full context.
    """

    def __init__(self, database: Optional[SupabaseDB] = None):
        self.db = database or db

    async def log_event(
        self,
        merchant_id: str,
        event_type: str,
        description: str,
        severity: str = "INFO",
        case_id: Optional[str] = None,
        action_id: Optional[str] = None,
        actor_type: str = "SYSTEM",
        actor_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Creates an immutable audit log entry."""
        log_entry = {
            "merchant_id": merchant_id,
            "case_id": case_id,
            "action_id": action_id,
            "actor_type": actor_type,
            "actor_id": actor_id,
            "event_type": event_type,
            "severity": severity,
            "description": description,
            "details": details or {},
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        return await self.db.create_audit_log(log_entry)

    async def get_case_audit_trail(self, case_id: str, merchant_id: str) -> List[Dict[str, Any]]:
        """Fetches full chronological audit trail for a recovery case."""
        return await self.db.get_audit_logs(case_id=case_id, merchant_id=merchant_id)


audit_service = AuditService()
