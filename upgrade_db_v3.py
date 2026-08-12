import mysql.connector

def upgrade_database_v3():
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
        print("Adding 'mobile' and 'address' columns to 'teachers' table...")
        try:
            cursor.execute("ALTER TABLE teachers ADD COLUMN mobile VARCHAR(20)")
            print("Successfully added 'mobile' to teachers.")
        except mysql.connector.Error as err:
            print(f"Column 'mobile' already exists or error: {err.msg}")

        try:
            cursor.execute("ALTER TABLE teachers ADD COLUMN address TEXT")
            print("Successfully added 'address' to teachers.")
        except mysql.connector.Error as err:
            print(f"Column 'address' already exists or error: {err.msg}")

        # 2. Update hods table
        print("Adding 'name', 'mobile', 'address', and 'unique_id' columns to 'hods' table...")
        try:
            cursor.execute("ALTER TABLE hods ADD COLUMN name VARCHAR(100)")
            print("Successfully added 'name' to hods.")
        except mysql.connector.Error as err:
            print(f"Column 'name' already exists or error: {err.msg}")

        try:
            cursor.execute("ALTER TABLE hods ADD COLUMN mobile VARCHAR(20)")
            print("Successfully added 'mobile' to hods.")
        except mysql.connector.Error as err:
            print(f"Column 'mobile' already exists or error: {err.msg}")

        try:
            cursor.execute("ALTER TABLE hods ADD COLUMN address TEXT")
            print("Successfully added 'address' to hods.")
        except mysql.connector.Error as err:
            print(f"Column 'address' already exists or error: {err.msg}")
            
        try:
            cursor.execute("ALTER TABLE hods ADD COLUMN unique_id VARCHAR(50)")
            print("Successfully added 'unique_id' to hods.")
        except mysql.connector.Error as err:
            print(f"Column 'unique_id' already exists or error: {err.msg}")

        db.commit()
        db.close()
        print("\nDatabase upgrade v3 completed successfully!")

    except Exception as e:
        print(f"Failed to connect or upgrade database: {e}")

if __name__ == "__main__":
    upgrade_database_v3()
