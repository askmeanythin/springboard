from flask import Flask, render_template, request, session, redirect, url_for, Response
import sqlite3
import cv2
import os
from datetime import datetime
import random
import string
import base64
import time


LOG_FOLDER = "logs"
DB_PATH = "database/exam.db"

os.makedirs(LOG_FOLDER, exist_ok=True)

FACE_MISSING_THRESHOLD = 5
MULTIPLE_FACE_THRESHOLD = 5
BROWSER_FOCUS_THRESHOLD = 3
FACE_MISSING_PENALTY = 10
MULTIPLE_FACE_PENALTY = 5
BROWSER_FOCUS_PENALTY = 5


def db_connect():
    connection = sqlite3.connect(
        DB_PATH,
        detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def sanitize_table_name(email):
    return (
        email
        .replace("@", "_")
        .replace(".", "_")
        .replace("-", "_")
    )


def ensure_candidate_log_table(cursor, email):
    table_name = sanitize_table_name(email)

    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS "{table_name}"
        (
            log_id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            event TEXT NOT NULL,
            remarks TEXT,
            integrity INTEGER NOT NULL,
            penalty INTEGER NOT NULL DEFAULT 0,
            event_type TEXT NOT NULL DEFAULT 'Exam Event'
        )
    """)

    cursor.execute(f"PRAGMA table_info('{table_name}')")
    columns = [row[1] for row in cursor.fetchall()]

    if "penalty" not in columns:
        cursor.execute(
            f"ALTER TABLE \"{table_name}\" ADD COLUMN penalty INTEGER NOT NULL DEFAULT 0"
        )

    if "event_type" not in columns:
        cursor.execute(
            f"ALTER TABLE \"{table_name}\" ADD COLUMN event_type TEXT NOT NULL DEFAULT 'Exam Event'"
        )


def get_latest_integrity(cursor, email):
    table_name = sanitize_table_name(email)

    cursor.execute(f'''
        SELECT integrity
        FROM "{table_name}"
        ORDER BY log_id DESC
        LIMIT 1
    ''')

    row = cursor.fetchone()

    return row[0] if row else 100


def get_latest_session_id(candidate_id):
    conn = db_connect()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT session_id
        FROM Session
        WHERE candidate_id=?
        ORDER BY session_id DESC
        LIMIT 1
    """, (candidate_id,))

    row = cursor.fetchone()
    conn.close()

    return row[0] if row else None


def format_duration(start_time, end_time=None):
    if start_time is None:
        return ""

    if isinstance(start_time, str):
        start_time = datetime.fromisoformat(start_time)

    if end_time is None:
        end_time = datetime.now()
    elif isinstance(end_time, str):
        end_time = datetime.fromisoformat(end_time)

    duration = end_time - start_time
    return str(duration).split(".")[0]


def parse_timestamp(value):
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    return None


def get_last_penalty_after(cursor, email, log_id, reason):
    table_name = sanitize_table_name(email)
    cursor.execute(f"""
        SELECT COUNT(*)
        FROM "{table_name}"
        WHERE event_type='Penalty'
        AND remarks LIKE ?
        AND log_id > ?
    """, (f"{reason}%", log_id))
    return cursor.fetchone()[0] > 0


def process_browser_focus_event(email, event):
    append_exam_log(
        email,
        event,
        remarks=event,
        event_type="Browser Event",
        penalty=0
    )

    if event != "Browser Focus Regained":
        return

    conn = db_connect()
    cursor = conn.cursor()
    ensure_candidate_log_table(cursor, email)

    table_name = sanitize_table_name(email)
    cursor.execute(f"""
        SELECT log_id, timestamp
        FROM "{table_name}"
        WHERE event_type='Browser Event'
        AND event='Browser Focus Lost'
        ORDER BY log_id DESC
        LIMIT 1
    """)
    lost_row = cursor.fetchone()

    if not lost_row:
        conn.close()
        return

    lost_id = lost_row["log_id"]
    lost_ts = parse_timestamp(lost_row["timestamp"])
    if lost_ts is None:
        conn.close()
        return

    if get_last_penalty_after(cursor, email, lost_id, "Browser Focus Lost"):
        conn.close()
        return

    elapsed = int((datetime.now() - lost_ts).total_seconds())
    if elapsed >= BROWSER_FOCUS_THRESHOLD:
        apply_penalty(
            email,
            "Browser Focus Lost",
            BROWSER_FOCUS_PENALTY,
            event="Browser Focus Lost Penalty"
        )

    conn.close()


