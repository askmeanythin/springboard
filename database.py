import sqlite3

conn = sqlite3.connect("database/exam.db")

cursor = conn.cursor()

cursor.execute("PRAGMA foreign_keys = ON")


cursor.execute("DROP TABLE IF EXISTS EventLog")
cursor.execute("DROP TABLE IF EXISTS Session")
cursor.execute("DROP TABLE IF EXISTS Candidate")


cursor.execute("""
CREATE TABLE Candidate
(
    candidate_id INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name TEXT NOT NULL,
    middle_name TEXT,
    last_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password TEXT NOT NULL,
    photo_path TEXT NOT NULL,
    registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")


cursor.execute("""
CREATE TABLE Session
(
    session_id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id INTEGER NOT NULL,
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    status TEXT,

    FOREIGN KEY(candidate_id)
    REFERENCES Candidate(candidate_id)
)
""")


cursor.execute("""
CREATE TABLE EventLog
(
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    remarks TEXT,

    FOREIGN KEY(candidate_id)
    REFERENCES Candidate(candidate_id)
)
""")


conn.commit()

conn.close()

print("Database created successfully.")
print("Candidate table created.")
print("Session table created.")
print("EventLog table created.")