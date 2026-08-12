import os
import mysql.connector
from dotenv import load_dotenv

load_dotenv()


class Database:

    def __init__(self):
        self.host = os.getenv("DB_HOST", "localhost")
        self.port = int(os.getenv("DB_PORT", "3306"))
        self.user = os.getenv("DB_USER", "root")
        self.password = os.getenv("DB_PASSWORD", "")
        self.database = os.getenv("DB_NAME", "attendance_system")

    def connect(self):
        try:
            return mysql.connector.connect(
                host=self.host,
                port=self.port,
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

            try:
                cursor.execute(query, params or ())
                db.commit()
                return True

            except Exception as e:
                print(f"Database query error: {e}")
                db.rollback()
                return False

            finally:
                cursor.close()
                db.close()

        return False

    def fetch_all(self, query, params=None):
        db = self.connect()

        if db:
            cursor = db.cursor()

            try:
                cursor.execute(query, params or ())
                result = cursor.fetchall()
                return result

            except Exception as e:
                print(f"Database fetch error: {e}")
                return []

            finally:
                cursor.close()
                db.close()

        return []

    def fetch_one(self, query, params=None):
        db = self.connect()

        if db:
            cursor = db.cursor()

            try:
                cursor.execute(query, params or ())
                result = cursor.fetchone()
                return result

            except Exception as e:
                print(f"Database fetch error: {e}")
                return None

            finally:
                cursor.close()
                db.close()

        return None


db_manager = Database()