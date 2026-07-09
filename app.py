from flask import Flask, render_template, request
import sqlite3

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

    cursor.execute("""
        INSERT INTO Candidate(name,email,password)
        VALUES(?,?,?)
    """, (name, email, password))

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

# ---------------- DASHBOARD ----------------

@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")


# ---------------- RUN APP ----------------

if __name__ == "__main__":
    app.run(debug=True)