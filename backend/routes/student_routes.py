"""
backend/routes/student_routes.py
----------------------------------
Flask Blueprint containing all routes for the SmartAttend application.

Route map:
    GET  /                          → Dashboard / Home
    GET  /register                  → Registration page
    POST /api/students              → Create a new student record
    GET  /api/students/<student_id> → Fetch a single student by ID
    GET  /api/students              → List all students (paginated)
    GET  /api/stats                 → Dashboard statistics
    POST /api/capture/start         → Open webcam + start session
    GET  /api/capture/frame         → MJPEG video stream
    POST /api/capture/trigger       → Trigger automatic image capture
    GET  /api/capture/status        → Poll capture progress
    POST /api/capture/stop          → Close webcam
    POST /api/capture/reset         → Reset capture (retake)
    POST /api/embedding/generate    → Generate + save embedding
"""

import logging
from flask import (
    Blueprint,
    Response,
    jsonify,
    render_template,
    request,
    stream_with_context,
    current_app,
)

from backend.services.student_service import StudentService
from backend.services.face_service import FaceService

logger = logging.getLogger(__name__)

# ─── Blueprint ────────────────────────────────────────────────────────────────
student_bp = Blueprint("student", __name__)

# ─── Module-level FaceService instance ───────────────────────────────────────
# Created lazily on first use so the Flask app context is available.
_face_service: FaceService | None = None


def get_face_service() -> FaceService:
    """Return (or lazily create) the module-level FaceService instance."""
    global _face_service
    if _face_service is None:
        cfg = current_app.config
        _face_service = FaceService(
            face_images_dir=cfg["FACE_IMAGES_FOLDER"],
            capture_count=cfg.get("CAPTURE_COUNT", 7),
        )
    return _face_service


# ─────────────────────────────────────────────────────────────────────────────
# Page Routes
# ─────────────────────────────────────────────────────────────────────────────


@student_bp.route("/")
def index():
    """Render the dashboard home page."""
    stats = StudentService.get_stats()
    return render_template("index.html", stats=stats)


@student_bp.route("/register")
def register():
    """Render the student registration page."""
    return render_template(
        "register.html", 
        capture_count=current_app.config.get("CAPTURE_COUNT", 15)
    )


@student_bp.route("/my-qr")
def my_qr_page():
    """Render the student QR code generation page."""
    return render_template("my_qr.html")


# ─────────────────────────────────────────────────────────────────────────────
# Student API Routes
# ─────────────────────────────────────────────────────────────────────────────


@student_bp.route("/api/students", methods=["POST"])
def create_student():
    """
    Create a new student record.

    Request body (JSON or form-data):
        student_id, full_name, department, year, section, email,
        phone_number (optional)

    Returns:
        201 Created  – { student: {...}, message: "..." }
        400 Bad Req  – { errors: [...] }
        409 Conflict – { error: "..." }
        500 Error    – { error: "..." }
    """
    data = request.get_json(silent=True) or request.form.to_dict()

    # Validate
    errors = StudentService.validate_registration_data(data)
    if errors:
        logger.warning("Validation failed: %s", errors)
        return jsonify({"errors": errors}), 400

    # Register
    student, error = StudentService.register_student(data)
    if error:
        status = 409 if "already registered" in error else 500
        return jsonify({"error": error}), status

    # Generate and email QR Code
    try:
        from backend.services.qr_service import QRService
        from backend.services.email_service import EmailService
        qr_bytes = QRService.generate_qr_bytes(student.student_id)
        if student.email:
            app_instance = current_app._get_current_object()
            EmailService.send_qr_email_async(
                app=app_instance,
                email_address=student.email,
                student_name=student.full_name,
                qr_bytes=qr_bytes
            )
    except Exception as e:
        logger.error(f"Failed to process QR email for {student.student_id}: {e}")

    return jsonify({
        "student": student.to_dict(),
        "message": f"Student '{student.full_name}' registered successfully!",
    }), 201


