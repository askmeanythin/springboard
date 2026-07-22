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

    conn = sqlite3.connect("database/exam.db")
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

    conn = sqlite3.connect("database/exam.db")
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

    conn = sqlite3.connect("database/exam.db")
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

    conn = sqlite3.connect("database/exam.db")
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO Session(candidate_id,start_time,status)
        VALUES(?,?,?)
    """, ("C001", datetime.now(), "Started"))

    conn.commit()
    conn.close()

    return "Exam Started Successfully!"


# ---------------- PAUSE EXAM ----------------

@app.route("/pause_exam", methods=["POST"])
def pause_exam():

    conn = sqlite3.connect("database/exam.db")
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE Session
        SET status=?
        WHERE session_id=(SELECT MAX(session_id) FROM Session)
    """, ("Paused",))

    conn.commit()
    conn.close()

    return "Exam Paused Successfully!"


# ---------------- RESUME EXAM ----------------

@app.route("/resume_exam", methods=["POST"])
def resume_exam():

    conn = sqlite3.connect("database/exam.db")
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE Session
        SET status=?
        WHERE session_id=(SELECT MAX(session_id) FROM Session)
    """, ("Resumed",))

    conn.commit()
    conn.close()

    return "Exam Resumed Successfully!"


# ---------------- END EXAM ----------------

@app.route("/end_exam", methods=["POST"])
def end_exam():

    conn = sqlite3.connect("database/exam.db")
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE Session
        SET
            end_time=?,
            status=?
        WHERE session_id=(SELECT MAX(session_id) FROM Session)
    """, (datetime.now(), "Completed"))

    conn.commit()
    conn.close()

    return "Exam Ended Successfully!"


# ---------------- DASHBOARD ----------------

@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")



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

face_cascade = cv2.CascadeClassifier(
    "haarcascade_frontalface_default.xml"
)

face_detected = True
face_count = 0
face_missing_start = None
missing_seconds = 0

last_face_count = 0
last_missing_state = False

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
        global missing_seconds

        global last_face_count
        global last_missing_state

        face_count = len(faces)

        email = current_candidate_email

        if email:

            if face_count >= 2 and last_face_count < 2:
                append_exam_log(
                    email,
                    f"Multiple Faces Detected ({face_count} Faces)"
                )

            elif face_count == 1 and last_face_count >= 2:
                append_exam_log(
                    email,
                    "Face Count Normal (1 Face)"
                )

        last_face_count = face_count



        if face_count == 0:

            if face_missing_start is None:

                face_missing_start = time.time()

                if email and not last_missing_state:
                    append_exam_log(
                        email,
                        "Candidate Missing"
                    )

                last_missing_state = True

            missing_seconds = int(
                time.time() - face_missing_start
            )

        else:

            if last_missing_state and email:

                append_exam_log(
                    email,
                    f"Candidate Returned (Missing {missing_seconds} sec)"
                )

            face_missing_start = None
            missing_seconds = 0
            last_missing_state = False

        global face_detected

        if len(faces) > 0:
            face_detected = True
        else:
            face_detected = False

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



@app.route("/browser_event", methods=["POST"])
def browser_event():

    if "candidate_email" not in session:
        return {"status": "error"}

    data = request.get_json()

    event = data.get("event")

    append_exam_log(
        session["candidate_email"],
        event
    )

    return {"status": "success"}


# ---------------- RUN APP ----------------

if __name__ == "__main__":
    app.run(debug=False)


