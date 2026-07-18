import base64
import logging
import os
import cv2
import numpy as np
from flask import Blueprint, jsonify, render_template, request

from backend.services.detection_service import get_detection_service
from backend.services.embedding_service import EmbeddingService
from backend.services.recognition_service import get_recognition_service
from backend.services.attendance_service import get_attendance_service
from backend.services.antispoof_service import get_antispoof_service
from backend.database.db import db
from backend.models.attendance import Attendance

logger = logging.getLogger(__name__)

attendance_bp = Blueprint("attendance", __name__)

_frame_counter = 0

@attendance_bp.route("/attendance", methods=["GET"])
def attendance_page():
    """Render the Live Attendance UI."""
    from flask import current_app
    fps = current_app.config.get("CAMERA_FPS", 10)
    return render_template("attendance.html", fps=fps)

@attendance_bp.route("/api/attendance/process-frame", methods=["POST"])
def process_frame():
    global _frame_counter
    _frame_counter += 1
    """
    Receive a base64-encoded frame from the browser.
    Run InsightFace detection → recognition → anti-spoof → attendance.
    
    Request JSON:
        frame: str (data:image/jpeg;base64,...)
        
    Returns:
        JSON with list of detections including liveness data.
    """
    data = request.get_json(silent=True) or {}
    frame_b64 = data.get("frame", "")
    
    if not frame_b64:
        return jsonify({"error": "No frame provided"}), 400
        
    # Decode base64 → numpy image
    try:
        if "," in frame_b64:
            frame_b64 = frame_b64.split(",", 1)[1]
        img_bytes = base64.b64decode(frame_b64)
        img_arr = np.frombuffer(img_bytes, dtype=np.uint8)
        frame = cv2.imdecode(img_arr, cv2.IMREAD_COLOR)
        
        if frame is None:
            return jsonify({"error": "Failed to decode frame"}), 400
    except Exception as exc:
        logger.error(f"Frame decode error: {exc}")
        return jsonify({"error": "Invalid base64 encoding"}), 400

    # Get services
    from backend.services.tracking_service import get_tracking_service
    from backend.services.detection_service import get_detection_service
    
    emb_svc = EmbeddingService()
    rec_svc = get_recognition_service()
    att_svc = get_attendance_service()
    spoof_svc = get_antispoof_service()
    track_svc = get_tracking_service()
    det_svc = get_detection_service()
    
    from flask import current_app
    is_spoof_enabled = current_app.config.get("ANTISPOOF_ENABLED", True)
    liveness_thresh = current_app.config.get("LIVENESS_THRESHOLD", 0.60)
    process_every_n = current_app.config.get("PROCESS_EVERY_N_FRAMES", 15)
    cooldown_seconds = current_app.config.get("DETECTION_COOLDOWN_SECONDS", 30)
    
    # Clean up old tracks so we don't hold memory forever
    track_svc.cleanup_stale_tracks(max_age_seconds=5)
    
    # ── 1. YOLOv11 Person Detection & ByteTrack ─────────────────────────
    tracked_people, err = det_svc.detect_people(frame)
    if err:
        logger.warning(f"Detection error: {err}")
        
    detections = []
    
    # ── 1.5 Scan for QR Code ──────────────────────────────────────────────
    qr_detector = cv2.QRCodeDetector()
    qr_data, _, _ = qr_detector.detectAndDecode(frame)
    qr_data = qr_data.strip() if qr_data else None
    
    # ── 1.6 QR-First Activation ───────────────────────────────────────────
    # If a QR code is detected, try to activate the student for face tracking
    qr_activated_student_id = None
    if qr_data:
        from backend.models.student import Student
        qr_student = Student.query.filter_by(student_id=qr_data).first()
        if qr_student:
            was_new = att_svc.activate_via_qr(qr_data)
            qr_activated_student_id = qr_data
            if was_new:
                # Mark first attendance immediately via QR
                student_dict = qr_student.to_dict()
                success, msg, color, att_id = att_svc.mark_attendance(student_dict, 1.0)
                logger.info(f"QR first attendance for {qr_data}: {msg}")
    
    # ── 2. Process Each Tracked Person ──────────────────────────────────
    for person in tracked_people:
        track_id = person.get("track_id")
        px, py, pw, ph = person["bbox"]
        px, py, pw, ph = int(px), int(py), int(pw), int(ph)
        
        # We need a fallback if tracking fails (track_id is None)
        # In that case, we don't cache, we just process normally using a dummy id
        use_cache = track_id is not None
        cached_data = track_svc.get_cached_identity(track_id) if use_cache else None
        
        det = {
            "track_id": track_id,
            "bbox": [px, py, pw, ph],
            "confidence": person["confidence"],
            "class": "person",
            "status_color": "gray",
            "label": "Analyzing...",
            "liveness_score": 0.0,
            "spoof_probability": 1.0,
            "spoof_type": "unknown",
        }
        
        if cached_data:
            # ── CACHE HIT: Skip heavy AI models! ─────────────────────────
            track_svc.update_last_seen(track_id)
            student = cached_data["student"]
            is_genuine = cached_data["is_genuine"]
            
            det["liveness_score"] = cached_data.get("live_conf", 1.0 if is_genuine else 0.0)
            det["spoof_probability"] = cached_data.get("spoof_conf", 0.0 if is_genuine else 1.0)
            det["spoof_type"] = cached_data["spoof_type"]
            
            # Phase 4: 10-Second Intelligent Verification
            import time
            duration = time.time() - cached_data["first_seen"]
            verification_seconds = current_app.config.get("ATTENDANCE_VERIFICATION_SECONDS", 10)
            
            if not is_genuine:
                det["status_color"] = "red"
                det["label"] = f"⚠ Spoof Detected"
            elif student:
                det["similarity"] = round(cached_data["sim"], 2)
                det["student_id"] = student["student_id"]
                
                # Check 2FA
                det["two_factor_verified"] = bool(qr_data and qr_data.lower() == student["student_id"].lower())
                
                # ── QR-First Gate: Check if student is QR-activated today ──
                is_activated = att_svc.is_qr_activated(student["student_id"])
                
                if not is_activated:
                    # Student has NOT scanned QR today → block face-only attendance
                    det["status_color"] = "orange"
                    det["label"] = f"{student['full_name']} — QR Required"
                    det["qr_required"] = True
                elif not cached_data["marked_attendance"]:
                    if duration >= verification_seconds:
                        success, msg, color, att_id = att_svc.mark_attendance(student, cached_data["sim"])
                        
                        # Phase 4: Calculate overall confidence score
                        overall_conf = (cached_data["sim"] + det["liveness_score"]) / 2.0
                        
                        if att_id:
                            # Update overall confidence in DB
                            try:
                                record = Attendance.query.get(att_id)
                                if record:
                                    record.overall_confidence_score = overall_conf
                                    db.session.commit()
                            except Exception:
                                db.session.rollback()

                        track_svc.mark_attendance_completed(track_id, attendance_db_id=att_id)
                        
                        det["status_color"] = color
                        det["label"] = f"{student['full_name']} ({msg})"
                    else:
                        det["status_color"] = "yellow"
                        det["label"] = f"Verifying {student['full_name']}... ({int(verification_seconds - duration)}s)"
                else:
                    det["status_color"] = "green"
                    det["label"] = f"{student['full_name']} (Present)"
            else:
                det["status_color"] = "red"
                det["label"] = f"Unknown Person"
                
                # Phase 4: Unknown Person Logging
                if not cached_data.get("snapshot_saved"):
                    # Trigger snapshot logic below by falling through or handling it here
                    pass
                
            detections.append(det)
            continue
            
        # ── CACHE MISS: Run InsightFace -> AntiSpoof -> ArcFace ──────────
        if _frame_counter % process_every_n != 0:
            det["status_color"] = "gray"
            det["label"] = "Analyzing..."
            detections.append(det)
            continue
            
        # Crop person from frame to speed up InsightFace
        # Add padding to crop for better face detection
        pad = 20
        y1 = max(0, py - pad)
        y2 = min(frame.shape[0], py + ph + pad)
        x1 = max(0, px - pad)
        x2 = min(frame.shape[1], px + pw + pad)
        
        crop_img = frame[y1:y2, x1:x2]
        if crop_img.size == 0:
            continue
            
        faces = emb_svc.get_faces(crop_img)
        
        if len(faces) == 0:
            # Person detected, but no face visible
            det["status_color"] = "gray"
            det["label"] = "No Face Visible"
            detections.append(det)
            continue
            
        # Take the largest face in the crop
        face = faces[0]
        
        # Calculate face bbox absolute coordinates
        fx1, fy1, fx2, fy2 = face.bbox.astype(int).tolist()
        abs_face_bbox = [x1 + fx1, y1 + fy1, (fx2 - fx1), (fy2 - fy1)]
        
        embedding = face.embedding
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm
        embedding = embedding.astype(np.float32)
        
        # Anti-Spoof Default values (if disabled)
        is_genuine = True
        spoof_label = "genuine"
        live_conf = 1.0
        spoof_conf = 0.0
        
        if is_spoof_enabled:
            live_conf, spoof_conf, spoof_label = spoof_svc.get_liveness(frame, abs_face_bbox)
            is_genuine = (spoof_label == "genuine" and live_conf >= liveness_thresh)
            
            det["liveness_score"] = round(live_conf, 2)
            det["spoof_probability"] = round(spoof_conf, 2)
            det["spoof_type"] = spoof_label
            
        student, sim = None, 0.0
        snapshot_saved = False
        
        if is_genuine:
            student, sim = rec_svc.recognize_face(embedding)
            if student:
                det["similarity"] = round(sim, 2)
                det["student_id"] = student["student_id"]
                
                # Check 2FA
                det["two_factor_verified"] = bool(qr_data and qr_data.lower() == student["student_id"].lower())
                
                # ── QR-First Gate ──
                is_activated = att_svc.is_qr_activated(student["student_id"])
                
                if not is_activated:
                    det["status_color"] = "orange"
                    det["label"] = f"{student['full_name']} — QR Required"
                    det["qr_required"] = True
                else:
                    det["status_color"] = "yellow"
                    det["label"] = f"Verifying {student['full_name']}... (10s)"
                
                # Log Genuine Attempt to Security Dashboard
                from backend.services.cooldown_service import get_cooldown_service
                cooldown_svc = get_cooldown_service()
                if not cooldown_svc.is_on_cooldown(f"sec_genuine_{student['student_id']}", cooldown_seconds):
                    try:
                        from backend.services.security_log_service import get_security_log_service
                        sec_log_svc = get_security_log_service()
                        sec_log_svc.log_attempt(
                            student_id=student["student_id"],
                            student_name=student["full_name"],
                            spoof_type="genuine",
                            liveness_score=live_conf if is_spoof_enabled else 1.0,
                            recognition_confidence=sim,
                            spoof_probability=spoof_conf if is_spoof_enabled else 0.0,
                            decision="accepted",
                            snapshot_path=None,
                        )
                    except Exception as e:
                        logger.error(f"Failed to log genuine attempt: {e}")
            else:
                det["status_color"] = "red"
                det["label"] = f"Unknown Person"
                
                # Phase 4: Save Unknown Person Snapshot
                from backend.services.cooldown_service import get_cooldown_service
                cooldown_svc = get_cooldown_service()
                if not cooldown_svc.is_on_cooldown(f"sec_unknown_{track_id}", cooldown_seconds):
                    try:
                        import uuid
                        import time
                        from backend.services.audit_service import get_audit_service
                        from backend.services.security_log_service import get_security_log_service
                        
                        folder = current_app.config.get("UNKNOWN_FACES_FOLDER")
                        os.makedirs(folder, exist_ok=True)
                        filename = f"unknown_{uuid.uuid4().hex[:8]}.jpg"
                        filepath = os.path.join(folder, filename)
                        cv2.imwrite(filepath, crop_img)
                        
                        audit_svc = get_audit_service()
                        audit_svc.log_unknown_person(filepath, float(face.det_score))
                        
                        # Store relative path for frontend rendering
                        relative_path = f"unknown_faces/{filename}"
                        
                        sec_log_svc = get_security_log_service()
                        sec_log_svc.log_attempt(
                            student_id=None,
                            student_name="Unknown Person",
                            spoof_type="unknown_face",
                            liveness_score=live_conf if is_spoof_enabled else 1.0,
                            recognition_confidence=float(face.det_score),
                            spoof_probability=spoof_conf if is_spoof_enabled else 0.0,
                            decision="rejected",
                            snapshot_path=relative_path,
                        )
                        
                        snapshot_saved = True
                    except Exception as e:
                        logger.error(f"Failed to save unknown person snapshot: {e}")
                        snapshot_saved = False
        else:
            det["status_color"] = "red"
            det["label"] = f"⚠ Spoof Detected"
            
            # Log Spoof Attempt to Security Dashboard
            from backend.services.cooldown_service import get_cooldown_service
            cooldown_svc = get_cooldown_service()
            if not cooldown_svc.is_on_cooldown(f"sec_spoof_{track_id}", cooldown_seconds):
                try:
                    import time
                    from backend.services.security_log_service import get_security_log_service
                    
                    folder = current_app.config.get("SECURITY_SNAPSHOTS_FOLDER", "uploads/security_snapshots")
                    os.makedirs(folder, exist_ok=True)
                    filename = f"spoof_{int(time.time() * 1000)}.jpg"
                    filepath = os.path.join(folder, filename)
                    cv2.imwrite(filepath, crop_img)
                    relative_path = f"security_snapshots/{filename}"
                    
                    # Try to recognize face if possible for the log
                    student_match, _ = rec_svc.recognize_face(embedding)
                    
                    sec_log_svc = get_security_log_service()
                    sec_log_svc.log_attempt(
                        student_id=student_match["student_id"] if student_match else None,
                        student_name=student_match["full_name"] if student_match else "Unknown",
                        spoof_type=spoof_label,
                        liveness_score=live_conf,
                        recognition_confidence=float(face.det_score),
                        spoof_probability=spoof_conf,
                        decision="rejected",
                        snapshot_path=relative_path,
                    )
                    snapshot_saved = True
                except Exception as e:
                    logger.error(f"Failed to log spoof attempt: {e}")
                    snapshot_saved = False
            
        # Save to Cache
        if use_cache:
            track_svc.cache_identity(
                track_id=track_id,
                student=student,
                sim=sim,
                is_genuine=is_genuine,
                spoof_type=spoof_label,
                live_conf=live_conf,
                spoof_conf=spoof_conf,
                marked_attendance=False, # Attendance is strictly delayed now
                snapshot_saved=snapshot_saved
            )
            # Mark snapshot saved if applicable
            if not student and is_genuine:
                track_svc._identity_cache[track_id]["snapshot_saved"] = snapshot_saved
            
        detections.append(det)
        
    return jsonify({
        "success": True,
        "detections": detections
    }), 200