@student_bp.route("/api/students/<string:student_id>", methods=["GET"])
def get_student(student_id: str):
    """
    Retrieve a single student by their student_id string.

    Returns:
        200 OK  – { student: {...} }
        404 Not Found – { error: "..." }
    """
    student = StudentService.get_student_by_id(student_id)
    if not student:
        return jsonify({"error": f"Student '{student_id}' not found."}), 404

    return jsonify({"student": student.to_dict()}), 200


@student_bp.route("/api/students/<string:student_id>/qr", methods=["GET"])
def generate_student_qr(student_id: str):
    """
    Generate a QR code containing the student_id for Two-Factor Attendance.
    """
    import io
    from flask import send_file
    from backend.services.qr_service import QRService
    
    # Verify student exists before generating QR
    student = StudentService.get_student_by_id(student_id)
    if not student:
        return jsonify({"error": f"Student '{student_id}' not found."}), 404
        
    qr_bytes = QRService.generate_qr_bytes(student_id)
    
    img_io = io.BytesIO(qr_bytes)
    return send_file(img_io, mimetype='image/png')


@student_bp.route("/api/students/<string:student_id>", methods=["DELETE"])
def delete_student(student_id: str):
    """
    Delete a single student by their student_id string.

    Returns:
        200 OK  – { message: "..." }
        404 Not Found – { error: "..." }
        500 Error – { error: "..." }
    """
    import shutil
    from pathlib import Path
    
    # 1. First find if they have a session dir with face images and delete it
    cfg = current_app.config
    images_dir = Path(cfg["FACE_IMAGES_FOLDER"])
    # The session dir is not strictly tied to the DB, but we can search for images
    # containing the student_id or just let it be. But to be clean, let's delete
    # any images matching the student ID.
    import glob
    search_pattern = str(images_dir / "**" / f"{student_id}_face_*.jpg")
    for file_path in glob.glob(search_pattern, recursive=True):
        try:
            Path(file_path).unlink()
        except:
            pass

    # 2. Delete from database
    success, error = StudentService.delete_student(student_id)
    if not success:
        return jsonify({"error": error}), 500 if "Failed to" in error else 404

    # 3. Invalidate recognition cache so the live camera stops recognizing them
    try:
        from backend.services.recognition_service import get_recognition_service
        rec_svc = get_recognition_service()
        rec_svc.invalidate_cache()
    except Exception as e:
        logger.error(f"Failed to invalidate recognition cache: {e}")

    return jsonify({"message": f"Student '{student_id}' deleted successfully."}), 200


@student_bp.route("/api/students", methods=["GET"])
def list_students():
    """
    Return a paginated list of all registered students.

    Query params:
        page (int, default 1), per_page (int, default 20)

    Returns:
        200 OK – { students: [...], total: N, page: N, pages: N }
    """
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)

    paginated = StudentService.get_all_students(page=page, per_page=per_page)
    
    from backend.models.attendance import Attendance
    from datetime import datetime, timezone
    today_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    student_ids = [s.student_id for s in paginated.items]
    attendances = Attendance.query.filter(
        Attendance.student_id.in_(student_ids),
        Attendance.date == today_date
    ).all()
    
    att_map = {a.student_id: a.time for a in attendances}
    
    students_data = []
    for s in paginated.items:
        s_dict = s.to_dict()
        if s.student_id in att_map:
            s_dict["today_status"] = "Present"
            s_dict["today_time"] = att_map[s.student_id]
        else:
            s_dict["today_status"] = "Absent"
            s_dict["today_time"] = None
        students_data.append(s_dict)

    return jsonify({
        "students": students_data,
        "total": paginated.total,
        "page": paginated.page,
        "pages": paginated.pages,
    }), 200


@student_bp.route("/api/stats", methods=["GET"])
def get_stats():
    """Return dashboard statistics."""
    return jsonify(StudentService.get_stats()), 200


# ─────────────────────────────────────────────────────────────────────────────
# Webcam / Capture Routes
# ─────────────────────────────────────────────────────────────────────────────


