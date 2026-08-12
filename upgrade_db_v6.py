import mysql.connector

def upgrade_database_v6():
    print("Connecting to the database...")
    try:
        db = mysql.connector.connect(
            host="localhost",
            user="root",
            password="Root@123",
            database="attendance_system"
        )
        cursor = db.cursor()
        
        # Add columns to attendance table
        print("Adding columns to 'attendance' table...")
        columns_to_add = [
            ("subject", "VARCHAR(100)"),
            ("year", "VARCHAR(50)"),
            ("branch", "VARCHAR(100)"),
            ("division", "VARCHAR(10)")
        ]
        
        for col, col_type in columns_to_add:
            try:
                # Check if column exists first (to be safe if run multiple times)
                cursor.execute(f"SHOW COLUMNS FROM attendance LIKE '{col}'")
                result = cursor.fetchone()
                if not result:
                    cursor.execute(f"ALTER TABLE attendance ADD COLUMN {col} {col_type}")
                    print(f"Successfully added '{col}' to attendance.")
                else:
                    print(f"Column '{col}' already exists in attendance.")
            except mysql.connector.Error as err:
                print(f"Column '{col}' error: {err.msg}")

        db.commit()
        db.close()
        print("\nDatabase upgrade v6 completed successfully!")

    except Exception as e:
        print(f"Failed to connect or upgrade database: {e}")

if __name__ == "__main__":
    upgrade_database_v6()
