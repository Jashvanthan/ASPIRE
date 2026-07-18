"""
backend/models/analytics.py
---------------------------
SQLAlchemy ORM models for Phase 4 Analytics, Auditing, and Unknown Person logging.
"""

from datetime import datetime, timezone
from backend.database.db import db

class UnknownPerson(db.Model):
    __tablename__ = "unknown_person"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    snapshot_path = db.Column(db.String(255), nullable=False)
    confidence = db.Column(db.Float, nullable=False)
    
    timestamp = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "snapshot_path": self.snapshot_path,
            "confidence": round(self.confidence, 3),
            "timestamp": self.timestamp.isoformat()
        }

class AttendanceCorrectionRequest(db.Model):
    __tablename__ = "attendance_correction_request"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    attendance_id = db.Column(db.Integer, db.ForeignKey('attendance.id'), nullable=False)
    requested_by = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="Pending") # Pending, Approved, Rejected
    reason = db.Column(db.String(255), nullable=False)
    
    timestamp = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "attendance_id": self.attendance_id,
            "requested_by": self.requested_by,
            "status": self.status,
            "reason": self.reason,
            "timestamp": self.timestamp.isoformat()
        }

class SystemAuditLog(db.Model):
    __tablename__ = "system_audit_log"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    event_type = db.Column(db.String(50), nullable=False, index=True) # e.g., 'UNKNOWN_PERSON', 'ATTENDANCE_MARKED', 'SPOOF_DETECTED'
    description = db.Column(db.Text, nullable=False)
    
    timestamp = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "event_type": self.event_type,
            "description": self.description,
            "timestamp": self.timestamp.isoformat()
        }
