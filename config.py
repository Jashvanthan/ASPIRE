"""
config.py
---------
Configuration classes for the SmartAttend application.
Supports Development and Production modes via environment variable.
"""

import os
from pathlib import Path

# ─── Base Paths ───────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent

# ── Load Environment Variables ────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=BASE_DIR / ".env")
except ImportError:
    # Fallback parser if python-dotenv is not installed
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        with open(env_file, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    if "=" in line:
                        key, val = line.split("=", 1)
                        os.environ[key.strip()] = val.strip().strip("'\"")
class Config:
    """Base configuration shared across all environments."""

    # ── Flask ─────────────────────────────────────────────────────────────────
    SECRET_KEY: str = os.environ.get("SECRET_KEY", "smartattend-dev-secret-key-2024")
    DEBUG: bool = False
    TESTING: bool = False

    # ── Database ──────────────────────────────────────────────────────────────
    SQLALCHEMY_DATABASE_URI: str = os.environ.get(
        "DATABASE_URL",
        f"sqlite:///{BASE_DIR / 'database' / 'smartattend.db'}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS: bool = False
    SQLALCHEMY_ECHO: bool = False

    # ── Upload Paths ──────────────────────────────────────────────────────────
    UPLOAD_FOLDER: Path = BASE_DIR / "uploads"
    FACE_IMAGES_FOLDER: Path = BASE_DIR / "uploads" / "face_images"
    EMBEDDINGS_FOLDER: Path = BASE_DIR / "uploads" / "embeddings"
    DATASETS_FOLDER: Path = BASE_DIR / "datasets"
    LOGS_FOLDER: Path = BASE_DIR / "logs"

    # ── Webcam & Face Capture ─────────────────────────────────────────────────
    WEBCAM_INDEX: int = 0                # Default camera index
    CAPTURE_COUNT: int = 15              # Number of face images to capture
    CAPTURE_DELAY_MS: int = 250          # Delay between captures (milliseconds)
    FRAME_WIDTH: int = 640
    FRAME_HEIGHT: int = 480
    CAMERA_FPS: int = 10                 # Target frontend framerate

    # ── InsightFace ───────────────────────────────────────────────────────────
    INSIGHTFACE_MODEL: str = "buffalo_s"  # Must match the model used during registration!
    INSIGHTFACE_CTX_ID: int = -1          # -1 = CPU, 0+ = GPU index
    RECOGNITION_THRESHOLD: float = 0.50

    # ── Anti-Spoofing ─────────────────────────────────────────────────────
    ANTISPOOF_ENABLED: bool = True
    ANTISPOOF_MODEL_PATH: str = "models/2.7_80x80_MiniFASNetV2.onnx"
    LIVENESS_THRESHOLD: float = 0.60      # Minimum live confidence score to accept
    SPOOF_THRESHOLD: float = 0.40         # Maximum spoof probability allowed
    SECURITY_SNAPSHOTS_FOLDER: Path = BASE_DIR / "uploads" / "security_snapshots"

    # ── Multi-Person Tracking (ByteTrack) ─────────────────────────────────
    TRACKING_ENABLED: bool = True
    TRACKING_MAX_AGE: int = 30            # Frames to keep a lost track in cache
    RECOGNITION_COOLDOWN_MINUTES: int = 5 # Prevent duplicate attendance for this track
    
    # ── Phase 4: Intelligent Verification & Analytics ─────────────────────
    ATTENDANCE_VERIFICATION_SECONDS: int = 10  # Seconds a person must be visible before attendance is marked
    UNKNOWN_PERSON_COOLDOWN_SECONDS: int = 60  # Cooldown before saving another snapshot of the same unknown person
    UNKNOWN_FACES_FOLDER: Path = BASE_DIR / "uploads" / "unknown_faces"

    # ── Pipeline & Performance ────────────────────────────────────────────
    DETECTION_COOLDOWN_SECONDS: int = 30       # Security logs cooldown
    PROCESS_EVERY_N_FRAMES: int = 15           # Limit heavy ML models for ~2 FPS
    ATTENDANCE_COOLDOWN_MINUTES: int = 40      # Cooldown between face-tracking attendance marks


    # ── Email / SMTP ──────────────────────────────────────────────────────────
    SMTP_SERVER: str = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
    SMTP_PORT: int = int(os.environ.get("SMTP_PORT", 587))
    SMTP_USERNAME: str = os.environ.get("SMTP_USERNAME", "")
    SMTP_PASSWORD: str = os.environ.get("SMTP_PASSWORD", "")
    MAIL_DEFAULT_SENDER: str = os.environ.get("MAIL_DEFAULT_SENDER", "SmartAttend <noreply@smartattend.com>")

    # ── CORS ──────────────────────────────────────────────────────────────────
    CORS_ORIGINS: list = ["*"]

    # ── Logging ───────────────────────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "smartattend.log"

    @classmethod
    def ensure_directories(cls) -> None:
        """Create all required application directories if they don't exist."""
        directories = [
            cls.UPLOAD_FOLDER,
            cls.FACE_IMAGES_FOLDER,
            cls.EMBEDDINGS_FOLDER,
            cls.DATASETS_FOLDER,
            cls.LOGS_FOLDER,
            cls.SECURITY_SNAPSHOTS_FOLDER,
            cls.UNKNOWN_FACES_FOLDER,
            BASE_DIR / "database",
        ]
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)


class DevelopmentConfig(Config):
    """Development environment configuration."""

    DEBUG: bool = True
    SQLALCHEMY_ECHO: bool = False  # Set True to log all SQL queries


class ProductionConfig(Config):
    """Production environment configuration."""

    DEBUG: bool = False
    LOG_LEVEL: str = "WARNING"


class TestingConfig(Config):
    """Testing environment configuration."""

    TESTING: bool = True
    SQLALCHEMY_DATABASE_URI: str = "sqlite:///:memory:"


# ─── Configuration Map ────────────────────────────────────────────────────────
config_map: dict = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig,
}


def get_config(env: str = None) -> Config:
    """
    Return the appropriate configuration class based on the environment.

    Args:
        env: Environment name string. Falls back to FLASK_ENV env var.

    Returns:
        Config subclass instance.
    """
    env = env or os.environ.get("FLASK_ENV", "development")
    return config_map.get(env, DevelopmentConfig)
