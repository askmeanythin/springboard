# Springboard

Springboard is a Flask-based online exam monitoring and integrity analysis system. It supports candidate registration, webcam photo capture, login with CAPTCHA, live exam monitoring through OpenCV face detection, browser focus logging, integrity scoring, and a final report view.

## What It Does

The application is designed to help supervise online exams by tracking suspicious behavior such as:

- missing face detection
- multiple faces in view
- browser tab or window focus loss
- exam session start/end timing
- event logging and integrity scoring

## Tech Stack

- Python
- Flask
- SQLite
- OpenCV
- HTML
- CSS
- JavaScript
- Jinja2 templates

## Project Structure

```text
springboard/
├── app.py
├── database.py
├── faker_data.py
├── requirements.txt
├── haarcascade_frontalface_default.xml
├── database/
│   └── exam.db
├── static/
│   └── css/
│       └── style.css
├── templates/
│   ├── capture_photo.html
│   ├── dashboard.html
│   ├── exam.html
│   ├── exam_entry.html
│   ├── index.html
│   ├── login.html
│   ├── register.html
│   ├── report.html
│   └── welcome.html
├── agile_docs/
└── logs/
```

## Main Workflow

```text
Home
↓
Exam Entry
↓
Register or Login
↓
Photo Capture
↓
Login
↓
Welcome
↓
Start Exam
↓
Live Monitoring
↓
End Exam
↓
Integrity Report
```

## Application Features

### Registration

- Candidate enters first name, middle name, last name, email, and password.
- CAPTCHA is used during registration.
- Candidate photo is captured in the browser before account creation is completed.
- Candidate data is stored in SQLite.

### Login

- Email, password, and CAPTCHA are required.
- Successful login stores candidate data in the Flask session.
- Login activity is logged for the candidate.

### Exam Monitoring

- Live webcam feed is streamed using OpenCV.
- Face detection is performed on each frame.
- Multiple face detection is monitored.
- Browser focus loss is tracked from the frontend using `visibilitychange`.
- Integrity score is reduced when suspicious behavior is detected.

### Reporting

- Final session details are read from SQLite.
- Candidate-specific logs are aggregated.
- A final integrity report is rendered with event history and score summary.

## Database

The app uses SQLite with a main database file at `database/exam.db`.

### Core Tables

- `Candidate` stores registered candidate details and photo path.
- `Session` stores exam session start/end/status.
- `MonitoringEvent` stores normalized event history.

### Dynamic Log Tables

The backend also creates a per-candidate log table using a sanitized version of the candidate's email address. These tables store exam events, browser events, penalties, and integrity history.

## Routes

### Public Pages

- `GET /` - home page
- `GET /exam-entry` - login/register entry page
- `GET /register` - registration form
- `POST /register` - registration submit
- `GET /capture-photo` - webcam photo capture page
- `POST /save-candidate-photo` - save captured photo and candidate record
- `GET /login` - login form
- `POST /login` - login submit
- `GET /welcome` - post-login welcome page
- `GET /dashboard` - simple exam control page
- `GET /report` - final integrity report

### Exam Controls

- `POST /start_exam`
- `POST /pause_exam`
- `POST /resume_exam`
- `POST /end_exam`

### Monitoring APIs

- `GET /exam` - live monitoring page
- `GET /video_feed` - webcam MJPEG stream
- `GET /monitor` - current face count JSON
- `GET /face_status` - current face presence JSON
- `GET /integrity` - current integrity score JSON
- `POST /browser_event` - browser focus event logging

## Running Locally

### 1. Create and activate a virtual environment

```bash
python -m venv venv
venv\Scripts\activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Make sure the database exists

If `database/exam.db` is missing or you want to recreate the schema from scratch, run:

```bash
python database.py
```

Warning: `database.py` drops existing normalized tables before recreating them.

### 4. Start the app

```bash
python app.py
```

Then open the local server in your browser, typically at:

```text
http://127.0.0.1:5000
```

## Important Notes

- Passwords are stored in plaintext in the current implementation.
- Face encoding / recognition is not implemented; the app captures a photo but does not match face embeddings.
- The exam slot selection UI in `capture_photo.html` is currently client-side only and is not persisted to the backend.
- The app uses global state for monitoring, so it is best suited to a single-user or demo environment.
- `faker_data.py` generates a CSV file of sample candidates, but `Faker` is not listed in `requirements.txt`.

## Utility Scripts

### `database.py`

Creates the SQLite schema from scratch.

### `faker_data.py`

Generates a `sample_candidates.csv` file with fake candidate data.

## Development Files

- `tempCodeRunnerFile.py` is a scratch file and not part of the application flow.
- `agile_docs/` contains spreadsheet templates and planning artifacts.

## Limitations

- No logout flow
- No password hashing
- No CSRF protection
- No face recognition
- No copy/paste monitoring
- No fullscreen enforcement
- No audio monitoring
- No persistent exam slot selection
- No admin dashboard for reviewing all candidates

## Recommended Next Steps

1. Add password hashing and proper session security.
2. Normalize the monitoring log schema instead of using per-candidate tables.
3. Move inline frontend scripts and styles into static assets.
4. Add tests for registration, login, monitoring, and reporting.
5. Implement true face recognition if identity verification is required.

## License

See [LICENSE](LICENSE) for license details.
