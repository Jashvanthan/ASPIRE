import sqlite3
import os
import sys

def run_migration():
    """
    Safely adds Phase 4 columns to the existing SQLite database without dropping tables.
    """
    # Fix: Point to the actual db in the root database/ folder
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    db_path = os.path.join(base_dir, 'database', 'smartattend.db')
    
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}. No migration needed.")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check existing columns
        cursor.execute("PRAGMA table_info(attendance)")
        columns = [info[1] for info in cursor.fetchall()]

        if "exit_time" not in columns:
            print("Adding 'exit_time' column...")
            cursor.execute("ALTER TABLE attendance ADD COLUMN exit_time VARCHAR(8)")
        
        if "total_duration_seconds" not in columns:
            print("Adding 'total_duration_seconds' column...")
            cursor.execute("ALTER TABLE attendance ADD COLUMN total_duration_seconds INTEGER NOT NULL DEFAULT 0")
            
        if "overall_confidence_score" not in columns:
            print("Adding 'overall_confidence_score' column...")
            cursor.execute("ALTER TABLE attendance ADD COLUMN overall_confidence_score FLOAT")

        conn.commit()
        print("Phase 4 migration completed successfully!")
    except Exception as e:
        print(f"Migration failed: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    run_migration()