@attendance_bp.route("/api/attendance/live", methods=["GET"])
def live_stats():
    """Returns today's attendance stats for the live dashboard."""
    att_svc = get_attendance_service()
    return jsonify(att_svc.get_today_stats()), 200

# ── Phase 4: Attendance Correction Workflow ─────────────────────────────────

@attendance_bp.route("/api/attendance/correction/request", methods=["POST"])
def request_correction():
    """Teacher requests an attendance correction."""
    data = request.get_json(silent=True) or {}
    
    required = ["attendance_id", "requested_by", "reason"]
    if not all(k in data for k in required):
        return jsonify({"success": False, "error": "Missing required fields"}), 400
        
    try:
        from backend.models.analytics import AttendanceCorrectionRequest
        from backend.services.audit_service import get_audit_service
        
        correction = AttendanceCorrectionRequest(
            attendance_id=data["attendance_id"],
            requested_by=data["requested_by"],
            reason=data["reason"],
            status="Pending"
        )
        db.session.add(correction)
        db.session.commit()
        
        # Log to Audit
        audit_svc = get_audit_service()
        audit_svc.log_event("CORRECTION_REQUESTED", f"{data['requested_by']} requested correction for attendance #{data['attendance_id']}")
        
        return jsonify({"success": True, "message": "Correction request submitted successfully"}), 201
    except Exception as e:
        db.session.rollback()
        logger.error(f"Correction request failed: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@attendance_bp.route("/api/attendance/correction/approve", methods=["POST"])
def approve_correction():
    """Admin approves or rejects a correction."""
    data = request.get_json(silent=True) or {}
    req_id = data.get("request_id")
    action = data.get("action") # "approve" or "reject"
    
    if not req_id or action not in ["approve", "reject"]:
        return jsonify({"success": False, "error": "Invalid request parameters"}), 400
        
    try:
        from backend.models.analytics import AttendanceCorrectionRequest
        from backend.services.audit_service import get_audit_service
        
        correction = AttendanceCorrectionRequest.query.get(req_id)
        if not correction:
            return jsonify({"success": False, "error": "Request not found"}), 404
            
        if correction.status != "Pending":
            return jsonify({"success": False, "error": f"Request already {correction.status}"}), 400
            
        correction.status = "Approved" if action == "approve" else "Rejected"
        
        if action == "approve":
            # Actually modify the attendance record
            att_record = Attendance.query.get(correction.attendance_id)
            if att_record:
                # Assuming correction means they were marked present but shouldn't be, or vice versa.
                # In this system, we simply mark them "Excused" or "Manual Present".
                att_record.attendance_status = "Manual Edit" 
        
        db.session.commit()
        
        # Log to Audit
        audit_svc = get_audit_service()
        audit_svc.log_event("CORRECTION_RESOLVED", f"Admin {action}d correction #{req_id} for attendance #{correction.attendance_id}")
        
        return jsonify({"success": True, "message": f"Request {action}d successfully"}), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"Correction approval failed: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@attendance_bp.route("/api/attendance/qr-mark", methods=["POST"])
def qr_mark():
    """
    Endpoint hit by the QR scanner to mark a student's QR scan.
    Marks attendance as Present AND unlocks their Face Tracking session for 40 minutes.
    """
    data = request.get_json(silent=True) or {}
    student_id = data.get("student_id")
    
    if not student_id:
        return jsonify({"success": False, "message": "No student ID provided"}), 400
        
    from backend.models.student import Student
    from datetime import datetime, timezone
    
    student = Student.query.filter_by(student_id=student_id).first()
    if not student:
        return jsonify({"success": False, "message": "Student not found"}), 404
        
    try:
        # 1. Update QR scan time to unlock face tracking for 40 min
        now = datetime.now(timezone.utc)
        student.last_qr_scan_time = now
        db.session.commit()
        
        # 2. Activate QR session in the in-memory service set
        att_svc = get_attendance_service()
        att_svc.activate_qr(student_id)  # marks them as QR-activated today
        
        # 3. Mark attendance using the correct signature: mark_attendance(student_dict, confidence)
        student_dict = student.to_dict()
        success, message, color, att_id = att_svc.mark_attendance(student_dict, 1.0)
        
        return jsonify({
            "success": True,
            "already_marked": not success,
            "time": now.strftime("%H:%M:%S"),
            "message": message if not success else "Attendance marked via QR scan ✓"
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to record QR scan: {e}")
        return jsonify({"success": False, "message": f"Internal error: {e}"}), 500
