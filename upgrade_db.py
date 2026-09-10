import os
import mysql.connector
from dotenv import load_dotenv

load_dotenv()

def upgrade_database():
    print("Connecting to the database...")
    try:
        db = mysql.connector.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "3306")),
            user=os.getenv("DB_USER", "root"),
            password=os.getenv("DB_PASSWORD", ""),
            database=os.getenv("DB_NAME", "attendance_system")
        )
        cursor = db.cursor()
        
        print("Checking if columns need to be added...")
        
        # We wrap in try-except because if columns already exist, it will throw an error
        try:
            cursor.execute("ALTER TABLE students ADD COLUMN year VARCHAR(50) DEFAULT '1st Year'")
            print("Successfully added 'year' column.")
        except mysql.connector.Error as err:
            print(f"Year column info: {err.msg}")

        try:
            cursor.execute("ALTER TABLE students ADD COLUMN branch VARCHAR(100) DEFAULT 'Computer Science'")
            print("Successfully added 'branch' column.")
        except mysql.connector.Error as err:
            print(f"Branch column info: {err.msg}")

        try:
            cursor.execute("ALTER TABLE students ADD COLUMN division VARCHAR(20) DEFAULT 'A'")
            print("Successfully added 'division' column.")
        except mysql.connector.Error as err:
            print(f"Division column info: {err.msg}")

        db.commit()
        db.close()
        print("\nDatabase upgrade completed successfully! You can now run python app.py")

    except Exception as e:
        print(f"Failed to connect or upgrade database: {e}")

if __name__ == "__main__":
    upgrade_database()
