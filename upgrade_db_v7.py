import os
from database import db_manager

def upgrade_database():
    print("Starting database schema upgrade...")
    
    try:
        # Check if columns already exist
        teacher_cols = db_manager.fetch_all("SHOW COLUMNS FROM teachers LIKE 'sex'")
        if not teacher_cols:
            db_manager.execute_query("ALTER TABLE teachers ADD COLUMN sex VARCHAR(20) DEFAULT 'Not Specified'")
            print("Added 'sex' column to 'teachers' table.")
            
        hod_cols = db_manager.fetch_all("SHOW COLUMNS FROM hods LIKE 'sex'")
        if not hod_cols:
            db_manager.execute_query("ALTER TABLE hods ADD COLUMN sex VARCHAR(20) DEFAULT 'Not Specified'")
            print("Added 'sex' column to 'hods' table.")
            
        student_cols = db_manager.fetch_all("SHOW COLUMNS FROM student_users LIKE 'sex'")
        if not student_cols:
            db_manager.execute_query("ALTER TABLE student_users ADD COLUMN sex VARCHAR(20) DEFAULT 'Not Specified'")
            print("Added 'sex' column to 'student_users' table.")
            
        print("Database schema upgrade completed successfully.")
        
    except Exception as e:
        print(f"Error during database upgrade: {e}")

if __name__ == "__main__":
    upgrade_database()
