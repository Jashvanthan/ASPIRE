"""
backend/models/attendance_correction.py
---------------------------------------
SQLAlchemy ORM model for storing attendance correction requests from teachers.
"""

from datetime import datetime, timezone
from backend.database.db import db

class AttendanceCorrection(db.Model):
    __tablename__ = "attendance_corrections"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    
    teacher_id = db.Column(db.String(100), nullable=False)
    student_id = db.Column(db.String(50), nullable=False, index=True)
    date = db.Column(db.String(10), nullable=False, index=True) # YYYY-MM-DD
    
    requested_status = db.Column(db.String(20), nullable=False) # Present, Absent
    reason = db.Column(db.Text, nullable=False)
    
    # pending, approved, rejected
    admin_status = db.Column(db.String(20), nullable=False, default="pending")
    admin_decision_reason = db.Column(db.Text, nullable=True)
    
    timestamp = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    
    resolved_at = db.Column(db.DateTime, nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "teacher_id": self.teacher_id,
            "student_id": self.student_id,
            "date": self.date,
            "requested_status": self.requested_status,
            "reason": self.reason,
            "admin_status": self.admin_status,
            "admin_decision_reason": self.admin_decision_reason,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None
        }

    def __repr__(self) -> str:
        return f"<AttendanceCorrection {self.student_id} on {self.date} -> {self.requested_status}>"
