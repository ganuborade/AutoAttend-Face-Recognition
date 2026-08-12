import mysql.connector

def reset_and_generate_keys():
    print("Connecting to database...")
    try:
        db = mysql.connector.connect(
            host="localhost",
            user="root",
            password="Root@123",
            database="attendance_system"
        )
        cursor = db.cursor()
        
        # Ensure HOD table exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS hod_auth_keys (
                id INT AUTO_INCREMENT PRIMARY KEY,
                auth_key VARCHAR(100) UNIQUE NOT NULL,
                is_used BOOLEAN DEFAULT FALSE
            )
        """)
        
        # Reset all existing HOD keys to unused
        cursor.execute("UPDATE hod_auth_keys SET is_used = 0")
        
        # Multiple HOD keys
        hod_keys = [
            'VISIONAI-HOD-2026', 
            'ADMIN-HOD-1234',
            'HOD-KEY-001',
            'HOD-KEY-002',
            'HOD-KEY-003',
            'HOD-KEY-004',
            'HOD-KEY-005'
        ]
        print("\n--- AVAILABLE HOD KEYS ---")
        for key in hod_keys:
            try:
                cursor.execute(f"INSERT INTO hod_auth_keys (auth_key, is_used) VALUES ('{key}', 0)")
            except mysql.connector.Error as err:
                if err.errno == 1062: # Duplicate entry
                    pass
            print(f"- {key}")
                    
        # Ensure Teacher table exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS teacher_auth_keys (
                id INT AUTO_INCREMENT PRIMARY KEY,
                auth_key VARCHAR(100) UNIQUE NOT NULL,
                is_used BOOLEAN DEFAULT FALSE
            )
        """)
        
        # Reset all existing Teacher keys to unused
        cursor.execute("UPDATE teacher_auth_keys SET is_used = 0")
        
        # Multiple Teacher keys
        teacher_keys = [
            'VISIONAI-TEACHER-2026', 
            'GUEST-TEACHER-1234',
            'TEACHER-KEY-001',
            'TEACHER-KEY-002',
            'TEACHER-KEY-003',
            'TEACHER-KEY-004',
            'TEACHER-KEY-005'
        ]
        print("\n--- AVAILABLE TEACHER KEYS ---")
        for key in teacher_keys:
            try:
                cursor.execute(f"INSERT INTO teacher_auth_keys (auth_key, is_used) VALUES ('{key}', 0)")
            except mysql.connector.Error as err:
                if err.errno == 1062: # Duplicate entry
                    pass
            print(f"- {key}")
        
        db.commit()
        db.close()
        print("\nSUCCESS: Database keys updated! All existing keys were marked as unused (available), and multiple new keys have been added.")
    except Exception as e:
        print(f"Error resetting keys: {e}")

if __name__ == "__main__":
    reset_and_generate_keys()