@student_bp.route("/api/capture/start", methods=["POST"])
def capture_start():
    """
    Initialize a new capture session (browser will supply frames via /api/capture/upload-frame).
    No server-side camera needed — browser uses getUserMedia().
    """
    import uuid
    from pathlib import Path

    data = request.get_json(silent=True) or {}
    student_id = data.get("student_id", "").strip()

    if not student_id:
        return jsonify({"error": "student_id is required."}), 400

    cfg = current_app.config
    session_id = str(uuid.uuid4())
    session_dir = Path(cfg["FACE_IMAGES_FOLDER"]) / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    # Store session info in app context (simple in-memory store for Phase 1)
    if not hasattr(current_app, '_capture_sessions'):
        current_app._capture_sessions = {}

    current_app._capture_sessions[session_id] = {
        "student_id": student_id,
        "session_dir": str(session_dir),
        "captured": [],
        "target": cfg.get("CAPTURE_COUNT", 7),
        "complete": False,
        "error": None,
    }

    logger.info("Capture session started: %s for student %s", session_id, student_id)
    return jsonify({
        "session_id": session_id,
        "target": cfg.get("CAPTURE_COUNT", 7),
        "message": "Session ready. Start sending frames.",
    }), 200


@student_bp.route("/api/capture/upload-frame", methods=["POST"])
def upload_frame():
    """
    Receive a base64-encoded JPEG frame from the browser.
    Run Haar cascade face detection.
    Save frame if exactly one face is detected.

    Request JSON:
        session_id: str
        frame: str  (data:image/jpeg;base64,... OR raw base64)
    """
    import base64
    import cv2
    import numpy as np
    from pathlib import Path

    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id", "")
    frame_b64 = data.get("frame", "")

    if not session_id or not frame_b64:
        return jsonify({"error": "session_id and frame are required."}), 400

    sessions = getattr(current_app, '_capture_sessions', {})
    session = sessions.get(session_id)
    if not session:
        return jsonify({"error": "Invalid or expired session."}), 404

    if session["complete"]:
        return jsonify({"status": "complete", "captured": len(session["captured"]),
                        "target": session["target"]}), 200

    # Decode base64 → numpy image
    try:
        if "," in frame_b64:
            frame_b64 = frame_b64.split(",", 1)[1]
        img_bytes = base64.b64decode(frame_b64)
        img_arr = np.frombuffer(img_bytes, dtype=np.uint8)
        frame = cv2.imdecode(img_arr, cv2.IMREAD_COLOR)
        if frame is None:
            return jsonify({"status": "skip", "reason": "decode_failed"}), 200
    except Exception as exc:
        logger.error("Frame decode error: %s", exc)
        return jsonify({"status": "skip", "reason": "decode_error"}), 200

    # Bypass real-time detection in the capture loop for maximum performance.
    # The actual face validation (ensuring exactly 1 face) will be done by the
    # highly accurate InsightFace model during the generate_embedding step.
    face_count = 1

    if face_count != 1:
        return jsonify({
            "status": "skip",
            "reason": "no_face" if face_count == 0 else "multiple_faces",
            "faces": face_count,
            "captured": len(session["captured"]),
            "target": session["target"],
        }), 200

    # Save valid frame
    idx = len(session["captured"]) + 1
    student_id = session["student_id"]
    filename = f"{student_id}_face_{idx:02d}.jpg"
    save_path = Path(session["session_dir"]) / filename
    cv2.imwrite(str(save_path), frame)
    session["captured"].append(str(save_path))

    captured = len(session["captured"])
    target = session["target"]

    if captured >= target:
        session["complete"] = True
        logger.info("Capture complete: %d frames for session %s", captured, session_id)

    return jsonify({
        "status": "saved" if not session["complete"] else "complete",
        "captured": captured,
        "target": target,
        "complete": session["complete"],
        "faces": face_count,
    }), 200


@student_bp.route("/api/capture/status", methods=["GET"])
def capture_status():
    """Poll current capture progress by session_id."""
    session_id = request.args.get("session_id", "")
    sessions = getattr(current_app, '_capture_sessions', {})
    session = sessions.get(session_id)

    if not session:
        return jsonify({"error": "Session not found."}), 404

    return jsonify({
        "session_id": session_id,
        "captured": len(session["captured"]),
        "target": session["target"],
        "complete": session["complete"],
        "error": session["error"],
        "in_progress": not session["complete"],
    }), 200


