import mysql.connector

class Database:
    def __init__(self):
        self.host = "localhost"
        self.user = "root"
        self.password = "Roor@123"
        self.database = "attendance_system"

    def connect(self):
        try:
            return mysql.connector.connect(
                host=self.host,
                user=self.user,
                password=self.password,
                database=self.database
            )
        except Exception as e:
            print(f"Database connection error: {e}")
            return None

    def execute_query(self, query, params=None):
        db = self.connect()
        if db:
            cursor = db.cursor()
            cursor.execute(query, params or ())
            db.commit()
            db.close()
            return True
        return False

    def fetch_all(self, query, params=None):
        db = self.connect()
        if db:
            cursor = db.cursor()
            cursor.execute(query, params or ())
            result = cursor.fetchall()
            db.close()
            return result
        return []

    def fetch_one(self, query, params=None):
        db = self.connect()
        if db:
            cursor = db.cursor()
            cursor.execute(query, params or ())
            result = cursor.fetchone()
            db.close()
            return result
        return None

db_manager = Database()
