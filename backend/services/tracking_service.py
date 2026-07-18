"""
backend/services/tracking_service.py
------------------------------------
Service for caching face recognition identities using ByteTrack tracking IDs.
This drastically reduces CPU usage by avoiding repeated face detection and 
recognition on the same person in consecutive frames.
"""

import logging
import time
from typing import Optional, Dict, Any

from flask import current_app
from backend.database.db import db
from backend.models.attendance import Attendance

logger = logging.getLogger(__name__)

class TrackingService:
    """
    Singleton service that maintains the Identity Cache mapping YOLO tracking IDs 
    to recognized Student identities and spoof results.
    """
    _instance: Optional["TrackingService"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
            
        self._initialized = True
        # Cache format: { track_id: { "student": dict, "sim": float, "is_genuine": bool, "spoof_type": str, "last_seen": float, "marked_attendance": bool } }
        self._identity_cache: Dict[int, Dict[str, Any]] = {}

    def get_cached_identity(self, track_id: int) -> Optional[Dict[str, Any]]:
        """Retrieve a cached identity for a track_id if it exists."""
        return self._identity_cache.get(track_id)

    def cache_identity(self, track_id: int, student: Optional[dict], sim: float, is_genuine: bool, spoof_type: str, live_conf: float, spoof_conf: float, marked_attendance: bool = False, attendance_db_id: int = None, snapshot_saved: bool = False):
        """Save a newly recognized identity to the cache."""
        now = time.time()
        # If it already exists, keep the original first_seen
        first_seen = now
        if track_id in self._identity_cache:
            first_seen = self._identity_cache[track_id]["first_seen"]
            
        self._identity_cache[track_id] = {
            "student": student,
            "sim": sim,
            "is_genuine": is_genuine,
            "spoof_type": spoof_type,
            "live_conf": live_conf,
            "spoof_conf": spoof_conf,
            "marked_attendance": marked_attendance,
            "attendance_db_id": attendance_db_id,
            "snapshot_saved": snapshot_saved,
            "first_seen": first_seen,
            "last_seen": now
        }
        logger.debug(f"Cached Track ID {track_id} -> Student: {student['full_name'] if student else 'Unknown'} | Genuine: {is_genuine}")

    def get_continuous_duration(self, track_id: int) -> float:
        """Returns the number of seconds this track ID has been continuously seen."""
        if track_id in self._identity_cache:
            return time.time() - self._identity_cache[track_id]["first_seen"]
        return 0.0

    def update_last_seen(self, track_id: int):
        """Update the last_seen timestamp to keep the cache alive."""
        if track_id in self._identity_cache:
            self._identity_cache[track_id]["last_seen"] = time.time()

    def mark_attendance_completed(self, track_id: int, attendance_db_id: int):
        """Flag that attendance has been marked so we don't spam the DB."""
        if track_id in self._identity_cache:
            self._identity_cache[track_id]["marked_attendance"] = True
            self._identity_cache[track_id]["attendance_db_id"] = attendance_db_id

    def cleanup_stale_tracks(self, max_age_seconds: int = 5):
        """
        Remove tracking IDs that haven't been seen recently.
        We use seconds instead of frames to decouple from frontend FPS.
        """
        current_time = time.time()
        stale_ids = []
        for tid, data in self._identity_cache.items():
            if current_time - data["last_seen"] > max_age_seconds:
                stale_ids.append(tid)
                
                # Phase 4: Exit Tracking
                if data.get("marked_attendance") and data.get("attendance_db_id"):
                    try:
                        record = Attendance.query.get(data["attendance_db_id"])
                        if record:
                            # Calculate duration based on first_seen and last_seen
                            duration = int(data["last_seen"] - data["first_seen"])
                            
                            # Convert last_seen timestamp to HH:MM:SS
                            from datetime import datetime, timezone
                            exit_time_str = datetime.fromtimestamp(data["last_seen"], tz=timezone.utc).strftime("%H:%M:%S")
                            
                            record.exit_time = exit_time_str
                            record.total_duration_seconds += duration
                            db.session.commit()
                            logger.info(f"Updated Exit Time for Track {tid} (Duration: {duration}s)")
                    except Exception as e:
                        db.session.rollback()
                        logger.error(f"Failed to update exit time for Track {tid}: {e}")
                
        for tid in stale_ids:
            del self._identity_cache[tid]
            logger.debug(f"Removed stale Track ID {tid} from cache.")

def get_tracking_service() -> TrackingService:
    return TrackingService()
