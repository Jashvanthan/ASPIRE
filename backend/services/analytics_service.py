"""
backend/services/analytics_service.py
-------------------------------------
Service to generate daily/weekly attendance trends, predictive analytics, 
and handle Rule-Based Natural Language Queries for the AI Assistant.
"""

import logging
from typing import Dict, Any, List
from datetime import datetime, timezone, timedelta
from sqlalchemy import func
from backend.database.db import db
from backend.models.attendance import Attendance
from backend.models.student import Student

logger = logging.getLogger(__name__)

class AnalyticsService:
    def get_dashboard_stats(self) -> Dict[str, Any]:
        """Returns aggregated stats for the dashboard."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        # Total Students
        total_students = Student.query.count()
        
        # Today's Attendance
        present_today = Attendance.query.filter_by(date=today, attendance_status="Present").count()
        absent_today = total_students - present_today if total_students > present_today else 0
        
        # Attendance Percentage
        attendance_pct = round((present_today / total_students * 100), 1) if total_students > 0 else 0
        
        # Late Arrivals (Arbitrary definition: arrived after 09:00:00)
        late_arrivals = Attendance.query.filter(
            Attendance.date == today,
            Attendance.time > "09:00:00"
        ).count()
        
        # Average Confidence Score
        avg_conf_row = db.session.query(func.avg(Attendance.overall_confidence_score)).filter_by(date=today).first()
        avg_conf = round(avg_conf_row[0] * 100, 1) if avg_conf_row and avg_conf_row[0] else 0.0

        return {
            "total_students": total_students,
            "present_today": present_today,
            "absent_today": absent_today,
            "attendance_percentage": attendance_pct,
            "late_arrivals": late_arrivals,
            "average_confidence": avg_conf
        }

    def get_advanced_analytics(self, year: int = None, department: str = None) -> Dict[str, Any]:
        """Calculates department, class, and trend attendance analysis with filters."""
        att_filters = []
        std_filters = []
        
        if year is not None:
            att_filters.append(Attendance.year == year)
            std_filters.append(Student.year == year)
        if department:
            att_filters.append(Attendance.department == department)
            std_filters.append(Student.department == department)

        # ── 1. Department-wise Analysis ─────────────────────────────────────
        dept_att_q = db.session.query(Attendance.department, func.count(Attendance.id))
        if att_filters: dept_att_q = dept_att_q.filter(*att_filters)
        dept_att = dept_att_q.group_by(Attendance.department).all()

        dept_std_q = db.session.query(Student.department, func.count(Student.id))
        if std_filters: dept_std_q = dept_std_q.filter(*std_filters)
        dept_std = dept_std_q.group_by(Student.department).all()

        std_map = {row[0]: row[1] for row in dept_std}
        department_data = []
        for dept_name, total_students in std_map.items():
            present_count = next((row[1] for row in dept_att if row[0] == dept_name), 0)
            absent_count = max(0, total_students - present_count)
            department_data.append({"label": dept_name, "present": present_count, "absent": absent_count})

        # ── 2. Class-wise Analysis (Year + Section) ─────────────────────────
        class_att_q = db.session.query(Attendance.year, Attendance.section, func.count(Attendance.id))
        if att_filters: class_att_q = class_att_q.filter(*att_filters)
        class_att = class_att_q.group_by(Attendance.year, Attendance.section).all()

        class_std_q = db.session.query(Student.year, Student.section, func.count(Student.id))
        if std_filters: class_std_q = class_std_q.filter(*std_filters)
        class_std = class_std_q.group_by(Student.year, Student.section).all()

        class_std_map = {(row[0], row[1]): row[2] for row in class_std}
        class_data = []
        for (y, sec), total_students in class_std_map.items():
            present_count = next((row[2] for row in class_att if row[0] == y and row[1] == sec), 0)
            absent_count = max(0, total_students - present_count)
            class_data.append({"label": f"Year {y} - Sec {sec}", "present": present_count, "absent": absent_count})

        # ── 3. Trend Analysis ───────────────────────────────────────────────
        std_q = db.session.query(Student)
        if std_filters: std_q = std_q.filter(*std_filters)
        total_students_in_filter = std_q.count()

        # Day-wise (last 7 days)
        day_att_q = db.session.query(Attendance.date, func.count(Attendance.id))
        if att_filters: day_att_q = day_att_q.filter(*att_filters)
        day_att = day_att_q.group_by(Attendance.date).order_by(Attendance.date.desc()).limit(7).all()
        
        day_data = []
        for date_str, present_count in reversed(day_att):
            absent_count = max(0, total_students_in_filter - present_count)
            day_data.append({"label": date_str, "present": present_count, "absent": absent_count})
        
        # Month-wise
        month_query = db.session.query(
            func.substr(Attendance.date, 1, 7).label('month'), 
            func.count(Attendance.id),
            func.count(func.distinct(Attendance.date))
        )
        if att_filters: month_query = month_query.filter(*att_filters)
        month_stats = month_query.group_by('month').order_by('month').all()

        month_data = []
        for month_str, present_count, distinct_days in month_stats:
            total_possible = total_students_in_filter * distinct_days
            absent_count = max(0, total_possible - present_count)
            month_data.append({"label": month_str, "present": present_count, "absent": absent_count})

        # Calendar Year-wise
        year_query = db.session.query(
            func.substr(Attendance.date, 1, 4).label('year'), 
            func.count(Attendance.id),
            func.count(func.distinct(Attendance.date))
        )
        if att_filters: year_query = year_query.filter(*att_filters)
        year_stats = year_query.group_by('year').order_by('year').all()

        year_data = []
        for yr_str, present_count, distinct_days in year_stats:
            total_possible = total_students_in_filter * distinct_days
            absent_count = max(0, total_possible - present_count)
            year_data.append({"label": yr_str, "present": present_count, "absent": absent_count})

        return {
            "department": department_data,
            "class_data": class_data,
            "trends": {
                "day": day_data,
                "month": month_data,
                "year": year_data
            }
        }

    def process_nlp_query(self, query: str) -> str:
        """
        Mistral AI-powered Natural Language Assistant.
        Fetches context from the database securely and asks Mistral to answer the query.
        """
        import os
        import json
        import urllib.request
        
        api_key = os.environ.get("MISTRAL_API_KEY")
        if not api_key:
            return "System Error: MISTRAL_API_KEY environment variable is not set. Please add it to your .env file and restart the server."
            
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        # 1. Gather Secure Context Data (No Raw SQL!)
        total_students = Student.query.count()
        present_today = Attendance.query.filter_by(date=today).count()
        absent_today = total_students - present_today if total_students > present_today else 0
        
        present_student_ids = [a.student_id for a in Attendance.query.filter_by(date=today).all()]
        absent_students = Student.query.filter(~Student.student_id.in_(present_student_ids)).all() if present_student_ids else Student.query.all()
        absent_names = ", ".join([s.full_name for s in absent_students])
        
        late_arrivals = Attendance.query.filter(Attendance.date == today, Attendance.time > "09:00:00").all()
        late_names = ", ".join([a.student_name for a in late_arrivals])
        
        # --- Dynamic Context Extraction ---
        # 1. Student Details (if mentioned in query)
        student_context = ""
        all_students = Student.query.all()
        for s in all_students:
            # Check if their first name, last name, or full name is in the query
            if any(name_part.lower() in query.lower() for name_part in s.full_name.split()) or s.student_id.lower() in query.lower():
                count = Attendance.query.filter_by(student_id=s.student_id).count()
                student_context += f"- {s.full_name} ({s.student_id}) from {s.department}: Present for {count} days total.\n"
                
        # 2. Department Analysis (if mentioned in query)
        dept_context = ""
        departments = db.session.query(Student.department).distinct().all()
        for d in departments:
            dept_name = d[0]
            if dept_name and dept_name.lower() in query.lower():
                total_dept = Student.query.filter_by(department=dept_name).count()
                present_dept = Attendance.query.filter_by(department=dept_name, date=today).count()
                dept_context += f"- Department {dept_name}: {total_dept} total students, {present_dept} present today, {total_dept - present_dept} absent today.\n"

        # 3. Overall Platform Analysis
        distinct_days = db.session.query(func.count(func.distinct(Attendance.date))).scalar() or 1
        total_attendance_records = Attendance.query.count()
        overall_avg = round((total_attendance_records / (total_students * distinct_days)) * 100, 1) if total_students > 0 else 0
        
        # 2. Build the prompt for Mistral
        system_prompt = f"""You are the SmartAIAttend Analytics Assistant.
