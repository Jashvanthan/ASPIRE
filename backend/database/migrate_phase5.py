import sqlite3
import os

def run_migration():
    """
    Safely adds the Phase 5 'batch' column to the database and backfills it.
    """
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    db_path = os.path.join(base_dir, 'database', 'smartattend.db')
    
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}. No migration needed.")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check students table
        cursor.execute("PRAGMA table_info(students)")
        student_columns = [info[1] for info in cursor.fetchall()]

        if "batch" not in student_columns:
            print("Adding 'batch' column to students table...")
            cursor.execute("ALTER TABLE students ADD COLUMN batch VARCHAR(20) DEFAULT 'Unknown'")
            
            # Backfill batch for students based on year (Assuming current year is ~2025/2026)
            # Year 1 -> 2025-29
            # Year 2 -> 2024-28
            # Year 3 -> 2023-27
            # Year 4 -> 2022-26
            cursor.execute("UPDATE students SET batch = '2025-29' WHERE year = 1")
            cursor.execute("UPDATE students SET batch = '2024-28' WHERE year = 2")
            cursor.execute("UPDATE students SET batch = '2023-27' WHERE year = 3")
            cursor.execute("UPDATE students SET batch = '2022-26' WHERE year = 4")

        # Check attendance table
        cursor.execute("PRAGMA table_info(attendance)")
        att_columns = [info[1] for info in cursor.fetchall()]

        if "batch" not in att_columns:
            print("Adding 'batch' column to attendance table...")
            cursor.execute("ALTER TABLE attendance ADD COLUMN batch VARCHAR(20) DEFAULT 'Unknown'")
            
            # Backfill batch for attendance based on year
            cursor.execute("UPDATE attendance SET batch = '2025-29' WHERE year = 1")
            cursor.execute("UPDATE attendance SET batch = '2024-28' WHERE year = 2")
            cursor.execute("UPDATE attendance SET batch = '2023-27' WHERE year = 3")
            cursor.execute("UPDATE attendance SET batch = '2022-26' WHERE year = 4")

        conn.commit()
        print("Phase 5 migration completed successfully!")
    except Exception as e:
        print(f"Phase 5 Migration failed: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    run_migration()
