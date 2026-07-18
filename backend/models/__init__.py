"""
backend/models/__init__.py
---------------------------
Models package initializer. Import all models here so SQLAlchemy
discovers them when `db.create_all()` is called.
"""

from backend.models.student import Student
from backend.models.attendance import Attendance
from backend.models.security_log import SecurityLog

__all__ = ["Student", "Attendance", "SecurityLog"]

