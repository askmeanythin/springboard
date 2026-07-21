import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database", "exam.db")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def execute_query(cursor, query, params=None):
    if params is None:
        params = ()
    print("Executing:", query)
    print("Parameters:", params)
    cursor.execute(query, params)

def init_db():
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        execute_query(cursor, "PRAGMA foreign_keys = ON")
        execute_query(cursor, "DROP TABLE IF EXISTS EventLog")
        execute_query(cursor, "DROP TABLE IF EXISTS Session")
        execute_query(cursor, "DROP TABLE IF EXISTS Candidate")

        execute_query(cursor, """
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

        execute_query(cursor, """
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

        execute_query(cursor, """
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
        print("Database created successfully.")
        print("Candidate table created.")
        print("Session table created.")
        print("EventLog table created.")

    except sqlite3.Error as e:
        print(f"Database Creation Error: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    init_db()