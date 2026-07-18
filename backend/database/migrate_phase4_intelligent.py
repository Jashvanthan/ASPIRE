import logging
from backend.database.db import db
from backend.models.unknown_person import UnknownPerson
from backend.models.audit_log import AuditLog
from backend.models.attendance_correction import AttendanceCorrection
from sqlalchemy import text

logger = logging.getLogger(__name__)

def run_migration():
    """
    Safely creates the new tables for the intelligent features:
    UnknownPerson, AuditLog, and AttendanceCorrection.
    SQLAlchemy's create_all() is safe because it only creates tables that don't exist.
    """
    try:
        # We need to make sure the engine knows about these models.
        # They are imported above, so they are registered in the metadata.
        db.create_all()
        logger.info("Phase 4 intelligent migrations completed successfully. New tables verified.")
    except Exception as e:
        logger.error(f"Error during Phase 4 intelligent migration: {e}")
        raise
