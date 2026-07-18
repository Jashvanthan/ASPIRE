"""
backend/services/advanced_analytics_service.py
----------------------------------------------
Service for handling complex aggregations, insights, and predictions
for the Phase 5 Advanced Analytics Dashboard.
"""

import logging
from typing import Dict, Any, List
from datetime import datetime, timezone, timedelta
from sqlalchemy import func
from backend.database.db import db
from backend.models.attendance import Attendance
from backend.models.student import Student

logger = logging.getLogger(__name__)

class AdvancedAnalyticsService:
    
    def _apply_filters(self, query, model, batch=None, year=None, department=None):
        if batch:
            query = query.filter(model.batch == batch)
        if year:
            query = query.filter(model.year == year)
        if department:
            query = query.filter(model.department == department)
        return query

    def get_filters(self) -> Dict[str, List[Any]]:
        """Returns the unique batches, years, and departments for the dropdowns."""
        batches = [row[0] for row in db.session.query(Student.batch).distinct().all()]
        years = [row[0] for row in db.session.query(Student.year).distinct().all()]
        departments = [row[0] for row in db.session.query(Student.department).distinct().all()]
        return {
            "batches": sorted(batches) if batches else ["2022-26", "2023-27", "2024-28", "2025-29"],
            "years": sorted(years),
            "departments": sorted(departments)
        }

    def get_dashboard_data(self, batch: str = None, year: int = None, department: str = None) -> Dict[str, Any]:
        """Calculates all metrics for the dashboard based on the active filters."""
        # Base queries
        std_q = self._apply_filters(db.session.query(Student), Student, batch, year, department)
        att_q = self._apply_filters(db.session.query(Attendance), Attendance, batch, year, department)
        
        total_students = std_q.count()
        if total_students == 0:
            return {"error": "No students found for this filter."}

        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        # 1. KPIs
        working_days = att_q.with_entities(func.count(func.distinct(Attendance.date))).scalar() or 0
        total_presents = att_q.count()
        
        # Calculate overall attendance %
        total_possible = total_students * working_days
        overall_attendance_pct = round((total_presents / total_possible * 100), 1) if total_possible > 0 else 0.0
        
        # Today's stats
        present_today = att_q.filter(Attendance.date == today_str).count()
        absent_today = total_students - present_today
        late_today = att_q.filter(Attendance.date == today_str, Attendance.time > "09:00:00").count()

        # 2. Class-wise Analysis
        class_std_q = self._apply_filters(
            db.session.query(Student.year, Student.section, func.count(Student.id)),
            Student, batch, year, department
        ).group_by(Student.year, Student.section).all()
        
        class_att_q = self._apply_filters(
            db.session.query(Attendance.year, Attendance.section, func.count(Attendance.id)),
            Attendance, batch, year, department
        ).group_by(Attendance.year, Attendance.section).all()

        class_att_map = {(r[0], r[1]): r[2] for r in class_att_q}
        class_data = []
        for y, sec, c_total in class_std_q:
            c_presents = class_att_map.get((y, sec), 0)
            c_possible = c_total * working_days
            c_pct = round((c_presents / c_possible * 100), 1) if c_possible > 0 else 0
            class_data.append({
                "label": f"Year {y}-{sec}",
                "total": c_total,
                "present_today": att_q.filter(Attendance.year==y, Attendance.section==sec, Attendance.date==today_str).count(),
                "attendance_pct": c_pct
            })

        # 3. Student Risk Analysis
        # Get present count per student
        student_att = self._apply_filters(
            db.session.query(Attendance.student_id, func.count(Attendance.id)),
            Attendance, batch, year, department
        ).group_by(Attendance.student_id).all()
        
        student_att_map = {r[0]: r[1] for r in student_att}
        
        risk_categories = {"low": 0, "medium": 0, "high": 0, "critical": 0}
        risk_students = []
        leaderboard_top = []
        leaderboard_bottom = []
        
        students = std_q.all()
        student_stats = []
        
        for s in students:
            presents = student_att_map.get(s.student_id, 0)
            pct = round((presents / working_days * 100), 1) if working_days > 0 else 100.0
            
            risk = "low"
            if pct < 60: risk = "critical"
            elif pct < 75: risk = "high"
            elif pct < 90: risk = "medium"
            
            risk_categories[risk] += 1
            
            s_data = {
                "name": s.full_name,
                "id": s.student_id,
                "pct": pct,
                "risk": risk
            }
            student_stats.append(s_data)
            
            if risk in ["high", "critical"]:
                risk_students.append(s_data)

        # Sort for leaderboards
        student_stats.sort(key=lambda x: x["pct"], reverse=True)
        leaderboard_top = student_stats[:10]
        leaderboard_bottom = student_stats[-10:] if len(student_stats) > 10 else student_stats[::-1]

        # 4. Trends (Daily/Monthly)
        daily_q = self._apply_filters(
            db.session.query(Attendance.date, func.count(Attendance.id)),
            Attendance, batch, year, department
        ).group_by(Attendance.date).order_by(Attendance.date.desc()).limit(14).all()
        
        daily_trend = []
        for date_str, presents in reversed(daily_q):
            daily_trend.append({"date": date_str, "present": presents, "absent": total_students - presents})

        month_q = self._apply_filters(
            db.session.query(func.substr(Attendance.date, 1, 7).label('month'), func.count(Attendance.id)),
            Attendance, batch, year, department
        ).group_by('month').order_by('month').limit(6).all()
        
        month_trend = [{"month": r[0], "present": r[1]} for r in month_q]

        # 5. Automated Insights & Predictions
        insights = []
        if risk_categories["critical"] > 0:
            insights.append(f"{risk_categories['critical']} students are critically below 60% attendance.")
        if daily_trend and len(daily_trend) >= 2:
            if daily_trend[-1]["present"] > daily_trend[-2]["present"]:
                insights.append("Attendance improved today compared to yesterday.")
            else:
                insights.append("Attendance dropped today.")
        if overall_attendance_pct > 85:
            insights.append(f"Overall health is excellent ({overall_attendance_pct}%).")
            
        predictions = []
        predictions.append(f"Expected attendance tomorrow: {round(overall_attendance_pct)}% based on average.")
        predictions.append(f"{risk_categories['high'] + risk_categories['critical']} students are at risk of detention.")

        return {
            "kpis": {
                "total_students": total_students,
                "overall_attendance_pct": overall_attendance_pct,
                "working_days": working_days,
                "present_today": present_today,
                "absent_today": absent_today,
                "late_today": late_today
            },
            "class_data": class_data,
            "risk": {
                "categories": risk_categories,
                "students": risk_students
            },
            "leaderboard": {
                "top": leaderboard_top,
                "bottom": leaderboard_bottom
            },
            "trends": {
                "daily": daily_trend,
                "monthly": month_trend
            },
            "insights": insights,
            "predictions": predictions
        }

def get_advanced_analytics_service() -> AdvancedAnalyticsService:
    return AdvancedAnalyticsService()