@student_bp.route("/api/capture/stop", methods=["POST"])
def capture_stop():
    """Release the webcam and end the session."""
    svc = get_face_service()
    svc.stop_camera()
    return jsonify({"message": "Camera stopped."}), 200


@student_bp.route("/api/capture/test", methods=["GET"])
def capture_test():
    """
    Scan camera indices 0-3 with multiple backends.
    Returns the first working camera or a clear error.
    Used for diagnostics from the UI.
    """
    import cv2
    results = []
    backends = [
        (cv2.CAP_DSHOW, "DirectShow"),
        (cv2.CAP_MSMF,  "MSMF"),
        (cv2.CAP_ANY,   "Default"),
    ]
    for idx in range(4):
        for backend, name in backends:
            try:
                cap = cv2.VideoCapture(idx, backend)
                if cap.isOpened():
                    ret, _ = cap.read()
                    cap.release()
                    if ret:
                        results.append({
                            "index": idx, "backend": name, "working": True
                        })
                        return jsonify({
                            "found": True,
                            "camera_index": idx,
                            "backend": name,
                            "message": f"Camera {idx} works with {name} backend.",
                            "all_results": results,
                        }), 200
                    else:
                        results.append({"index": idx, "backend": name, "working": False, "reason": "no_frames"})
                        cap.release()
                else:
                    results.append({"index": idx, "backend": name, "working": False, "reason": "not_opened"})
            except Exception as e:
                results.append({"index": idx, "backend": name, "working": False, "reason": str(e)})

    return jsonify({
        "found": False,
        "message": "No working camera found. Check Windows camera permissions.",
        "all_results": results,
    }), 404


@student_bp.route("/api/capture/reset", methods=["POST"])
def capture_reset():
    """Reset the current capture session (allow retake without restarting camera)."""
    svc = get_face_service()
    svc.reset_session()
    return jsonify({"message": "Capture session reset. Ready to retake."}), 200


# ─────────────────────────────────────────────────────────────────────────────
# Embedding Routes
# ─────────────────────────────────────────────────────────────────────────────


@student_bp.route("/api/embedding/generate", methods=["POST"])
def generate_embedding():
    """
    Generate a face embedding from session-captured images and
    persist it to the student's database record.

    Request body (JSON):
        student_id (str)
        session_id (str)
    """
    from backend.services.embedding_service import EmbeddingService
    from pathlib import Path

    data = request.get_json(silent=True) or {}
    student_id = data.get("student_id", "").strip()
    session_id = data.get("session_id", "").strip()

    if not student_id:
        return jsonify({"error": "student_id is required."}), 400

    # Verify student exists
    student = StudentService.get_student_by_id(student_id)
    if not student:
        return jsonify({"error": f"Student '{student_id}' not found."}), 404

    # Get session image paths
    sessions = getattr(current_app, '_capture_sessions', {})
    session = sessions.get(session_id)

    if not session or not session.get("captured"):
        return jsonify({"error": "No captured images found. Please capture face first."}), 400

    image_paths = [Path(p) for p in session["captured"] if Path(p).exists()]
    if not image_paths:
        return jsonify({"error": "Captured image files not found on disk."}), 500

    # Generate embedding
    cfg = current_app.config
    svc = EmbeddingService(
        model_name=cfg.get("INSIGHTFACE_MODEL", "buffalo_s"),
        ctx_id=cfg.get("INSIGHTFACE_CTX_ID", -1),
    )
    embedding, error = svc.generate_from_images(image_paths)

    if error:
        logger.error("Embedding generation failed: %s", error)
        return jsonify({"error": error}), 500

    # Save embedding to DB
    updated_student, db_error = StudentService.update_embedding(student_id, embedding)
    if db_error:
        return jsonify({"error": db_error}), 500

    # Clean up session
    if session_id in sessions:
        del sessions[session_id]

    # Invalidate recognition cache so the new student is instantly recognized
    try:
        from backend.services.recognition_service import get_recognition_service
        rec_svc = get_recognition_service()
        rec_svc.invalidate_cache()
    except Exception as e:
        logger.error(f"Failed to invalidate recognition cache: {e}")

    return jsonify({
        "message": f"Face registered successfully for {updated_student.full_name}!",
        "student": updated_student.to_dict(),
    }), 200
