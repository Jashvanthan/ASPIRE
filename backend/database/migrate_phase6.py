import sqlite3
import os
import sys

def run_migration():
    """
    Phase 6 Migration: Add last_qr_scan_time column to students table.
    """
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    db_path = os.path.join(base_dir, "database", "smartattend.db")

    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}. No migration needed.")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if last_qr_scan_time exists in students
        cursor.execute("PRAGMA table_info(students)")
        columns = [info[1] for info in cursor.fetchall()]

        if 'last_qr_scan_time' not in columns:
            print("Adding last_qr_scan_time to students table...")
            cursor.execute("ALTER TABLE students ADD COLUMN last_qr_scan_time DATETIME")

        # Create unknown_person table if missing (used by audit_service)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS unknown_person (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_path VARCHAR(255) NOT NULL,
                confidence FLOAT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
            
        conn.commit()
        print("Phase 6 migration completed successfully!")
    except Exception as e:
        print(f"Error during Phase 6 migration: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    run_migration()
