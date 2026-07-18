"""
backend/scripts/dedupe_logs.py
------------------------------
Removes duplicated security logs and attendance logs that occurred within
the newly established cooldown windows.
"""

import os
import sys
import argparse
from datetime import timedelta

# Add project root to PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from app import create_app
from backend.database.db import db
from backend.models.security_log import SecurityLog
from backend.models.attendance import Attendance

def dedupe_security_logs(app):
    """Remove security logs that occur within 30 seconds of the previous log for the same identity."""
    print("Starting deduplication of Security Logs...")
    with app.app_context():
        # Fetch all logs ordered by timestamp
        logs = SecurityLog.query.order_by(SecurityLog.timestamp).all()
        
        last_seen = {}
        to_delete = []
        
        for log in logs:
            # Group by student_id if available, otherwise by spoof_type
            key = log.student_id if log.student_id else f"{log.spoof_type}_unknown"
            
            if key in last_seen:
                time_diff = log.timestamp - last_seen[key].timestamp
                # If less than 30 seconds, it's a duplicate
                if time_diff < timedelta(seconds=30):
                    to_delete.append(log)
                    continue
            
            # Update last seen
            last_seen[key] = log
            
        print(f"Found {len(to_delete)} duplicate security logs.")
        if to_delete:
            for log in to_delete:
                db.session.delete(log)
            db.session.commit()
            print(f"Successfully deleted {len(to_delete)} security logs.")
        else:
            print("No security logs to delete.")


def dedupe_attendance_logs(app):
    """Remove attendance logs that occur within 1 minute of the previous log for the same identity."""
    print("Starting deduplication of Attendance Logs...")
    with app.app_context():
        logs = Attendance.query.order_by(Attendance.created_at).all()
        
        last_seen = {}
        to_delete = []
        
        for log in logs:
            key = log.student_id
            
            if key in last_seen:
                time_diff = log.created_at - last_seen[key].created_at
                # If less than 60 seconds, it's a duplicate
                if time_diff < timedelta(seconds=60):
                    to_delete.append(log)
                    continue
            
            last_seen[key] = log
            
        print(f"Found {len(to_delete)} duplicate attendance logs.")
        if to_delete:
            for log in to_delete:
                db.session.delete(log)
            db.session.commit()
            print(f"Successfully deleted {len(to_delete)} attendance logs.")
        else:
            print("No attendance logs to delete.")

def main():
    parser = argparse.ArgumentParser(description="Deduplicate logs in the database.")
    parser.add_argument("--security", action="store_true", help="Deduplicate security logs")
    parser.add_argument("--attendance", action="store_true", help="Deduplicate attendance logs")
    parser.add_argument("--all", action="store_true", help="Deduplicate all logs")
    
    args = parser.parse_args()
    
    if not (args.security or args.attendance or args.all):
        print("Please specify --security, --attendance, or --all")
        sys.exit(1)
        
    app = create_app()
    
    if args.security or args.all:
        dedupe_security_logs(app)
        
    if args.attendance or args.all:
        dedupe_attendance_logs(app)

if __name__ == "__main__":
    main()
