"""
backend/models/student.py
--------------------------
SQLAlchemy ORM model for the Students table.

Schema:
    id              – Integer primary key (auto-increment)
    student_id      – Unique student identifier (e.g. "CS2024001")
    full_name       – Student's full name
    department      – Department / program (e.g. "Computer Science")
    year            – Academic year (1-4)
    section         – Section label (e.g. "A", "B")
    email           – Institutional email
    phone_number    – Optional contact number
    face_embedding  – JSON-serialized numpy array (InsightFace 512-d)
    registered_date – UTC timestamp of first registration
    updated_date    – UTC timestamp of last modification
"""

import json
from datetime import datetime, timezone

import numpy as np

from backend.database.db import db


class Student(db.Model):
    """ORM representation of a registered student with face embedding."""

    __tablename__ = "students"

    # ── Primary Key ───────────────────────────────────────────────────────────
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    # ── Identity Fields ───────────────────────────────────────────────────────
    student_id = db.Column(db.String(50), unique=True, nullable=False, index=True)
    full_name = db.Column(db.String(150), nullable=False)
    department = db.Column(db.String(100), nullable=False)
    batch = db.Column(db.String(20), nullable=False, default="Unknown")
    year = db.Column(db.Integer, nullable=False)
    section = db.Column(db.String(10), nullable=False)
    email = db.Column(db.String(200), nullable=False)
    phone_number = db.Column(db.String(20), nullable=True)

    # ── Face Embedding ────────────────────────────────────────────────────────
    # Stored as a JSON string of a Python list (serialized from numpy float32)
    face_embedding = db.Column(db.Text, nullable=True)

    # ── Timestamps ────────────────────────────────────────────────────────────
    registered_date = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    updated_date = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    last_qr_scan_time = db.Column(
        db.DateTime,
        nullable=True
    )

    def is_face_tracking_unlocked(self, cooldown_minutes=40) -> bool:
        """
        Check if the student scanned their QR code within the cooldown period.
        SQLite stores datetimes as naive (no tzinfo), so we compare naive UTC.
        """
        if not self.last_qr_scan_time:
            return False

        # last_qr_scan_time from SQLite is naive — compare to naive UTC now
        scan_time = self.last_qr_scan_time
        if scan_time.tzinfo is not None:
            # Already timezone-aware, strip to naive for consistent subtraction
            scan_time = scan_time.replace(tzinfo=None)

        now = datetime.utcnow()  # naive UTC
        diff = now - scan_time
        return diff.total_seconds() <= (cooldown_minutes * 60)

    # ── Embedding Helpers ─────────────────────────────────────────────────────

    def set_embedding(self, embedding: np.ndarray) -> None:
        """
        Serialize a numpy array embedding and store it as JSON text.

        Args:
            embedding: 1-D numpy float32 array (512 dimensions for InsightFace).
        """
        if embedding is not None:
            self.face_embedding = json.dumps(embedding.tolist())

    def get_embedding(self) -> np.ndarray | None:
        """
        Deserialize the stored JSON embedding back into a numpy array.

        Returns:
            numpy.ndarray of float32 or None if not set.
        """
        if self.face_embedding:
            return np.array(json.loads(self.face_embedding), dtype=np.float32)
        return None

    @property
    def has_embedding(self) -> bool:
        """Return True if a face embedding has been registered."""
        return self.face_embedding is not None and len(self.face_embedding) > 0

    # ── Serialization ─────────────────────────────────────────────────────────

    def to_dict(self, include_embedding: bool = False) -> dict:
        """
        Serialize the model to a JSON-safe dictionary.

        Args:
            include_embedding: If True, includes the raw embedding list.

        Returns:
            dict with student data.
        """
        data = {
            "id": self.id,
            "student_id": self.student_id,
            "full_name": self.full_name,
            "department": self.department,
            "batch": self.batch,
            "year": self.year,
            "section": self.section,
            "email": self.email,
            "phone_number": self.phone_number,
            "has_embedding": self.has_embedding,
            "registered_date": self.registered_date.isoformat() if self.registered_date else None,
            "updated_date": self.updated_date.isoformat() if self.updated_date else None,
        }
        if include_embedding and self.has_embedding:
            data["face_embedding"] = json.loads(self.face_embedding)
        return data

    def __repr__(self) -> str:
        return f"<Student {self.student_id} – {self.full_name}>"
