"""
backend/models/attendance.py
----------------------------
SQLAlchemy ORM model for the Attendance table.
"""

from datetime import datetime, timezone
from sqlalchemy import UniqueConstraint
from backend.database.db import db

class Attendance(db.Model):
    __tablename__ = "attendance"
    __table_args__ = (
        UniqueConstraint("student_id", "date", name="uq_student_date"),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    student_id = db.Column(db.String(50), nullable=False, index=True)
    student_name = db.Column(db.String(150), nullable=False)
    department = db.Column(db.String(100), nullable=False)
    batch = db.Column(db.String(20), nullable=False, default="Unknown")
    year = db.Column(db.Integer, nullable=False)
    section = db.Column(db.String(10), nullable=False)
    
    # Store date and time separately for easier querying
    date = db.Column(db.String(10), nullable=False, index=True) # YYYY-MM-DD
    time = db.Column(db.String(8), nullable=False) # HH:MM:SS
    
    confidence = db.Column(db.Float, nullable=False)
    
    # ── Phase 4: Entry & Exit Tracking ─────────────────────────────
    exit_time = db.Column(db.String(8), nullable=True) # HH:MM:SS
    total_duration_seconds = db.Column(db.Integer, nullable=False, default=0)
    overall_confidence_score = db.Column(db.Float, nullable=True) # 0-100 scale

    attendance_status = db.Column(db.String(20), nullable=False, default="Present")
    
    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "student_id": self.student_id,
            "student_name": self.student_name,
            "department": self.department,
            "batch": self.batch,
            "year": self.year,
            "section": self.section,
            "date": self.date,
            "time": self.time,
            "exit_time": self.exit_time,
            "duration": self.total_duration_seconds,
            "confidence": round(self.confidence, 3),
            "overall_confidence": round(self.overall_confidence_score, 2) if self.overall_confidence_score else None,
            "attendance_status": self.attendance_status,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }

    def __repr__(self) -> str:
        return f"<Attendance {self.student_id} on {self.date} {self.time}>"
