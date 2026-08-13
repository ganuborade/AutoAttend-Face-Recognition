from flask import Flask, render_template, request, redirect, url_for, Response, session, flash
import cv2
import os
import json
import urllib.request
from dotenv import load_dotenv
load_dotenv()
import numpy as np
from datetime import datetime
import mysql.connector
import smtplib
from email.mime.text import MIMEText
import pickle
from database import db_manager
import threading
from functools import wraps
import string
import random

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

STATIC_IMAGES_DIR = os.path.join(
    BASE_DIR,
    "static",
    "images"
)

os.makedirs(
    STATIC_IMAGES_DIR,
    exist_ok=True
)

# Global status tracker for biometrics capture
capture_status = {}

# Recognition settings/state. LBPH returns a distance: LOWER = BETTER MATCH.
# These values can be overridden with environment variables.
RECOGNITION_THRESHOLD = float(os.getenv("RECOGNITION_THRESHOLD", "65"))
REQUIRED_MATCH_FRAMES = int(os.getenv("REQUIRED_MATCH_FRAMES", "5"))
recognition_state = {}


def project_path(filename):
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)


# Thread-safe caching for face recognition models and cascade classifiers
_cached_recognizer = None
_cached_id_to_label = None
_cached_face_cascade = None
_cached_model_mtime = 0.0
_cached_label_map_mtime = 0.0
_model_cache_lock = threading.Lock()


def get_face_cascade():
    """Load and cache the Haar Cascade classifier globally as it never changes."""
    global _cached_face_cascade
    if _cached_face_cascade is None:
        cascade_path = project_path("haarcascade_frontalface_default.xml")
        if not os.path.exists(cascade_path):
            raise FileNotFoundError("haarcascade_frontalface_default.xml not found.")
        face_cascade = cv2.CascadeClassifier(cascade_path)
        if face_cascade.empty():
            raise RuntimeError("Unable to load Haar Cascade.")
        _cached_face_cascade = face_cascade
    return _cached_face_cascade


def load_face_model():
    """Load LBPH model, label map and Haar cascade using absolute paths, using cached copies when files haven't changed."""
    global _cached_recognizer, _cached_id_to_label, _cached_model_mtime, _cached_label_map_mtime

    trainer_path = project_path("trainer.yml")
    label_map_path = project_path("label_map.pkl")

    if not os.path.exists(trainer_path):
        raise FileNotFoundError("trainer.yml not found. Train the model first.")
    if not os.path.exists(label_map_path):
        raise FileNotFoundError("label_map.pkl not found. Train the model first.")

    try:
        t_mtime = os.path.getmtime(trainer_path)
        l_mtime = os.path.getmtime(label_map_path)
    except OSError:
        t_mtime = 0.0
        l_mtime = 0.0

    face_cascade = get_face_cascade()

    with _model_cache_lock:
        if (_cached_recognizer is None or
            _cached_id_to_label is None or
            t_mtime > _cached_model_mtime or
            l_mtime > _cached_label_map_mtime):
            
            print(f"[CACHE] Loading/Reloading face recognition model (mtimes: {t_mtime}, {l_mtime})...")
            
            if not hasattr(cv2, "face"):
                raise RuntimeError("cv2.face is unavailable. Install opencv-contrib-python.")

            recognizer = cv2.face.LBPHFaceRecognizer_create()
            recognizer.read(trainer_path)

            with open(label_map_path, "rb") as f:
                id_to_label = pickle.load(f)

            _cached_recognizer = recognizer
            _cached_id_to_label = id_to_label
            _cached_model_mtime = t_mtime
            _cached_label_map_mtime = l_mtime

    return _cached_recognizer, _cached_id_to_label, face_cascade


