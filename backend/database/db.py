"""
backend/database/db.py
-----------------------
Shared SQLAlchemy database instance.

This module defines the single `db` object that is imported by all models
and registered with the Flask app in the application factory.
"""

from flask_sqlalchemy import SQLAlchemy

# ─── Shared Database Instance ─────────────────────────────────────────────────
db: SQLAlchemy = SQLAlchemy()