def get_report_metrics(email):
    table_name = sanitize_table_name(email)
    conn = db_connect()
    cursor = conn.cursor()

    ensure_candidate_log_table(cursor, email)

    cursor.execute(f"""
        SELECT COUNT(*)
        FROM "{table_name}"
        WHERE penalty > 0
        AND event_type = 'Penalty'
        AND remarks LIKE 'Candidate Missing%'
    """)
    face_absence_count = cursor.fetchone()[0]

    cursor.execute(f"""
        SELECT COUNT(*)
        FROM "{table_name}"
        WHERE penalty > 0
        AND event_type = 'Penalty'
        AND remarks LIKE 'Browser Focus Lost%'
    """)
    browser_focus_loss_count = cursor.fetchone()[0]

    cursor.execute(f"""
        SELECT COUNT(*)
        FROM "{table_name}"
        WHERE penalty > 0
        AND event_type = 'Penalty'
        AND remarks LIKE 'Multiple Faces Detected%'
    """)
    multiple_face_count = cursor.fetchone()[0]

    cursor.execute(f"""
        SELECT COUNT(*)
        FROM "{table_name}"
        WHERE penalty > 0
    """)
    total_suspicious_events = cursor.fetchone()[0]

    cursor.execute(f"""
        SELECT log_id, timestamp, event, remarks, integrity, penalty, event_type
        FROM "{table_name}"
        ORDER BY log_id ASC
    """)
    event_timeline = [dict(row) for row in cursor.fetchall()]

    final_integrity = 100
    if event_timeline:
        final_integrity = event_timeline[-1]["integrity"]

    conn.close()

    if final_integrity >= 90:
        overall_remark = "Excellent integrity maintained."
    elif final_integrity >= 70:
        overall_remark = "Good integrity with minor issues."
    elif final_integrity >= 40:
        overall_remark = "Integrity concerns detected. Review required."
    else:
        overall_remark = "Integrity severely compromised."

    return {
        "face_absence_count": face_absence_count,
        "browser_focus_loss_count": browser_focus_loss_count,
        "multiple_face_count": multiple_face_count,
        "total_suspicious_events": total_suspicious_events,
        "final_integrity": final_integrity,
        "overall_remark": overall_remark,
        "event_timeline": event_timeline
    }


def append_exam_log(email, event, remarks=None, event_type="Exam Event", penalty=0):
    table_name = sanitize_table_name(email)

    conn = db_connect()
    cursor = conn.cursor()

    ensure_candidate_log_table(cursor, email)

    integrity = get_latest_integrity(cursor, email)

    cursor.execute(f'''
        INSERT INTO "{table_name}"
        (
            event,
            remarks,
            integrity,
            penalty,
            event_type
        )
        VALUES (?, ?, ?, ?, ?)
    ''',
    (
        event,
        remarks,
        integrity,
        penalty,
        event_type
    ))

    conn.commit()
    conn.close()


def apply_penalty(email, reason, penalty, event="Penalty"):
    table_name = sanitize_table_name(email)

    conn = db_connect()
    cursor = conn.cursor()

    ensure_candidate_log_table(cursor, email)

    current_integrity = get_latest_integrity(cursor, email)
    new_integrity = max(0, current_integrity - penalty)

    cursor.execute(f'''
        INSERT INTO "{table_name}"
        (
            event,
            remarks,
            integrity,
            penalty,
            event_type
        )
        VALUES (?, ?, ?, ?, ?)
    ''',
    (
        event,
        f"{reason} (-{penalty})",
        new_integrity,
        penalty,
        "Penalty"
    ))

    conn.commit()
    conn.close()


def create_candidate_log_table(cursor, email):
    ensure_candidate_log_table(cursor, email)


def write_user_log(email, message):
    append_exam_log(
        email,
        "System Log",
        message,
        event_type="System Log",
        penalty=0
    )

# ---------------- HOME PAGE ----------------


app = Flask(__name__)
app.secret_key = "exam-monitoring-secret-key"

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

    conn = db_connect()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT candidate_id FROM Candidate WHERE email=?",
        (email,)
    )

    existing_user = cursor.fetchone()

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

    conn = db_connect()
    cursor = conn.cursor()

    try:

        cursor.execute("""
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
        """, (
            candidate["first_name"],
            candidate["middle_name"],
            candidate["last_name"],
            candidate["email"],
            candidate["password"],
            photo_path
        ))

        candidate_id = cursor.lastrowid
        create_candidate_log_table(
            cursor,
            candidate["email"]
        )

        cursor.execute("""
            INSERT INTO EventLog
            (
                candidate_id,
                event_type,
                remarks
            )
            VALUES (?, ?, ?)
        """, (
            candidate_id,
            "Candidate Registered",
            "Candidate account created and identity photo captured"
        ))

        conn.commit()

        write_user_log(
            candidate["email"],
            "Account Created\nPhoto Captured Successfully\nCandidate Registered Successfully"
        )

    except sqlite3.IntegrityError:

        conn.rollback()
        conn.close()

        return "Email already registered!"

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

    conn = db_connect()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            candidate_id,
            first_name,
            middle_name,
            last_name,
            email
        FROM Candidate
        WHERE email=? AND password=?
    """, (
        email,
        password
    ))

    user = cursor.fetchone()

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

    if "candidate_id" not in session:
        return redirect(url_for("login_page"))

    conn = db_connect()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO Session(candidate_id,start_time,status)
        VALUES(?,?,?)
    """, (
        session["candidate_id"],
        datetime.now(),
        "Started"
    ))

    conn.commit()
    conn.close()

    return redirect(url_for("exam"))


