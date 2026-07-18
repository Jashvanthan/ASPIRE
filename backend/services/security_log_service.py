"""
backend/services/security_log_service.py
-----------------------------------------
Service for persisting and querying security / anti-spoof events.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from backend.database.db import db
from backend.models.security_log import SecurityLog

logger = logging.getLogger(__name__)


class SecurityLogService:
    """
    Singleton service for security event logging and statistics.
    """

    _instance: Optional["SecurityLogService"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        logger.info("SecurityLogService created.")

    # ──────────────────────────────────────────────────────────────────────
    # Write
    # ──────────────────────────────────────────────────────────────────────

    def log_attempt(
        self,
        student_id: Optional[str],
        student_name: Optional[str],
        spoof_type: str,
        liveness_score: float,
        recognition_confidence: float,
        spoof_probability: float,
        decision: str,
        snapshot_path: Optional[str] = None,
        details: Optional[dict] = None,
        camera_id: str = "cam-1",
    ) -> Optional[SecurityLog]:
        """Create a new security log record."""
        try:
            entry = SecurityLog(
                camera_id=camera_id,
                student_id=student_id,
                student_name=student_name,
                spoof_type=spoof_type,
                liveness_score=liveness_score,
                recognition_confidence=recognition_confidence,
                spoof_probability=spoof_probability,
                decision=decision,
                snapshot_path=snapshot_path,
                details_json=json.dumps(details) if details else None,
            )
            db.session.add(entry)
            db.session.commit()
            logger.info(
                "Security log: type=%s decision=%s student=%s",
                spoof_type,
                decision,
                student_id or "unknown",
            )
            return entry
        except Exception as exc:
            db.session.rollback()
            logger.error("Failed to write security log: %s", exc)
            return None

    # ──────────────────────────────────────────────────────────────────────
    # Read — Statistics
    # ──────────────────────────────────────────────────────────────────────

    def get_today_stats(self) -> dict:
        """Return aggregate security statistics for today."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        try:
            all_today = SecurityLog.query.filter(
                db.func.date(SecurityLog.timestamp) == today
            ).all()

            total = len(all_today)
            accepted = sum(1 for r in all_today if r.decision == "accepted")
            rejected = sum(1 for r in all_today if r.decision == "rejected")

            # Breakdown by spoof type
            type_counts: dict[str, int] = {}
            for r in all_today:
                t = r.spoof_type or "unknown"
                type_counts[t] = type_counts.get(t, 0) + 1

            return {
                "total_checks": total,
                "accepted": accepted,
                "rejected": rejected,
                "spoof_types": type_counts,
                "date": today,
            }
        except Exception as exc:
            logger.error("Failed to fetch security stats: %s", exc)
            return {
                "total_checks": 0,
                "accepted": 0,
                "rejected": 0,
                "spoof_types": {},
                "date": today,
            }

    # ──────────────────────────────────────────────────────────────────────
    # Read — Alerts / Logs
    # ──────────────────────────────────────────────────────────────────────

    def get_recent_alerts(self, limit: int = 20) -> list[dict]:
        """Return the most recent rejected (spoof) attempts."""
        try:
            records = (
                SecurityLog.query.filter_by(decision="rejected")
                .order_by(SecurityLog.timestamp.desc())
                .limit(limit)
                .all()
            )
            return [r.to_dict() for r in records]
        except Exception as exc:
            logger.error("Failed to fetch alerts: %s", exc)
            return []

    def get_logs(
        self,
        page: int = 1,
        per_page: int = 20,
        spoof_type: Optional[str] = None,
        decision: Optional[str] = None,
        date: Optional[str] = None,
    ) -> dict:
        """Paginated, filterable security log query."""
        try:
            query = SecurityLog.query

            if spoof_type:
                query = query.filter_by(spoof_type=spoof_type)
            if decision:
                query = query.filter_by(decision=decision)
            if date:
                query = query.filter(
                    db.func.date(SecurityLog.timestamp) == date
                )

            query = query.order_by(SecurityLog.timestamp.desc())
            pagination = query.paginate(page=page, per_page=per_page, error_out=False)

            return {
                "logs": [r.to_dict() for r in pagination.items],
                "total": pagination.total,
                "page": pagination.page,
                "per_page": per_page,
                "pages": pagination.pages,
            }
        except Exception as exc:
            logger.error("Failed to fetch security logs: %s", exc)
            return {"logs": [], "total": 0, "page": 1, "per_page": per_page, "pages": 0}


def get_security_log_service() -> SecurityLogService:
    return SecurityLogService()
