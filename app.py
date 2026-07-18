"""
app.py
------
SmartAttend Flask Application Factory.

Run with:
    python app.py                  (development)
    FLASK_ENV=production python app.py

PyCharm run configuration:
    Script: app.py
    Working directory: SmartAttend/
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
from pathlib import Path

from flask import Flask
from flask_cors import CORS

# ── Ensure the project root is on the Python path (needed for PyCharm) ────────
ROOT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR))

from config import get_config
from backend.database.db import db
from backend.routes.student_routes import student_bp
from backend.routes.attendance_routes import attendance_bp
from backend.routes.analytics_routes import analytics_bp
from backend.routes.security_routes import security_bp

# Import models so SQLAlchemy discovers them for create_all()
import backend.models  # noqa: F401


# ─────────────────────────────────────────────────────────────────────────────
# Logging Setup
# ─────────────────────────────────────────────────────────────────────────────

def configure_logging(app: Flask) -> None:
    """Configure rotating file logger + stream handler for the application."""
    cfg = app.config
    log_dir: Path = cfg["LOGS_FOLDER"]
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / cfg.get("LOG_FILE", "smartattend.log")

    log_level = getattr(logging, cfg.get("LOG_LEVEL", "INFO"), logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s – %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Rotating file handler (5 MB × 3 backups)
    file_handler = RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(log_level)

    # Stream handler (console)
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    stream_handler.setLevel(log_level)

    # Apply to root logger so all modules benefit
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(stream_handler)

    app.logger.info("Logging configured → %s", log_file)


# ─────────────────────────────────────────────────────────────────────────────
# Application Factory
# ─────────────────────────────────────────────────────────────────────────────

def create_app(env: str = None) -> Flask:
    """
    Create and configure the Flask application.

    Args:
        env: Optional environment name ('development', 'production', 'testing').
             Defaults to the FLASK_ENV environment variable.

    Returns:
        Configured Flask application instance.
    """
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )

    # ── Load configuration ────────────────────────────────────────────────────
    config_class = get_config(env)
    app.config.from_object(config_class)
    config_class.ensure_directories()

    # ── Extensions ────────────────────────────────────────────────────────────
    db.init_app(app)
    CORS(app, origins=app.config.get("CORS_ORIGINS", ["*"]))

    # ── Logging ───────────────────────────────────────────────────────────────
    configure_logging(app)

    # ── Database ──────────────────────────────────────────────────────────────
    with app.app_context():
        db.create_all()
        app.logger.info("Database tables verified / created.")
        
        # Auto-apply Phase 4 migrations if needed
        try:
            from backend.database.migrate_phase4 import run_migration as run_phase4
            run_phase4()
            app.logger.info("Phase 4 schema migrations checked/applied.")
        except Exception as e:
            app.logger.warning(f"Could not auto-apply Phase 4 migrations: {e}")

        # Auto-apply Phase 5 migrations if needed
        try:
            from backend.database.migrate_phase5 import run_migration as run_phase5
            run_phase5()
            app.logger.info("Phase 5 schema migrations checked/applied.")
        except Exception as e:
            app.logger.warning(f"Could not auto-apply Phase 5 migrations: {e}")

        # Auto-apply Phase 6 migrations if needed
        try:
            from backend.database.migrate_phase6 import run_migration as run_phase6
            run_phase6()
            app.logger.info("Phase 6 schema migrations checked/applied.")
        except Exception as e:
            app.logger.warning(f"Could not auto-apply Phase 6 migrations: {e}")

    # ── Blueprints ────────────────────────────────────────────────────────────
    app.register_blueprint(student_bp)
    app.register_blueprint(attendance_bp)
    app.register_blueprint(security_bp)
    app.register_blueprint(analytics_bp)

    from backend.routes.advanced_analytics_routes import advanced_analytics_bp
    app.register_blueprint(advanced_analytics_bp)

    app.logger.info("Blueprints registered.")

    # ── Role Selector Routes ──────────────────────────────────────────────────
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "smartattend_secret_key_123")

    from flask import session, redirect, request

    @app.route("/set_role/<role>")
    def set_role(role):
        if role in ["admin", "staff", "student"]:
            session["role"] = role
        return redirect(request.referrer or "/")

    @app.context_processor
    def inject_role():
        return {"current_role": session.get("role", "admin")}

    app.logger.info(
        "SmartAttend started in '%s' mode on http://127.0.0.1:5000",
        env or os.environ.get("FLASK_ENV", "development"),
    )

    return app


# ─────────────────────────────────────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    flask_app = create_app()
    flask_app.run(
        host="0.0.0.0",
        port=5000,
        debug=flask_app.config.get("DEBUG", True),
        use_reloader=False,   # Disable reloader to prevent camera double-init
        threaded=True,        # Required for concurrent MJPEG streaming
    )
