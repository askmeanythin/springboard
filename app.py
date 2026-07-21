from flask import Flask, render_template, request, session, redirect, url_for, Response
import sqlite3
import cv2
import os
from datetime import datetime
import random
import string
import base64
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database", "exam.db")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

print("Database:", DB_PATH)
print("Exists:", os.path.exists(DB_PATH))

try:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('Candidate', 'Session', 'EventLog')")
    existing_tables = [row[0] for row in cursor.fetchall()]
    for table in ['Candidate', 'Session', 'EventLog']:
        if table not in existing_tables:
            print(f"Warning: Table '{table}' is missing!")
except sqlite3.Error as e:
    print(f"Warning: Failed to validate tables: {e}")
finally:
    if 'conn' in locals() and conn:
        conn.close()

face_cascade = cv2.CascadeClassifier(
    cv2.data.haarcascades +
    "haarcascade_frontalface_default.xml"
)


LOG_FOLDER = "logs"

os.makedirs(LOG_FOLDER, exist_ok=True)

def write_user_log(email, message):
    filename = os.path.join(LOG_FOLDER, f"{email}.log")

    with open(filename, "a") as file:
        file.write("=" * 50 + "\n")
        file.write(message + "\n")
        file.write("Date : " + datetime.now().strftime("%d-%m-%Y") + "\n")
        file.write("Time : " + datetime.now().strftime("%H:%M:%S") + "\n")
        file.write("=" * 50 + "\n\n")

def append_exam_log(email, message):

    filename = os.path.join(LOG_FOLDER, f"{email}.log")

    with open(filename, "a") as file:
        file.write(f"[{datetime.now().strftime('%H:%M:%S')}] {message}\n")

app = Flask(__name__)
app.secret_key = "exam-monitoring-secret-key"


# ---------------- HOME PAGE ----------------

@app.route("/")
def home():
    return render_template("index.html")


# ---------------- EXAM ENTRY PAGE ----------------

@app.route("/exam-entry")
def exam_entry():
    return render_template("exam_entry.html")


# ---------------- REGISTER PAGE ----------------

@app.route("/register")
def register_page():

    captcha = "".join(
        random.choices(
            string.ascii_uppercase + string.digits,
            k=6
        )
    )

    session["captcha"] = captcha

    return render_template(
        "register.html",
        captcha=captcha
    )


# ---------------- REGISTER CANDIDATE ----------------

@app.route("/register", methods=["POST"])
def register():

    first_name = request.form["first_name"].strip()
    middle_name = request.form["middle_name"].strip()
    last_name = request.form["last_name"].strip()
    email = request.form["email"].strip()
    password = request.form["password"]
    confirm_password = request.form["confirm_password"]
    entered_captcha = request.form["captcha"].strip().upper()

    if first_name == "":
        return "First Name cannot be empty!"

    if last_name == "":
        return "Last Name cannot be empty!"

    if email == "":
        return "Email cannot be empty!"

    if "@" not in email or "." not in email:
        return "Invalid Email Format!"

    if password == "":
        return "Password cannot be empty!"

    if password != confirm_password:
        return "Passwords do not match!"

    stored_captcha = session.get("captcha")

    if entered_captcha != stored_captcha:
        return "Invalid CAPTCHA!"

    query = "SELECT candidate_id FROM Candidate WHERE email=?"
    params = (email,)
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        print("Executing:", query)
        print("Parameters:", params)
        cursor.execute(query, params)
        existing_user = cursor.fetchone()
    except sqlite3.Error as e:
        print(f"Database Error: {e}")
        return f"Database Error: {e}", 500
    finally:
        if conn:
            conn.close()

    if existing_user:
        return "Email already registered!"

    session["pending_candidate"] = {
        "first_name": first_name,
        "middle_name": middle_name,
        "last_name": last_name,
        "email": email,
        "password": password
    }

    session.pop("captcha", None)

    return redirect(url_for("capture_photo"))


@app.route("/capture-photo")
def capture_photo():

    if "pending_candidate" not in session:
        return redirect(url_for("register_page"))

    return render_template("capture_photo.html")

