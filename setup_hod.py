import mysql.connector

def setup_hod():
    print("Connecting to database...")
    try:
        db = mysql.connector.connect(
            host="localhost",
            user="root",
            password="Root@123",
            database="attendance_system"
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
        
        print("Inserting default HOD account (hod/hod123)...")
        try:
            cursor.execute("INSERT INTO hods (username, password) VALUES ('hod', 'hod123')")
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
