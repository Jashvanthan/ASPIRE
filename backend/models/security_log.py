"""
backend/models/security_log.py
-------------------------------
SQLAlchemy ORM model for the SecurityLog table.
Stores every anti-spoofing verification attempt for auditing.
"""

from datetime import datetime, timezone
from backend.database.db import db


class SecurityLog(db.Model):
    __tablename__ = "security_logs"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    timestamp = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    # Camera identification
    camera_id = db.Column(db.String(50), nullable=False, default="cam-1")

    # Student identification (nullable — may not be recognized)
    student_id = db.Column(db.String(50), nullable=True, index=True)
    student_name = db.Column(db.String(150), nullable=True)

    # Anti-spoof verdict
    spoof_type = db.Column(
        db.String(50), nullable=False, default="genuine"
    )  # genuine | printed_photo | screen_replay | occlusion | static_image
    liveness_score = db.Column(db.Float, nullable=False, default=0.0)
    recognition_confidence = db.Column(db.Float, nullable=False, default=0.0)
    spoof_probability = db.Column(db.Float, nullable=False, default=0.0)
    decision = db.Column(
        db.String(20), nullable=False, default="rejected"
    )  # accepted | rejected

    # Optional snapshot of the attempt
    snapshot_path = db.Column(db.String(500), nullable=True)

    # Detailed sub-scores stored as JSON text
    details_json = db.Column(db.Text, nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "camera_id": self.camera_id,
            "student_id": self.student_id,
            "student_name": self.student_name,
            "spoof_type": self.spoof_type,
            "liveness_score": round(self.liveness_score, 3),
            "recognition_confidence": round(self.recognition_confidence, 3),
            "spoof_probability": round(self.spoof_probability, 3),
            "decision": self.decision,
            "snapshot_path": self.snapshot_path,
            "details_json": self.details_json,
        }

    def __repr__(self) -> str:
        return (
            f"<SecurityLog {self.id} "
            f"type={self.spoof_type} "
            f"decision={self.decision}>"
        )