@app.route("/save-candidate-photo", methods=["POST"])
def save_candidate_photo():

    if "pending_candidate" not in session:
        return redirect(url_for("register_page"))

    photo_data = request.form.get("photo_data")

    if not photo_data:
        return "Photo was not captured."

    candidate = session["pending_candidate"]

    try:

        image_data = photo_data.split(",", 1)[1]

        image_bytes = base64.b64decode(image_data)

    except (IndexError, ValueError):
        return "Invalid photo data."

    if not os.path.exists("photos"):
        os.makedirs("photos")

    safe_email = (
        candidate["email"]
        .replace("@", "_")
        .replace(".", "_")
    )

    photo_path = f"photos/{safe_email}.jpg"

    with open(photo_path, "wb") as photo_file:
        photo_file.write(image_bytes)

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        query_candidate = """
            INSERT INTO Candidate
            (
                first_name,
                middle_name,
                last_name,
                email,
                password,
                photo_path
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """
        params_candidate = (
            candidate["first_name"],
            candidate["middle_name"],
            candidate["last_name"],
            candidate["email"],
            candidate["password"],
            photo_path
        )
        print("Executing:", query_candidate)
        print("Parameters:", params_candidate)
        cursor.execute(query_candidate, params_candidate)

        candidate_id = cursor.lastrowid

        query_event = """
            INSERT INTO EventLog
            (
                candidate_id,
                event_type,
                timestamp,
                remarks
            )
            VALUES (?, ?, ?, ?)
        """
        params_event = (
            candidate_id,
            "Candidate Registered",
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Candidate account created and identity photo captured"
        )
        print("Executing:", query_event)
        print("Parameters:", params_event)
        cursor.execute(query_event, params_event)

        conn.commit()

        write_user_log(
            candidate["email"],
            "Account Created\nPhoto Captured Successfully\nCandidate Registered Successfully"
        )

    except sqlite3.IntegrityError:
        if conn:
            conn.rollback()
        return "Email already registered!"
    except sqlite3.Error as e:
        print(f"Database Error: {e}")
        if conn:
            conn.rollback()
        return f"Database Error: {e}", 500
    finally:
        if conn:
            conn.close()

    session.pop("pending_candidate", None)

    return redirect(url_for("login_page"))



# ---------------- LOGIN PAGE ----------------

# ---------------- LOGIN PAGE ----------------

@app.route("/login")
def login_page():

    captcha = "".join(
        random.choices(
            string.ascii_uppercase + string.digits,
            k=6
        )
    )

    session["login_captcha"] = captcha

    return render_template(
        "login.html",
        captcha=captcha
    )


# ---------------- LOGIN ----------------

@app.route("/login", methods=["POST"])
def login():

    email = request.form["email"].strip()
    password = request.form["password"]
    entered_captcha = request.form["captcha"].strip().upper()

    if email == "":
        return "Enter Email"

    if password == "":
        return "Enter Password"

    stored_captcha = session.get("login_captcha")

    if entered_captcha != stored_captcha:
        return "Invalid CAPTCHA!"

    query = """
        SELECT
            candidate_id,
            first_name,
            middle_name,
            last_name,
            email
        FROM Candidate
        WHERE email=? AND password=?
    """
    params = (email, password)
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        print("Executing:", query)
        print("Parameters:", params)
        cursor.execute(query, params)
        user = cursor.fetchone()
    except sqlite3.Error as e:
        print(f"Database Error: {e}")
        return f"Database Error: {e}", 500
    finally:
        if conn:
            conn.close()

    if user is None:
        return "Invalid Email or Password!"

    candidate_id = user[0]
    first_name = user[1]
    middle_name = user[2]
    last_name = user[3]

    if middle_name:
        full_name = f"{first_name} {middle_name} {last_name}"
    else:
        full_name = f"{first_name} {last_name}"

    session["candidate_id"] = candidate_id
    session["candidate_name"] = full_name
    session["candidate_email"] = user[4]

    write_user_log(
        email,
        "Login Successful"
    )

    session.pop("login_captcha", None)

    return redirect(url_for("welcome"))


# ---------------- WELCOME PAGE ----------------

@app.route("/welcome")
def welcome():

    if "candidate_id" not in session:
        return redirect(url_for("login_page"))

    candidate_name = session.get("candidate_name")

    return render_template(
        "welcome.html",
        name=candidate_name
    )

# ---------------- START EXAM ----------------

@app.route("/start_exam", methods=["POST"])
def start_exam():

    candidate_id = session["candidate_id"]

    query = """
INSERT INTO Session(candidate_id,start_time,status)
VALUES(?,?,?)
"""
    params = (
        candidate_id,
        datetime.now(),
        "Started"
    )
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        print("Executing:", query)
        print("Parameters:", params)
        cursor.execute(query, params)
        conn.commit()
    except sqlite3.Error as e:
        print(f"Database Error: {e}")
        return f"Database Error: {e}", 500
    finally:
        if conn:
            conn.close()

    return "Exam Started Successfully!"