Answer the user's question accurately using ONLY the context provided below.
Be concise, helpful, and professional. Do not expose internal database IDs or technical mechanisms.

[TODAY'S CONTEXT: {today}]
- Total Students Enrolled: {total_students}
- Total Present Today: {present_today}
- Total Absent Today: {absent_today}
- Absent Students: {absent_names if absent_names else 'None'}
- Late Arrivals (after 9:00 AM): {late_names if late_names else 'None'}

[OVERALL ANALYSIS CONTEXT]
- Total Active Days Recorded: {distinct_days}
- Overall Platform Attendance Average: {overall_avg}%

[DYNAMIC CONTEXT]
{student_context if student_context else "- No specific student details requested."}
{dept_context if dept_context else "- No specific department details requested."}
"""

        try:
            url = "https://api.mistral.ai/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": "mistral-tiny",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": query}
                ],
                "temperature": 0.3
            }
            
            data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            
            with urllib.request.urlopen(req, timeout=10) as response:
                result = json.loads(response.read().decode('utf-8'))
                return result["choices"][0]["message"]["content"]
                
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8')
            logger.error(f"Mistral API HTTPError {e.code}: {error_body}")
            return f"Sorry, I encountered an HTTP error {e.code} communicating with the AI service."
        except Exception as e:
            logger.error(f"Mistral Request Failed: {e}")
            return "An internal error occurred while processing your request. Please check the server logs."

def get_analytics_service() -> AnalyticsService:
    return AnalyticsService()
