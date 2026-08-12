import mysql.connector

def setup_hod_keys():
    print("Connecting to the database...")
    try:
        db = mysql.connector.connect(
            host="localhost",
            user="root",
            password="Root@123",
            database="attendance_system"
        )
        cursor = db.cursor()
        
        # Create table if it doesn't exist
        print("Creating hod_auth_keys table if it doesn't exist...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS hod_auth_keys (
                id INT AUTO_INCREMENT PRIMARY KEY,
                auth_key VARCHAR(100) UNIQUE NOT NULL,
                is_used BOOLEAN DEFAULT FALSE
            )
        """)
        
        # Insert a default key
        print("Adding default key: VISIONAI-HOD-2026")
        try:
            cursor.execute("INSERT INTO hod_auth_keys (auth_key) VALUES ('VISIONAI-HOD-2026')")
            print("Successfully added default key: VISIONAI-HOD-2026")
        except mysql.connector.Error as err:
            if err.errno == 1062: # Duplicate entry
                print("Default key 'VISIONAI-HOD-2026' already exists in the database.")
            else:
                print(f"Error inserting default key: {err.msg}")

        # Add another key just to show it's dynamic
        print("Adding secondary key: ADMIN-HOD-1234")
        try:
            cursor.execute("INSERT INTO hod_auth_keys (auth_key) VALUES ('ADMIN-HOD-1234')")
            print("Successfully added secondary key: ADMIN-HOD-1234")
        except mysql.connector.Error as err:
            if err.errno == 1062: # Duplicate entry
                print("Secondary key 'ADMIN-HOD-1234' already exists in the database.")
            else:
                print(f"Error inserting secondary key: {err.msg}")

        db.commit()
        db.close()
        print("\nHOD Keys setup completed successfully!")

    except Exception as e:
        print(f"Failed to connect or setup keys: {e}")

if __name__ == "__main__":
    setup_hod_keys()
