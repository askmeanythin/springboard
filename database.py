import sqlite3

conn = sqlite3.connect("database/exam.db")

cursor = conn.cursor()

cursor.execute("PRAGMA foreign_keys = OFF")


cursor.execute("DROP TABLE IF EXISTS Candidate")
cursor.execute("DROP TABLE IF EXISTS Exam")
cursor.execute("DROP TABLE IF EXISTS ExamSession")
cursor.execute("DROP TABLE IF EXISTS MonitoringEvent")
cursor.execute("DROP TABLE IF EXISTS Penalty")
cursor.execute("DROP TABLE IF EXISTS Screenshot")
cursor.execute("DROP TABLE IF EXISTS IntegrityHistory")
cursor.execute("DROP TABLE IF EXISTS BrowserEvent")
cursor.execute("DROP TABLE IF EXISTS Report")

cursor.execute("PRAGMA foreign_keys = ON")


cursor.execute("""
CREATE TABLE Candidate
(
    candidate_id INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name TEXT NOT NULL,
    middle_name TEXT,
    last_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password TEXT NOT NULL,
    password_hash TEXT,
    photo_path TEXT NOT NULL,
    registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")


cursor.execute("""
CREATE TABLE Exam
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
CREATE TABLE ExamSession
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
CREATE TABLE MonitoringEvent
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
CREATE TABLE Penalty
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
CREATE TABLE Screenshot
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
CREATE TABLE IntegrityHistory
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
CREATE TABLE BrowserEvent
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
CREATE TABLE Report
(
    report_id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL UNIQUE,
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    summary_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(session_id) REFERENCES ExamSession(session_id) ON DELETE CASCADE
)
""")


cursor.execute("CREATE INDEX idx_candidate_email ON Candidate(email)")
cursor.execute("CREATE INDEX idx_examsession_candidate_status ON ExamSession(candidate_id, status)")
cursor.execute("CREATE INDEX idx_monitoringevent_session_timestamp ON MonitoringEvent(session_id, event_timestamp)")
cursor.execute("CREATE INDEX idx_penalty_session_applied ON Penalty(session_id, applied_at)")
cursor.execute("CREATE INDEX idx_screenshot_session_captured ON Screenshot(session_id, captured_at)")
cursor.execute("CREATE INDEX idx_integrityhistory_session_recorded ON IntegrityHistory(session_id, recorded_at)")
cursor.execute("CREATE INDEX idx_browserevent_session_started ON BrowserEvent(session_id, started_at)")


cursor.execute(
    """
    INSERT INTO Exam (exam_name, description, status)
    VALUES (?, ?, 'Active')
    """,
    ("Default Exam", "Default exam used by the existing portal flow."),
)


conn.commit()

conn.close()

print("Database created successfully.")
print("Candidate table created.")
print("Exam table created.")
print("ExamSession table created.")
print("Monitoring tables created.")