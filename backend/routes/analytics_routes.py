"""
backend/routes/analytics_routes.py
----------------------------------
REST API endpoints for the Phase 4 Analytics Dashboard and AI Assistant.
"""

from flask import Blueprint, jsonify, request, render_template
from backend.services.analytics_service import get_analytics_service

analytics_bp = Blueprint("analytics", __name__)

@analytics_bp.route("/analytics", methods=["GET"])
def analytics_page():
    """Render the Analytics Dashboard."""
    return render_template("analytics.html")

@analytics_bp.route("/ai-assistant", methods=["GET"])
def ai_assistant_page():
    """Render the AI Assistant Dashboard."""
    return render_template("ai_assistant.html")

@analytics_bp.route("/api/analytics/dashboard", methods=["GET"])
def get_dashboard():
    """Retrieve daily/weekly trends and general dashboard stats."""
    svc = get_analytics_service()
    stats = svc.get_dashboard_stats()
    return jsonify({"success": True, "data": stats}), 200

@analytics_bp.route("/api/analytics/advanced", methods=["GET"])
def get_advanced_analytics():
    """Retrieve advanced analytics (department, class, trends) with optional filters."""
    year_str = request.args.get("year")
    department = request.args.get("department")
    
    year = int(year_str) if year_str and year_str.isdigit() else None
    if department == "":
        department = None

    svc = get_analytics_service()
    data = svc.get_advanced_analytics(year=year, department=department)
    return jsonify({"success": True, "data": data}), 200

@analytics_bp.route("/api/analytics/assistant", methods=["POST"])
def nlp_assistant():
    """Process natural language queries for the AI Attendance Assistant."""
    data = request.get_json()
    if not data or "query" not in data:
        return jsonify({"success": False, "message": "No query provided"}), 400
        
    svc = get_analytics_service()
    response = svc.process_nlp_query(data["query"])
    
    return jsonify({
        "success": True,
        "response": response
    }), 200
