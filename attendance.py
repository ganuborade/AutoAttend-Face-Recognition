import cv2
import os
import numpy as np
from datetime import datetime
import mysql.connector

# ---------------- DATABASE ----------------
db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="Root@123"
)
cursor = db.cursor()
cursor.execute("USE attendance_system")

# ---------------- LOAD IMAGES ----------------
path = "static/images"
known_faces = []
known_names = []

for roll in os.listdir(path):
    roll_path = os.path.join(path, roll)

    if not os.path.isdir(roll_path):
        continue

    for img_name in os.listdir(roll_path):
        img_path = f"{roll_path}/{img_name}"
        img = cv2.imread(img_path, 0)

        if img is None:
            continue

        if face is None or face.size == 0:
            continue

        face = cv2.resize(face, (200, 200))
        known_faces.append(img)
        known_names.append(roll)

        lecture_no = 1

# ---------------- CAMERA ----------------
cap = cv2.VideoCapture(0)

face_cascade = cv2.CascadeClassifier(
    cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
)

last_seen = {}

# ---------------- MAIN LOOP ----------------
while True:
    ret, frame = cap.read()

    if not ret:
        break

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    faces = face_cascade.detectMultiScale(gray, 1.3, 5)

    for (x, y, w, h) in faces:
        face = gray[y:y+h, x:x+w]
        face = cv2.resize(face, (200, 200))

        matches = {}

        # 🔥 MATCHING LOGIC (IMPROVED)
        for i, known_face in enumerate(known_faces):
            diff = np.sum((known_face - face) ** 2)

            if diff < 1300000:   # balanced threshold
                name_temp = known_names[i]
                matches[name_temp] = matches.get(name_temp, 0) + 1

        roll = None

        # 🔥 REQUIRE MIN 3 MATCHES (IMPORTANT)
        if matches:
            best_match = max(matches, key=matches.get)

            if matches[best_match] >= 3:
                roll = best_match

        # ---------------- ATTENDANCE ----------------
        if roll is not None:
            now = datetime.now()

            # 🔥 COOLDOWN (avoid multiple entries)
            if roll in last_seen and (now - last_seen[roll]).seconds < 5:
                continue

            last_seen[roll] = now

            date = now.strftime('%Y-%m-%d')
            time = now.strftime('%H:%M:%S')

            check_query = """
            SELECT * FROM attendance 
            WHERE roll=%s AND date=%s AND lecture_no=%s
            """
            cursor.execute(check_query, (roll, date, lecture_no))
            result = cursor.fetchone()

            if result is None:
                insert_query = """
                INSERT INTO attendance (roll, date, time, lecture_no)
                VALUES (%s, %s, %s, %s)
                """
                cursor.execute(insert_query, (roll, date, time, lecture_no))
                db.commit()

                print("Marked:", roll)

            display_name = f"{roll} (L{lecture_no})"
        else:
            display_name = "Unknown"

        # ---------------- DISPLAY ----------------
        cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
        cv2.putText(frame, display_name, (x, y-10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0,255,0), 2)

    cv2.imshow("Attendance System", frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# ---------------- CLEANUP ----------------
cap.release()
cv2.destroyAllWindows()