def detect_largest_face(frame, face_cascade):
    """Return the largest detected face as (x,y,w,h), or None."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(
        gray, scaleFactor=1.2, minNeighbors=5, minSize=(80, 80)
    )
    if len(faces) == 0:
        return gray, None
    return gray, max(faces, key=lambda r: r[2] * r[3])


def verify_student_for_class(roll, teacher_id, year, branch, division):
    return db_manager.fetch_one(
        """SELECT id, name FROM students
           WHERE roll=%s AND teacher_id=%s
           AND year=%s AND branch=%s AND division=%s""",
        (roll, teacher_id, year, branch, division)
    )

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'teacher_id' not in session:
            flash('Please log in to access this page.', 'danger')
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated_function

def get_smtp_connection(timeout=5):
    """Establish connection to SMTP server with configurable timeout (tries Port 587 STARTTLS then Port 465 SSL fallback)."""
    sender_email = os.getenv("SENDER_EMAIL")
    sender_password = os.getenv("SENDER_PASSWORD")
    if not sender_email or not sender_password:
        raise ValueError("SENDER_EMAIL or SENDER_PASSWORD environment variables are not set.")

    e587_err = None
    # Try Port 587 (TLS) first
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587, timeout=timeout)
        server.starttls()
        server.login(sender_email, sender_password)
        return server, sender_email
    except Exception as e587:
        e587_err = e587
        print(f"[SMTP] Port 587 failed ({e587}). Trying Port 465 SSL fallback...")

    # Fallback to Port 465 (SSL) if Port 587 is blocked by host
    try:
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465, timeout=timeout)
        server.login(sender_email, sender_password)
        return server, sender_email
    except Exception as e465:
        raise RuntimeError(f"SMTP Port 587 failed ({e587_err}) and Port 465 failed ({e465}). Your cloud host is blocking SMTP traffic.")


def send_email_via_resend(api_key, to_email, subject, body):
    """Send email over HTTPS using Resend API (Port 443, never blocked by cloud hosts)."""
    url = "https://api.resend.com/emails"
    sender_email = os.getenv("RESEND_FROM_EMAIL", "AutoAttend <onboarding@resend.dev>")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "from": sender_email,
        "to": [to_email],
        "subject": subject,
        "text": body
    }
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers=headers,
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            if response.status in (200, 201):
                print(f"[RESEND API] Email successfully sent to {to_email}")
                return True, "Email sent via Resend API"
            else:
                return False, f"Resend API returned status code {response.status}"
    except urllib.error.HTTPError as e:
        err_body = e.read().decode('utf-8')
        print(f"[RESEND API] HTTP Error {e.code}: {err_body}")
        return False, f"Resend API Error {e.code}: {err_body}"
    except Exception as e:
        print(f"[RESEND API] Failed to send email via Resend: {e}")
        return False, str(e)


def send_email_message(to_email, subject, body, timeout=5):
    """Utility helper to send a single email safely with 3-tier fallback (Resend API -> SMTP 587 -> SSL 465)."""
    # Tier 1: Resend HTTP API (if RESEND_API_KEY is configured in environment)
    resend_key = os.getenv("RESEND_API_KEY")
    if resend_key:
        success, msg = send_email_via_resend(resend_key, to_email, subject, body)
        if success:
            return True, msg
        print(f"[EMAIL ENGINE] Resend API failed ({msg}), falling back to SMTP...")

    # Tier 2 & 3: Gmail SMTP (Port 587 STARTTLS -> Port 465 SSL fallback)
    try:
        server, sender_email = get_smtp_connection(timeout=timeout)
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = sender_email
        msg['To'] = to_email
        server.sendmail(sender_email, to_email, msg.as_string())
        server.quit()
        return True, "Email sent successfully via SMTP."
    except Exception as e:
        print(f"Email error for {to_email}: {e}")
        return False, str(e)


def send_welcome_email(email, name, role):
    subject = f"Welcome to AutoAttend - {role} Registration"
    body = f"Hello {name},\n\nYou have successfully registered as a {role} in the AutoAttend Attendance System.\n\nWelcome aboard!"
    success, msg = send_email_message(email, subject, body, timeout=5)
    if success:
        print(f"Welcome email sent to {role}: {email}")
    else:
        print(f"Failed to send welcome email to {email}: {msg}")

# ---------------- LOGIN & REGISTRATION ----------------
@app.route('/health')
def health():
    return "OK", 200
@app.route('/')
def home():
    if 'teacher_id' in session:
        return redirect(url_for('dashboard'))
    return render_template("login.html")

@app.route('/login', methods=['POST'])
def login():
    username = request.form['username']
    password = request.form['password']

    teacher = db_manager.fetch_one("SELECT id, name FROM teachers WHERE username=%s AND password=%s", (username, password))
    if teacher:
        session['teacher_id'] = teacher[0]
        session['teacher_name'] = teacher[1]
        return redirect(url_for('dashboard'))
    else:
        flash("Invalid Credentials or you are not registered!", "danger")
        return redirect(url_for('home'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    # If a logged-in teacher clicks register, log them out to prevent mixed sessions
    if 'teacher_id' in session:
        session.clear()
        
    if request.method == 'POST':
        name = request.form['name']
        username = request.form['username']
        password = request.form['password']
        mobile = request.form.get('mobile', '')
        address = request.form.get('address', '')
        email = request.form.get('email', '')
        college = request.form.get('college', '')
        university = request.form.get('university', '')
        sex = request.form.get('sex', 'Not Specified')
        unique_id = request.form.get('unique_id', '').strip()
        
        # Check authorization key
        auth_key_record = db_manager.fetch_one("SELECT id FROM teacher_auth_keys WHERE auth_key=%s AND is_used=0", (unique_id,))
        if not auth_key_record:
            flash("Invalid or already used Teacher Authorization ID. Registration denied.", "danger")
            return redirect(url_for('register'))

        # Check if username or email exists
        existing = db_manager.fetch_one("SELECT id FROM teachers WHERE username=%s OR email=%s", (username, email))
        if existing:
            flash("Username or Email already registered. Please choose another or login.", "warning")
            return redirect(url_for('register'))
            
        # Generate OTP and store in session
        otp = ''.join(random.choices(string.digits, k=6))
        session['reg_otp'] = otp
        session['reg_data'] = {
            'role': 'teacher',
            'name': name,
            'username': username,
            'password': password,
            'mobile': mobile,
            'address': address,
            'email': email,
            'college': college,
            'university': university,
            'sex': sex,
            'auth_key_id': auth_key_record[0]
        }
        
        if email:
            subject = "AutoAttend - Registration OTP Verification"
            body = f"Hello {name},\n\nYour OTP for AutoAttend Registration is: {otp}\n\nPlease enter this to verify your email."
            success, err_msg = send_email_message(email, subject, body, timeout=5)
            if success:
                flash("An OTP has been sent to your email to complete registration.", "info")
            else:
                print(f"OTP Email error: {err_msg}")
                flash(f"Error sending OTP: {err_msg}. Please check SMTP credentials or network settings.", "danger")
                return redirect(url_for('register'))
        else:
            flash("Email is required for OTP verification.", "danger")
            return redirect(url_for('register'))
            
        return redirect(url_for('verify_registration_otp'))
        
    return render_template("register.html")

@app.route('/logout')
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for('home'))

# ---------------- DASHBOARD ----------------
@app.route('/dashboard')
@login_required
def dashboard():
    teacher_id = session['teacher_id']
    try:
        # Fetch institutional info
        teacher_info = db_manager.fetch_one("SELECT college, university FROM teachers WHERE id=%s", (teacher_id,))
        college = teacher_info[0] if teacher_info and teacher_info[0] else "Not specified"
        university = teacher_info[1] if teacher_info and teacher_info[1] else "Not specified"
        
        # Get chart data for last 5 lectures using a single query
        results = db_manager.fetch_all("""
            SELECT lecture_no, COUNT(*) 
            FROM attendance 
            WHERE teacher_id = %s 
            GROUP BY lecture_no 
            ORDER BY lecture_no DESC 
            LIMIT 5
        """, (teacher_id,))
        results = results[::-1]
        labels = [f"Lecture {r[0]}" for r in results]
        data_points = [r[1] for r in results]
    except:
        labels = []
        data_points = []
        college = "Not specified"
        university = "Not specified"
        
    return render_template("dashboard.html", labels=labels, data=data_points, college=college, university=university)

# ---------------- ADD STUDENT ----------------
@app.route('/add_student', methods=['GET', 'POST'])
@login_required
def add_student():
    teacher_id = session['teacher_id']

    if request.method == 'POST':
        name = request.form['name'].strip()
        roll = request.form['roll'].strip()
        email = request.form['email'].strip()
        year = request.form.get('year', '1st Year').strip()
        branch = request.form.get('branch', 'Computer Science').strip()
        division = request.form.get('division', 'A').strip()

        existing = db_manager.fetch_one(
            "SELECT id FROM students WHERE teacher_id=%s AND (roll=%s OR email=%s)",
            (teacher_id, roll, email)
        )
        if existing:
            flash("A student with this Roll Number or Email already exists in your class.", "danger")
            return redirect(url_for('add_student'))

        folder_path = os.path.join(project_path('static'), 'images', roll)
        os.makedirs(folder_path, exist_ok=True)

        query = """INSERT INTO students
                   (name, roll, email, year, branch, division, teacher_id)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)"""
        try:
            db_manager.execute_query(query, (name, roll, email, year, branch, division, teacher_id))
        except Exception as e:
            print("Student insertion error:", e)
            flash("Unable to register student.", "danger")
            return redirect(url_for('add_student'))

        capture_status[roll] = "capturing"
        return redirect(url_for('capture_biometrics', roll=roll, name=name, email=email))

    return render_template("add_student.html")


@app.route('/capture_biometrics/<roll>')
@login_required
def capture_biometrics(roll):
    name = request.args.get('name', 'Student')
    email = request.args.get('email', '')
    return render_template("capture_biometrics.html", roll=roll, name=name, email=email)


def background_tasks(roll, name, email):
    try:
        # Import the training module only when training is actually requested.
        # This prevents model training from happening when Gunicorn imports app.py.
        from train import train_model

        print(f"Training model after biometric capture for Roll No: {roll}")
        success = train_model()
        if not success:
            raise RuntimeError("Model training returned False.")

        print("Model training completed.")

    except Exception as e:
        print("Model training error:", e)
        capture_status[roll] = "error"
        return

    if email:
        send_welcome_email(email, name, "student")

    capture_status[roll] = "done"


@app.route('/capture_frame/<roll>', methods=['POST'])
def capture_frame(roll):
    """Receive camera frames from the browser and save 30 detected face crops."""
    if 'teacher_id' not in session and 'hod_id' not in session:
        return {"success": False, "message": "Login required."}, 401

    try:
        if 'frame' not in request.files:
            return {"success": False, "message": "No camera frame received."}, 400

        image_bytes = request.files['frame'].read()
        frame = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            return {"success": False, "message": "Could not decode camera frame."}, 400

        face_cascade = get_face_cascade()
        gray, face_rect = detect_largest_face(frame, face_cascade)
        folder_path = os.path.join(project_path('static'), 'images', roll)
        os.makedirs(folder_path, exist_ok=True)

        existing_images = [
            f for f in os.listdir(folder_path)
            if f.lower().endswith(('.jpg', '.jpeg', '.png'))
        ]
        count = len(existing_images)

        if count >= 30:
            if capture_status.get(roll) != "processing":
                capture_status[roll] = "processing"
                name = request.form.get('name', 'Student')
                email = request.form.get('email', '')
                threading.Thread(target=background_tasks, args=(roll, name, email), daemon=True).start()
            return {"success": True, "captured": True, "count": 30, "total": 30, "completed": True, "message": "30 face images captured. Training model..."}

        if face_rect is None:
            return {"success": True, "captured": False, "count": count, "total": 30, "completed": False, "message": "No face detected. Keep your face inside the camera."}

        x, y, w, h = face_rect
        face_image = gray[y:y+h, x:x+w]
        if face_image.size == 0:
            return {"success": True, "captured": False, "count": count, "total": 30, "message": "Invalid face detected."}

        image_name = os.path.join(folder_path, f"{count}.jpg")
        if not cv2.imwrite(image_name, face_image):
            return {"success": False, "message": "Unable to save face image."}, 500

        count += 1
        capture_status[roll] = "capturing"

        if count >= 30:
            capture_status[roll] = "processing"
            name = request.form.get('name', 'Student')
            email = request.form.get('email', '')
            threading.Thread(target=background_tasks, args=(roll, name, email), daemon=True).start()

        return {
            "success": True, "captured": True, "count": count, "total": 30,
            "completed": count >= 30,
            "message": "30 images captured. Training model..." if count >= 30 else f"Face captured: {count}/30"
        }

    except Exception as e:
        print("Capture frame error:", e)
        capture_status[roll] = "error"
        return {"success": False, "message": "Capture error: " + str(e)}, 500


# ---------------- LEGACY LOCAL CAMERA CAPTURE ----------------
def gen_capture_frames(roll, name, email):
    folder_path = os.path.join(project_path('static'), 'images', roll)
    os.makedirs(folder_path, exist_ok=True)
    cap = cv2.VideoCapture(0)
    count = 0

    try:
        _, _, face_cascade = load_face_model()
        while count < 30:
            success, frame = cap.read()
            if not success:
                break
            gray, face_rect = detect_largest_face(frame, face_cascade)
            if face_rect is not None:
                x, y, w, h = face_rect
                cv2.rectangle(frame, (x, y), (x+w, y+h), (255, 0, 0), 2)
                cv2.imwrite(os.path.join(folder_path, f"{count}.jpg"), gray[y:y+h, x:x+w])
                count += 1
            cv2.putText(frame, f"Captured: {count}/30", (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
            ret, buffer = cv2.imencode('.jpg', frame)
            if ret:
                yield b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n'
    finally:
        cap.release()

    capture_status[roll] = "processing"
    threading.Thread(target=background_tasks, args=(roll, name, email), daemon=True).start()
    yield b'--frame\r\nContent-Type: text/plain\r\n\r\nDONE\r\n'


@app.route('/video_feed/capture/<roll>')
@login_required
def video_feed_capture(roll):
    return Response(
        gen_capture_frames(roll, request.args.get('name', ''), request.args.get('email', '')),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )


@app.route('/check_status/<roll>')
def check_status(roll):
    return {"status": capture_status.get(roll, "unknown")}


# ---------------- START LECTURE ----------------
@app.route('/start_lecture', methods=['GET', 'POST'])
@login_required
def start_lecture():
    if request.method == 'GET':
        return render_template("lecture.html")

    lecture_no = request.form['lecture_no']
    subject = request.form.get('subject', 'Unknown Subject')
    year = request.form.get('year', '1st Year')
    branch = request.form.get('branch', 'Computer Science')
    division = request.form.get('division', 'A')

    # Store in session
    session['current_lecture_info'] = {
        'lecture_no': lecture_no,
        'subject': subject,
        'year': year,
        'branch': branch,
        'division': division
    }

    return redirect(url_for('live_lecture', lecture_no=lecture_no))

@app.route('/live_lecture/<lecture_no>')
@login_required
def live_lecture(lecture_no):
    lecture_info = session.get('current_lecture_info', {})
    subject = lecture_info.get('subject', 'Unknown Subject')
    return render_template("live_lecture.html", lecture_no=lecture_no, subject=subject)

def gen_lecture_frames(lecture_no, teacher_id, subject, year, branch, division):
    """Legacy local-camera route. Browser deployment should use /recognize_frame instead."""
    try:
        recognizer, id_to_label, face_cascade = load_face_model()
    except Exception as e:
        print("Model error:", e)
        return

    cap = cv2.VideoCapture(0)
    last_seen = {}
    recognition_counts = {}

    try:
        while True:
            success, frame = cap.read()
            if not success:
                break

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(gray, 1.2, 5, minSize=(80, 80))

            for (x, y, w, h) in faces:
                face = gray[y:y+h, x:x+w]
                if face.size == 0:
                    continue

                face_proc = cv2.resize(face, (200, 200))
                face_proc = cv2.equalizeHist(face_proc)
                person_id, distance = recognizer.predict(face_proc)
                roll = id_to_label.get(person_id, "Unknown") if distance < RECOGNITION_THRESHOLD else "Unknown"
                student_check = verify_student_for_class(roll, teacher_id, year, branch, division) if roll != "Unknown" else None

                if student_check:
                    recognition_counts[roll] = recognition_counts.get(roll, 0) + 1
                    if recognition_counts[roll] >= REQUIRED_MATCH_FRAMES:
                        now = datetime.now()
                        if roll not in last_seen or (now - last_seen[roll]).total_seconds() >= 5:
                            last_seen[roll] = now
                            date = now.strftime('%Y-%m-%d')
                            time = now.strftime('%H:%M:%S')
                            exists = db_manager.fetch_one(
                                "SELECT * FROM attendance WHERE roll=%s AND date=%s AND lecture_no=%s AND teacher_id=%s AND subject=%s",
                                (roll, date, lecture_no, teacher_id, subject)
                            )
                            if exists is None:
                                db_manager.execute_query(
                                    "INSERT INTO attendance (roll,date,time,lecture_no,teacher_id,subject,year,branch,division) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                                    (roll, date, time, lecture_no, teacher_id, subject, year, branch, division)
                                )
                        label = f"{student_check[1]} - Roll {roll}"
                        color = (0, 255, 0)
                    else:
                        label = f"Verifying {roll} ({recognition_counts[roll]}/{REQUIRED_MATCH_FRAMES})"
                        color = (0, 165, 255)
                else:
                    label = "Unknown / Not in this class"
                    color = (0, 0, 255)
                    recognition_counts.clear()

                cv2.rectangle(frame, (x, y), (x+w, y+h), color, 2)
                cv2.putText(frame, label, (x, max(25, y-10)), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

            ret, buffer = cv2.imencode('.jpg', frame)
            if ret:
                yield b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n'
    finally:
        cap.release()


@app.route('/video_feed/lecture/<lecture_no>')
def video_feed_lecture(lecture_no):
    teacher_id = session.get('teacher_id')
    if teacher_id is None:
        return redirect(url_for('home'))
    lecture_info = session.get('current_lecture_info', {})
    subject = lecture_info.get('subject', 'Unknown Subject')
    year = lecture_info.get('year', '1st Year')
    branch = lecture_info.get('branch', 'Computer Science')
    division = lecture_info.get('division', 'A')
    return Response(gen_lecture_frames(lecture_no, teacher_id, subject, year, branch, division), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/recognize_frame/<lecture_no>', methods=['POST'])
@login_required
def recognize_frame(lecture_no):
    """Recognize one browser-camera frame, verify class membership, require stable matches, then mark attendance."""
    try:
        if 'frame' not in request.files:
            return {"success": False, "message": "No camera frame received."}, 400

        image_bytes = request.files['frame'].read()
        if not image_bytes:
            return {"success": False, "message": "Empty camera frame."}, 400

        frame = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            return {"success": False, "message": "Could not decode camera frame."}, 400

        teacher_id = session['teacher_id']
        lecture_info = session.get('current_lecture_info', {})
        subject = lecture_info.get('subject', 'Unknown Subject')
        year = lecture_info.get('year', '1st Year')
        branch = lecture_info.get('branch', 'Computer Science')
        division = lecture_info.get('division', 'A')

        recognizer, id_to_label, face_cascade = load_face_model()
        gray, face_rect = detect_largest_face(frame, face_cascade)

        state_key = f"{teacher_id}:{lecture_no}"
        state = recognition_state.setdefault(state_key, {"roll": None, "count": 0})

        if face_rect is None:
            state['roll'] = None
            state['count'] = 0
            return {"success": True, "recognized": False, "message": "No face detected."}

        x, y, w, h = face_rect
        face = gray[y:y+h, x:x+w]
        if face.size == 0:
            return {"success": True, "recognized": False, "message": "Invalid face detected."}

        face_proc = cv2.resize(face, (200, 200))
        face_proc = cv2.equalizeHist(face_proc)
        person_id, distance = recognizer.predict(face_proc)
        print(f"Prediction: ID={person_id}, LBPH distance={distance:.2f}, threshold={RECOGNITION_THRESHOLD}")

        # Lower LBPH distance is a better match. Never accept a prediction above the threshold.
        if distance >= RECOGNITION_THRESHOLD:
            state['roll'] = None
            state['count'] = 0
            return {
                "success": True, "recognized": False,
                "message": f"Face detected, but not matched. Match distance: {distance:.1f}"
            }

        roll = str(id_to_label.get(person_id, "Unknown"))
        if roll == "Unknown":
            state['roll'] = None
            state['count'] = 0
            return {"success": True, "recognized": False, "message": "Model returned an unknown student ID."}

        student = verify_student_for_class(roll, teacher_id, year, branch, division)
        if not student:
            state['roll'] = None
            state['count'] = 0
            return {
                "success": True, "recognized": False,
                "roll": roll,
                "message": f"Roll {roll} is not registered in this class."
            }

        # Require the same roll to be recognized in several consecutive requests.
        if state['roll'] == roll:
            state['count'] += 1
        else:
            state['roll'] = roll
            state['count'] = 1

        name = student[1]
        if state['count'] < REQUIRED_MATCH_FRAMES:
            return {
                "success": True, "recognized": False, "verifying": True,
                "roll": roll, "name": name,
                "distance": round(float(distance), 2),
                "message": f"Verifying {name} - Roll {roll} ({state['count']}/{REQUIRED_MATCH_FRAMES})"
            }

        now = datetime.now()
        date = now.strftime('%Y-%m-%d')
        time = now.strftime('%H:%M:%S')

        check_query = """SELECT * FROM attendance
                         WHERE roll=%s AND date=%s AND lecture_no=%s
                         AND teacher_id=%s AND subject=%s"""
        result = db_manager.fetch_one(check_query, (roll, date, lecture_no, teacher_id, subject))

        if result is None:
            insert_query = """INSERT INTO attendance
                (roll,date,time,lecture_no,teacher_id,subject,year,branch,division)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)"""
            db_manager.execute_query(insert_query, (roll, date, time, lecture_no, teacher_id, subject, year, branch, division))
            message = f"Attendance marked: {name} - Roll {roll}"
            marked = True
        else:
            message = f"Already present: {name} - Roll {roll}"
            marked = False

        return {
            "success": True, "recognized": True, "marked": marked,
            "roll": roll, "name": name,
            "distance": round(float(distance), 2),
            "message": message
        }

    except Exception as e:
        print("Recognition error:", e)
        return {"success": False, "message": "Recognition error: " + str(e)}, 500


@app.route('/delete_student/<roll>', methods=['POST'])
@login_required
def delete_student(roll):
    teacher_id = session['teacher_id']
    # Delete from DB
    db_manager.execute_query("DELETE FROM students WHERE roll=%s AND teacher_id=%s", (roll, teacher_id))
    db_manager.execute_query("DELETE FROM attendance WHERE roll=%s AND teacher_id=%s", (roll, teacher_id))
    
    # Delete folder
    import shutil
    folder_path = f"static/images/{roll}"
    if os.path.exists(folder_path):
        shutil.rmtree(folder_path)
        
    # Retrain model since a student is removed
    from train import train_model
    train_model()
    
    return redirect(url_for('view_students'))

# ---------------- VIEW STUDENTS ----------------
@app.route('/view_students', methods=['GET'])
@login_required
def view_students():
    teacher_id = session['teacher_id']
    year = request.args.get('year', '')
    branch = request.args.get('branch', '')
    division = request.args.get('division', '')
    search = request.args.get('search', '')

    query = "SELECT name, roll, email, year, branch, division FROM students WHERE teacher_id=%s"
    params = [teacher_id]

    if year:
        query += " AND year=%s"
        params.append(year)
    if branch:
        query += " AND branch=%s"
        params.append(branch)
    if division:
        query += " AND division=%s"
        params.append(division)
    if search:
        query += " AND name LIKE %s"
        params.append(f"%{search}%")

    data = db_manager.fetch_all(query, tuple(params))
    return render_template("view_students.html", students=data, filters={'year': year, 'branch': branch, 'division': division, 'search': search})

# ---------------- VIEW ATTENDANCE ----------------
@app.route('/view_attendance', methods=['GET'])
@login_required
def view_attendance():
    teacher_id = session['teacher_id']
    year = request.args.get('year', '')
    branch = request.args.get('branch', '')
    division = request.args.get('division', '')

    query = """
        SELECT a.roll, a.date, a.time, a.lecture_no, s.name, s.year, s.branch, s.division, a.subject 
        FROM attendance a
        LEFT JOIN students s ON a.roll = s.roll
        WHERE a.teacher_id=%s
    """
    params = [teacher_id]

    if year:
        query += " AND s.year=%s"
        params.append(year)
    if branch:
        query += " AND s.branch=%s"
        params.append(branch)
    if division:
        query += " AND s.division=%s"
        params.append(division)

    query += " ORDER BY a.date DESC, a.time DESC"

    data = db_manager.fetch_all(query, tuple(params))
    return render_template("view_attendance.html", records=data, filters={'year': year, 'branch': branch, 'division': division})

# ---------------- EMAIL ----------------
@app.route('/send_email', methods=['GET', 'POST'])
@login_required
def send_email():
    teacher_id = session['teacher_id']
    if request.method == 'GET':
        lecture_no = request.args.get('lecture_no', '1')
        today = datetime.now().strftime('%Y-%m-%d')

        students = db_manager.fetch_all("SELECT roll, name, email FROM students WHERE teacher_id=%s", (teacher_id,))

        query_attendance = """
            SELECT roll FROM attendance 
            WHERE date=%s AND lecture_no=%s AND teacher_id=%s
        """
        present_data = db_manager.fetch_all(query_attendance, (today, lecture_no, teacher_id))
        present = [row[0] for row in present_data]
        
        absent_students = [s for s in students if s[0] not in present]
        
        return render_template("send_email.html", absentees=absent_students, lecture_no=lecture_no)

    if request.method == 'POST':
        selected_rolls = request.form.getlist('selected_students')
        lecture_no = request.form.get('lecture_no')
        
        if not selected_rolls:
            return "No students selected!"
            
        placeholders = ', '.join(['%s'] * len(selected_rolls))
        query = f"SELECT roll, email FROM students WHERE roll IN ({placeholders}) AND teacher_id=%s"
        params = tuple(selected_rolls) + (teacher_id,)
        students_to_email = db_manager.fetch_all(query, params)

        sent_count = 0
        for roll, email in students_to_email:
            subject = "Attendance Alert - Absence Notification"
            body = f"Dear Student ({roll}),\n\nYou were marked absent for Lecture {lecture_no}. Please ensure you attend the next classes.\n\nRegards,\nAutoAttend Attendance System"

            success, msg = send_email_message(email, subject, body, timeout=5)
            if success:
                sent_count += 1

        if sent_count > 0:
            flash(f"Successfully sent alert emails to {sent_count} students!", "success")
        else:
            flash("Failed to send alert emails. Please configure RESEND_API_KEY or check network/SMTP settings.", "danger")
        return redirect(url_for('send_email', lecture_no=lecture_no))

# ---------------- NEW PROFESSIONAL ROUTES ----------------
@app.route('/analytics')
@login_required
def analytics():
    teacher_id = session['teacher_id']
    try:
        total_students = db_manager.fetch_one("SELECT COUNT(*) FROM students WHERE teacher_id=%s", (teacher_id,))[0]
        total_lectures = db_manager.fetch_one("SELECT COUNT(DISTINCT date, lecture_no, subject) FROM attendance WHERE teacher_id=%s", (teacher_id,))[0]
        total_attendance = db_manager.fetch_one(
            """SELECT COUNT(*) FROM attendance 
               WHERE teacher_id=%s AND roll IN (SELECT roll FROM students WHERE teacher_id=%s)""",
            (teacher_id, teacher_id)
        )[0]
        
        if total_students > 0 and total_lectures > 0:
            avg_attendance = min(100, int((total_attendance / (total_students * total_lectures)) * 100))
        else:
            avg_attendance = 0
            
        # Simplified "below 75%" logic for demo
        below_75 = max(0, total_students - int(total_attendance / total_lectures if total_lectures > 0 else 0))
        
        # Pie chart data
        present = total_attendance
        absent = max(0, (total_students * total_lectures) - present)
        
    except:
        avg_attendance = 0
        total_lectures = 0
        below_75 = 0
        present = 0
        absent = 0

    return render_template("analytics.html", 
                           avg_attendance=avg_attendance, 
                           total_lectures=total_lectures,
                           below_75=below_75,
                           present=present,
                           absent=absent)

@app.route('/settings')
@login_required
def settings():
    return render_template("settings.html")

@app.route('/retrain_model', methods=['POST'])
@login_required
def retrain_model_route():
    try:
        # Import only when the user explicitly requests retraining.
        from train import train_model

        success = train_model()
        if success:
            flash("Model retraining completed successfully!", "success")
        else:
            flash("Model retraining failed. Check the server logs.", "danger")
    except Exception as e:
        flash(f"Error during retraining: {e}", "danger")
    return redirect(url_for('settings'))

@app.route('/support')
@login_required
def support():
    return render_template("support.html")

# ---------------- HOD PORTAL ----------------
@app.route('/hod_register', methods=['GET', 'POST'])
def hod_register():
    if 'hod_id' in session:
        session.clear()
        
    if request.method == 'POST':
        name = request.form['name']
        mobile = request.form.get('mobile', '')
        address = request.form.get('address', '')
        username = request.form['username']
        password = request.form['password']
        unique_id = request.form['unique_id'].strip()
        email = request.form.get('email', '')
        college = request.form.get('college', '')
        university = request.form.get('university', '')
        sex = request.form.get('sex', 'Not Specified')
        
        # Check authorization key from database
        auth_key_record = db_manager.fetch_one("SELECT id FROM hod_auth_keys WHERE auth_key=%s AND is_used=0", (unique_id,))
        if not auth_key_record:
            flash("Invalid or already used Authorization Unique ID. Registration denied.", "danger")
            return redirect(url_for('hod_register'))
            
        # Check if username or email exists
        existing = db_manager.fetch_one("SELECT id FROM hods WHERE username=%s OR email=%s", (username, email))
        if existing:
            flash("Username or Email already registered. Please choose another.", "warning")
            return redirect(url_for('hod_register'))
            
        otp = ''.join(random.choices(string.digits, k=6))
        session['reg_otp'] = otp
        session['reg_data'] = {
            'role': 'hod',
            'name': name,
            'username': username,
            'password': password,
            'mobile': mobile,
            'address': address,
            'unique_id': unique_id,
            'email': email,
            'college': college,
            'university': university,
            'sex': sex,
            'auth_key_id': auth_key_record[0]
        }
        
        if email:
            subject = "AutoAttend - Registration OTP Verification"
            body = f"Hello {name},\n\nYour OTP for AutoAttend Registration is: {otp}\n\nPlease enter this to verify your email."
            success, err_msg = send_email_message(email, subject, body, timeout=5)
            if success:
                flash("An OTP has been sent to your email to complete registration.", "info")
            else:
                print(f"OTP Email error: {err_msg}")
                flash(f"Error sending OTP: {err_msg}. Please check SMTP credentials or network settings.", "danger")
                return redirect(url_for('hod_register'))
        else:
            flash("Email is required for OTP verification.", "danger")
            return redirect(url_for('hod_register'))
            
        return redirect(url_for('verify_registration_otp'))
        
    return render_template("hod_register.html")

@app.route('/hod_login', methods=['GET', 'POST'])
def hod_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        hod = db_manager.fetch_one("SELECT id FROM hods WHERE username=%s AND password=%s", (username, password))
        if hod:
            session['hod_id'] = hod[0]
            return redirect(url_for('hod_dashboard'))
        else:
            flash("Invalid HOD Credentials!", "danger")
            return redirect(url_for('hod_login'))
            
    return render_template("hod_login.html")

def hod_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'hod_id' not in session:
            flash('Please log in as HOD to access this page.', 'danger')
            return redirect(url_for('hod_login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/hod_logout')
def hod_logout():
    session.pop('hod_id', None)
    flash("HOD logged out.", "info")
    return redirect(url_for('home'))

@app.route('/hod_dashboard')
@hod_required
def hod_dashboard():
    hod_id = session['hod_id']
    hod_info = db_manager.fetch_one("SELECT college, university FROM hods WHERE id=%s", (hod_id,))
    college = hod_info[0] if hod_info and hod_info[0] else "Not specified"
    university = hod_info[1] if hod_info and hod_info[1] else "Not specified"

    query = """
        SELECT t.id, t.name, t.username, COUNT(s.id) as student_count
        FROM teachers t
        LEFT JOIN students s ON t.id = s.teacher_id
        GROUP BY t.id, t.name, t.username
    """
    teachers_data = db_manager.fetch_all(query)
    return render_template("hod_dashboard.html", teachers=teachers_data, college=college, university=university)

@app.route('/hod/teacher/<int:teacher_id>')
@hod_required
def hod_teacher_view(teacher_id):
    teacher = db_manager.fetch_one("SELECT name FROM teachers WHERE id=%s", (teacher_id,))
    if not teacher:
        return "Teacher not found", 404
        
    try:
        total_students = db_manager.fetch_one("SELECT COUNT(*) FROM students WHERE teacher_id=%s", (teacher_id,))[0]
        total_lectures = db_manager.fetch_one("SELECT COUNT(DISTINCT date, lecture_no, subject) FROM attendance WHERE teacher_id=%s", (teacher_id,))[0]
        total_attendance = db_manager.fetch_one(
            """SELECT COUNT(*) FROM attendance 
               WHERE teacher_id=%s AND roll IN (SELECT roll FROM students WHERE teacher_id=%s)""",
            (teacher_id, teacher_id)
        )[0]
        
        if total_students > 0 and total_lectures > 0:
            avg_attendance = min(100, int((total_attendance / (total_students * total_lectures)) * 100))
        else:
            avg_attendance = 0
            
        below_75 = max(0, total_students - int(total_attendance / total_lectures if total_lectures > 0 else 0))
        present = total_attendance
        absent = max(0, (total_students * total_lectures) - present)
        
    except:
        avg_attendance = 0
        total_lectures = 0
        below_75 = 0
        present = 0
        absent = 0

    return render_template("analytics.html", 
                           avg_attendance=avg_attendance, 
                           total_lectures=total_lectures,
                           below_75=below_75,
                           present=present,
                           absent=absent,
                           teacher_name=teacher[0],
                           is_hod_view=True)

@app.route('/hod/teacher/<int:teacher_id>/students')
@hod_required
def hod_teacher_students(teacher_id):
    teacher = db_manager.fetch_one("SELECT name FROM teachers WHERE id=%s", (teacher_id,))
    if not teacher:
        flash("Teacher not found", "danger")
        return redirect(url_for('hod_dashboard'))
        
    students = db_manager.fetch_all("SELECT name, roll, email, year, branch, division FROM students WHERE teacher_id=%s", (teacher_id,))
    return render_template("hod_teacher_students.html", students=students, teacher_name=teacher[0], teacher_id=teacher_id)

def retrain_model_background():
    try:
        from train import train_model
        print("Starting background model retraining...")
        success = train_model()
        if success:
            print("Background model retraining completed.")
        else:
            print("Background model retraining failed.")
    except Exception as e:
        print("Background model retraining error:", e)


@app.route('/hod/teacher/<int:teacher_id>/delete_student/<roll>', methods=['POST'])
@hod_required
def hod_delete_student(teacher_id, roll):
    db_manager.execute_query("DELETE FROM students WHERE roll=%s AND teacher_id=%s", (roll, teacher_id))
    db_manager.execute_query("DELETE FROM attendance WHERE roll=%s AND teacher_id=%s", (roll, teacher_id))
    
    import shutil
    folder_path = f"static/images/{roll}"
    if os.path.exists(folder_path):
        shutil.rmtree(folder_path)
        
    threading.Thread(
        target=retrain_model_background,
        daemon=True
    ).start()
    flash(f"Student {roll} deleted successfully.", "success")
    return redirect(url_for('hod_teacher_students', teacher_id=teacher_id))

@app.route('/hod/teacher/<int:teacher_id>/settings')
@hod_required
def hod_teacher_settings(teacher_id):
    teacher = db_manager.fetch_one("SELECT id, name, username, mobile, address, email, college, university FROM teachers WHERE id=%s", (teacher_id,))
    if not teacher:
        flash("Teacher not found", "danger")
        return redirect(url_for('hod_dashboard'))
    return render_template("hod_teacher_settings.html", teacher=teacher)

@app.route('/hod/teacher/<int:teacher_id>/delete_teacher', methods=['POST'])
@hod_required
def hod_delete_teacher(teacher_id):
    db_manager.execute_query("DELETE FROM students WHERE teacher_id=%s", (teacher_id,))
    db_manager.execute_query("DELETE FROM attendance WHERE teacher_id=%s", (teacher_id,))
    db_manager.execute_query("DELETE FROM teachers WHERE id=%s", (teacher_id,))
    flash("Teacher deleted successfully.", "success")
    return redirect(url_for('hod_dashboard'))

@app.route('/hod/teacher/<int:teacher_id>/add_student', methods=['GET', 'POST'])
@hod_required
def hod_add_student(teacher_id):
    teacher = db_manager.fetch_one("SELECT name FROM teachers WHERE id=%s", (teacher_id,))
    if not teacher:
        return redirect(url_for('hod_dashboard'))
        
    if request.method == 'POST':
        name = request.form['name']
        roll = request.form['roll']
        email = request.form['email']
        year = request.form.get('year', '1st Year')
        branch = request.form.get('branch', 'Computer Science')
        division = request.form.get('division', 'A')

        folder_path = f"static/images/{roll}"
        os.makedirs(folder_path, exist_ok=True)

        query = "INSERT INTO students (name, roll, email, year, branch, division, teacher_id) VALUES (%s, %s, %s, %s, %s, %s, %s)"
        try:
            db_manager.execute_query(query, (name, roll, email, year, branch, division, teacher_id))
        except Exception as e:
            pass 

        capture_status[roll] = "capturing"
        return redirect(url_for('hod_capture_biometrics', teacher_id=teacher_id, roll=roll, name=name, email=email))

    return render_template("add_student.html", is_hod=True, teacher_id=teacher_id)

@app.route('/hod/teacher/<int:teacher_id>/capture_biometrics/<roll>')
@hod_required
def hod_capture_biometrics(teacher_id, roll):
    name = request.args.get('name', 'Student')
    email = request.args.get('email', '')
    return render_template("capture_biometrics.html", roll=roll, name=name, email=email, is_hod=True, teacher_id=teacher_id)

# ---------------- STUDENT PORTAL ----------------
def student_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'student_id' not in session:
            flash('Please log in as a student to access this page.', 'danger')
            return redirect(url_for('student_login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/student_login', methods=['GET', 'POST'])
def student_login():
    if request.method == 'POST':
        roll_number = request.form['roll_number']
        password = request.form['password']
        
        student = db_manager.fetch_one("SELECT id, name, roll_number FROM student_users WHERE roll_number=%s AND password=%s", (roll_number, password))
        if student:
            session['student_id'] = student[0]
            session['student_name'] = student[1]
            session['student_roll'] = student[2]
            return redirect(url_for('student_dashboard'))
        else:
            flash("Invalid Roll Number or Password!", "danger")
            return redirect(url_for('student_login'))
            
    return render_template("student_login.html")

@app.route('/student_register', methods=['GET', 'POST'])
def student_register():
    if request.method == 'POST':
        name = request.form['name']
        roll_number = request.form['roll_number']
        email = request.form['email']
        password = request.form['password']
        college = request.form.get('college', '')
        university = request.form.get('university', '')
        district = request.form.get('district', '')
        taluka = request.form.get('taluka', '')
        mobile = request.form.get('mobile', '')
        address = request.form.get('address', '')
        class_name = request.form.get('class_name', '')
        branch = request.form.get('branch', '')
        sex = request.form.get('sex', 'Not Specified')
        
        existing = db_manager.fetch_one("SELECT id FROM student_users WHERE roll_number=%s OR email=%s", (roll_number, email))
        if existing:
            flash("Roll Number or Email already registered. Please login.", "warning")
            return redirect(url_for('student_login'))
            
        otp = ''.join(random.choices(string.digits, k=6))
        session['reg_otp'] = otp
        session['reg_data'] = {
            'role': 'student',
            'name': name,
            'roll_number': roll_number,
            'email': email,
            'password': password,
            'college': college,
            'university': university,
            'district': district,
            'taluka': taluka,
            'mobile': mobile,
            'address': address,
            'class_name': class_name,
            'branch': branch,
            'sex': sex
        }
        
        if email:
            subject = "AutoAttend - Registration OTP Verification"
            body = f"Hello {name},\n\nYour OTP for AutoAttend Registration is: {otp}\n\nPlease enter this to verify your email."
            success, err_msg = send_email_message(email, subject, body, timeout=5)
            if success:
                flash("An OTP has been sent to your email to complete registration.", "info")
            else:
                print(f"OTP Email error: {err_msg}")
                flash(f"Error sending OTP: {err_msg}. Please check SMTP credentials or network settings.", "danger")
                return redirect(url_for('student_register'))
        else:
            flash("Email is required for OTP verification.", "danger")
            return redirect(url_for('student_register'))
            
        return redirect(url_for('verify_registration_otp'))
        
    return render_template("student_register.html")

@app.route('/student_logout')
def student_logout():
    session.pop('student_id', None)
    session.pop('student_name', None)
    session.pop('student_roll', None)
    flash("Student logged out.", "info")
    return redirect(url_for('home'))

@app.route('/student_dashboard')
@student_required
def student_dashboard():
    roll = session['student_roll']
    
    query = """
        SELECT a.date, a.time, a.lecture_no, t.name as teacher_name, a.subject 
        FROM attendance a
        LEFT JOIN teachers t ON a.teacher_id = t.id
        WHERE a.roll=%s
        ORDER BY a.date DESC, a.time DESC
    """
    records = db_manager.fetch_all(query, (roll,))
    total_attended = len(records)
    
    # Calculate unique lectures attended vs total available? 
    # For simplicity, we just show total present count and history since calculating total possible lectures across all teachers is complex without enrollment maps.
    
    return render_template("student_dashboard.html", records=records, total_attended=total_attended)

def generate_random_password(length=8):
    characters = string.ascii_letters + string.digits
    return ''.join(random.choice(characters) for i in range(length))

# ---------------- FORGOT PASSWORD ----------------
@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        role = request.form['role']
        identifier = request.form['identifier']
        email = request.form['email']
        
        table = ""
        id_col = ""
        
        if role == 'teacher':
            table = "teachers"
            id_col = "username"
        elif role == 'hod':
            table = "hods"
            id_col = "username"
        elif role == 'student':
            table = "student_users"
            id_col = "roll_number"
            
        if table:
            user = db_manager.fetch_one(f"SELECT id FROM {table} WHERE {id_col}=%s AND email=%s", (identifier, email))
            if user:
                new_pass = generate_random_password()
                db_manager.execute_query(f"UPDATE {table} SET password=%s WHERE id=%s", (new_pass, user[0]))
                
                subject = "AutoAttend - Password Reset"
                body = f"Hello,\n\nYour password has been successfully reset.\n\nYour new password is: {new_pass}\n\nPlease login and keep this safe."
                success, err_msg = send_email_message(email, subject, body, timeout=5)
                if success:
                    flash("A new password has been sent to your email.", "success")
                else:
                    print(f"Password reset email error: {err_msg}")
                    flash(f"Error sending email: {err_msg}. Please try again later.", "danger")
            else:
                flash("No matching record found for the provided details.", "danger")
                
        return redirect(url_for('forgot_password'))
        
    return render_template("forgot_password.html")

def generate_otp(length=6):
    return ''.join(random.choices(string.digits, k=length))

# ---------------- CHANGE PASSWORD (LOGGED IN) ----------------
@app.route('/change_password', methods=['GET', 'POST'])
def change_password():
    role = None
    user_id = None
    
    if 'teacher_id' in session:
        role = 'teacher'
        user_id = session['teacher_id']
    elif 'hod_id' in session:
        role = 'hod'
        user_id = session['hod_id']
    elif 'student_id' in session:
        role = 'student'
        user_id = session['student_id']
    else:
        flash("Please log in to change your password.", "warning")
        return redirect(url_for('home'))
        
    if request.method == 'POST':
        action = request.form.get('action')
        
        # Determine table and fetch email
        if role == 'teacher':
            email = db_manager.fetch_one("SELECT email FROM teachers WHERE id=%s", (user_id,))[0]
            table = "teachers"
        elif role == 'hod':
            email = db_manager.fetch_one("SELECT email FROM hods WHERE id=%s", (user_id,))[0]
            table = "hods"
        elif role == 'student':
            email = db_manager.fetch_one("SELECT email FROM student_users WHERE id=%s", (user_id,))[0]
            table = "student_users"
            
        if not email:
            flash("No email registered with your account. Cannot send OTP.", "danger")
            return redirect(url_for(f'{role}_profile'))
            
        if action == 'send_otp':
            otp = generate_otp()
            session['change_pwd_otp'] = otp
            
            subject = "AutoAttend - Password Change Verification"
            body = f"Hello,\n\nYour OTP to change your password is: {otp}\n\nDo not share this with anyone."
            success, err_msg = send_email_message(email, subject, body, timeout=5)
            if success:
                flash("An OTP has been sent to your email.", "success")
                return render_template("change_password.html", otp_sent=True, role=role, email=email)
            else:
                print(f"Change password OTP email error: {err_msg}")
                flash(f"Error sending OTP email: {err_msg}. Please try again later.", "danger")
                return redirect(url_for(f'{role}_profile'))
                
        elif action == 'verify_otp':
            user_otp = request.form.get('otp')
            new_password = request.form.get('new_password')
            
            if 'change_pwd_otp' in session and session['change_pwd_otp'] == user_otp:
                db_manager.execute_query(f"UPDATE {table} SET password=%s WHERE id=%s", (new_password, user_id))
                session.pop('change_pwd_otp', None)
                flash("Password changed successfully!", "success")
                return redirect(url_for(f'{role}_profile'))
            else:
                flash("Invalid or expired OTP. Please try again.", "danger")
                return render_template("change_password.html", otp_sent=True, role=role, email=email)
                
    return render_template("change_password.html", otp_sent=False, role=role)

# ---------------- PROFILES ----------------
@app.route('/teacher_profile', methods=['GET', 'POST'])
@login_required
def teacher_profile():
    teacher_id = session['teacher_id']
    if request.method == 'POST':
        name = request.form['name']
        mobile = request.form['mobile']
        address = request.form['address']
        email = request.form['email']
        college = request.form['college']
        university = request.form['university']
        sex = request.form.get('sex', 'Not Specified')
        
        current_email = db_manager.fetch_one("SELECT email FROM teachers WHERE id=%s", (teacher_id,))[0]
        
        if email != current_email:
            otp = ''.join(random.choices(string.digits, k=6))
            session['update_profile_otp'] = otp
            session['update_profile_data'] = {
                'role': 'teacher',
                'id': teacher_id,
                'name': name,
                'mobile': mobile,
                'address': address,
                'email': email,
                'college': college,
                'university': university,
                'sex': sex
            }
            subject = "AutoAttend - Verify New Email Address"
            body = f"Hello {name},\n\nYour OTP to verify your new email address is: {otp}\n\nIf you did not request this change, please ignore this email."
            success, err_msg = send_email_message(email, subject, body, timeout=5)
            if success:
                flash("An OTP has been sent to your new email address for verification.", "info")
                return redirect(url_for('verify_profile_update_otp'))
            else:
                print(f"Teacher profile email update OTP error: {err_msg}")
                flash(f"Error sending OTP to new email: {err_msg}. Please try again.", "danger")
                return redirect(url_for('teacher_profile'))
        else:
            db_manager.execute_query("UPDATE teachers SET name=%s, mobile=%s, address=%s, email=%s, college=%s, university=%s, sex=%s WHERE id=%s", 
                                     (name, mobile, address, email, college, university, sex, teacher_id))
            flash("Profile updated successfully!", "success")
            return redirect(url_for('teacher_profile'))
        
    teacher = db_manager.fetch_one("SELECT name, username, mobile, address, email, college, university, sex FROM teachers WHERE id=%s", (teacher_id,))
    return render_template("teacher_profile.html", user=teacher)

@app.route('/hod_profile', methods=['GET', 'POST'])
@hod_required
def hod_profile():
    hod_id = session['hod_id']
    if request.method == 'POST':
        name = request.form['name']
        mobile = request.form['mobile']
        address = request.form['address']
        email = request.form['email']
        college = request.form['college']
        university = request.form['university']
        sex = request.form.get('sex', 'Not Specified')
        
        current_email = db_manager.fetch_one("SELECT email FROM hods WHERE id=%s", (hod_id,))[0]
        
        if email != current_email:
            otp = ''.join(random.choices(string.digits, k=6))
            session['update_profile_otp'] = otp
            session['update_profile_data'] = {
                'role': 'hod',
                'id': hod_id,
                'name': name,
                'mobile': mobile,
                'address': address,
                'email': email,
                'college': college,
                'university': university,
                'sex': sex
            }
            subject = "AutoAttend - Verify New Email Address"
            body = f"Hello {name},\n\nYour OTP to verify your new email address is: {otp}\n\nIf you did not request this change, please ignore this email."
            success, err_msg = send_email_message(email, subject, body, timeout=5)
            if success:
                flash("An OTP has been sent to your new email address for verification.", "info")
                return redirect(url_for('verify_profile_update_otp'))
            else:
                print(f"HOD profile email update OTP error: {err_msg}")
                flash(f"Error sending OTP to new email: {err_msg}. Please try again.", "danger")
                return redirect(url_for('hod_profile'))
        else:
            db_manager.execute_query("UPDATE hods SET name=%s, mobile=%s, address=%s, email=%s, college=%s, university=%s, sex=%s WHERE id=%s", 
                                     (name, mobile, address, email, college, university, sex, hod_id))
            flash("Profile updated successfully!", "success")
            return redirect(url_for('hod_profile'))
        
    hod = db_manager.fetch_one("SELECT name, username, mobile, address, email, college, university, sex FROM hods WHERE id=%s", (hod_id,))
    return render_template("hod_profile.html", user=hod)

@app.route('/student_profile', methods=['GET', 'POST'])
@student_required
def student_profile():
    student_id = session['student_id']
    if request.method == 'POST':
        name = request.form['name']
        mobile = request.form['mobile']
        address = request.form['address']
        email = request.form['email']
        district = request.form['district']
        taluka = request.form['taluka']
        sex = request.form.get('sex', 'Not Specified')
        
        current_email = db_manager.fetch_one("SELECT email FROM student_users WHERE id=%s", (student_id,))[0]
        
        if email != current_email:
            otp = ''.join(random.choices(string.digits, k=6))
            session['update_profile_otp'] = otp
            session['update_profile_data'] = {
                'role': 'student',
                'id': student_id,
                'name': name,
                'mobile': mobile,
                'address': address,
                'email': email,
                'district': district,
                'taluka': taluka,
                'sex': sex
            }
            subject = "AutoAttend - Verify New Email Address"
            body = f"Hello {name},\n\nYour OTP to verify your new email address is: {otp}\n\nIf you did not request this change, please ignore this email."
            success, err_msg = send_email_message(email, subject, body, timeout=5)
            if success:
                flash("An OTP has been sent to your new email address for verification.", "info")
                return redirect(url_for('verify_profile_update_otp'))
            else:
                print(f"Student profile email update OTP error: {err_msg}")
                flash(f"Error sending OTP to new email: {err_msg}. Please try again.", "danger")
                return redirect(url_for('student_profile'))
        else:
            db_manager.execute_query("UPDATE student_users SET name=%s, mobile=%s, address=%s, email=%s, district=%s, taluka=%s, sex=%s WHERE id=%s", 
                                     (name, mobile, address, email, district, taluka, sex, student_id))
            flash("Profile updated successfully!", "success")
            return redirect(url_for('student_profile'))
        
    student = db_manager.fetch_one("SELECT name, roll_number, mobile, address, email, college, university, district, taluka, class_name, branch, sex FROM student_users WHERE id=%s", (student_id,))
    return render_template("student_profile.html", user=student)

# ---------------- DELETE / UPDATE PROFILE VERIFICATION ----------------
@app.route('/request_delete_profile', methods=['GET'])
def request_delete_profile():
    role = None
    user_id = None
    email = None
    name = None
    
    if 'teacher_id' in session:
        role = 'teacher'
        user_id = session['teacher_id']
        user_data = db_manager.fetch_one("SELECT email, name FROM teachers WHERE id=%s", (user_id,))
    elif 'hod_id' in session:
        role = 'hod'
        user_id = session['hod_id']
        user_data = db_manager.fetch_one("SELECT email, name FROM hods WHERE id=%s", (user_id,))
    elif 'student_id' in session:
        role = 'student'
        user_id = session['student_id']
        user_data = db_manager.fetch_one("SELECT email, name FROM student_users WHERE id=%s", (user_id,))
    else:
        flash("Please log in to perform this action.", "warning")
        return redirect(url_for('home'))
        
    if user_data:
        email, name = user_data
    else:
        flash("Account not found.", "danger")
        return redirect(url_for('home'))

    if not email:
        flash("No email registered with your account to receive OTP.", "danger")
        return redirect(url_for(f'{role}_profile'))

    otp = ''.join(random.choices(string.digits, k=6))
    session['delete_profile_otp'] = otp
    session['delete_profile_role'] = role
    session['delete_profile_id'] = user_id
    
    subject = "AutoAttend - Profile Deletion Verification"
    body = f"Hello {name},\n\nYou have requested to delete your profile. Your OTP is: {otp}\n\nIf you did not request this, please change your password immediately."
    success, err_msg = send_email_message(email, subject, body, timeout=5)
    if success:
        flash("An OTP has been sent to your registered email for verification.", "info")
        return render_template("verify_delete_profile_otp.html", email=email)
    else:
        print(f"Delete profile OTP email error: {err_msg}")
        flash(f"Error sending OTP email: {err_msg}. Please try again later.", "danger")
        return redirect(url_for(f'{role}_profile'))

@app.route('/verify_delete_profile', methods=['POST'])
def verify_delete_profile():
    user_otp = request.form.get('otp')
    role = session.get('delete_profile_role')
    user_id = session.get('delete_profile_id')
    session_otp = session.get('delete_profile_otp')
    
    if not role or not user_id or not session_otp:
        flash("Session expired or invalid request. Please try again.", "warning")
        return redirect(url_for('home'))
        
    if user_otp == session_otp:
        if role == 'teacher':
            db_manager.execute_query("DELETE FROM students WHERE teacher_id=%s", (user_id,))
            db_manager.execute_query("DELETE FROM attendance WHERE teacher_id=%s", (user_id,))
            db_manager.execute_query("DELETE FROM teachers WHERE id=%s", (user_id,))
            flash("Your profile and all related data have been deleted.", "info")
            
        elif role == 'hod':
            hod_data = db_manager.fetch_one("SELECT unique_id FROM hods WHERE id=%s", (user_id,))
            if hod_data and hod_data[0]:
                db_manager.execute_query("UPDATE hod_auth_keys SET is_used=0 WHERE auth_key=%s", (hod_data[0],))
            db_manager.execute_query("DELETE FROM hods WHERE id=%s", (user_id,))
            flash("Your profile has been deleted.", "info")
            
        elif role == 'student':
            db_manager.execute_query("DELETE FROM student_users WHERE id=%s", (user_id,))
            flash("Your profile has been deleted.", "info")
            
        session.clear()
        return redirect(url_for('home'))
    else:
        flash("Invalid OTP. Please try again.", "danger")
        return render_template("verify_delete_profile_otp.html", error=True)

@app.route('/verify_profile_update_otp', methods=['GET', 'POST'])
def verify_profile_update_otp():
    if request.method == 'GET':
        if 'update_profile_otp' not in session:
            flash("Session expired or invalid request.", "warning")
            return redirect(url_for('home'))
        return render_template('verify_profile_update_otp.html')

    if request.method == 'POST':
        user_otp = request.form.get('otp')
        session_otp = session.get('update_profile_otp')
        data = session.get('update_profile_data')
        
        if not session_otp or not data:
            flash("Session expired or invalid request. Please try again.", "warning")
            return redirect(url_for('home'))
            
        if user_otp == session_otp:
            role = data['role']
            user_id = data['id']
            name = data['name']
            mobile = data['mobile']
            address = data['address']
            email = data['email']
            
            if role == 'teacher':
                college = data['college']
                university = data['university']
                sex = data['sex']
                db_manager.execute_query("UPDATE teachers SET name=%s, mobile=%s, address=%s, email=%s, college=%s, university=%s, sex=%s WHERE id=%s", 
                                         (name, mobile, address, email, college, university, sex, user_id))
            elif role == 'hod':
                college = data['college']
                university = data['university']
                sex = data['sex']
                db_manager.execute_query("UPDATE hods SET name=%s, mobile=%s, address=%s, email=%s, college=%s, university=%s, sex=%s WHERE id=%s", 
                                         (name, mobile, address, email, college, university, sex, user_id))
            elif role == 'student':
                district = data['district']
                taluka = data['taluka']
                sex = data['sex']
                db_manager.execute_query("UPDATE student_users SET name=%s, mobile=%s, address=%s, email=%s, district=%s, taluka=%s, sex=%s WHERE id=%s", 
                                         (name, mobile, address, email, district, taluka, sex, user_id))
                                         
            session.pop('update_profile_otp', None)
            session.pop('update_profile_data', None)
            flash(f"Profile and email updated successfully!", "success")
            return redirect(url_for(f'{role}_profile'))
        else:
            flash("Invalid OTP. Please try again.", "danger")
            return render_template('verify_profile_update_otp.html', error=True)

# ---------------- EDIT STUDENT (Teacher/HOD) ----------------
@app.route('/edit_student/<roll>', methods=['GET', 'POST'])
@login_required
def edit_student(roll):
    teacher_id = session['teacher_id']
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        year = request.form['year']
        branch = request.form['branch']
        division = request.form['division']
        db_manager.execute_query("UPDATE students SET name=%s, email=%s, year=%s, branch=%s, division=%s WHERE roll=%s AND teacher_id=%s", 
                                 (name, email, year, branch, division, roll, teacher_id))
        flash(f"Student {roll} updated successfully!", "success")
        return redirect(url_for('view_students'))
        
    student = db_manager.fetch_one("SELECT name, roll, email, year, branch, division FROM students WHERE roll=%s AND teacher_id=%s", (roll, teacher_id))
    return render_template("edit_student.html", student=student, role="teacher")

@app.route('/hod/edit_student/<roll>', methods=['GET', 'POST'])
@hod_required
def hod_edit_student(roll):
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        year = request.form['year']
        branch = request.form['branch']
        division = request.form['division']
        db_manager.execute_query("UPDATE students SET name=%s, email=%s, year=%s, branch=%s, division=%s WHERE roll=%s", 
                                 (name, email, year, branch, division, roll))
        flash(f"Student {roll} updated successfully!", "success")
        teacher_id = request.args.get('teacher_id')
        return redirect(url_for('hod_teacher_students', teacher_id=teacher_id))
        
    teacher_id = request.args.get('teacher_id')
    student = db_manager.fetch_one("SELECT name, roll, email, year, branch, division FROM students WHERE roll=%s", (roll,))
    return render_template("edit_student.html", student=student, role="hod", teacher_id=teacher_id)

# ---------------- VERIFY REGISTRATION OTP ----------------
@app.route('/verify_registration_otp', methods=['GET', 'POST'])
def verify_registration_otp():
    if 'reg_otp' not in session or 'reg_data' not in session:
        flash("No pending registration found or session expired.", "warning")
        return redirect(url_for('home'))
        
    if request.method == 'POST':
        user_otp = request.form.get('otp')
        if user_otp == session.get('reg_otp'):
            data = session['reg_data']
            role = data['role']
            email = data.get('email')
            name = data.get('name')
            
            try:
                if role == 'teacher':
                    db_manager.execute_query(
                        "INSERT INTO teachers (name, username, password, mobile, address, email, college, university, sex) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)", 
                        (data['name'], data['username'], data['password'], data['mobile'], data['address'], data['email'], data['college'], data['university'], data.get('sex', 'Not Specified'))
                    )
                    db_manager.execute_query("UPDATE teacher_auth_keys SET is_used=1 WHERE id=%s", (data['auth_key_id'],))
                    flash("Registration successful! You can now log in.", "success")
                    redirect_url = url_for('home')
                    
                elif role == 'hod':
                    db_manager.execute_query(
                        "INSERT INTO hods (name, username, password, mobile, address, unique_id, email, college, university, sex) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)", 
                        (data['name'], data['username'], data['password'], data['mobile'], data['address'], data['unique_id'], data['email'], data['college'], data['university'], data.get('sex', 'Not Specified'))
                    )
                    db_manager.execute_query("UPDATE hod_auth_keys SET is_used=1 WHERE id=%s", (data['auth_key_id'],))
                    flash("HOD Registration successful! You can now log in.", "success")
                    redirect_url = url_for('hod_login')
                    
                elif role == 'student':
                    db_manager.execute_query(
                        """INSERT INTO student_users 
                           (name, roll_number, email, password, college, university, district, taluka, mobile, address, class_name, branch, sex) 
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""", 
                        (data['name'], data['roll_number'], data['email'], data['password'], data['college'], data['university'], data['district'], data['taluka'], data['mobile'], data['address'], data['class_name'], data['branch'], data.get('sex', 'Not Specified'))
                    )
                    flash("Student Registration successful! You can now log in.", "success")
                    redirect_url = url_for('student_login')
                    
                if email:
                    threading.Thread(target=send_welcome_email, args=(email, name, role.capitalize())).start()
                    
                session.pop('reg_otp', None)
                session.pop('reg_data', None)
                return redirect(redirect_url)
                
            except Exception as e:
                print(f"DB Error during registration: {e}")
                flash("An error occurred while saving your account. Please try again.", "danger")
                session.pop('reg_otp', None)
                session.pop('reg_data', None)
                return redirect(url_for('home'))
                
        else:
            flash("Invalid OTP. Please try again.", "danger")
            
    return render_template("verify_registration_otp.html")

# ---------------- RUN ----------------
if __name__ == '__main__':
    from upgrade_db_v7 import upgrade_database
    upgrade_database()
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", 5000)),
        debug=False
    )