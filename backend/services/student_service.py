"""
backend/services/student_service.py
-------------------------------------
Business logic for student registration and management.

Responsibilities:
    - Validate registration form data
    - Check for duplicate Student IDs
    - Persist students to the database
    - Retrieve student records
"""

import logging
import re
from datetime import datetime, timezone
from typing import Any

from backend.database.db import db
from backend.models.student import Student

logger = logging.getLogger(__name__)


class StudentService:
    """Encapsulates all business logic related to student management."""

    # ── Validation Constants ──────────────────────────────────────────────────
    VALID_YEARS = [1, 2, 3, 4]
    EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    PHONE_PATTERN = re.compile(r"^\+?[\d\s\-()]{7,15}$")

    # ─────────────────────────────────────────────────────────────────────────
    # Public Methods
    # ─────────────────────────────────────────────────────────────────────────

    @classmethod
    def validate_registration_data(cls, data: dict) -> list[str]:
        """
        Validate all fields required for student registration.

        Args:
            data: Dictionary of form fields from the HTTP request.

        Returns:
            List of error message strings. Empty list means data is valid.
        """
        errors: list[str] = []

        # Required fields presence check
        required = {
            "student_id": "Student ID",
            "full_name": "Full Name",
            "department": "Department",
            "year": "Year",
            "section": "Section",
            "email": "Email",
        }
        for field, label in required.items():
            value = data.get(field, "").strip()
            if not value:
                errors.append(f"{label} is required.")

        if errors:
            return errors  # Return early – no point doing deeper validation

        # Student ID: alphanumeric, 3–30 chars
        student_id = data.get("student_id", "").strip()
        if not re.match(r"^[A-Za-z0-9_\-]{3,30}$", student_id):
            errors.append(
                "Student ID must be 3–30 alphanumeric characters "
                "(underscores and hyphens allowed)."
            )

        # Full name: 2–150 chars
        full_name = data.get("full_name", "").strip()
        if len(full_name) < 2 or len(full_name) > 150:
            errors.append("Full Name must be between 2 and 150 characters.")

        # Department: 2–100 chars
        department = data.get("department", "").strip()
        if len(department) < 2 or len(department) > 100:
            errors.append("Department must be between 2 and 100 characters.")

        # Year: must be 1–4
        try:
            year = int(data.get("year", 0))
            if year not in cls.VALID_YEARS:
                errors.append("Year must be between 1 and 4.")
        except (ValueError, TypeError):
            errors.append("Year must be a valid integer (1–4).")

        # Section: 1–10 chars
        section = data.get("section", "").strip()
        if len(section) < 1 or len(section) > 10:
            errors.append("Section must be between 1 and 10 characters.")

        # Email format
        email = data.get("email", "").strip()
        if not cls.EMAIL_PATTERN.match(email):
            errors.append("Email address is not valid.")

        # Phone (optional) – validate only if provided
        phone = data.get("phone_number", "").strip()
        if phone and not cls.PHONE_PATTERN.match(phone):
            errors.append("Phone number format is not valid.")

        return errors

    @classmethod
    def is_duplicate(cls, student_id: str, exclude_id: int = None) -> bool:
        """
        Check whether a student_id already exists in the database.

        Args:
            student_id: The ID to check.
            exclude_id: Optional DB primary key to exclude (for updates).

        Returns:
            True if duplicate found, False otherwise.
        """
        query = Student.query.filter_by(student_id=student_id.strip())
        if exclude_id:
            query = query.filter(Student.id != exclude_id)
        return query.first() is not None

    @classmethod
    def register_student(cls, data: dict) -> tuple[Student | None, str | None]:
        """
        Persist a new student record to the database.

        Args:
            data: Validated form data dictionary.

        Returns:
            Tuple of (Student instance, error_message).
            On success: (Student, None). On failure: (None, error_string).
        """
        student_id = data.get("student_id", "").strip()

        # Duplicate check
        if cls.is_duplicate(student_id):
            msg = f"Student ID '{student_id}' is already registered."
            logger.warning("Duplicate registration attempt: %s", student_id)
            return None, msg

        try:
            student = Student(
                student_id=student_id,
                full_name=data.get("full_name", "").strip(),
                department=data.get("department", "").strip(),
                year=int(data.get("year")),
                section=data.get("section", "").strip(),
                email=data.get("email", "").strip(),
                phone_number=data.get("phone_number", "").strip() or None,
            )
            db.session.add(student)
            db.session.commit()
            logger.info("Student registered: %s (%s)", student.full_name, student.student_id)
            return student, None

        except Exception as exc:
            db.session.rollback()
            msg = f"Database error during registration: {exc}"
            logger.error(msg, exc_info=True)
            return None, msg

    @classmethod
    def update_embedding(
        cls, student_id: str, embedding
    ) -> tuple[Student | None, str | None]:
        """
        Attach a face embedding to an existing student record.

        Args:
            student_id: The student's unique ID.
            embedding:  numpy.ndarray with 512-d float32 values.

        Returns:
            Tuple of (updated Student, error_message).
        """
        student = Student.query.filter_by(student_id=student_id).first()
        if not student:
            return None, f"Student '{student_id}' not found."

        try:
            student.set_embedding(embedding)
            student.updated_date = datetime.now(timezone.utc)
            db.session.commit()
            logger.info("Embedding updated for student: %s", student_id)
            return student, None
        except Exception as exc:
            db.session.rollback()
            msg = f"Failed to save embedding: {exc}"
            logger.error(msg, exc_info=True)
            return None, msg

    @classmethod
    def get_student_by_id(cls, student_id: str) -> Student | None:
        """Retrieve a student record by their unique student_id string."""
        return Student.query.filter_by(student_id=student_id.strip()).first()

    @classmethod
    def get_all_students(cls, page: int = 1, per_page: int = 20) -> Any:
        """
        Return a paginated list of all registered students.

        Args:
            page: Page number (1-indexed).
            per_page: Records per page.

        Returns:
            SQLAlchemy Pagination object.
        """
        return Student.query.order_by(Student.registered_date.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )

    @classmethod
    def delete_student(cls, student_id: str) -> tuple[bool, str | None]:
        """
        Delete a student record from the database.
        
        Args:
            student_id: The student's unique ID.
            
        Returns:
            Tuple of (success_bool, error_message).
        """
        student = cls.get_student_by_id(student_id)
        if not student:
            return False, f"Student '{student_id}' not found."
            
        try:
            db.session.delete(student)
            db.session.commit()
            logger.info("Student deleted: %s", student_id)
            return True, None
        except Exception as exc:
            db.session.rollback()
            msg = f"Failed to delete student: {exc}"
            logger.error(msg, exc_info=True)
            return False, msg

    @classmethod
    def get_stats(cls) -> dict:
        """Return basic registration statistics for the dashboard."""
        total = Student.query.count()
        with_embedding = Student.query.filter(
            Student.face_embedding.isnot(None)
        ).count()
        
        # Get today's attendance count and dept breakdown
        from backend.models.attendance import Attendance
        from sqlalchemy import func
        from datetime import datetime, timezone
        
        today_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        today_present = 0
        dept_breakdown = {}
        
        try:
            today_present = Attendance.query.filter_by(date=today_date).count()
            
            # 1. Initialize all existing departments with 0
            all_depts = db.session.query(Student.department).distinct().all()
            dept_breakdown = {d[0]: 0 for d in all_depts if d[0]}
            
            # 2. Get today's present counts per department
            dept_counts = db.session.query(
                Attendance.department,
                func.count(Attendance.id)
            ).filter(
                Attendance.date == today_date,
                Attendance.attendance_status == "Present"
            ).group_by(Attendance.department).all()
            
            for dept, count in dept_counts:
                dept_breakdown[dept] = count
                
        except Exception:
            pass
            
        return {
            "total_students": total,
            "registered_with_face": with_embedding,
            "pending_face_capture": total - with_embedding,
            "today_present": today_present,
            "today_absent": max(0, with_embedding - today_present),
            "attendance_rate": f"{(today_present / with_embedding * 100):.1f}%" if with_embedding > 0 else "0%",
            "dept_breakdown": dept_breakdown
        }