# ---------------- PAUSE EXAM ----------------

@app.route("/pause_exam", methods=["POST"])
def pause_exam():

    if "candidate_id" not in session:
        return redirect(url_for("login_page"))

    session_id = get_latest_session_id(session["candidate_id"])
    if session_id is None:
        return "No active session found.", 400

    conn = db_connect()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE Session
        SET status=?
        WHERE session_id=?
    """, ("Paused", session_id))

    conn.commit()
    conn.close()

    return "Exam Paused Successfully!"


# ---------------- RESUME EXAM ----------------

@app.route("/resume_exam", methods=["POST"])
def resume_exam():

    if "candidate_id" not in session:
        return redirect(url_for("login_page"))

    session_id = get_latest_session_id(session["candidate_id"])
    if session_id is None:
        return "No active session found.", 400

    conn = db_connect()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE Session
        SET status=?
        WHERE session_id=?
    """, ("Resumed", session_id))

    conn.commit()
    conn.close()

    return "Exam Resumed Successfully!"


# ---------------- END EXAM ----------------

@app.route("/end_exam", methods=["POST"])
def end_exam():

    if "candidate_id" not in session:
        return redirect(url_for("login_page"))

    session_id = get_latest_session_id(session["candidate_id"])
    if session_id is None:
        return "No active session found.", 400

    conn = db_connect()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE Session
        SET
            end_time=?,
            status=?
        WHERE session_id=?
    """, (datetime.now(), "Completed", session_id))

    conn.commit()
    conn.close()

    return "Exam Ended Successfully!"


@app.route("/report")
def report():

    if "candidate_id" not in session or "candidate_email" not in session:
        return redirect(url_for("login_page"))

    conn = db_connect()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            session_id,
            start_time,
            end_time,
            status
        FROM Session
        WHERE candidate_id=?
        ORDER BY session_id DESC
        LIMIT 1
    """, (session["candidate_id"],))

    session_data = cursor.fetchone()
    conn.close()

    metrics = get_report_metrics(session["candidate_email"])

    duration = ""
    if session_data:
        duration = format_duration(session_data["start_time"], session_data["end_time"])

    return render_template(
        "report.html",
        candidate_id=session.get("candidate_id"),
        candidate_name=session.get("candidate_name"),
        candidate_email=session.get("candidate_email"),
        session_data=session_data,
        duration=duration,
        face_absence_count=metrics["face_absence_count"],
        browser_focus_loss_count=metrics["browser_focus_loss_count"],
        multiple_face_count=metrics["multiple_face_count"],
        total_suspicious_events=metrics["total_suspicious_events"],
        final_integrity=metrics["final_integrity"],
        overall_remark=metrics["overall_remark"],
        event_timeline=metrics["event_timeline"]
    )
# ---------------- DASHBOARD ----------------

@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")



# ---------------- Exam ----------------
@app.route("/exam")
def exam():

    if "candidate_id" not in session:
        return redirect(url_for("login_page"))

    email = session["candidate_email"]
    append_exam_log(
        email,
        "Exam Started",
        f"Initial Status\nFaces Detected : {face_count}\nMissing Time : 0 sec",
        event_type="Exam Event",
        penalty=0
    )

    global current_candidate_email
    current_candidate_email = email

    return render_template("exam.html")

face_cascade = cv2.CascadeClassifier(
    "haarcascade_frontalface_default.xml"
)

face_detected = True
face_count = 0
face_missing_start = None
face_missing_active = False
face_missing_penalty_given = False
missing_seconds = 0

multiple_face_start = None
multiple_face_active = False
multiple_face_penalty_given = False

browser_focus_lost_start = None
browser_focus_lost_active = False
browser_focus_penalty_given = False

current_candidate_email = None

