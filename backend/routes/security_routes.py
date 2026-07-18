"""
backend/routes/security_routes.py
-----------------------------------
REST API endpoints and page routes for the Anti-Spoofing / Security module.
"""

import base64
import logging

import cv2
import numpy as np
from flask import Blueprint, jsonify, render_template, request, current_app

from backend.services.security_log_service import get_security_log_service
from backend.services.anti_spoof_service import get_anti_spoof_service
from backend.services.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)

security_bp = Blueprint("security", __name__)


# ─── Page ─────────────────────────────────────────────────────────────────────


@security_bp.route("/security", methods=["GET"])
def security_dashboard():
    """Render the Security Dashboard page."""
    return render_template("security.html")


# ─── API: Manual liveness check (for debugging / testing) ─────────────────────


@security_bp.route("/api/security/check", methods=["POST"])
def check_liveness():
    """
    Perform a one-shot anti-spoof check on a submitted frame.

    Request JSON:
        frame: str (data:image/jpeg;base64,...)

    Returns:
        JSON with liveness analysis results.
    """
    data = request.get_json(silent=True) or {}
    frame_b64 = data.get("frame", "")

    if not frame_b64:
        return jsonify({"error": "No frame provided"}), 400

    try:
        if "," in frame_b64:
            frame_b64 = frame_b64.split(",", 1)[1]
        img_bytes = base64.b64decode(frame_b64)
        img_arr = np.frombuffer(img_bytes, dtype=np.uint8)
        frame = cv2.imdecode(img_arr, cv2.IMREAD_COLOR)
        if frame is None:
            return jsonify({"error": "Failed to decode frame"}), 400
    except Exception as exc:
        return jsonify({"error": f"Invalid image: {exc}"}), 400

    emb_svc = EmbeddingService()
    faces = emb_svc.get_faces(frame)

    if not faces:
        return jsonify({"error": "No face detected", "faces": 0}), 200

    anti_svc = get_anti_spoof_service()
    results = []

    for face in faces:
        result = anti_svc.verify(
            frame=frame,
            face=face,
            recognition_confidence=0.0,
            student=None,
        )
        results.append(result.to_dict())

    return jsonify({"success": True, "faces": len(faces), "results": results}), 200


# ─── API: Security Logs ──────────────────────────────────────────────────────


@security_bp.route("/api/security/logs", methods=["GET"])
def security_logs():
    """
    Paginated, filterable security logs.

    Query params:
        page (int, default 1)
        per_page (int, default 20)
        type (str, optional) — filter by spoof_type
        decision (str, optional) — "accepted" | "rejected"
        date (str, optional) — YYYY-MM-DD
    """
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    spoof_type = request.args.get("type", None)
    decision = request.args.get("decision", None)
    date = request.args.get("date", None)

    svc = get_security_log_service()
    result = svc.get_logs(
        page=page,
        per_page=per_page,
        spoof_type=spoof_type,
        decision=decision,
        date=date,
    )
    return jsonify(result), 200


# ─── API: Security Stats ─────────────────────────────────────────────────────


@security_bp.route("/api/security/stats", methods=["GET"])
def security_stats():
    """Return today's security statistics."""
    svc = get_security_log_service()
    return jsonify(svc.get_today_stats()), 200


# ─── API: Security Alerts ────────────────────────────────────────────────────


@security_bp.route("/api/security/alerts", methods=["GET"])
def security_alerts():
    """Return recent spoof alerts."""
    limit = request.args.get("limit", 20, type=int)
    svc = get_security_log_service()
    return jsonify({"alerts": svc.get_recent_alerts(limit)}), 200


# ─── API: Security Settings ─────────────────────────────────────────────────


@security_bp.route("/api/security/settings", methods=["GET"])
def get_settings():
    """Return current anti-spoof threshold settings."""
    return jsonify({
        "liveness_threshold": current_app.config.get("LIVENESS_THRESHOLD", 0.60),
        "spoof_threshold": current_app.config.get("SPOOF_THRESHOLD", 0.40),
        "recognition_threshold": current_app.config.get("RECOGNITION_THRESHOLD", 0.50),
    }), 200


@security_bp.route("/api/security/settings", methods=["PUT"])
def update_settings():
    """
    Update anti-spoof thresholds at runtime.

    Request JSON:
        liveness_threshold (float, optional)
        spoof_threshold (float, optional)
        recognition_threshold (float, optional)
    """
    data = request.get_json(silent=True) or {}

    updated = {}
    for key in ("liveness_threshold", "spoof_threshold", "recognition_threshold"):
        if key in data:
            try:
                val = float(data[key])
                val = max(0.0, min(1.0, val))  # Clamp 0-1
                config_key = key.upper()
                current_app.config[config_key] = val
                updated[key] = val
            except (ValueError, TypeError):
                pass

    if not updated:
        return jsonify({"error": "No valid settings provided"}), 400

    logger.info("Security settings updated: %s", updated)
    return jsonify({"success": True, "updated": updated}), 200


@security_bp.route("/api/security/uploads/<path:filename>")
def serve_security_uploads(filename):
    """Serve uploaded snapshots (security_snapshots/ or unknown_faces/)."""
    from flask import send_from_directory
    upload_folder = current_app.config.get("UPLOAD_FOLDER")
    return send_from_directory(upload_folder, filename)
