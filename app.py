from flask import Flask, render_template, request
import sqlite3

app = Flask(__name__)

@app.route("/")
def home():
    return render_template("register.html")


@app.route("/register", methods=["POST"])
def register():

    name = request.form["name"]
    email = request.form["email"]
    password = request.form["password"]

    conn = sqlite3.connect("database/exam.db")
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO Candidate(name,email,password)
        VALUES(?,?,?)
    """,(name,email,password))

    conn.commit()
    conn.close()

    return "Candidate Registered Successfully!"


if __name__ == "__main__":
    app.run(debug=True)