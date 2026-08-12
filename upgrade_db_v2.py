import mysql.connector

def upgrade_database():
    print("Connecting to the database...")
    try:
        db = mysql.connector.connect(
            host="localhost",
            user="root",
            password="Root@123",
            database="attendance_system"
        )
        cursor = db.cursor()
        
        print("Creating 'teachers' table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS teachers (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(100),
                username VARCHAR(50) UNIQUE,
                password VARCHAR(100)
            )
        """)
        
        print("Adding 'teacher_id' column to 'students' table...")
        try:
            cursor.execute("ALTER TABLE students ADD COLUMN teacher_id INT DEFAULT 1")
            print("Successfully added 'teacher_id' to students.")
        except mysql.connector.Error as err:
            print(f"Column already exists or error: {err.msg}")

        print("Adding 'teacher_id' column to 'attendance' table...")
        try:
            cursor.execute("ALTER TABLE attendance ADD COLUMN teacher_id INT DEFAULT 1")
            print("Successfully added 'teacher_id' to attendance.")
        except mysql.connector.Error as err:
            print(f"Column already exists or error: {err.msg}")

        db.commit()
        db.close()
        print("\nDatabase upgrade completed successfully! The system is now ready for multiple teachers.")
        print("Please restart python app.py")

    except Exception as e:
        print(f"Failed to connect or upgrade database: {e}")

if __name__ == "__main__":
    upgrade_database()
