import mysql.connector

def upgrade_database_v5():
    print("Connecting to the database...")
    try:
        db = mysql.connector.connect(
            host="localhost",
            user="root",
            password="Root@123",
            database="attendance_system"
        )
        cursor = db.cursor()
        
        # 1. Update teachers table
        print("Adding columns to 'teachers' table...")
        for col, col_type in [("email", "VARCHAR(100)"), ("college", "VARCHAR(255)"), ("university", "VARCHAR(255)")]:
            try:
                cursor.execute(f"ALTER TABLE teachers ADD COLUMN {col} {col_type}")
                print(f"Successfully added '{col}' to teachers.")
            except mysql.connector.Error as err:
                print(f"Column '{col}' error: {err.msg}")

        # 2. Update hods table
        print("Adding columns to 'hods' table...")
        for col, col_type in [("email", "VARCHAR(100)"), ("college", "VARCHAR(255)"), ("university", "VARCHAR(255)")]:
            try:
                cursor.execute(f"ALTER TABLE hods ADD COLUMN {col} {col_type}")
                print(f"Successfully added '{col}' to hods.")
            except mysql.connector.Error as err:
                print(f"Column '{col}' error: {err.msg}")

        # 3. Create teacher_auth_keys table
        print("Creating 'teacher_auth_keys' table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS teacher_auth_keys (
                id INT AUTO_INCREMENT PRIMARY KEY,
                auth_key VARCHAR(100) UNIQUE NOT NULL,
                is_used BOOLEAN DEFAULT FALSE
            )
        """)

        # 4. Create student_users table
        print("Creating 'student_users' table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS student_users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                roll_number VARCHAR(50) UNIQUE NOT NULL,
                email VARCHAR(100) UNIQUE NOT NULL,
                password VARCHAR(255) NOT NULL,
                college VARCHAR(255),
                university VARCHAR(255),
                district VARCHAR(100),
                taluka VARCHAR(100),
                mobile VARCHAR(20),
                address TEXT,
                class_name VARCHAR(50),
                branch VARCHAR(100)
            )
        """)

        db.commit()
        db.close()
        print("\nDatabase upgrade v5 completed successfully!")

    except Exception as e:
        print(f"Failed to connect or upgrade database: {e}")

if __name__ == "__main__":
    upgrade_database_v5()
