from flask import Flask, render_template, request
import sqlite3
import cv2
import os
from datetime import datetime

app = Flask(__name__)


# ---------------- HOME PAGE ----------------

@app.route("/")
def home():
    return render_template("index.html")


# ---------------- REGISTER PAGE ----------------

@app.route("/register")
def register_page():
    return render_template("register.html")


# ---------------- REGISTER CANDIDATE ----------------

@app.route("/register", methods=["POST"])
@app.route("/register", methods=["POST"])
def register():

    name = request.form["name"].strip()
    email = request.form["email"].strip()
    password = request.form["password"].strip()

    if name == "":
        return "Name cannot be empty!"

    if email == "":
        return "Email cannot be empty!"

    if "@" not in email or "." not in email:
        return "Invalid Email Format!"

    if password == "":
        return "Password cannot be empty!"

    conn = sqlite3.connect("database/exam.db")
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM Candidate WHERE email=?",
        (email,)
    )

    existing_user = cursor.fetchone()

    if existing_user:
        conn.close()
        return "Email already registered!"

    # ---------------- PHOTO CAPTURE ----------------

    camera = cv2.VideoCapture(0, cv2.CAP_DSHOW)

    if not camera.isOpened():
        conn.close()
        return "Could not open webcam."

    print("Press C to Capture Photo")

    photo_path = ""

    while True:

        ret, frame = camera.read()

        if not ret:
            break

        cv2.imshow("Capture Photo", frame)

        key = cv2.waitKey(1)

        if key == ord('c'):

            if not os.path.exists("photos"):
                os.makedirs("photos")

            photo_path = f"photos/{email}.jpg"

            cv2.imwrite(photo_path, frame)

            break

    camera.release()
    cv2.destroyAllWindows()
    if photo_path == "":
        conn.close()
        return "Photo was not captured."

    # ---------------- SAVE DATA ----------------

    cursor.execute("""
        INSERT INTO Candidate(name,email,password,photo_path)
        VALUES(?,?,?,?)
    """, (name, email, password, photo_path))

    conn.commit()
    conn.close()

    return "Candidate Registered Successfully!"

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
