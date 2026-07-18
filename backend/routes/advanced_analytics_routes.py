"""
backend/routes/advanced_analytics_routes.py
-------------------------------------------
REST API endpoints for the Phase 5 Advanced Analytics Dashboard.
"""

from flask import Blueprint, jsonify, request, render_template, Response
import io
import csv

from backend.services.advanced_analytics_service import get_advanced_analytics_service

advanced_analytics_bp = Blueprint("advanced_analytics", __name__)

@advanced_analytics_bp.route("/advanced-analytics", methods=["GET"])
def advanced_analytics_page():
    """Render the Advanced Analytics Dashboard."""
    return render_template("advanced_analytics.html")

@advanced_analytics_bp.route("/api/advanced-analytics/filters", methods=["GET"])
def get_filters():
    """Returns available batches, years, and departments."""
    svc = get_advanced_analytics_service()
    filters = svc.get_filters()
    return jsonify({"success": True, "data": filters}), 200

@advanced_analytics_bp.route("/api/advanced-analytics/dashboard", methods=["GET"])
def get_dashboard():
    """Retrieve all dashboard KPIs, charts, insights, and predictions."""
    batch = request.args.get("batch")
    
    year_str = request.args.get("year")
    year = int(year_str) if year_str and year_str.isdigit() else None
    
    department = request.args.get("department")
    if department == "": department = None
    if batch == "": batch = None

    svc = get_advanced_analytics_service()
    data = svc.get_dashboard_data(batch=batch, year=year, department=department)
    
    if "error" in data:
        return jsonify({"success": False, "message": data["error"]}), 400
        
    return jsonify({"success": True, "data": data}), 200

@advanced_analytics_bp.route("/api/advanced-analytics/export", methods=["GET"])
def export_csv():
    """Export the current dashboard data as CSV."""
    batch = request.args.get("batch")
    
    year_str = request.args.get("year")
    year = int(year_str) if year_str and year_str.isdigit() else None
    
    department = request.args.get("department")
    if department == "": department = None
    if batch == "": batch = None

    svc = get_advanced_analytics_service()
    data = svc.get_dashboard_data(batch=batch, year=year, department=department)
    
    if "error" in data:
        return jsonify({"success": False, "message": data["error"]}), 400

    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write KPIs
    writer.writerow(["--- KPI Summary ---"])
    writer.writerow(["Total Students", data["kpis"]["total_students"]])
    writer.writerow(["Overall Attendance %", data["kpis"]["overall_attendance_pct"]])
    writer.writerow(["Working Days", data["kpis"]["working_days"]])
    writer.writerow(["Present Today", data["kpis"]["present_today"]])
    writer.writerow(["Absent Today", data["kpis"]["absent_today"]])
    writer.writerow([])
    
    # Write Risk Students
    writer.writerow(["--- Students At Risk ---"])
    writer.writerow(["Name", "Student ID", "Attendance %", "Risk Level"])
    for s in data["risk"]["students"]:
        writer.writerow([s["name"], s["id"], s["pct"], s["risk"]])

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=advanced_analytics_export.csv"}
    )
