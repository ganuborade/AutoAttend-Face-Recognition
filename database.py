import os
import threading
import mysql.connector
from mysql.connector import pooling
from dotenv import load_dotenv

load_dotenv()


class Database:

    def __init__(self):
        self.host = os.getenv("DB_HOST")
        self.port = int(os.getenv("DB_PORT", "3306"))
        self.user = os.getenv("DB_USER")
        self.password = os.getenv("DB_PASSWORD")
        self.database = os.getenv("DB_NAME")

        # Connection-pool settings
        self.pool_name = "autoattend_pool"
        self.pool_size = 5

        # Pool is created lazily.
        # This prevents Flask from failing during startup if
        # Aiven is temporarily unavailable.
        self.pool = None

        # Prevent multiple threads from creating the pool simultaneously.
        self.pool_lock = threading.Lock()

    # ---------------------------------------------------------
    # CREATE / RECREATE CONNECTION POOL
    # ---------------------------------------------------------
    def _create_pool(self):
        with self.pool_lock:

            # Another thread may already have created it.
            if self.pool is not None:
                return

            try:
                print("Creating MySQL connection pool...")

                self.pool = pooling.MySQLConnectionPool(
                    pool_name=self.pool_name,
                    pool_size=self.pool_size,

                    host=self.host,
                    port=self.port,
                    user=self.user,
                    password=self.password,
                    database=self.database,

                    # Important for Aiven/network connections
                    connection_timeout=10,

                    # Reset connection/session state when returned
                    pool_reset_session=True
                )

                print(
                    f"MySQL connection pool created successfully "
                    f"(size={self.pool_size})"
                )

            except Exception as e:
                self.pool = None
                print(f"Database pool creation error: {e}")
                raise

    # ---------------------------------------------------------
    # GET ONE CONNECTION FROM POOL
    # ---------------------------------------------------------
    def _get_connection(self):
        try:

            if self.pool is None:
                self._create_pool()

            db = self.pool.get_connection()

            # Check connection health.
            # Reconnect if the connection was dropped.
            db.ping(
                reconnect=True,
                attempts=2,
                delay=0.5
            )

            return db

        except Exception as e:

            print(f"Pool connection error: {e}")

            # Recreate the pool once.
            self.pool = None

            self._create_pool()

            db = self.pool.get_connection()

            db.ping(
                reconnect=True,
                attempts=2,
                delay=0.5
            )

            return db

    # ---------------------------------------------------------
    # RESET POOL AFTER A CONNECTION FAILURE
    # ---------------------------------------------------------
    def _reset_pool(self):
        with self.pool_lock:

            try:
                if self.pool is not None:
                    self.pool = None
                    print("MySQL connection pool reset.")
            except Exception as e:
                print(f"Pool reset error: {e}")

    # ---------------------------------------------------------
    # EXECUTE INSERT / UPDATE / DELETE / DDL
    # ---------------------------------------------------------
    def execute_query(self, query, params=None):

        last_error = None

        # Retry once if Aiven connection drops.
        for attempt in range(2):

            db = None
            cursor = None

            try:
                db = self._get_connection()
                cursor = db.cursor()

                cursor.execute(
                    query,
                    params or ()
                )

                db.commit()

                return True

            except (
                mysql.connector.errors.InterfaceError,
                mysql.connector.errors.OperationalError,
                mysql.connector.errors.DatabaseError
            ) as e:

                last_error = e

                print(
                    f"Database execute error "
                    f"(attempt {attempt + 1}/2): {e}"
                )

                if db is not None:
                    try:
                        db.rollback()
                    except Exception:
                        pass

                self._reset_pool()

            except Exception as e:

                print(f"Query execution error: {e}")

                if db is not None:
                    try:
                        db.rollback()
                    except Exception:
                        pass

                return False

            finally:

                if cursor is not None:
                    try:
                        cursor.close()
                    except Exception:
                        pass

                if db is not None:
                    try:
                        db.close()
                    except Exception:
                        pass

        print(f"Database execute failed after retry: {last_error}")
        return False

    # ---------------------------------------------------------
    # FETCH ALL
    # ---------------------------------------------------------
    def fetch_all(self, query, params=None):

        last_error = None

        for attempt in range(2):

            db = None
            cursor = None

            try:

                db = self._get_connection()
                cursor = db.cursor()

                cursor.execute(
                    query,
                    params or ()
                )

                return cursor.fetchall()

            except (
                mysql.connector.errors.InterfaceError,
                mysql.connector.errors.OperationalError,
                mysql.connector.errors.DatabaseError
            ) as e:

                last_error = e

                print(
                    f"Database fetch_all error "
                    f"(attempt {attempt + 1}/2): {e}"
                )

                self._reset_pool()

            except Exception as e:

                print(f"Fetch all error: {e}")
                return []

            finally:

                if cursor is not None:
                    try:
                        cursor.close()
                    except Exception:
                        pass

                if db is not None:
                    try:
                        db.close()
                    except Exception:
                        pass

        print(f"Database fetch_all failed after retry: {last_error}")
        return []

    # ---------------------------------------------------------
    # FETCH ONE
    # ---------------------------------------------------------
    def fetch_one(self, query, params=None):

        last_error = None

        for attempt in range(2):

            db = None
            cursor = None

            try:

                db = self._get_connection()
                cursor = db.cursor()

                cursor.execute(
                    query,
                    params or ()
                )

                return cursor.fetchone()

            except (
                mysql.connector.errors.InterfaceError,
                mysql.connector.errors.OperationalError,
                mysql.connector.errors.DatabaseError
            ) as e:

                last_error = e

                print(
                    f"Database fetch_one error "
                    f"(attempt {attempt + 1}/2): {e}"
                )

                self._reset_pool()

            except Exception as e:

                print(f"Fetch one error: {e}")
                return None

            finally:

                if cursor is not None:
                    try:
                        cursor.close()
                    except Exception:
                        pass

                if db is not None:
                    try:
                        db.close()
                    except Exception:
                        pass

        print(f"Database fetch_one failed after retry: {last_error}")
        return None

    # ---------------------------------------------------------
    # DIRECT CONNECTION TEST
    # ---------------------------------------------------------
    def connect(self):

        try:

            db = self._get_connection()

            print("Database connection successful.")

            return db

        except Exception as e:

            print(f"Database connection error: {e}")

            return None


# Global database manager
db_manager = Database()