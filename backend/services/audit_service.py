"""
backend/services/audit_service.py
---------------------------------
Service to manage System Audit Logs and Unknown Person events.
"""

import logging
from typing import List, Dict, Any
from backend.database.db import db
from backend.models.analytics import SystemAuditLog, UnknownPerson

logger = logging.getLogger(__name__)

class AuditService:
    def log_event(self, event_type: str, description: str):
        """Log a system event to the database."""
        try:
            log = SystemAuditLog(event_type=event_type, description=description)
            db.session.add(log)
            db.session.commit()
            logger.info(f"Audit Logged [{event_type}]: {description}")
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to log event: {e}")

    def log_unknown_person(self, snapshot_path: str, confidence: float):
        """Save a record of an unknown person."""
        try:
            unknown = UnknownPerson(snapshot_path=snapshot_path, confidence=confidence)
            db.session.add(unknown)
            db.session.commit()
            
            # Also log to system audit
            self.log_event("UNKNOWN_PERSON", f"Unknown person detected with confidence {confidence:.2f}")
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to log unknown person: {e}")
            
    def get_recent_logs(self, limit: int = 50) -> List[Dict[str, Any]]:
        logs = SystemAuditLog.query.order_by(SystemAuditLog.timestamp.desc()).limit(limit).all()
        return [log.to_dict() for log in logs]

def get_audit_service() -> AuditService:
    return AuditService()
