import logging
from datetime import datetime, timezone
import time
from typing import Tuple, Dict, Any, List

from backend.models.attendance import Attendance
from backend.database.db import db
from sqlalchemy import func
from backend.services.cooldown_service import get_cooldown_service

logger = logging.getLogger(__name__)

class AttendanceService:
    """
    Service for marking attendance and managing session state.
    Implements QR-first gating: students must scan QR for their first
    attendance of the day, after which face tracking is activated.
    """
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(AttendanceService, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        
        # In-memory QR activation tracking: { student_id: activation_timestamp }
        self._qr_activated_today: Dict[str, float] = {}
        self._activation_date: str = ""  # Track current date to auto-reset
        
        logger.info("AttendanceService created.")

    # ── QR Activation Methods ────────────────────────────────────────────────

    def _ensure_daily_reset(self):
        """Reset QR activations if the date has changed."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self._activation_date != today:
            self._qr_activated_today.clear()
            self._activation_date = today
            logger.info(f"Daily QR activation reset for {today}")

    def activate_via_qr(self, student_id: str) -> bool:
        """
        Activate a student for face-tracking attendance via QR scan.
        Returns True if this is a new activation, False if already activated.
        """
        self._ensure_daily_reset()
        if student_id in self._qr_activated_today:
            return False  # Already activated today
        self._qr_activated_today[student_id] = time.time()
        logger.info(f"QR activated student {student_id} for face tracking today")
        return True

    def is_qr_activated(self, student_id: str) -> bool:
        """Check if a student has scanned their QR today."""
        self._ensure_daily_reset()
        return student_id in self._qr_activated_today

    def activate_qr(self, student_id: str) -> bool:
        """Alias for activate_via_qr for convenience."""
        return self.activate_via_qr(student_id)

    # ── Attendance Marking ───────────────────────────────────────────────────

    def mark_attendance(self, student: dict, confidence: float, **kwargs) -> Tuple[bool, str, str]:
        """
        Attempt to mark attendance for a recognized student.
        Enforces 40-minute cooldown between consecutive marks.
        
        Returns:
            Tuple of (success_bool, message, status_color_class, attendance_id)
        """
        student_id = student.get("student_id")
        student_name = student.get("full_name")
        
        if not student_id:
            return False, "Invalid student data", "red", None
            
        now = datetime.now(timezone.utc)
        today_date = now.strftime("%Y-%m-%d")
        current_time = now.strftime("%H:%M:%S")
        
        # 1. Check 40-minute cooldown (from config)
        from flask import current_app
        cooldown_minutes = current_app.config.get("ATTENDANCE_COOLDOWN_MINUTES", 40)
        cooldown_seconds = cooldown_minutes * 60
        
        cooldown_svc = get_cooldown_service()
        if cooldown_svc.is_on_cooldown(f"att_{student_id}", cooldown_seconds):
            return False, "Already Marked", "yellow", None

        try:
            # 2. Check Database for duplicate today
            existing_record = Attendance.query.filter_by(
                student_id=student_id, 
                date=today_date
            ).order_by(Attendance.id.desc()).first()
            
            # Entry/Exit Tracking - use the 40-min cooldown as session timeout
            if existing_record:
                if existing_record.exit_time:
                    exit_dt = datetime.strptime(f"{today_date} {existing_record.exit_time}", "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                    if (now - exit_dt).total_seconds() > cooldown_seconds:
                        pass  # Create a new session
                    else:
                        return False, "Already Marked (Same Session)", "yellow", existing_record.id
                else:
                    # Active session without an exit time yet
                    return False, "Already Marked", "yellow", existing_record.id
                
            # 3. Insert new attendance record
            new_attendance = Attendance(
                student_id=student_id,
                student_name=student_name,
                department=student.get("department", "Unknown"),
                batch=student.get("batch", "Unknown"),
                year=student.get("year", 1),
                section=student.get("section", "A"),
                date=today_date,
                time=current_time,
                confidence=confidence,
                overall_confidence_score=kwargs.get("overall_confidence", confidence * 100),
                attendance_status="Present"
            )
            
            db.session.add(new_attendance)
            db.session.commit()
            db.session.refresh(new_attendance)
            
            logger.info(f"Attendance marked successfully for {student_name} ({student_id})")
            return True, "Attendance Marked", "green", new_attendance.id
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error marking attendance for {student_id}: {e}")
            return False, "Database Error", "red", None
    def is_qr_activated(self, student_id: str) -> bool:
        """
        Check if the student has scanned their QR code within the 40-minute window.
        """
        try:
            from backend.models.student import Student
            student = Student.query.filter_by(student_id=student_id).first()
            if student:
                return student.is_face_tracking_unlocked(cooldown_minutes=40)
            return False
        except Exception as e:
            logger.error(f"Error checking QR activation for {student_id}: {e}")
            return False

    def get_today_stats(self) -> Dict[str, Any]:
        """Get summary statistics for today's attendance."""
        now = datetime.now(timezone.utc)
        today_date = now.strftime("%Y-%m-%d")
        
        try:
            # Total present today
            present_count = Attendance.query.filter_by(date=today_date).count()
            
            # Total registered students
            from backend.models.student import Student
            total_students = Student.query.count()
            
            # Latest 5 records
            latest_records = Attendance.query.filter_by(date=today_date)\
                .order_by(Attendance.id.desc()).limit(5).all()
                
            return {
                "present": present_count,
                "total": total_students,
                "absent": max(0, total_students - present_count),
                "latest": [r.to_dict() for r in latest_records]
            }
        except Exception as e:
            logger.error(f"Error fetching today stats: {e}")
            return {"present": 0, "total": 0, "absent": 0, "latest": []}

def get_attendance_service() -> AttendanceService:
    return AttendanceService()