def generate_frames():

    camera = cv2.VideoCapture(0)

    camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    camera.set(cv2.CAP_PROP_FPS, 30)

    while True:

        success, frame = camera.read()

        if not success:
            break

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        faces = face_cascade.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(80, 80)
        )

        global face_count
        global face_missing_start
        global face_missing_active
        global face_missing_penalty_given
        global missing_seconds

        global multiple_face_start
        global multiple_face_active
        global multiple_face_penalty_given

        face_count = len(faces)
        email = current_candidate_email

        if email:
            if face_count >= 2:
                if not multiple_face_active:
                    multiple_face_active = True
                    multiple_face_start = time.time()
                    multiple_face_penalty_given = False
                    append_exam_log(
                        email,
                        f"Multiple faces detected ({face_count} faces)",
                        remarks=f"{face_count} faces detected",
                        event_type="Security Log"
                    )
                elif not multiple_face_penalty_given:
                    active_seconds = int(time.time() - multiple_face_start)
                    if active_seconds >= MULTIPLE_FACE_THRESHOLD:
                        apply_penalty(
                            email,
                            "Multiple Faces Detected",
                            MULTIPLE_FACE_PENALTY,
                            event="Multiple Faces Penalty"
                        )
                        multiple_face_penalty_given = True
            elif multiple_face_active:
                append_exam_log(
                    email,
                    "Face count normal (1 face)",
                    remarks="Multiple face event resolved",
                    event_type="Security Log"
                )
                multiple_face_active = False
                multiple_face_start = None
                multiple_face_penalty_given = False

        last_face_count = face_count

        if face_count == 0:
            if not face_missing_active:
                face_missing_active = True
                face_missing_start = time.time()
                missing_seconds = 0
                append_exam_log(
                    email,
                    "Candidate missing detected",
                    remarks="Face missing detected",
                    event_type="Security Log"
                )

            missing_seconds = int(time.time() - face_missing_start)

            if email and not face_missing_penalty_given:
                if missing_seconds >= FACE_MISSING_THRESHOLD:
                    apply_penalty(
                        email,
                        "Candidate Missing",
                        FACE_MISSING_PENALTY,
                        event="Candidate Missing Penalty"
                    )
                    face_missing_penalty_given = True

        else:
            if face_missing_active:
                append_exam_log(
                    email,
                    f"Candidate returned after {missing_seconds} sec",
                    remarks=f"Face returned after {missing_seconds} sec",
                    event_type="Security Log"
                )
            face_missing_active = False
            face_missing_start = None
            missing_seconds = 0
            face_missing_penalty_given = False

        global face_detected
        face_detected = face_count > 0

        for (x, y, w, h) in faces:
            cv2.rectangle(
                frame,
                (x, y),
                (x + w, y + h),
                (0, 255, 0),
                2
            )

        current_time = datetime.now().strftime("%H:%M:%S")

        cv2.putText(
            frame,
            f"Time : {current_time}",
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 0),
            2
        )
        
        cv2.putText(
            frame,
            f"Faces : {face_count}",
            (10, 60),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 0),
            2
        )

        if face_count == 0:

            cv2.putText(
                frame,
                f"Missing : {missing_seconds} sec",
                (10, 90),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 0, 255),
                2
            )

        _, buffer = cv2.imencode(
            ".jpg",
            frame,
            [cv2.IMWRITE_JPEG_QUALITY, 95]
        )

        frame = buffer.tobytes()

        yield (
            b'--frame\r\n'
            b'Content-Type: image/jpeg\r\n\r\n' +
            frame +
            b'\r\n'
        )

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

@app.route("/integrity")
def integrity():

    if "candidate_email" not in session:
        return {"integrity": 100}

    email = session["candidate_email"]
    conn = db_connect()
    cursor = conn.cursor()

    ensure_candidate_log_table(cursor, email)

    cursor.execute(f"""
        SELECT integrity
        FROM "{sanitize_table_name(email)}"
        ORDER BY log_id DESC
        LIMIT 1
    """)

    row = cursor.fetchone()
    conn.close()

    return {"integrity": row[0] if row else 100}


@app.route("/browser_event", methods=["POST"])
def browser_event():

    if "candidate_email" not in session:
        return {"status": "error"}

    data = request.get_json() or {}
    event = data.get("event")
    if not event:
        return {"status": "error", "message": "Missing event"}, 400

    append_exam_log(
        session["candidate_email"],
        event,
        event_type="Browser Event",
        remarks=event,
        penalty=0
    )

    if event == "Browser Focus Regained":
        process_browser_focus_event(session["candidate_email"], event)

    return {"status": "success"}


# ---------------- RUN APP ----------------

if __name__ == "__main__":
    app.run(debug=False)