# ---------------- PAUSE EXAM ----------------

@app.route("/pause_exam", methods=["POST"])
def pause_exam():

    query = """
        UPDATE Session
        SET status=?
        WHERE session_id=(SELECT MAX(session_id) FROM Session)
    """
    params = ("Paused",)
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        print("Executing:", query)
        print("Parameters:", params)
        cursor.execute(query, params)
        conn.commit()
    except sqlite3.Error as e:
        print(f"Database Error: {e}")
        return f"Database Error: {e}", 500
    finally:
        if conn:
            conn.close()

    return "Exam Paused Successfully!"


# ---------------- RESUME EXAM ----------------

@app.route("/resume_exam", methods=["POST"])
def resume_exam():

    query = """
        UPDATE Session
        SET status=?
        WHERE session_id=(SELECT MAX(session_id) FROM Session)
    """
    params = ("Resumed",)
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        print("Executing:", query)
        print("Parameters:", params)
        cursor.execute(query, params)
        conn.commit()
    except sqlite3.Error as e:
        print(f"Database Error: {e}")
        return f"Database Error: {e}", 500
    finally:
        if conn:
            conn.close()

    return "Exam Resumed Successfully!"


# ---------------- END EXAM ----------------

@app.route("/end_exam", methods=["POST"])
def end_exam():

    query = """
        UPDATE Session
        SET
            end_time=?,
            status=?
        WHERE session_id=(SELECT MAX(session_id) FROM Session)
    """
    params = (datetime.now(), "Completed")
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        print("Executing:", query)
        print("Parameters:", params)
        cursor.execute(query, params)
        conn.commit()
    except sqlite3.Error as e:
        print(f"Database Error: {e}")
        return f"Database Error: {e}", 500
    finally:
        if conn:
            conn.close()

    return "Exam Ended Successfully!"


# ---------------- DASHBOARD ----------------

@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")

@app.route("/browser_event", methods=["POST"])
def browser_event():

    if "candidate_id" not in session:
        return "Unauthorized", 401

    data = request.get_json()

    event_type = data.get("event_type")

    remarks = data.get("remarks", "")

    candidate_id = session["candidate_id"]

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    query = """
        INSERT INTO EventLog
        (
            candidate_id,
            event_type,
            timestamp,
            remarks
        )
        VALUES (?, ?, ?, ?)
    """
    params = (
        candidate_id,
        event_type,
        timestamp,
        remarks
    )
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        print("Executing:", query)
        print("Parameters:", params)
        cursor.execute(query, params)
        conn.commit()
    except sqlite3.Error as e:
        print(f"Database Error: {e}")
        return f"Database Error: {e}", 500
    finally:
        if conn:
            conn.close()

    return {"status": "success"}



# ---------------- Exam ----------------
@app.route("/exam")
def exam():

    if "candidate_id" not in session:
        return redirect(url_for("login_page"))
    

    write_user_log(
        session["candidate_email"],
        f"""Exam Started

    Initial Status
    Faces Detected : {face_count}
    Missing Time : 0 sec"""
    )

    global current_candidate_email
    current_candidate_email = session["candidate_email"]

    return render_template("exam.html")
face_count = 0
face_detected = False
current_candidate_email = None


def generate_frames():
    global face_count
    global face_detected

    camera = cv2.VideoCapture(0, cv2.CAP_DSHOW)

    camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    while True:

        success, frame = camera.read()

        if not success:
            break

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        faces = face_cascade.detectMultiScale(
            gray,
            scaleFactor=1.2,
            minNeighbors=5,
            minSize=(80, 80)
        )

        face_count = len(faces)
        face_detected = (face_count > 0)

        for (x, y, w, h) in faces:
            cv2.rectangle(
                frame,
                (x, y),
                (x + w, y + h),
                (0, 255, 0),
                2
            )

        _, buffer = cv2.imencode(".jpg", frame)
        frame = buffer.tobytes()

        yield (
            b'--frame\r\n'
            b'Content-Type: image/jpeg\r\n\r\n' +
            frame +
            b'\r\n'
        )

    camera.release()
@app.route("/video_feed")
def video_feed():
    return Response(
        generate_frames(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )


@app.route("/monitor")
def monitor():
    return {
        "face_count": face_count
    }


@app.route("/face_status")
def face_status():
    return {
        "face_detected": face_detected
    }



# ---------------- RUN APP ----------------

if __name__ == "__main__":
    app.run(debug=True)


