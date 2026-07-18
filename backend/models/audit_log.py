"""
backend/models/audit_log.py
---------------------------
SQLAlchemy ORM model for storing system audit logs.
"""

from datetime import datetime, timezone
from backend.database.db import db

class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user = db.Column(db.String(100), nullable=False, default="System")
    role = db.Column(db.String(50), nullable=False, default="Admin")
    
    event_type = db.Column(db.String(100), nullable=False, index=True)
    description = db.Column(db.Text, nullable=False)
    ip_address = db.Column(db.String(50), nullable=True)
    
    timestamp = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user": self.user,
            "role": self.role,
            "event_type": self.event_type,
            "description": self.description,
            "ip_address": self.ip_address,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None
        }

    def __repr__(self) -> str:
        return f"<AuditLog {self.event_type} at {self.timestamp}>"
