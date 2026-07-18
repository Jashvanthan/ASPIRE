"""
backend/models/unknown_person.py
--------------------------------
SQLAlchemy ORM model for storing Unknown Person detections.
"""

from datetime import datetime, timezone
from backend.database.db import db

class UnknownPerson(db.Model):
    __tablename__ = "unknown_persons"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    snapshot_path = db.Column(db.String(500), nullable=False)
    camera_id = db.Column(db.String(50), nullable=False, default="cam-1")
    
    detection_confidence = db.Column(db.Float, nullable=False, default=0.0)
    liveness_score = db.Column(db.Float, nullable=False, default=0.0)
    
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
            "camera_id": self.camera_id,
            "detection_confidence": round(self.detection_confidence, 3),
            "liveness_score": round(self.liveness_score, 3),
            "timestamp": self.timestamp.isoformat() if self.timestamp else None
        }

    def __repr__(self) -> str:
        return f"<UnknownPerson {self.id} at {self.timestamp}>"
