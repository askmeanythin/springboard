from flask import Flask, render_template, request, session, redirect, url_for
import sqlite3
import cv2
import os
from datetime import datetime
import random
import string
import base64


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

    except sqlite3.IntegrityError:

        conn.rollback()
        conn.close()

        return "Email already registered!"

    conn.close()

    session.pop("pending_candidate", None)

    return redirect(url_for("login_page"))



# ---------------- LOGIN PAGE ----------------

@app.route("/login")
def login_page():
    return render_template("login.html")


# ---------------- LOGIN ----------------

@app.route("/login", methods=["POST"])
def login():

    email = request.form["email"].strip()
    password = request.form["password"].strip()

    if email == "":
        return "Enter Email"

    if password == "":
        return "Enter Password"

    conn = sqlite3.connect("database/exam.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM Candidate
        WHERE email=? AND password=?
    """, (email, password))

    user = cursor.fetchone()

    conn.close()

    if user:
        return render_template("dashboard.html", name=user[1])
    else:
        return "Invalid Email or Password!"


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


# ---------------- RUN APP ----------------

if __name__ == "__main__":
    app.run(debug=False)