from database import db_manager


def run_query(query):
    db = db_manager.connect()

    if not db:
        print("Aiven connection failed.")
        return

    cursor = db.cursor()

    try:
        cursor.execute(query)

        print(f"\nQUERY: {query}")

        rows = cursor.fetchall()

        for row in rows:
            print(row)

    except Exception as e:
        print("Query error:", e)

    finally:
        cursor.close()
        db.close()


print("========== AIVEN DATABASE TEST ==========")

run_query("SELECT VERSION()")
run_query("SELECT DATABASE()")
run_query("SHOW TABLES")
run_query("SELECT COUNT(*) FROM students")
run_query("SELECT COUNT(*) FROM attendance")
run_query("SELECT COUNT(*) FROM teachers")