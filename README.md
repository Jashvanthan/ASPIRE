# SmartAttend – AI Smart Attendance System

> **Phase 1: Project Setup + Student Registration Module**

A production-quality, modular Flask + SQLite + InsightFace attendance system with real-time webcam face capture and 512-d ArcFace embedding registration.

---

## 🚀 Quick Start (PyCharm)

### Prerequisites

| Requirement | Version |
|---|---|
| Python | 3.10+ |
| pip | Latest |
| Webcam | Required for face capture |
| Internet | First run (InsightFace model download) |

---

### 1. Open Project

Open the `SmartAttend/` folder as the **project root** in PyCharm.

---

### 2. Create Virtual Environment

In PyCharm: **File → Settings → Python Interpreter → Add → Virtualenv → New**

Or via terminal:

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate
```

---

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

> ⚠️ **InsightFace** requires `onnxruntime` and C++ Build Tools on Windows.
> If install fails, run: `pip install cmake` first, then retry.

---

### 4. Run the Application

```bash
python app.py
```

Open your browser: **http://127.0.0.1:5000**

> ℹ️ The SQLite database (`database/smartattend.db`) is created automatically on first run.

---

### 5. PyCharm Run Configuration

1. **Run → Edit Configurations**
2. Click **+** → **Python**
3. Set:
   - **Script**: `app.py`
   - **Working directory**: `SmartAttend/` (the folder containing `app.py`)
4. Click **OK → Run**

---

## 📁 Project Structure

```
SmartAttend/
├── app.py                          # Flask application factory + entry point
├── config.py                       # Dev / Prod / Test configuration classes
├── requirements.txt
├── README.md
│
├── backend/
│   ├── __init__.py
│   ├── database/
│   │   ├── __init__.py
│   │   └── db.py                   # Shared SQLAlchemy instance
│   ├── models/
│   │   ├── __init__.py
│   │   └── student.py              # Student ORM model
│   ├── routes/
│   │   ├── __init__.py
│   │   └── student_routes.py       # All Flask routes (Blueprint)
│   └── services/
│       ├── __init__.py
│       ├── student_service.py      # Registration business logic
│       ├── face_service.py         # Webcam + capture service
│       └── embedding_service.py    # InsightFace ArcFace embedding
│
├── templates/
│   ├── base.html                   # Sidebar + topbar layout
│   ├── index.html                  # Dashboard page
│   └── register.html               # Student registration page
│
├── static/
│   ├── css/
│   │   ├── main.css                # Dark glassmorphism theme
│   │   └── register.css            # Registration page styles
│   └── js/
│       ├── main.js                 # Sidebar, toasts, global utils
│       └── register.js             # Registration + webcam workflow
│
├── database/                       # SQLite DB auto-created here
├── uploads/
│   ├── face_images/                # Temporary captured face images
│   └── embeddings/                 # Reserved for future embedding exports
├── datasets/
└── logs/                           # Rotating application logs
```

---

## 🗄️ Database Schema

### `students` table

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PK | Auto-increment primary key |
| `student_id` | VARCHAR(50) UNIQUE | e.g. `CS2024001` |
| `full_name` | VARCHAR(150) | Student's full name |
| `department` | VARCHAR(100) | e.g. `Computer Science` |
| `year` | INTEGER | 1–4 |
| `section` | VARCHAR(10) | e.g. `A`, `B` |
| `email` | VARCHAR(200) | Institutional email |
| `phone_number` | VARCHAR(20) | Optional |
| `face_embedding` | TEXT | JSON-serialized 512-d float32 array |
| `registered_date` | DATETIME | UTC timestamp |
| `updated_date` | DATETIME | UTC timestamp |

---

## 🔌 API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Dashboard home |
| `GET` | `/register` | Registration page |
| `POST` | `/api/students` | Create student record |
| `GET` | `/api/students/<id>` | Get student by ID |
| `GET` | `/api/students` | List all students |
| `GET` | `/api/stats` | Dashboard statistics |
| `POST` | `/api/capture/start` | Open webcam |
| `GET` | `/api/capture/frame` | MJPEG live stream |
| `POST` | `/api/capture/trigger` | Start face capture loop |
| `GET` | `/api/capture/status` | Poll capture progress |
| `POST` | `/api/capture/stop` | Release webcam |
| `POST` | `/api/capture/reset` | Reset capture session |
| `POST` | `/api/embedding/generate` | Generate + save embedding |

---

## ⚙️ Configuration

Edit `config.py` or set environment variables:

| Variable | Default | Description |
|---|---|---|
| `FLASK_ENV` | `development` | App environment |
| `SECRET_KEY` | (dev key) | Flask session secret |
| `DATABASE_URL` | `sqlite:///database/smartattend.db` | Database URI |
| `WEBCAM_INDEX` | `0` | Primary camera index |
| `CAPTURE_COUNT` | `7` | Face images to capture |
| `INSIGHTFACE_MODEL` | `buffalo_l` | InsightFace model pack |

---

## 🎯 Registration Workflow

```
1. Fill form (Student ID, Name, Dept, Year, Section, Email)
2. Click "Register Student" → saves to SQLite
3. Click "Open Camera" → webcam opens, MJPEG stream starts
4. Click "Capture Face" → auto-captures 7 frames with face detection
5. Progress dots fill as images are captured
6. Embedding generated from captured images via InsightFace ArcFace
7. Embedding stored in DB → camera closes → success card shown
8. Click "Register Another" to reset and start over
```

---

## ⚠️ Troubleshooting

| Problem | Solution |
|---|---|
| Webcam not opening | Check Windows camera permissions; try `WEBCAM_INDEX=1` in config |
| InsightFace install error | Install [Microsoft C++ Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) first |
| First run slow | InsightFace downloads `buffalo_l` model (~300 MB) on first use |
| `No face detected` | Ensure good lighting and face centered in frame |
| Multiple faces error | Only one face should be visible during capture |
| Port 5000 in use | Set `port=5001` in `app.py` bottom section |

---

## 🛡️ Security Notes

- All inputs validated server-side using `StudentService.validate_registration_data()`
- SQLAlchemy ORM used throughout → no raw SQL → SQL injection protected
- Duplicate Student ID check before any DB write
- Only face embeddings stored; raw images are temporary session files

---

## 🔮 Phase 2 Roadmap (Not in scope)

- Real-time attendance marking via face recognition
- YOLOv11 person detection
- Attendance dashboard with charts
- PDF/CSV report export
- Liveness detection

---

*Built for the AI Make-A-Thon · SmartAttend Phase 1*
