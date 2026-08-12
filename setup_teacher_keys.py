import mysql.connector

def setup_teacher_keys():
    print("Connecting to the database...")
    try:
        db = mysql.connector.connect(
            host="localhost",
            user="root",
            password="Root@123",
            database="attendance_system"
        )
        cursor = db.cursor()
        
        # Insert a default key
        print("Adding default teacher key: VISIONAI-TEACHER-2026")
        try:
            cursor.execute("INSERT INTO teacher_auth_keys (auth_key) VALUES ('VISIONAI-TEACHER-2026')")
            print("Successfully added default key: VISIONAI-TEACHER-2026")
        except mysql.connector.Error as err:
            if err.errno == 1062: # Duplicate entry
                print("Default key already exists in the database.")
            else:
                print(f"Error inserting default key: {err.msg}")

        # Insert secondary key
        print("Adding secondary teacher key: GUEST-TEACHER-1234")
        try:
            cursor.execute("INSERT INTO teacher_auth_keys (auth_key) VALUES ('GUEST-TEACHER-1234')")
            print("Successfully added secondary key: GUEST-TEACHER-1234")
        except mysql.connector.Error as err:
            if err.errno == 1062: # Duplicate entry
                print("Secondary key already exists in the database.")
            else:
                print(f"Error inserting secondary key: {err.msg}")

        db.commit()
        db.close()
        print("\nTeacher Keys setup completed successfully!")

    except Exception as e:
        print(f"Failed to connect or setup keys: {e}")

if __name__ == "__main__":
    setup_teacher_keys()
