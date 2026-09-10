import os
import mysql.connector
from dotenv import load_dotenv

load_dotenv()

def setup_hod():
    print("Connecting to database...")
    try:
        db = mysql.connector.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "3306")),
            user=os.getenv("DB_USER", "root"),
            password=os.getenv("DB_PASSWORD", ""),
            database=os.getenv("DB_NAME", "attendance_system")
        )
        cursor = db.cursor()
        
        print("Creating 'hods' table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS hods (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(50) UNIQUE,
                password VARCHAR(100)
            )
        """)
        
        hod_user = os.getenv("DEFAULT_HOD_USERNAME", "hod")
        hod_pass = os.getenv("DEFAULT_HOD_PASSWORD", "hod123")
        print(f"Inserting default HOD account ({hod_user}/******)...")
        try:
            cursor.execute("INSERT INTO hods (username, password) VALUES (%s, %s)", (hod_user, hod_pass))
            db.commit()
            print("Successfully created default HOD account.")
        except mysql.connector.Error as err:
            if err.errno == 1062: # Duplicate entry
                print("Default HOD account already exists.")
            else:
                print(f"Error inserting HOD account: {err}")

        db.close()
        print("\nHOD Setup completed successfully!")

    except Exception as e:
        print(f"Failed to connect or setup database: {e}")

if __name__ == "__main__":
    setup_hod()
