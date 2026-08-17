from flask import Flask, render_template, request, session, redirect, url_for, Response, send_from_directory, stream_with_context
import sqlite3
import cv2
import os
from datetime import datetime
import random
import string
import base64
import time
from pathlib import Path
from werkzeug.security import check_password_hash, generate_password_hash


LOG_FOLDER = "logs"
SCREENSHOT_FOLDER = "screenshots"
DB_PATH = "database/exam.db"
DEFAULT_EXAM_NAME = "Default Exam"

os.makedirs(LOG_FOLDER, exist_ok=True)
os.makedirs(SCREENSHOT_FOLDER, exist_ok=True)

FACE_MISSING_THRESHOLD = 5
MULTIPLE_FACE_THRESHOLD = 5
BROWSER_FOCUS_THRESHOLD = 3
FACE_MISSING_PENALTY = 25
MULTIPLE_FACE_PENALTY = 15
BROWSER_FOCUS_PENALTY = 5


def db_connect():
    connection = sqlite3.connect(
        DB_PATH,
        timeout=10,
        detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout=10000")
    return connection


def ensure_production_schema():
    conn = db_connect()
    cursor = conn.cursor()

    cursor.execute("PRAGMA table_info('Candidate')")
    candidate_columns = {row[1] for row in cursor.fetchall()}
    if "password_hash" not in candidate_columns:
        cursor.execute("ALTER TABLE Candidate ADD COLUMN password_hash TEXT")


    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Admin
        (
            admin_id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)


    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Exam
        (
            exam_id INTEGER PRIMARY KEY AUTOINCREMENT,
            exam_name TEXT NOT NULL UNIQUE,
            description TEXT,
            status TEXT NOT NULL DEFAULT 'Active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ExamSession
        (
            session_id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id INTEGER NOT NULL,
            exam_id INTEGER NOT NULL,
            start_time TIMESTAMP,
            end_time TIMESTAMP,
            status TEXT NOT NULL DEFAULT 'Started',
            initial_integrity INTEGER NOT NULL DEFAULT 100,
            current_integrity INTEGER NOT NULL DEFAULT 100,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(candidate_id) REFERENCES Candidate(candidate_id) ON DELETE CASCADE,
            FOREIGN KEY(exam_id) REFERENCES Exam(exam_id) ON DELETE RESTRICT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS MonitoringEvent
        (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            event_subtype TEXT NOT NULL,
            severity TEXT NOT NULL DEFAULT 'Info',
            event_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            remarks TEXT,
            face_count INTEGER,
            browser_state TEXT,
            source TEXT NOT NULL DEFAULT 'cv',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(session_id) REFERENCES ExamSession(session_id) ON DELETE CASCADE
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Penalty
        (
            penalty_id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL,
            session_id INTEGER NOT NULL,
            penalty_points INTEGER NOT NULL,
            reason TEXT NOT NULL,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(event_id) REFERENCES MonitoringEvent(event_id) ON DELETE CASCADE,
            FOREIGN KEY(session_id) REFERENCES ExamSession(session_id) ON DELETE CASCADE
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Screenshot
        (
            screenshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL,
            session_id INTEGER NOT NULL,
            screenshot_path TEXT NOT NULL,
            captured_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            image_type TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(event_id) REFERENCES MonitoringEvent(event_id) ON DELETE CASCADE,
            FOREIGN KEY(session_id) REFERENCES ExamSession(session_id) ON DELETE CASCADE
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS IntegrityHistory
        (
            integrity_history_id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            event_id INTEGER,
            integrity_before INTEGER NOT NULL,
            integrity_after INTEGER NOT NULL,
            delta INTEGER NOT NULL,
            recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(session_id) REFERENCES ExamSession(session_id) ON DELETE CASCADE,
            FOREIGN KEY(event_id) REFERENCES MonitoringEvent(event_id) ON DELETE SET NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS BrowserEvent
        (
            browser_event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ended_at TIMESTAMP,
            duration_seconds INTEGER,
            remarks TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(session_id) REFERENCES ExamSession(session_id) ON DELETE CASCADE
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Report
        (
            report_id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL UNIQUE,
            generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            summary_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(session_id) REFERENCES ExamSession(session_id) ON DELETE CASCADE
        )
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_examsession_candidate_status ON ExamSession(candidate_id, status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_monitoringevent_session_timestamp ON MonitoringEvent(session_id, event_timestamp)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_monitoringevent_type ON MonitoringEvent(event_type, event_subtype)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_penalty_session_applied ON Penalty(session_id, applied_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_screenshot_session_captured ON Screenshot(session_id, captured_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_integrityhistory_session_recorded ON IntegrityHistory(session_id, recorded_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_browserevent_session_started ON BrowserEvent(session_id, started_at)")

    cursor.execute(
        """
        INSERT OR IGNORE INTO Exam (exam_name, description, status)
        VALUES (?, ?, 'Active')
        """,
        (DEFAULT_EXAM_NAME, "Default exam used by the existing portal flow."),
    )

    cursor.execute(
        """
            INSERT OR IGNORE INTO Admin (email, password_hash)
            VALUES (?, ?)
        """,
        (
            "admin@gmail.com",
            generate_password_hash("admin")
        )
    )

    conn.commit()
    conn.close()


def get_default_exam_id(cursor):
    cursor.execute("SELECT exam_id FROM Exam ORDER BY exam_id ASC LIMIT 1")
    row = cursor.fetchone()
    return row[0] if row else None


def get_active_exam_session_id(candidate_id=None):
    current_session_id = session.get("exam_session_id")
    if current_session_id:
        if get_exam_session_record(current_session_id) is not None:
            return current_session_id
        session.pop("exam_session_id", None)

    if candidate_id is None:
        candidate_id = session.get("candidate_id")

    if candidate_id is None:
        return None

    conn = db_connect()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT session_id
        FROM ExamSession
        WHERE candidate_id=?
        ORDER BY session_id DESC
        LIMIT 1
        """,
        (candidate_id,)
    )
    row = cursor.fetchone()
    conn.close()
    if row is None:
        return None

    session["exam_session_id"] = row[0]
    return row[0]


def get_exam_session_record(session_id):
    if session_id is None:
        return None

    conn = db_connect()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            session_id,
            candidate_id,
            exam_id,
            start_time,
            end_time,
            status,
            initial_integrity,
            current_integrity
        FROM ExamSession
        WHERE session_id=?
        """,
        (session_id,)
    )
    row = cursor.fetchone()
    conn.close()
    return row


def save_violation_screenshot(frame, session_id, violation_type):
    if frame is None or session_id is None:
        return None

    safe_violation = violation_type.lower().replace(" ", "_")
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    relative_folder = f"session_{session_id}"
    folder_path = os.path.join(SCREENSHOT_FOLDER, relative_folder)
    os.makedirs(folder_path, exist_ok=True)

    filename = f"{safe_violation}_{timestamp}.jpg"
    file_path = os.path.join(folder_path, filename)

    if cv2.imwrite(file_path, frame):
        return f"{relative_folder}/{filename}"

    return None


def record_monitoring_violation(session_id, event_type, event_subtype, penalty_points=0, remarks=None, frame=None, face_count_value=None, browser_state=None, source="cv", severity="Warning", conn=None, cursor=None):
    if session_id is None:
        return None

    if get_exam_session_record(session_id) is None:
        return None

    owns_connection = conn is None or cursor is None
    if owns_connection:
        conn = db_connect()
        cursor = conn.cursor()

    try:
        if owns_connection:
            conn.execute("BEGIN")

        cursor.execute(
            "SELECT current_integrity FROM ExamSession WHERE session_id=?",
            (session_id,)
        )
        session_row = cursor.fetchone()
        integrity_before = session_row[0] if session_row else 100
        integrity_after = max(0, integrity_before - penalty_points)

        cursor.execute(
            """
            INSERT INTO MonitoringEvent
            (
                session_id,
                event_type,
                event_subtype,
                severity,
                remarks,
                face_count,
                browser_state,
                source
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                event_type,
                event_subtype,
                severity,
                remarks,
                face_count_value,
                browser_state,
                source,
            )
        )
        event_id = cursor.lastrowid

        screenshot_path = None
        if frame is not None:
            screenshot_path = save_violation_screenshot(frame, session_id, event_subtype)
            if screenshot_path:
                cursor.execute(
                    """
                    INSERT INTO Screenshot
                    (
                        event_id,
                        session_id,
                        screenshot_path,
                        image_type
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (event_id, session_id, screenshot_path, event_subtype)
                )

        if penalty_points:
            cursor.execute(
                """
                INSERT INTO Penalty
                (
                    event_id,
                    session_id,
                    penalty_points,
                    reason
                )
                VALUES (?, ?, ?, ?)
                """,
                (event_id, session_id, penalty_points, event_subtype)
            )

        cursor.execute(
            """
            INSERT INTO IntegrityHistory
            (
                session_id,
                event_id,
                integrity_before,
                integrity_after,
                delta
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, event_id, integrity_before, integrity_after, -penalty_points)
        )

        cursor.execute(
            """
            UPDATE ExamSession
            SET current_integrity=?, updated_at=CURRENT_TIMESTAMP
            WHERE session_id=?
            """,
            (integrity_after, session_id)
        )

        if owns_connection:
            conn.commit()
        return {
            "event_id": event_id,
            "integrity_before": integrity_before,
            "integrity_after": integrity_after,
            "screenshot_path": screenshot_path,
        }
    except Exception:
        if owns_connection:
            conn.rollback()
        raise
    finally:
        if owns_connection:
            conn.close()


def get_session_violation_rows(session_id):
    if session_id is None:
        return []

    conn = db_connect()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            me.event_id,
            me.event_timestamp,
            me.event_type,
            me.event_subtype,
            me.remarks,
            me.face_count,
            me.browser_state,
            COALESCE(p.penalty_points, 0) AS penalty_points,
            ih.integrity_after,
            s.screenshot_path
        FROM MonitoringEvent me
        LEFT JOIN Penalty p ON p.event_id = me.event_id
        LEFT JOIN IntegrityHistory ih ON ih.event_id = me.event_id
        LEFT JOIN Screenshot s ON s.event_id = me.event_id
        WHERE me.session_id=?
        AND COALESCE(p.penalty_points, 0) > 0
        ORDER BY me.event_timestamp ASC, me.event_id ASC
        """,
        (session_id,)
    )
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_session_summary(session_id):
    summary = {
        "session": None,
        "violations": [],
        "total_penalties": 0,
        "total_screenshots": 0,
        "final_integrity": 100,
        "duration": "",
    }

    session_row = get_exam_session_record(session_id)
    if session_row is not None:
        summary["session"] = session_row
        summary["final_integrity"] = session_row[7] if session_row[7] is not None else 100
        summary["duration"] = format_duration(session_row[3], session_row[4])

    violations = get_session_violation_rows(session_id)
    summary["violations"] = violations
    summary["total_penalties"] = sum(item["penalty_points"] for item in violations)
    summary["total_screenshots"] = sum(1 for item in violations if item.get("screenshot_path"))

    return summary


def get_latest_integrity(cursor, email):
    session_id = get_active_exam_session_id()
    if session_id is not None:
        cursor.execute(
            """
            SELECT current_integrity
            FROM ExamSession
            WHERE session_id=?
            """,
            (session_id,)
        )
        row = cursor.fetchone()
        if row is not None:
            return row[0]

    return 100


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
    session_id = get_active_exam_session_id()
    if session_id is None:
        return False

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM MonitoringEvent me
        INNER JOIN Penalty p ON p.event_id = me.event_id
        WHERE me.session_id=?
        AND p.reason LIKE ?
        AND me.event_id > ?
        """,
        (session_id, f"{reason}%", log_id)
    )
    return cursor.fetchone()[0] > 0


def get_report_metrics(email):
    conn = db_connect()
    cursor = conn.cursor()

    session_id = get_active_exam_session_id()
    if session_id is None:
        return {
            "face_absence_count": 0,
            "browser_focus_loss_count": 0,
            "multiple_face_count": 0,
            "total_suspicious_events": 0,
            "final_integrity": 100,
            "overall_remark": "No session data available.",
            "event_timeline": []
        }

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM MonitoringEvent me
        INNER JOIN Penalty p ON p.event_id = me.event_id
        WHERE me.session_id=? AND p.reason='Candidate Missing'
        """,
        (session_id,)
    )
    face_absence_count = cursor.fetchone()[0]

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM MonitoringEvent me
        INNER JOIN Penalty p ON p.event_id = me.event_id
        WHERE me.session_id=? AND p.reason='Browser Focus Lost'
        """,
        (session_id,)
    )
    browser_focus_loss_count = cursor.fetchone()[0]

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM MonitoringEvent me
        INNER JOIN Penalty p ON p.event_id = me.event_id
        WHERE me.session_id=? AND p.reason='Multiple Faces Detected'
        """,
        (session_id,)
    )
    multiple_face_count = cursor.fetchone()[0]

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM Penalty
        WHERE session_id=?
        """,
        (session_id,)
    )
    total_suspicious_events = cursor.fetchone()[0]

    cursor.execute(
        """
        SELECT current_integrity
        FROM ExamSession
        WHERE session_id=?
        """,
        (session_id,)
    )
    row = cursor.fetchone()
    final_integrity = row[0] if row else 100

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
        "overall_remark": overall_remark
    }


def append_exam_log(email, event, remarks=None, event_type="Exam Event", penalty=0):
    conn = db_connect()
    cursor = conn.cursor()

    session_id = get_active_exam_session_id()
    if session_id is None:
        conn.close()
        return

    if get_exam_session_record(session_id) is None:
        session.pop("exam_session_id", None)
        conn.close()
        return

    try:
        conn.execute("BEGIN")
        cursor.execute(
            "SELECT current_integrity FROM ExamSession WHERE session_id=?",
            (session_id,)
        )
        row = cursor.fetchone()
        integrity = row[0] if row else 100

        cursor.execute(
            """
            INSERT INTO MonitoringEvent
            (
                session_id,
                event_type,
                event_subtype,
                severity,
                remarks,
                source
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (session_id, event_type, event, "Info", remarks, "system")
        )
        event_id = cursor.lastrowid

        if penalty:
            cursor.execute(
                """
                INSERT INTO Penalty
                (
                    event_id,
                    session_id,
                    penalty_points,
                    reason
                )
                VALUES (?, ?, ?, ?)
                """,
                (event_id, session_id, penalty, event)
            )

            new_integrity = max(0, integrity - penalty)
            cursor.execute(
                """
                INSERT INTO IntegrityHistory
                (
                    session_id,
                    event_id,
                    integrity_before,
                    integrity_after,
                    delta
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, event_id, integrity, new_integrity, -penalty)
            )
            cursor.execute(
                """
                UPDATE ExamSession
                SET current_integrity=?, updated_at=CURRENT_TIMESTAMP
                WHERE session_id=?
                """,
                (new_integrity, session_id)
            )

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def apply_penalty(email, reason, penalty, event="Penalty"):
    conn = db_connect()
    cursor = conn.cursor()

    session_id = get_active_exam_session_id()
    if session_id is None:
        conn.close()
        return

    if get_exam_session_record(session_id) is None:
        session.pop("exam_session_id", None)
        conn.close()
        return

    try:
        conn.execute("BEGIN")
        cursor.execute(
            "SELECT current_integrity FROM ExamSession WHERE session_id=?",
            (session_id,)
        )
        row = cursor.fetchone()
        current_integrity = row[0] if row else 100
        new_integrity = max(0, current_integrity - penalty)

        cursor.execute(
            """
            INSERT INTO MonitoringEvent
            (
                session_id,
                event_type,
                event_subtype,
                severity,
                remarks,
                source
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (session_id, "Penalty", reason, "Warning", f"{reason} (-{penalty})", "system")
        )
        event_id = cursor.lastrowid

        cursor.execute(
            """
            INSERT INTO Penalty
            (
                event_id,
                session_id,
                penalty_points,
                reason
            )
            VALUES (?, ?, ?, ?)
            """,
            (event_id, session_id, penalty, reason)
        )
        cursor.execute(
            """
            INSERT INTO IntegrityHistory
            (
                session_id,
                event_id,
                integrity_before,
                integrity_after,
                delta
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, event_id, current_integrity, new_integrity, -penalty)
        )
        cursor.execute(
            """
            UPDATE ExamSession
            SET current_integrity=?, updated_at=CURRENT_TIMESTAMP
            WHERE session_id=?
            """,
            (new_integrity, session_id)
        )

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def create_candidate_log_table(cursor, email):
    return None


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
ensure_production_schema()

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
        "password": password,
        "password_hash": generate_password_hash(password)
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
        conn.execute("BEGIN")

        password_hash = candidate["password_hash"]

        cursor.execute("""
            INSERT INTO Candidate
            (
                first_name,
                middle_name,
                last_name,
                email,
                password,
                password_hash,
                photo_path
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            candidate["first_name"],
            candidate["middle_name"],
            candidate["last_name"],
            candidate["email"],
            password_hash,
            password_hash,
            photo_path
        ))

        conn.commit()

    except sqlite3.IntegrityError:

        conn.rollback()
        conn.close()

        if os.path.exists(photo_path):
            try:
                os.remove(photo_path)
            except OSError:
                pass

        return "Email already registered!"

    except Exception:

        conn.rollback()
        conn.close()

        if os.path.exists(photo_path):
            try:
                os.remove(photo_path)
            except OSError:
                pass

        raise

    conn.close()

    session.pop("pending_candidate", None)

    return redirect(url_for("login_page"))


@app.route("/screenshots/<path:screenshot_path>")
def screenshot_file(screenshot_path):

    if "candidate_id" not in session:
        return redirect(url_for("login_page"))

    return send_from_directory(SCREENSHOT_FOLDER, screenshot_path)

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

# ---------- Check Admin First ----------

    cursor.execute("""
        SELECT
            admin_id,
            email,
            password_hash
        FROM Admin
        WHERE email=?
    """, (email,))

    admin = cursor.fetchone()

    if admin is not None:

        if check_password_hash(admin[2], password):

            session.clear()
            session["admin_id"] = admin[0]
            session["admin_email"] = admin[1]

            conn.close()
            session.pop("login_captcha", None)

            return redirect(url_for("admin_dashboard"))

    # ---------- Candidate Login ----------

    cursor.execute("""
        SELECT
            candidate_id,
            first_name,
            middle_name,
            last_name,
            email,
            password,
            password_hash
        FROM Candidate
        WHERE email=?
    """, (email,))

    user = cursor.fetchone()

    conn.close()

    if user is None:
        return "Invalid Email or Password!"

    candidate_id = user[0]
    first_name = user[1]
    middle_name = user[2]
    last_name = user[3]
    stored_password = user[5]
    stored_password_hash = user[6]

    password_is_valid = False
    if stored_password_hash:
        password_is_valid = check_password_hash(stored_password_hash, password)
    elif stored_password:
        password_is_valid = stored_password == password

    if not password_is_valid:
        return "Invalid Email or Password!"

    if not stored_password_hash or stored_password != stored_password_hash:
        password_hash = generate_password_hash(password)
        cursor.execute(
            """
            UPDATE Candidate
            SET password=?, password_hash=?
            WHERE candidate_id=?
            """,
            (password_hash, password_hash, candidate_id)
        )
        conn.commit()

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


@app.route("/logout", methods=["POST", "GET"])
def logout():

    session.clear()
    return redirect(url_for("home"))


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

    exam_id = get_default_exam_id(cursor)
    if exam_id is None:
        conn.close()
        return "Exam setup is missing.", 500

    conn.execute("BEGIN")

    cursor.execute("""
        INSERT INTO ExamSession
        (
            candidate_id,
            exam_id,
            start_time,
            status,
            initial_integrity,
            current_integrity
        )
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        session["candidate_id"],
        exam_id,
        datetime.now(),
        "Started",
        100,
        100,
    ))

    current_session_id = cursor.lastrowid

    conn.commit()
    conn.close()

    session["exam_session_id"] = current_session_id

    return redirect(url_for("exam"))


# ---------------- PAUSE EXAM ----------------

@app.route("/pause_exam", methods=["POST"])
def pause_exam():

    if "candidate_id" not in session:
        return redirect(url_for("login_page"))

    session_id = get_active_exam_session_id()
    if session_id is None:
        return "No active session found.", 400

    conn = db_connect()
    cursor = conn.cursor()

    conn.execute("BEGIN")

    cursor.execute("""
        UPDATE ExamSession
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

    session_id = get_active_exam_session_id()
    if session_id is None:
        return "No active session found.", 400

    conn = db_connect()
    cursor = conn.cursor()

    conn.execute("BEGIN")

    cursor.execute("""
        UPDATE ExamSession
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

    session_id = get_active_exam_session_id()
    if session_id is None:
        return "No active session found.", 400

    conn = db_connect()
    cursor = conn.cursor()

    conn.execute("BEGIN")

    now = datetime.now()

    cursor.execute("""
        UPDATE ExamSession
        SET
            end_time=?,
            status=?,
            updated_at=CURRENT_TIMESTAMP
        WHERE session_id=?
    """, (now, "Completed", session_id))

    conn.commit()
    conn.close()

    return "Exam Ended Successfully!"


@app.route("/report")
def report():

    if "candidate_id" not in session or "candidate_email" not in session:
        return redirect(url_for("login_page"))

    current_session_id = get_active_exam_session_id()

    conn = db_connect()
    cursor = conn.cursor()

    metrics = get_report_metrics(session["candidate_email"])
    normalized_summary = get_session_summary(current_session_id)

    if normalized_summary["session"] is not None:
        session_row = normalized_summary["session"]
        session_data = (
            session_row[0],
            session_row[3],
            session_row[4],
            session_row[5]
        )
        duration = normalized_summary["duration"]
    else:
        session_data = None
        duration = ""

    conn.close()

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
        violations=normalized_summary["violations"],
        total_penalties=normalized_summary["total_penalties"],
        total_screenshots=normalized_summary["total_screenshots"],
        normalized_integrity=normalized_summary["final_integrity"]
    )
# ---------------- ADMIN DASHBOARD ----------------

@app.route("/admin/dashboard")
def admin_dashboard():

    if "admin_id" not in session:
        return redirect(url_for("login_page"))

    conn = db_connect()
    cursor = conn.cursor()

    # =========================================================
    # ALL REGISTERED CANDIDATES
    # =========================================================

    cursor.execute("""
        SELECT
            c.candidate_id,
            c.first_name,
            c.middle_name,
            c.last_name,
            c.email,

            COUNT(es.session_id) AS total_tests

        FROM Candidate c

        LEFT JOIN ExamSession es
            ON c.candidate_id = es.candidate_id

        GROUP BY c.candidate_id

        ORDER BY c.candidate_id
    """)

    users = cursor.fetchall()


    # =========================================================
    # TOTAL EXAM SESSIONS
    # =========================================================

    cursor.execute("""
        SELECT COUNT(*)
        FROM ExamSession
    """)

    total_tests = cursor.fetchone()[0] or 0


    # =========================================================
    # COMPLETED SESSIONS
    # =========================================================

    cursor.execute("""
        SELECT COUNT(*)
        FROM ExamSession
        WHERE status = 'Completed'
           OR end_time IS NOT NULL
    """)

    completed_tests = cursor.fetchone()[0] or 0


    # =========================================================
    # ACTIVE SESSIONS
    # =========================================================

    cursor.execute("""
        SELECT COUNT(*)
        FROM ExamSession
        WHERE status IN ('Started', 'Resumed')
        AND end_time IS NULL
    """)

    active_tests = cursor.fetchone()[0] or 0

    print("\n========== ACTIVE SESSION CHECK ==========")

    cursor.execute("""
        SELECT
            session_id,
            candidate_id,
            start_time,
            end_time,
            status
        FROM ExamSession
        WHERE status IN ('Started', 'Resumed')
        AND end_time IS NULL
        ORDER BY session_id
    """)

    active_rows = cursor.fetchall()

    print("ACTIVE SESSION COUNT:", len(active_rows))

    for row in active_rows:
        print(
            "Session ID:", row["session_id"],
            "| Candidate ID:", row["candidate_id"],
            "| Start:", row["start_time"],
            "| End:", row["end_time"],
            "| Status:", row["status"]
        )

    print("==========================================\n")


    # =========================================================
    # AVERAGE INTEGRITY
    # =========================================================

    cursor.execute("""
        SELECT AVG(current_integrity)
        FROM ExamSession
    """)

    average_integrity = cursor.fetchone()[0]

    if average_integrity is None:
        average_integrity = 100

    average_integrity = round(average_integrity, 1)


    # =========================================================
    # SUSPICIOUS ACTIVITY
    # =========================================================

    cursor.execute("""
        SELECT COUNT(*)
        FROM Penalty
    """)

    total_violations = cursor.fetchone()[0] or 0


    # =========================================================
    # ALERT TESTS
    # =========================================================
    #
    # Any examination session with integrity below 45
    # is considered an alert and requires admin review.
    # =========================================================

    cursor.execute("""
        SELECT
            es.session_id,
            es.candidate_id,
            c.first_name,
            c.middle_name,
            c.last_name,
            c.email,
            es.current_integrity,
            es.status,
            es.start_time,
            es.end_time

        FROM ExamSession es

        JOIN Candidate c
            ON c.candidate_id = es.candidate_id

        WHERE es.current_integrity < 45

        ORDER BY es.current_integrity ASC
    """)

    alert_rows = cursor.fetchall()


    # Number of tests below the alert threshold

    alert_count = len(alert_rows)


    # ---------------------------------------------------------
    # Alert percentage
    # ---------------------------------------------------------

    if total_tests > 0:

        alert_percentage = round(
            (alert_count / total_tests) * 100,
            1
        )

    else:

        alert_percentage = 0


    # =========================================================
    # PER-CANDIDATE STATISTICS
    # =========================================================
    # For the candidate overview panel when a candidate is selected

    # Build a dict of candidate stats keyed by candidate_id
    candidate_stats = {}

    # Get all candidate IDs from users
    candidate_ids = [u["candidate_id"] for u in users]

    if candidate_ids:
        placeholders = ",".join("?" * len(candidate_ids))

        # Average integrity per candidate
        cursor.execute(f"""
            SELECT
                c.candidate_id,
                AVG(es.current_integrity) as avg_integrity,
                COUNT(es.session_id) as total_tests,
                SUM(CASE WHEN es.status = 'Completed' OR es.end_time IS NOT NULL THEN 1 ELSE 0 END) as completed_tests,
                MAX(es.start_time) as latest_start
            FROM Candidate c
            LEFT JOIN ExamSession es ON c.candidate_id = es.candidate_id
            WHERE c.candidate_id IN ({placeholders})
            GROUP BY c.candidate_id
        """, candidate_ids)

        integrity_rows = cursor.fetchall()
        for row in integrity_rows:
            candidate_stats[row["candidate_id"]] = {
                "avg_integrity": round(row["avg_integrity"], 1) if row["avg_integrity"] is not None else None,
                "total_tests": row["total_tests"] or 0,
                "completed_tests": row["completed_tests"] or 0,
                "latest_start": row["latest_start"]
            }

        # Total violations per candidate (from Penalty -> ExamSession)
        cursor.execute(f"""
            SELECT
                c.candidate_id,
                COUNT(p.penalty_id) as total_violations
            FROM Candidate c
            LEFT JOIN ExamSession es ON c.candidate_id = es.candidate_id
            LEFT JOIN Penalty p ON es.session_id = p.session_id
            WHERE c.candidate_id IN ({placeholders})
            GROUP BY c.candidate_id
        """, candidate_ids)

        violation_rows = cursor.fetchall()
        for row in violation_rows:
            cid = row["candidate_id"]
            if cid in candidate_stats:
                candidate_stats[cid]["total_violations"] = row["total_violations"] or 0
            else:
                candidate_stats[cid] = {"total_violations": row["total_violations"] or 0}

        # Latest exam session per candidate (for "Latest Examination" section)
        cursor.execute(f"""
            SELECT
                c.candidate_id,
                es.session_id,
                es.exam_id,
                e.exam_name,
                es.start_time,
                es.end_time,
                es.current_integrity,
                es.status
            FROM Candidate c
            LEFT JOIN ExamSession es ON c.candidate_id = es.candidate_id
            LEFT JOIN Exam e ON es.exam_id = e.exam_id
            WHERE c.candidate_id IN ({placeholders})
            ORDER BY c.candidate_id, es.start_time DESC
        """, candidate_ids)

        latest_rows = cursor.fetchall()
        seen = set()
        for row in latest_rows:
            cid = row["candidate_id"]
            if cid not in seen:
                seen.add(cid)
                if cid in candidate_stats:
                    candidate_stats[cid]["latest_exam"] = {
                        "session_id": row["session_id"],
                        "exam_id": row["exam_id"],
                        "exam_name": row["exam_name"],
                        "start_time": row["start_time"],
                        "end_time": row["end_time"],
                        "integrity": row["current_integrity"],
                        "status": row["status"]
                    }
                else:
                    candidate_stats[cid] = {
                        "latest_exam": {
                            "session_id": row["session_id"],
                            "exam_id": row["exam_id"],
                            "exam_name": row["exam_name"],
                            "start_time": row["start_time"],
                            "end_time": row["end_time"],
                            "integrity": row["current_integrity"],
                            "status": row["status"]
                        }
                    }

    # =========================================================
    # EVIDENCE COUNT
    # =========================================================

    cursor.execute("""
        SELECT COUNT(*)
        FROM Screenshot
    """)

    evidence_captured = cursor.fetchone()[0] or 0


    # =========================================================
    # RISK DISTRIBUTION
    # =========================================================

    cursor.execute("""
        SELECT current_integrity
        FROM ExamSession
    """)

    integrity_rows = cursor.fetchall()


    risk_counts = {
        "Low": 0,
        "Medium": 0,
        "High": 0
    }


    for row in integrity_rows:

        integrity = row[0]

        if integrity is None:
            continue

        if integrity >= 70:

            risk_counts["Low"] += 1

        elif integrity >= 40:

            risk_counts["Medium"] += 1

        else:

            risk_counts["High"] += 1


    total_risk_sessions = sum(risk_counts.values())


    if total_risk_sessions > 0:

        low_risk_percentage = round(
            (risk_counts["Low"] / total_risk_sessions) * 100,
            1
        )

        medium_risk_percentage = round(
            (risk_counts["Medium"] / total_risk_sessions) * 100,
            1
        )

        high_risk_percentage = round(
            (risk_counts["High"] / total_risk_sessions) * 100,
            1
        )

    else:

        low_risk_percentage = 0
        medium_risk_percentage = 0
        high_risk_percentage = 0


    # =========================================================
    # AVERAGE EXAM DURATION
    # =========================================================

    cursor.execute("""
        SELECT AVG(
            (julianday(end_time) - julianday(start_time)) * 86400
        )
        FROM ExamSession
        WHERE start_time IS NOT NULL
          AND end_time IS NOT NULL
    """)

    average_duration_seconds = cursor.fetchone()[0]


    if average_duration_seconds is None:
        average_duration_seconds = 0


    average_duration_seconds = int(
        average_duration_seconds
    )


    if average_duration_seconds < 60:

        average_duration = (
            f"{average_duration_seconds} sec"
        )

    else:

        average_minutes = (
            average_duration_seconds // 60
        )

        remaining_seconds = (
            average_duration_seconds % 60
        )


        if average_minutes < 60:

            if remaining_seconds > 0:

                average_duration = (
                    f"{average_minutes}m "
                    f"{remaining_seconds}s"
                )

            else:

                average_duration = (
                    f"{average_minutes}m"
                )

        else:

            hours = average_minutes // 60

            minutes = average_minutes % 60


            if minutes > 0:

                average_duration = (
                    f"{hours}h {minutes}m"
                )

            else:

                average_duration = (
                    f"{hours}h"
                )


    conn.close()


    # =========================================================
    # SEND EVERYTHING TO ADMIN PAGE
    # =========================================================

    return render_template(

        "admin_dashboard.html",

        users=users,

        total_tests=total_tests,

        completed_tests=completed_tests,

        active_tests=active_tests,

        average_integrity=average_integrity,

        total_violations=total_violations,

        evidence_captured=evidence_captured,

        risk_counts=risk_counts,

        low_risk_percentage=low_risk_percentage,

        medium_risk_percentage=medium_risk_percentage,

        high_risk_percentage=high_risk_percentage,

        average_duration=average_duration,

        alert_count=alert_count,

        alert_percentage=alert_percentage,

        alert_rows=alert_rows,

        candidate_stats=candidate_stats

    )



# ---------------- CANDIDATE FULL ANALYSIS ----------------

@app.route("/admin/candidate/<int:candidate_id>")
def admin_candidate_analysis(candidate_id):

    if "admin_id" not in session:
        return redirect(url_for("login_page"))

    conn = db_connect()
    cursor = conn.cursor()

    # =========================================================
    # CANDIDATE EXISTS?
    # =========================================================

    cursor.execute("""
        SELECT
            candidate_id,
            first_name,
            middle_name,
            last_name,
            email,
            photo_path
        FROM Candidate
        WHERE candidate_id = ?
    """, (candidate_id,))

    candidate = cursor.fetchone()

    if candidate is None:
        conn.close()
        return "Candidate not found", 404

    # =========================================================
    # CANDIDATE STATS
    # =========================================================

    # Average integrity + total/completed tests
    cursor.execute("""
        SELECT
            AVG(es.current_integrity) as avg_integrity,
            COUNT(es.session_id) as total_tests,
            SUM(CASE WHEN es.status = 'Completed' OR es.end_time IS NOT NULL THEN 1 ELSE 0 END) as completed_tests
        FROM ExamSession es
        WHERE es.candidate_id = ?
    """, (candidate_id,))

    stat_row = cursor.fetchone()
    avg_integrity = stat_row["avg_integrity"]
    total_tests = stat_row["total_tests"] or 0
    completed_tests = stat_row["completed_tests"] or 0

    if avg_integrity is None:
        avg_integrity = None
    else:
        avg_integrity = round(avg_integrity, 1)

    # Total violations
    cursor.execute("""
        SELECT COUNT(p.penalty_id) as total_violations
        FROM ExamSession es
        LEFT JOIN Penalty p ON es.session_id = p.session_id
        WHERE es.candidate_id = ?
    """, (candidate_id,))

    violation_row = cursor.fetchone()
    total_violations = violation_row["total_violations"] or 0

    # Current status (latest session status or "Registered")
    cursor.execute("""
        SELECT status
        FROM ExamSession
        WHERE candidate_id = ?
        ORDER BY start_time DESC
        LIMIT 1
    """, (candidate_id,))

    status_row = cursor.fetchone()
    current_status = status_row["status"] if status_row else "Registered"

    # =========================================================
    # EXAMINATION HISTORY
    # =========================================================
    # Every ExamSession for this candidate, newest first

    cursor.execute("""
        SELECT
            es.session_id,
            es.exam_id,
            e.exam_name,
            es.start_time,
            es.end_time,
            es.current_integrity,
            es.status
        FROM ExamSession es
        LEFT JOIN Exam e ON es.exam_id = e.exam_id
        WHERE es.candidate_id = ?
        ORDER BY es.start_time DESC
    """, (candidate_id,))

    exam_history = cursor.fetchall()

    conn.close()

    # Build stat object for template
    stats = {
        "avg_integrity": avg_integrity,
        "total_tests": total_tests,
        "completed_tests": completed_tests,
        "total_violations": total_violations,
        "current_status": current_status
    }

    return render_template(
        "admin_candidate_analysis.html",
        candidate=candidate,
        stats=stats,
        exam_history=exam_history
    )



# ---------------- NORMAL DASHBOARD ----------------

@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")



# ---------------- Exam ----------------
@app.route("/exam")
def exam():

    if "candidate_id" not in session:
        return redirect(url_for("login_page"))

    email = session["candidate_email"]
    session_id = get_active_exam_session_id()
    append_exam_log(
        email,
        "Exam Started",
        f"Initial Status\nFaces Detected : {face_count}\nMissing Time : 0 sec",
        event_type="Exam Event",
        penalty=0
    )

    if session_id is not None:
        record_monitoring_violation(
            session_id,
            event_type="Exam",
            event_subtype="Exam Started",
            penalty_points=0,
            remarks="Exam started",
            source="system",
            severity="Info"
        )

    global current_candidate_email
    current_candidate_email = email

    return render_template(
        "exam.html",
        exam_session_id=session_id,
        candidate_name=session.get("candidate_name"),
        candidate_email=session.get("candidate_email")
    )

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
        active_session_id = get_active_exam_session_id()

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
                        violation_result = None
                        if active_session_id is not None:
                            violation_result = record_monitoring_violation(
                                active_session_id,
                                event_type="Face Monitoring",
                                event_subtype="Multiple Faces Detected",
                                penalty_points=MULTIPLE_FACE_PENALTY,
                                remarks=f"{face_count} faces detected",
                                frame=frame,
                                face_count_value=face_count,
                                source="cv",
                                severity="Warning"
                            )
                        if violation_result is not None:
                            append_exam_log(
                                email,
                                "Multiple faces penalty recorded",
                                remarks=f"{face_count} faces detected",
                                event_type="Security Log",
                                penalty=0
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
                    violation_result = None
                    if active_session_id is not None:
                        violation_result = record_monitoring_violation(
                            active_session_id,
                            event_type="Face Monitoring",
                            event_subtype="Face Missing",
                            penalty_points=FACE_MISSING_PENALTY,
                            remarks="Face missing detected",
                            frame=frame,
                            face_count_value=0,
                            source="cv",
                            severity="Warning"
                        )
                    if violation_result is not None:
                        append_exam_log(
                            email,
                            "Face missing penalty recorded",
                            remarks="Face missing detected",
                            event_type="Security Log",
                            penalty=0
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

    requested_session_id = request.args.get("session_id", type=int)
    if requested_session_id is not None:
        session["exam_session_id"] = requested_session_id

    return Response(
        stream_with_context(generate_frames()),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )

@app.route("/monitor")
def monitor():

    session_id = request.args.get("session_id", type=int) or get_active_exam_session_id()
    if session_id is None:
        return {"face_count": face_count}

    normalized_summary = get_session_summary(session_id)
    latest_face_count = face_count
    if normalized_summary["violations"]:
        latest_face_count = normalized_summary["violations"][-1].get("face_count") or face_count

    return {
        "face_count": latest_face_count,
        "session_id": session_id
    }


@app.route("/face_status")
def face_status():

    return {
        "face_detected": face_detected
    }

@app.route("/integrity")
def integrity():

    session_id = request.args.get("session_id", type=int) or get_active_exam_session_id()
    if session_id is not None:
        row = get_exam_session_record(session_id)
        if row is not None:
            return {"integrity": row[7], "session_id": session_id}

    return {"integrity": 100}


@app.route("/browser_event", methods=["POST"])
def browser_event():

    data = request.get_json() or {}
    session_id = request.args.get("session_id", type=int) or data.get("session_id") or get_active_exam_session_id()
    if session_id is None:
        return {"status": "error"}

    event = data.get("event")
    if not event:
        return {"status": "error", "message": "Missing event"}, 400

    conn = db_connect()
    cursor = conn.cursor()

    try:
        conn.execute("BEGIN")

        if event == "Browser Focus Lost":
            cursor.execute(
                """
                INSERT INTO BrowserEvent
                (
                    session_id,
                    event_type,
                    started_at,
                    remarks
                )
                VALUES (?, ?, ?, ?)
                """,
                (session_id, event, datetime.now(), event)
            )
        elif event == "Browser Focus Regained":
            cursor.execute(
                """
                SELECT browser_event_id, started_at
                FROM BrowserEvent
                WHERE session_id=? AND event_type='Browser Focus Lost' AND ended_at IS NULL
                ORDER BY browser_event_id DESC
                LIMIT 1
                """,
                (session_id,)
            )
            last_lost = cursor.fetchone()
            if last_lost:
                started_at = parse_timestamp(last_lost[1])
                duration_seconds = 0
                if started_at is not None:
                    duration_seconds = int((datetime.now() - started_at).total_seconds())

                cursor.execute(
                    """
                    UPDATE BrowserEvent
                    SET ended_at=?, duration_seconds=?, remarks=?
                    WHERE browser_event_id=?
                    """,
                    (datetime.now(), duration_seconds, event, last_lost[0])
                )

                if duration_seconds >= BROWSER_FOCUS_THRESHOLD:
                    record_monitoring_violation(
                        session_id,
                        event_type="Browser Monitoring",
                        event_subtype="Browser Focus Lost",
                        penalty_points=BROWSER_FOCUS_PENALTY,
                        remarks="Browser focus lost for too long",
                        source="browser",
                        severity="Warning",
                        conn=conn,
                        cursor=cursor
                    )

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return {"status": "success"}


# ---------------- RUN APP ----------------

if __name__ == "__main__":
    app.run(debug=False)


