import logging
from datetime import datetime, timezone
import time
from typing import Tuple, Dict, Any, List

from backend.models.attendance import Attendance
from backend.database.db import db
from sqlalchemy import func

logger = logging.getLogger(__name__)

class AttendanceService:
    """
    Service for marking attendance and managing session state.
    Prevents duplicate entries and implements recognition cooldown.
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
        
        # Cooldown cache to prevent spamming the DB for the same person in the same session
        # Format: {student_id: timestamp_of_last_check}
        self._cooldowns: Dict[str, float] = {}
        # Cooldown duration in seconds
        self.COOLDOWN_SECONDS = 5.0
        
        logger.info("AttendanceService created.")

    def mark_attendance(self, student: dict, confidence: float, **kwargs) -> Tuple[bool, str, str]:
        """
        Attempt to mark attendance for a recognized student.
        
        Returns:
            Tuple of (success_bool, message, status_color_class)
        """
        student_id = student.get("student_id")
        student_name = student.get("full_name")
        
        if not student_id:
            return False, "Invalid student data", "red"
            
        now = datetime.now(timezone.utc) # Using UTC to match DB default, but local time is better for actual date grouping
        # For a real school app, you'd want local timezone, but we'll use a simple YYYY-MM-DD
        today_date = now.strftime("%Y-%m-%d")
        current_time = now.strftime("%H:%M:%S")
        
        # 1. Check Cooldown Cache (Memory) to avoid DB spam
        current_ts = time.time()
        last_check = self._cooldowns.get(student_id, 0)
        
        if current_ts - last_check < self.COOLDOWN_SECONDS:
            # We recently processed this person, assume Already Marked for UI stability
            return False, "Already Marked", "yellow"
            
        # Update cooldown timestamp
        self._cooldowns[student_id] = current_ts

        try:
            # 2. Check Database for duplicate today
            # We want the most recent attendance record for this student today
            existing_record = Attendance.query.filter_by(
                student_id=student_id, 
                date=today_date
            ).order_by(Attendance.id.desc()).first()
            
            # Feature 2: Entry/Exit Tracking - Configurable timeout (30 mins = 1800s)
            SESSION_TIMEOUT_SECONDS = 1800
            
            if existing_record:
                if existing_record.exit_time:
                    # Parse exit time to check if it has been more than 30 mins
                    exit_dt = datetime.strptime(f"{today_date} {existing_record.exit_time}", "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                    if (now - exit_dt).total_seconds() > SESSION_TIMEOUT_SECONDS:
                        # Create a NEW session for this student!
                        pass
                    else:
                        # Returning within timeout, treat as already marked
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
