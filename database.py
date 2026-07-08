import sqlite3

conn = sqlite3.connect("database/exam.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS Candidate(
    candidate_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    photo_path TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS Session(
    session_id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id INTEGER,
    start_time TEXT,
    end_time TEXT,
    status TEXT,
    FOREIGN KEY(candidate_id) REFERENCES Candidate(candidate_id)
)
""")

conn.commit()
conn.close()

print("Database and tables created successfully!")